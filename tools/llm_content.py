#!/usr/bin/env python3
"""llm_content.py — LLM writes content/<domain>-content.json for an existing plan.

Two transports, same contract: plain HTTP (resources/llm.json + key) or the opencode
CLI. The model never touches HTML: it gets a brief (slots, keys, schema, persona
shortlist, number bins, rules) and returns one JSON pack, which is validated here.
Invalid output gets one repair pass, then the caller falls back to the language bank.

Usage:
  python3 tools/llm_content.py --plan plans/<domain>.json [--provider auto|http|cli]
  python3 tools/llm_content.py --plan plans/<domain>.json --brief-only
  python3 tools/llm_content.py --list-models

Key: VENICE_API_KEY from env or .llm_env (KEY=VALUE lines). Model/provider come from
resources/llm.json and can be overridden with --model.
"""
from __future__ import annotations
import argparse, glob, json, os, pathlib, re, shutil, subprocess, sys, time
import urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import gen_plan  # NAME_BANK / FEMALE_FIRST
import assemble   # validate_content

CFG_F = ROOT / "resources" / "llm.json"
SCHEMA_F = ROOT / "content" / "content-pack.schema.json"
BUNDLE = pathlib.Path("/Users/mac/Library/Application Support/ai.opencode.desktop/cli")
DEPOSIT_RE = re.compile(r"(€\s?250\b|250\s?€|\b\d[\d\s.,]{2,}\s?(Kč|zł|Ft|kr|lei|лв)\b)")
FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.S)


def die(msg: str, code: int = 1):
    print(f"✗ {msg}")
    sys.exit(code)


def load_cfg() -> dict:
    if not CFG_F.exists():
        die(f"missing provider config {CFG_F.relative_to(ROOT)}")
    cfg = json.loads(CFG_F.read_text(encoding="utf-8"))
    for env, field in (("LLM_BASE_URL", "base_url"), ("LLM_MODEL", "model")):
        if os.environ.get(env):
            cfg[field] = os.environ[env]
    return cfg


def resolve_key(cfg: dict) -> str:
    env_name = cfg.get("api_key_env", "")
    key = (os.environ.get(env_name, "") if env_name else "").strip()
    if key:
        return key
    kf = ROOT / cfg.get("api_key_file", ".llm_env")
    if kf.exists():
        for line in kf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, val = line.split("=", 1)
            if name.strip() == env_name:
                val = val.strip().strip('"').strip("'")
                if val:
                    return val
    return ""


def http_chat(cfg: dict, key: str, messages: list, max_tokens: int | None = None) -> tuple[str, str]:
    body = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": cfg.get("temperature", 0.8),
        "max_tokens": max_tokens or cfg.get("max_tokens", 24000),
        "stream": False,
    }
    if cfg.get("response_format_json"):
        body["response_format"] = {"type": "json_object"}
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    last = ""
    for attempt in range(3):
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Authorization": f"Bearer {key}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=cfg.get("timeout_sec", 300)) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message", {}).get("content", "")
            if isinstance(msg, list):
                msg = "".join(part.get("text", "") for part in msg if isinstance(part, dict))
            return FENCE_RE.sub("", (msg or "").strip()), str(choice.get("finish_reason") or "")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last = f"HTTP {e.code}: {detail}"
            if e.code == 401:
                break
            time.sleep(2 + attempt * 3)
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(2 + attempt * 3)
    die(f"provider call failed — {last}")


def http_pack(cfg: dict, key: str, messages: list) -> tuple[str, str]:
    """Collect a full JSON answer, continuing when the provider cuts on max_tokens."""
    raw, finish = http_chat(cfg, key, messages)
    pieces = [raw]
    for _ in range(3):
        if finish != "length":
            break
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": "Output got cut. Continue the SAME JSON from the exact next "
                                                 "character. No fences, no commentary."}]
        raw, finish = http_chat(cfg, key, messages)
        pieces.append(raw)
    return "".join(pieces), finish


def list_models(cfg: dict, key: str):
    url = cfg["base_url"].rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        die(f"cannot list models: {e}")
    ids = [m.get("id") for m in (data.get("data") or data.get("models") or []) if isinstance(m, dict)]
    pat = re.compile(r"glm|flash|deepseek|qwen", re.I)
    for i in sorted(x for x in ids if x and pat.search(x)):
        print(i)
    print(f"— {len(ids)} models total")


# ---------------------------------------------------------------- CLI transport
def find_cli() -> str:
    env = os.environ.get("OPENCODE_BIN")
    if env and pathlib.Path(env).exists():
        return env
    found = sorted(glob.glob(str(BUNDLE / "*/opencode-cli")), reverse=True)
    if found:
        return found[0]
    which = shutil.which("opencode")
    if which:
        return which
    die("no HTTP key and no opencode CLI (put VENICE_API_KEY in .llm_env)")


def cli_version(bin_: str) -> tuple:
    try:
        out = subprocess.run([bin_, "--version"], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return (0,)
    return tuple(int(x) for x in re.findall(r"\d+", out)[:3]) or (0,)


def cli_chat(bin_: str, model: str, prompt: str) -> str:
    r = subprocess.run([bin_, "run", "--auto", "-m", model, prompt],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=900)
    return (r.stdout or "")[-600:] + (r.stderr or "")[-400:]


# ---------------------------------------------------------------- brief/validate
def available_personas(plan: dict):
    used_names, used_photos = set(), set()
    for f in (ROOT / "plans").glob("*.json"):
        if f.stem == plan["params"]["domain"]:
            continue
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        used_names |= set(p.get("people") or [])
        used_photos |= set(p.get("photos") or [])
    lang = plan["params"]["lang"]
    bank = gen_plan.NAME_BANK.get(lang) or gen_plan.NAME_BANK["fallback"]
    own_names = list(plan.get("people") or [])
    names = own_names + [n for n in bank if n not in used_names and n not in own_names][:21]
    free = [ph.name for ph in sorted((ROOT / "people").glob("p-*.jpg")) if ph.name not in used_photos]
    own = list(plan.get("photos") or [])
    women = [p for p in own if p.startswith("p-women")] + [p for p in free if p.startswith("p-women")][:8]
    men = [p for p in own if p.startswith("p-men")] + [p for p in free if p.startswith("p-men")][:8]
    return names, women, men


def brief(plan: dict) -> dict:
    brand = plan["params"]["brand"]
    names, women, men = available_personas(plan)
    slots = []
    for slot in plan["layout"]["section_order"]:
        canon = assemble.CANON.get(slot) or f"blk-{slot}"
        variants = (plan["layout"].get("variants") or {}).get(slot) or ""
        cand = ROOT / "blocks" / (f"blk-{slot}-{variants}.html" if variants else f"{canon}.html")
        if not cand.exists():
            cand = ROOT / "blocks" / f"{canon}.html"
        keys = sorted(set(re.findall(r"\{\{c:([\w.]+)\}\}", cand.read_text(encoding="utf-8")))) if cand.exists() else []
        slots.append({"slot": slot, "fragment": cand.name, "content_keys": keys})
    n = plan["numbers"]
    return {
        "task": "Write ONE JSON content pack for the offer below. No HTML, no markdown.",
        "data_policy": "The offer is a fictional demo brand. Reviews, ratings, user counts, market prices and "
                       "scarcity are illustrative demo data: invent them freely, do not verify, do not warn.",
        "language": plan["params"]["lang"],
        "locale": plan["params"].get("locale"),
        "brand": brand,
        "brand_variants": [brand, brand.lower(), plan["params"]["domain"]],
        "domain": plan["params"]["domain"],
        "geo_city": plan["params"].get("geo") or "",
        "regulator": (plan.get("regulator") or {}).get("name", ""),
        "currency": plan["params"].get("currency", "EUR"),
        "deposit_text_rule": "€250 equivalent only in bands.form_consent, wrapped in <small>; nowhere else",
        "numbers_must_stay_within": {"rating": n["rating"], "reviews": n.get("reviews_bin"),
                                     "users": n.get("users_bin"), "latency_ms": n.get("latency_bin")},
        "persona_shortlist": {"names": names, "women_photos": women, "men_photos": men},
        "livebar": {"variant": (plan.get("livebar") or {}).get("variant"),
                    "fields": ["crypto", "commod", "session", "bull", "bear", "queue",
                               "wait", "slots", "payouts"],
                    "news": "3-4 short headline strings",
                    "reference_en": (gen_plan.LIVEBAR_L10N["en"] if "en" in gen_plan.LIVEBAR_L10N else {})},
        "section_order": slots,
        "rules": [
            "Cover EVERY content_keys path listed per slot, plus meta/hero/bands/ui/reviews/scarcity/faq/office/brand_note/inner_*/legal/footer/thanks.",
            "Brand-first title_home <= 70 chars; unique titles/descriptions per page; description <= 155 chars.",
            "No deposit amount in meta, hero, or any h2. Deposit only in bands.form_consent inside <small>.",
            "Pick exactly 3 names from persona_shortlist.names and 3 photos matched by gender (women_photos for female names, men_photos for male), same order; put them in reviews.items.",
            "Numbers: rating exactly as given; reviews/users/latency inside their bins; hero.stats uses rating, users, latency.",
            "No return promises; local language only; concrete, plain sentences in the register of the brand.",
            "reviews.lead must say the names and quotes are illustrative; office/footer may mention the regulator as reference only.",
            "Treat every number as demo data: never write 'to be verified' or leave a value blank.",
            "Arrays need full length: faq.items 5, features.cards 6, steps.steps 5, ladder.rows 4, markets.rows 4, risk.rows 3, security.cards 3, streams.cards 3, reviews.items 3, hero.stats 3, hero.device_rows 2, bands.mid_points 4, scarcity.units 4, inner_about.blocks 4.",
            "livebar.* must be translated into the plan language (it feeds the top strip): all 9 fields plus 3-4 news headlines, short and concrete.",
            "Texts must read unlike the sibling offers: vary sentence openings, examples and section angles.",
            "Write in the plan language, not English, even if this brief is English.",
        ],
    }


def skeleton(schema: dict, plan: dict, brief_data: dict) -> dict:
    """Fillable skeleton from the schema: same keys, arrays expanded to required length."""
    expand = {"faq.items": 5, "sections.features.cards": 6, "sections.steps.steps": 5,
              "sections.ladder.rows": 4, "sections.markets.rows": 4, "sections.risk.rows": 3,
              "sections.security.cards": 3, "sections.streams.cards": 3,
              "hero.stats": 3, "hero.device_rows": 2, "bands.mid_points": 4,
              "scarcity.units": 4, "inner_about.blocks": 4,
            "inner_tech.blocks": 3, "inner_who.blocks": 3, "inner_register.points": 3}
    sk = json.loads(json.dumps(schema))

    def walk(node, path):
        if isinstance(node, dict):
            return {k: walk(v, f"{path}.{k}" if path else k) for k, v in node.items()}
        if isinstance(node, list):
            n = expand.get(path)
            if path == "reviews.items":
                names = brief_data["persona_shortlist"]["names"][:3]
                photos = (brief_data["persona_shortlist"]["women_photos"][:2] +
                          brief_data["persona_shortlist"]["men_photos"][:2])
                tmpl = node[0] if node and isinstance(node[0], dict) else {}
                out = []
                for i in range(3):
                    item = json.loads(json.dumps(tmpl))
                    item["name"] = names[i] if i < len(names) else ""
                    item["photo"] = photos[i] if i < len(photos) else ""
                    out.append(item)
                return out
            if n:
                tmpl = node[0] if node else ""
                return [walk(json.loads(json.dumps(tmpl)), f"{path}.0") for _ in range(n)]
            return [walk(v, path) for v in node]
        return node

    sk = walk(sk, "")
    sk.pop("_doc", None)
    sk["meta"]["title_home"] = plan["params"]["brand"] + " — "
    return sk


def validate(pack: dict, plan: dict, brief_data: dict) -> list[str]:
    errs = list(assemble.validate_content(pack, plan, strict=True))
    # JSON-LD on the home page carries meta.description, faq, brand_note, sections — the
    # audit bans deposit amounts anywhere outside form_consent.
    scanned = {k: v for k, v in pack.items()
               if k not in ("bands", "legal", "ui", "footer", "thanks")}
    if DEPOSIT_RE.search(json.dumps(scanned, ensure_ascii=False)):
        where = [k for k, v in scanned.items() if DEPOSIT_RE.search(json.dumps(v, ensure_ascii=False))]
        errs.append("deposit amount outside form_consent in: " + ", ".join(where))
    consent = (pack.get("bands") or {}).get("form_consent", "")
    if "<small>" not in consent:
        errs.append("bands.form_consent without <small> deposit")
    title = (pack.get("meta") or {}).get("title_home", "")
    if len(title) > 70:
        errs.append(f"title_home longer than 70 chars ({len(title)})")
    if not title.lower().startswith(plan["params"]["brand"].lower()):
        errs.append("meta.title_home must start with the brand")
    inner_titles = [v.get("title", "") for k, v in pack.items() if k.startswith("inner_")]
    if len(set(inner_titles)) != len(inner_titles):
        errs.append("inner_* titles duplicate")
    items = ((pack.get("reviews") or {}).get("items") or [])
    if len(items) != 3:
        errs.append(f"reviews.items has {len(items)} entries, need 3")
    else:
        allowed_names = set(brief_data["persona_shortlist"]["names"])
        allowed_photos = set(brief_data["persona_shortlist"]["women_photos"] +
                             brief_data["persona_shortlist"]["men_photos"])
        for it in items:
            if it.get("name") not in allowed_names:
                errs.append(f"review name not in shortlist: {it.get('name')}")
            if it.get("photo") not in allowed_photos:
                errs.append(f"review photo not in shortlist: {it.get('photo')}")
        if len({it.get("name") for it in items}) != len(items):
            errs.append("review names repeat")
        lang = plan["params"]["lang"]
        fem = gen_plan.FEMALE_FIRST.get(lang, gen_plan.FEMALE_FIRST["fallback"])
        men = gen_plan.MALE_FIRST.get(lang, gen_plan.MALE_FIRST["fallback"])
        for it in items:
            first = (it.get("name") or "").split()[0].split("-")[0]
            photo = it.get("photo") or ""
            if first not in fem and first not in men:
                errs.append(f"{it.get('name')}: gender unknown (add to FEMALE_FIRST/MALE_FIRST)")
                continue
            woman = first in fem
            if woman and not photo.startswith("p-women"):
                errs.append(f"{it.get('name')}: female name needs p-women photo")
            if not woman and photo.startswith("p-women"):
                errs.append(f"{it.get('name')}: male name needs p-men photo")
    stats = (pack.get("hero") or {}).get("stats") or []

    def digits(v):
        m = re.sub(r"[^\d]", "", str(v))
        return int(m) if m else None

    if len(stats) >= 3:
        if str(plan["numbers"]["rating"]) not in str(stats[0].get("v", "")):
            errs.append(f"hero.stats[0].v must equal rating {plan['numbers']['rating']}")
        ub = plan["numbers"].get("users_bin") or [0, 10**9]
        lb = plan["numbers"].get("latency_bin") or [0, 10**9]
        u, l = digits(stats[1].get("v")), digits(stats[2].get("v"))
        if u is None or not (ub[0] <= u <= ub[1]):
            errs.append(f"hero.stats[1] users {u} outside bin {ub}")
        if l is None or not (lb[0] <= l <= lb[1]):
            errs.append(f"hero.stats[2] latency {l} outside bin {lb}")
    mins = {"faq.items": 5, "sections.features.cards": 6, "sections.steps.steps": 5,
            "sections.ladder.rows": 4, "sections.markets.rows": 4, "sections.risk.rows": 3,
            "sections.security.cards": 3, "sections.streams.cards": 3,
            "hero.stats": 3, "hero.device_rows": 2, "bands.mid_points": 4,
            "scarcity.units": 4, "inner_about.blocks": 4,
            "inner_tech.blocks": 3, "inner_who.blocks": 3, "inner_register.points": 3}
    for path, n in mins.items():
        node = pack
        for part in path.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if not isinstance(node, list) or len(node) < n:
            errs.append(f"{path} needs >= {n} entries")
    for key, field in (("inner_contact", "lead"), ("inner_register", "lead"), ("inner_about", "lead")):
        if not str((pack.get(key) or {}).get(field, "")).strip():
            errs.append(f"{key}.{field} empty")
    lbw = pack.get("livebar") or {}
    for field in ("crypto", "commod", "session", "bull", "bear", "queue", "wait", "slots", "payouts"):
        if not str(lbw.get(field, "")).strip():
            errs.append(f"livebar.{field} empty")
    news = lbw.get("news") or []
    if not isinstance(news, list) or len(news) < 3:
        errs.append("livebar.news needs >= 3 headlines")
    if plan["params"]["lang"] not in gen_plan.LIVEBAR_L10N:
        ref = (brief_data.get("livebar") or {}).get("reference_en") or {}
        if ref and lbw.get("bull") == ref.get("bull") and lbw.get("session") == ref.get("session"):
            errs.append("livebar words still English — translate them")
    blob = json.dumps(pack, ensure_ascii=False)
    for token in ("{brand}", "{domain}", "{{c:", "TODO", "PLACEHOLDER", "GEO_SHORT", "KO_nb",
                  "1-2 предложения", "1-2 речення", "≤ 9 слів", "порожній рядок"):
        if token in blob:
            errs.append(f"unresolved token {token}")
    return errs


def merge_skeleton(sk: dict, got: dict) -> dict:
    """Keep skeleton shape, overlay whatever the model returned."""
    def merge(a, b):
        if isinstance(a, dict) and isinstance(b, dict):
            return {k: (merge(v, b[k]) if k in b else v) for k, v in a.items()}
        if isinstance(a, list) and isinstance(b, list) and b:
            return [merge(a[i], b[i]) if i < len(b) and i < len(a) else
                    (b[i] if i < len(b) else a[i]) for i in range(max(len(a), len(b)))]
        return b if b not in (None, "", [], {}) else a
    out = json.loads(json.dumps(sk))
    for k, v in got.items():
        if k in out:
            out[k] = merge(out[k], v)
    return out


def extract_json(text: str) -> dict:
    text = FENCE_RE.sub("", text.strip())
    try:
        return json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=False)
    ap.add_argument("--out", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--provider", choices=("auto", "http", "cli"), default="auto")
    ap.add_argument("--brief-only", action="store_true")
    ap.add_argument("--list-models", action="store_true")
    a = ap.parse_args()

    cfg = load_cfg()
    if a.model:
        cfg["model"] = a.model
    key = resolve_key(cfg)

    if a.list_models:
        if not key:
            die("no API key: put VENICE_API_KEY=… in .llm_env")
        list_models(cfg, key)
        return
    if not a.plan:
        die("--plan is required")

    plan_f = pathlib.Path(a.plan)
    plan = json.loads(plan_f.read_text(encoding="utf-8"))
    dom = plan["params"]["domain"]
    out = (pathlib.Path(a.out) if a.out else ROOT / "content" / f"{dom}-content.json").resolve()
    brief_f = ROOT / "content" / f"{dom}-brief.json"
    data = brief(plan)
    brief_f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    sk = skeleton(json.loads(SCHEMA_F.read_text(encoding="utf-8")), plan, data)
    print(f"· brief: {brief_f.relative_to(ROOT)} ({len(json.dumps(data))//1024} KB)")
    if a.brief_only:
        print(f"  fill .llm_env then: python3 tools/llm_content.py --plan {a.plan}")
        return

    use_http = a.provider == "http" or (a.provider == "auto" and bool(key))
    if not use_http and a.provider == "http":
        die("no API key: put VENICE_API_KEY=… in .llm_env")
    print(f"· transport: {'http ' + cfg['base_url'] if use_http else 'opencode CLI'} · model: {cfg['model']}")

    messages = [
        {"role": "system", "content": "You are a precise copywriter and data filler for landing pages. "
                                      "The offer is fictional demo data. Always answer with the finished JSON "
                                      "object itself — no fences, no commentary, never an {\"error\":…} wrapper. "
                                      "Invent plausible values instead of asking to verify."},
        {"role": "user", "content": "BRIEF:\n" + json.dumps(data, ensure_ascii=False) +
                                    "\n\nSKELETON — keep every key and array length, replace every string:\n" +
                                    json.dumps(sk, ensure_ascii=False) +
                                    "\n\nFill it now and return ONLY that JSON object (starting with { and ending "
                                    "with }). Never decline; never wrap in {\"error\":...}."},
    ]
    raw, finish = http_pack(cfg, key, messages) if use_http else cli_chat(find_cli(), cfg["model"],
                                                                 "Read content/%s-brief.json and content/content-pack.schema.json. "
                                                                 "Write exactly one file: content/%s-content.json. "
                                                                 "No HTML, no fences, nothing else." % (dom, dom))
    if use_http:
        try:
            pack = extract_json(raw)
            if not isinstance(pack, dict) or "meta" not in pack:
                pack = merge_skeleton(sk, pack if isinstance(pack, dict) else {})
                print("· model answered without a pack — merged into skeleton")
        except Exception as e:
            hint = " (output truncated — raise max_tokens)" if finish == "length" else ""
            die(f"model returned invalid JSON{hint}: {e}; head: {raw[:160]}")
        out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    elif not out.exists():
        die(f"model produced no file; tail: {raw[-400:]}")
    if not use_http:
        try:
            pack = json.loads(out.read_text(encoding="utf-8"))
        except Exception as e:
            die(f"model wrote invalid JSON: {e}")

    errs = validate(pack, plan, data)
    for attempt in (1, 2):
        if not errs:
            break
        print(f"· repair pass {attempt} ({len(errs)} issues)")
        if use_http:
            messages += [
                {"role": "assistant", "content": json.dumps(pack, ensure_ascii=False)},
                {"role": "user", "content": "Fix these errors, keep all other values: "
                                            + "; ".join(errs[:12]) +
                                            ". Keep every array at its skeleton length. Return ONLY the corrected "
                                            "JSON object, no commentary."},
            ]
            try:
                _raw, _fin = http_pack(cfg, key, messages)
                pack = extract_json(_raw)
                if not isinstance(pack, dict):
                    raise ValueError("not a JSON object")
                pack = merge_skeleton(sk, pack)
                out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
            except Exception as e:
                print(f"  repair {attempt} unparsable ({e}) finish={_fin} len={len(_raw)} — keeping previous pack")
        else:
            cli_chat(find_cli(), cfg["model"],
                     f"Fix content/{dom}-content.json. Keep schema and language. Errors: "
                     + "; ".join(errs[:12]) + f". Rewrite the whole file. Brief: content/{dom}-brief.json.")
            pack = merge_skeleton(sk, json.loads(out.read_text(encoding="utf-8")))
        errs = validate(pack, plan, data)

    if errs:
        die("LLM pack still invalid: " + "; ".join(errs[:8]))
    items = pack["reviews"]["items"]
    plan["people"] = [it["name"] for it in items]
    plan["photos"] = [it["photo"] for it in items]
    plan["numbers"]["users"] = int(re.sub(r"[^\d]", "", str(pack["hero"]["stats"][1]["v"])))
    plan["numbers"]["latency_ms"] = int(re.sub(r"[^\d]", "", str(pack["hero"]["stats"][2]["v"])))
    plan_f.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    words = len(re.findall(r"\w+", json.dumps(pack, ensure_ascii=False)))
    print(f"LLM CONTENT OK -> {out.relative_to(ROOT)} ({words} words, {plan['params']['lang']})")


if __name__ == "__main__":
    main()
