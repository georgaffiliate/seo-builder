#!/usr/bin/env python3
"""localize.py — master English copy → any target language, via the LLM.

The factory owns the structure and the English source: content_gen writes a full pack
from the en bank, this tool asks the model to rewrite every human-visible string into
the plan language, then validates that nothing was dropped, invented or half-translated.

The model never writes HTML and never decides what content exists — it only translates
values we hand it, key by key. Anything that does not check out goes back as a repair
instruction; a pack that still fails is rejected instead of shipped.

Usage:
  python3 tools/localize.py --plan plans/<domain>.json --content content/<domain>-content.json
  python3 tools/localize.py --plan … --content … --payload-only     # print the payload
  python3 tools/localize.py --plan … --content … --dry-run          # collect + validate only
"""
from __future__ import annotations
import argparse, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import llm_content  # transport (http/cli), cfg, json extraction

# ------------------------------------------------------------------ master copy
# values that must survive translation untouched
WHITELIST_PATHS = {
    "meta.email", "meta.telephone", "hero.device_bal_v", "hero.device_pct",
    "ui.cur_code", "ui.cur_sym", "ui.min_init",
}
WHITELIST_WORDS = {"api", "sepa", "visa", "mastercard", "eur", "ms", "swift"}
TICKER_RE = re.compile(r"[A-Z0-9/.\-]{3,12}")


def _is_ticker(text: str) -> bool:
    """MIX-GL / BND-EU / BTC/EUR / 24/7 — codes and ratios, never prose."""
    return bool(TICKER_RE.fullmatch(text)) and bool(re.search(r"[\d/\-]", text))
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PH_RE = re.compile(r"\{(\w+)\}")
TAG_RE = re.compile(r"</?([a-zA-Z][\w-]*)[^>]*>")
DIGITS_RE = re.compile(r"\d+")
PLAN_TEXT_ROOTS = ("layout.menu", "livebar.subs", "layout.slugs", "pulse_sim")


def _leaves(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _leaves(v, f"{path}.{i}")
    else:
        yield path, node


def _set_path(tree, path, value):
    parts = path.split(".")
    node = tree
    for p in parts[:-1]:
        node = node[int(p)] if isinstance(node, list) else node[p]
    last = parts[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value


def _get_path(tree, path):
    node = tree
    for p in path.split("."):
        node = node[int(p)] if isinstance(node, list) else node[p]
    return node


EMAIL_RE = re.compile(r"^[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}$")


def needs_translation(path: str, value) -> bool:
    """Everything the visitor reads, minus numbers, tickers, emails and fixed codes."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or not re.search(r"[^\W\d_]", text, re.UNICODE):
        return False
    if path in WHITELIST_PATHS or path.endswith((".vv", ".photo", ".ic", ".g", ".sym")):
        return False
    if path.endswith("meta.keywords"):
        return False          # search queries: brand + "login" stay as people type them
    # a bare address or URL is not copy — but a paragraph that merely mentions
    # info@{domain} is (legal.privacy / thanks.warn used to stay English because of this)
    if EMAIL_RE.match(text) or text.startswith(("http://", "https://")):
        return False
    if _is_ticker(text) or text.lower() in WHITELIST_WORDS:
        return False
    if re.fullmatch(r"[\W\d_]+", text):          # symbols, arrows, percentages
        return False
    return True


def mark_eyebrow(value, brand: str) -> bool:
    """True when an eyebrow is the brand mark itself ("BITNOVA · PT", "ALIAS · SI"),
    which must never be translated. A plain "PLATFORM"/"RISKS" is copy and is."""
    raw = str(value or "").strip()
    key = re.sub(r"\s+", "", str(brand or "")).casefold()
    if key and key in re.sub(r"\s+", "", raw).casefold():
        return True
    return "·" in raw and not re.search(r"[a-z\u00e0-\u024f]", raw)


def collect(pack: dict, plan: dict) -> dict:
    """Flatten every translatable string: {'content.…': text, 'plan.…': text}."""
    out = {}
    brand = plan["params"]["brand"]
    for path, value in _leaves(pack):
        if path.endswith(".eyebrow") and mark_eyebrow(value, brand):
            continue          # brand mark + geo code, nothing to translate
        if needs_translation(path, value):
            out[f"content.{path}"] = value
    domain = plan["params"]["domain"]
    for path, value in _leaves(plan):
        if not path.startswith(PLAN_TEXT_ROOTS) or not needs_translation(path, value):
            continue
        if path.endswith("GEO_SHORT") or path.endswith(".LB1D") or value.strip() in (brand, domain):
            continue
        out[f"plan.{path}"] = value
    return out


# ------------------------------------------------------------------ validation
LABEL_WORD = re.compile(r"^(?:[A-Z][a-z\u00c0-\u024f]{0,7}|[A-Z0-9][A-Z0-9·/&.\-]*)$")


def _label_like(text: str) -> bool:
    """'Menu', 'Base', 'INDEX EU', 'Pro' — short label tokens that legitimately read
    the same in many languages (a full sentence never matches)."""
    words = [w.strip(",. ;:!?«»\"'()") for w in text.split()]
    words = [w for w in words if w]
    return 0 < len(words) <= 3 and all(LABEL_WORD.match(w) for w in words)


NON_LATIN_LANGS = {"ja", "zh", "ko", "ru", "uk", "bg", "mk", "el", "he", "ar", "fa",
                   "hi", "bn", "ta", "te", "th", "ka", "hy", "ur", "sr"}


def validate(src: dict, dst: dict, lang: str, brand: str = "", domain: str = "") -> list[str]:
    """Structural + copy checks: same keys, placeholders, digits, tags, real translation."""
    errs = []
    brand_key = re.sub(r"\s+", "", brand).casefold()
    missing = sorted(set(src) - set(dst))
    extra = sorted(set(dst) - set(src))
    if missing:
        errs.append(f"missing {len(missing)} strings: {', '.join(missing[:5])}")
    if extra:
        errs.append(f"invented {len(extra)} strings: {', '.join(extra[:5])}")
    for path, text in src.items():
        if path not in dst:
            continue
        new = dst[path]
        if not isinstance(new, str) or not new.strip():
            errs.append(f"{path}: empty translation")
            continue
        if sorted(PH_RE.findall(text)) != sorted(PH_RE.findall(new)):
            errs.append(f"{path}: placeholders changed "
                        f"({PH_RE.findall(text)} → {PH_RE.findall(new)})")
        if sorted(TAG_RE.findall(text)) != sorted(TAG_RE.findall(new)):
            errs.append(f"{path}: html tags changed ({TAG_RE.findall(text)} → {TAG_RE.findall(new)})")
        # languages reorder numbers ("2,4% in the last 30 days" → "son 30 günde %2,4"),
        # so compare the multiset — a dropped or altered figure is still an error
        if sorted(DIGITS_RE.findall(text)) != sorted(DIGITS_RE.findall(new)):
            errs.append(f"{path}: numbers changed ({' '.join(DIGITS_RE.findall(text))} → "
                        f"{' '.join(DIGITS_RE.findall(new))})")
        if brand_key and brand_key in re.sub(r"\s+", "", text).casefold() \
                and brand_key not in re.sub(r"\s+", "", new).casefold():
            errs.append(f"{path}: brand name lost")
        if domain and domain in text and domain not in new:
            errs.append(f"{path}: domain changed")
        if path.startswith("plan.layout.slugs."):
            if not SLUG_RE.match(new) or not 2 < len(new) <= 34:
                errs.append(f"{path}: '{new}' is not a kebab-case ascii slug")
            continue
        if path.startswith("plan.layout.menu.") and lang in NON_LATIN_LANGS \
                and re.search(r"[A-Za-z]{2,}", new):
            errs.append(f"{path}: menu label still in Latin script for '{lang}' ('{new[:24]}')")
            continue
        if new.strip() == text.strip() and lang != "en" and re.search(r"[^\W\d_]{3,}", text, re.UNICODE):
            if _label_like(text):
                continue          # Menu / Base / Pro / INDEX EU: same word by nature
            errs.append(f"{path}: not translated ('{text[:40]}')")
    return errs


def leftover_english(dst: dict) -> list[str]:
    """Soft signal: an English function word survived in a translated string."""
    bad = []
    for path, text in dst.items():
        if isinstance(text, str) and re.search(r"\b(the|and|with|your|this|that)\b", text, re.I):
            bad.append(f"{path}: …{text[:50]}…")
    return bad


# ------------------------------------------------------------------ transport
def ask(cfg, key, use_http, lang, payload: dict, errors=None, brand: str = "") -> dict:
    instruction = (
        "You are a native landing-page copywriter. Rewrite the VALUES of this JSON object in "
        f"the language '{lang}' — do not translate literally: change sentence openings and word "
        "order where it helps, keep every fact, keep the tone sober and concrete. The result is "
        "published next to other offers of the same type, so it must read as freshly written copy, "
        "never as a template translation. "
        + (f"The brand is '{brand}' — never translate, transliterate or shorten it. " if brand else "") +
        "Rules: keep placeholders like {brand} or {city} exactly; "
        "keep html tags (<small>, <p>) exactly; keep numbers, prices, times, percentages, tickers, "
        "emails, urls and the brand name unchanged, but write them with the locale's separators "
        "(comma decimals for pt/es/it/fr/de/pt-BR: '+2,4%', '87 450'); paths starting with "
        "'plan.layout.slugs.' must be kebab-case ascii slugs without diacritics. "
        "Return ONLY the JSON object with the same keys."
    )
    if errors:
        instruction += ("\nFix these problems from the previous attempt, keep everything else: "
                        + "; ".join(errors[:15]))
    messages = [
        {"role": "system", "content": "You translate landing-page copy precisely. Answer with the "
                                      "finished JSON object only — no fences, no commentary."},
        {"role": "user", "content": instruction + "\n\nJSON:\n" + json.dumps(payload, ensure_ascii=False)},
    ]
    if use_http:
        raw, finish = llm_content.http_chat(cfg, key, messages)
        if finish == "length":
            raise RuntimeError("translation truncated — raise max_tokens")
    else:
        tmp = ROOT / "content" / "_translate_io.json"
        tmp.write_text(json.dumps({"instruction": instruction, "payload": payload},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        llm_content.cli_chat(llm_content.find_cli(), cfg["model"],
                             f"Read content/_translate_io.json. Translate every value of payload into "
                             f"'{lang}' per its instruction. Write exactly one file "
                             f"content/_translate_out.json with the translated JSON object. Nothing else.")
        raw = (ROOT / "content" / "_translate_out.json").read_text(encoding="utf-8")
    out = llm_content.extract_json(raw) if use_http else json.loads(raw)
    if not isinstance(out, dict):
        raise RuntimeError("model did not return a JSON object")
    return out


def chunk(payload: dict, limit: int = 14000) -> list[dict]:
    chunks, cur, size = [], {}, 0
    for k, v in payload.items():
        piece = len(k) + len(str(v)) + 6
        if cur and size + piece > limit:
            chunks.append(cur)
            cur, size = {}, 0
        cur[k] = v
        size += piece
    if cur:
        chunks.append(cur)
    return chunks


def translate(cfg, key, use_http, lang, payload: dict, passes: int = 2,
              brand: str = "", domain: str = "") -> tuple[dict, list[str]]:
    out: dict = {}
    for part in chunk(payload):
        got: dict = {}
        errs: list[str] = []
        for attempt in range(passes + 1):
            try:
                got = ask(cfg, key, use_http, lang, part, errs or None, brand)
            except Exception as e:
                print(f"  · translation attempt {attempt + 1} failed: {e}")
                continue
            errs = validate(part, got, lang, brand, domain)
            if not errs:
                break
            print(f"  · repair pass {attempt + 1} ({len(errs)} issues)")
        out.update({k: v for k, v in got.items() if k in part and isinstance(v, str)})

    # self-heal before giving up: a whole chunk sometimes fails on one stubborn string,
    # while the same string alone goes through — retry the leftovers one by one
    bad = sorted({e.split(":")[0] for e in validate(payload, out, lang, brand, domain)})
    for path in bad[:40]:
        if path not in payload:
            continue
        single = {path: payload[path]}
        for _ in range(2):
            try:
                got = ask(cfg, key, use_http, lang, single, None, brand)
            except Exception:
                break
            if path in got and isinstance(got[path], str) and not validate(
                    single, {path: got[path]}, lang, brand, domain):
                out[path] = got[path]
                print(f"  · rescued {path} with a single-string retry")
                break
    return out, validate(payload, out, lang, brand, domain)


def main():
    ap = argparse.ArgumentParser(description="translate the master English pack into the plan language")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--content", required=True)
    ap.add_argument("--provider", default="auto", choices=["", "auto", "http", "cli"])
    ap.add_argument("--model", default="")
    ap.add_argument("--lang", default="", help="target language (default: plan params.lang)")
    ap.add_argument("--plan-only", action="store_true",
                    help="translate only plan-level strings (menu, top strip, slugs) — used when "
                         "the copy already came from the model")
    ap.add_argument("--payload-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    plan_f = pathlib.Path(a.plan)
    content_f = pathlib.Path(a.content)
    plan = json.loads(plan_f.read_text(encoding="utf-8"))
    pack = json.loads(content_f.read_text(encoding="utf-8")) if content_f.exists() else {}
    lang = (a.lang or plan["params"].get("lang") or "en").lower()
    payload = collect(pack, plan)
    if a.plan_only:
        payload = {k: v for k, v in payload.items() if k.startswith("plan.")}
    print(f"· {len(payload)} strings to translate into '{lang}'")

    if a.payload_only:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return
    if lang == "en":
        print("· language is en — nothing to do")
        return
    if a.dry_run:
        print("· dry run: payload collected, no model call")
        return

    cfg = llm_content.load_cfg()
    if a.model:
        cfg["model"] = a.model
    key = llm_content.resolve_key(cfg)
    use_http = a.provider == "http" or (a.provider in ("", "auto") and bool(key))
    if not use_http and a.provider == "http":
        llm_content.die("no API key: put VENICE_API_KEY=… in .llm_env")
    print(f"· transport: {'http ' + cfg['base_url'] if use_http else 'opencode CLI'} · model: {cfg['model']}")

    out, errs = translate(cfg, key, use_http, lang, payload,
                          brand=plan["params"]["brand"], domain=plan["params"]["domain"])
    if errs:
        llm_content.die("translation failed: " + "; ".join(errs[:8]))

    fresh_plan = json.loads(json.dumps(plan))
    fresh_pack = json.loads(json.dumps(pack))
    for path, text in out.items():
        if path.startswith("content."):
            _set_path(fresh_pack, path[len("content."):], text)
        elif path.startswith("plan."):
            _set_path(fresh_plan, path[len("plan."):], text)
    if not a.plan_only:
        content_f.write_text(json.dumps(fresh_pack, ensure_ascii=False, indent=1), encoding="utf-8")
    plan_f.write_text(json.dumps(fresh_plan, ensure_ascii=False, indent=1), encoding="utf-8")

    soft = leftover_english(out)
    if soft:
        print(f"! {len(soft)} strings still carry English words — spot-check: " + "; ".join(soft[:3]))
    words = len(re.findall(r"\w+", json.dumps(out, ensure_ascii=False)))
    print(f"LOCALIZED -> {content_f.name} ({words} words, {lang}) + plan menu/livebar/slugs")


if __name__ == "__main__":
    main()
