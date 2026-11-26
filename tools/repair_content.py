#!/usr/bin/env python3
"""repair_content.py — ask the model to fix exactly what the content validator complains about.

The build should not relax a rule just because the first answer was weak, and it should
not die either: the validator names the keys, this tool sends them back ("rewrite only
these, keep everything else"), merges the patch and validates again. After the budget is
spent the problems are printed and the exit code is non-zero — a red build, as agreed for
the test stage.

Usage:
  python3 tools/repair_content.py --plan plans/<d>.json --content content/<d>-content.json
  python3 tools/repair_content.py --plan … --content … --dry-run     # list problems only
"""
from __future__ import annotations
import argparse, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import assemble          # validate_content
import llm_content       # transport, cfg, extract_json

PATH_RE = re.compile(
    r"\b((?:sections|hero|bands|meta|footer|faq|reviews|office|thanks|legal|"
    r"inner_[a-z]+|scarcity|ui|livebar|brand_note)\.[\w.]+)")
FIELDS = ("a", "q", "d", "t", "n", "v")


def _get(pack, path):
    node = pack
    for part in path.split("."):
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                return None
            node = node[int(part)]
        elif isinstance(node, dict):
            if part not in node:
                return None
            node = node[part]
        else:
            return None
    return node


def _set(pack, path, value):
    parts = path.split(".")
    node = pack
    for part in parts[:-1]:
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                return False
            node = node[int(part)]
        elif isinstance(node, dict):
            nxt = node.get(part)
            if nxt is None:
                nxt = {}
                node[part] = nxt
            node = nxt
        else:
            return False
    last = parts[-1]
    if isinstance(node, list):
        if not last.isdigit() or int(last) >= len(node):
            return False
        node[int(last)] = value
    elif isinstance(node, dict):
        node[last] = value
    else:
        return False
    return True


def suspects(errs: list) -> list:
    """Keys mentioned by the validator messages (empty list = send the whole pack)."""
    # aggregate findings ("faq answer too short", "inner_product has 250 words") name no
    # dotted path; repair_targets maps them to the object that actually needs rewriting
    out = list(llm_content.repair_targets(errs))
    for e in errs:
        for m in PATH_RE.findall(e):
            if m not in out:
                out.append(m)
        if "faq answer" in e:
            for i in range(12):
                for f in ("a", "q"):
                    p = f"faq.items.{i}.{f}"
                    if p not in out:
                        out.append(p)
    return out


def ask_patch(cfg, key, use_http, lang, pack, errs, keys):
    ctx = {k: _get(pack, k) for k in keys} if keys else None
    instruction = (
        "You are repairing a landing-page content pack. The validator rejected it. "
        f"Rewrite ONLY what is needed to fix these problems, in the language '{lang}':\n- "
        + "\n- ".join(errs[:20])
        + "\n\nReturn a JSON object of the form {\"dotted.path\": <new value>} with only the "
          "changed values (a string, or the complete array/object when the path points at one). "
          "Keep numbers, tickers, emails, the brand name and placeholders "
          "like {brand} untouched. Answers that are too short must become two full sentences. "
          "Never return null or an empty string."
    )
    if ctx is not None:
        instruction += "\n\nCurrent values of the mentioned keys:\n" + json.dumps(ctx, ensure_ascii=False)
    else:
        instruction += "\n\nFull pack:\n" + json.dumps(pack, ensure_ascii=False)
    messages = [
        {"role": "system", "content": "You repair JSON content packs. Answer with the patch "
                                      "object only — no fences, no commentary."},
        {"role": "user", "content": instruction},
    ]
    if use_http:
        raw, finish = llm_content.http_chat(cfg, key, messages)
        if finish == "length":
            raise RuntimeError("patch truncated — raise max_tokens")
    else:
        tmp = ROOT / "content" / "_repair_io.json"
        tmp.write_text(json.dumps({"instruction": instruction}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        llm_content.cli_chat(llm_content.find_cli(), cfg["model"],
                             "Read content/_repair_io.json. Return the patch JSON object it asks for "
                             "as content/_repair_out.json — nothing else.")
        raw = (ROOT / "content" / "_repair_out.json").read_text(encoding="utf-8")
    out = llm_content.extract_json(raw) if use_http else json.loads(raw)
    if not isinstance(out, dict):
        raise RuntimeError("model did not return a patch object")
    return out


def main():
    ap = argparse.ArgumentParser(description="repair the content pack in place")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--content", required=True)
    ap.add_argument("--provider", default="auto", choices=["", "auto", "http", "cli"])
    ap.add_argument("--model", default="")
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    plan_f = pathlib.Path(a.plan)
    content_f = pathlib.Path(a.content)
    plan = json.loads(plan_f.read_text(encoding="utf-8"))
    pack = json.loads(content_f.read_text(encoding="utf-8"))
    lang = plan["params"].get("lang", "en")

    errs = assemble.validate_content(pack, plan, strict=True)
    if not errs:
        print("· content already valid — nothing to repair")
        return
    print(f"· {len(errs)} content problem(s):")
    for e in errs[:10]:
        print("   -", e)
    if a.dry_run:
        return

    cfg = llm_content.load_cfg()
    if a.model:
        cfg["model"] = a.model
    key = llm_content.resolve_key(cfg)
    use_http = a.provider == "http" or (a.provider in ("", "auto") and bool(key))
    if not use_http and a.provider == "http":
        llm_content.die("no API key: put VENICE_API_KEY=… in .llm_env")
    print(f"· transport: {'http ' + cfg['base_url'] if use_http else 'opencode CLI'} · model: {cfg['model']}")

    for attempt in range(a.passes):
        keys = suspects(errs)
        try:
            patch = ask_patch(cfg, key, use_http, lang, pack, errs, keys)
        except Exception as e:
            print(f"  · repair attempt {attempt + 1} unparsable: {e}")
            continue
        applied = 0
        for path, value in patch.items():
            if not isinstance(path, str) or value is None:
                continue
            old = _get(pack, path)
            if old is None and path.split(".")[0] not in pack:
                continue
            # a different shape means the model misunderstood; keep the old value
            if old is not None and type(old) is not type(value):
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if _set(pack, path, value):
                applied += 1
        content_f.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
        errs = assemble.validate_content(pack, plan, strict=True)
        print(f"  · pass {attempt + 1}: applied {applied} value(s), {len(errs)} problem(s) left")
        if not errs:
            print("CONTENT REPAIRED")
            return
    llm_content.die("content still invalid after repair passes: " + "; ".join(errs[:6]))


if __name__ == "__main__":
    main()
