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
import argparse, glob, json, os, pathlib, random, re, shutil, subprocess, sys, time
import urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import gen_plan  # NAME_BANK / FEMALE_FIRST
import assemble   # validate_content
import content_gen  # merged_bank / topup_new_keys (migration of older packs)

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
    """Photos are the only hard-constrained persona asset (never reused across plans);
    names/cities/roles are invented by the model per geo, so no per-language bank is needed."""
    used_names, used_photos = set(), set()
    for f in (ROOT / "plans").glob("*.json"):
        if f.stem == plan["params"]["domain"]:
            continue
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        used_names |= {n.lower() for n in (p.get("people") or [])}
        used_photos |= set(p.get("photos") or [])
    free = [ph.name for ph in sorted((ROOT / "people").glob("p-*.jpg")) if ph.name not in used_photos]
    own = list(plan.get("photos") or [])
    women = [p for p in own if p.startswith("p-women")] + [p for p in free if p.startswith("p-women")][:8]
    men = [p for p in own if p.startswith("p-men")] + [p for p in free if p.startswith("p-men")][:8]
    return sorted(used_names), women, men


def sibling_persona_values(plan: dict) -> tuple[list, list]:
    """Cities and tenures already shown by same-brand sibling offers (from profiles/).
    Passed to the model as a soft avoid-hint: exact repeats of the full trio are what
    twin_check used to flag; occasional single collisions are acceptable."""
    cities, tenures = [], []
    brand = (plan["params"].get("brand") or "").lower()
    if not brand:
        return cities, tenures
    for f in sorted((ROOT / "profiles").glob("*.json")):
        if f.stem == plan["params"]["domain"]:
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (d.get("brand") or "").lower() != brand:
            continue
        for p in (d.get("personas") or []):
            if (p.get("city") or "").strip():
                cities.append(p["city"].strip())
            if (p.get("tenure") or "").strip():
                tenures.append(str(p["tenure"]).strip())
    return cities, tenures


TENURE_EXAMPLES = [["3 months", "8 months", "2 years"],
                   ["5 months", "1 year", "3 years"],
                   ["7 months", "18 months", "4 years"],
                   ["2 months", "1 year", "5 years"],
                   ["6 months", "2 years", "6 years"]]


def brief(plan: dict) -> dict:
    brand = plan["params"]["brand"]
    used_names, women, men = available_personas(plan)
    sib_cities, sib_tenures = sibling_persona_values(plan)
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
    style_ref = (gen_plan.NAME_BANK.get(plan["params"]["lang"]) or gen_plan.NAME_BANK["fallback"])[:3]
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
        "persona_policy": {
            "rule": "Invent 3 personas that read as native to the geo (names, cities, professions in the "
                    "plan language). Do NOT copy the style_reference names. Photos are FIXED and already "
                    "pre-filled in the skeleton — keep them in this exact order and invent a name whose "
                    "gender matches each photo (p-women-* → female, p-men-* → male) and set g to f or m.",
            "cities": "3 DIFFERENT real cities of the geo (geo_city may be at most one of them); never "
                      "repeat a city inside one pack and never reuse sibling cities.",
            "tenure": "3 DIFFERENT believable tenures (for example: " +
                      " / ".join(random.choice(TENURE_EXAMPLES)) + "), phrased freshly in the plan "
                      "language — do not reuse this example verbatim.",
            "style_reference_only": style_ref,
            "names_already_used_by_other_offers_do_not_reuse": sorted(used_names)[:60],
            "sibling_values_avoid_if_possible": {
                "cities": sorted({c.lower() for c in sib_cities}),
                "tenures": sorted({t.lower() for t in sib_tenures}),
                "note": "Cities/tenures already shown by sibling offers of this brand. "
                        "Pick different ones when the geo allows; a single overlap is tolerable, "
                        "copying the whole trio is not."},
            "women_photos": women, "men_photos": men,
        },
        "livebar": {"variant": (plan.get("livebar") or {}).get("variant"),
                    "fields": ["crypto", "commod", "session", "bull", "bear", "queue",
                               "wait", "slots", "payouts"],
                    "news": "3-4 short headline strings",
                    "reference_en": (gen_plan.LIVEBAR_L10N["en"] if "en" in gen_plan.LIVEBAR_L10N else {})},
        "section_order": slots,
        "rules": [
            "Cover EVERY content_keys path listed per slot, plus meta/hero/bands/ui/reviews/scarcity/faq/office/brand_note/inner_*/legal/footer/thanks.",
            "Brand-first title_home <= 70 chars; unique titles/descriptions per page; description <= 155 chars.",
            "hero.h1_rest continues the sentence after the brand; hero.h1_accent is the closing accent (2-4 words). NEVER repeat the brand in either line: the h1 already prints it in .brand-line.",
            "No deposit amount in meta, hero, or any h2. Deposit only in bands.form_consent inside <small>.",
            "reviews.items: exactly 3 entries, photos kept as pre-filled, names/cities/roles/tenures invented per persona_policy, each item carries g (f|m) matching its photo.",
            "Numbers: rating exactly as given; reviews/users/latency inside their bins; hero.stats uses rating, users, latency.",
            "sections.stats.rating/reviews/orders/api are WORD captions for the numbers band (e.g. 'valoración media', 'reseñas verificadas', 'operaciones al día', 'disponibilidad de la API') — never digits, never the figure repeated.",
            "inner_about/inner_who/inner_tech titles feed the page <title> AND the menu label: name the page's own topic (about = who we are, who = who it is for), not a different section.",
            "Never glue the brand to the previous word: 'el login de la plataforma o Photon AI opiniones…' needs the space — 'oPhoton AI' is a defect.",
            "office.* labels are 1–3 word captions ('Dirección', 'Horario', 'Teléfono', 'Escríbenos'), never a sentence. Do not invent e-mail or phone: they are injected from the offer and meta.email/telephone are overwritten.",
            "No return promises; local language only; concrete, plain sentences in the register of the brand.",
            "hero.device_note is the caption under the mocked panel: you write it yourself, in the plan "
            "language, as an illustration / interface-preview phrase. Placeholder wording is rejected: "
            "never 'sample data', 'demo data', 'dati di esempio', 'datos de ejemplo'.",
            "hero.device_rows are the parts of the headline hero.device_bal: the two row values MUST add up "
            "exactly to that balance. Row labels are neutral holding categories in the plan language — "
            "never promise yield ('interest-bearing cash' and the like).",
            "reviews.lead must say the names and quotes are illustrative; office/footer may mention the regulator as reference only.",
            "Treat every number as demo data: never write 'to be verified' or leave a value blank.",
            "Format numbers, prices and percentages with the locale separators of the plan language "
            "(comma decimals for pt/es/it/fr/de).",
            "Arrays need full length: faq.items 5, features.cards 6, steps.steps 5, ladder.rows 4, markets.rows 4, risk.rows 3, security.cards 3, streams.cards 3, reviews.items 3, hero.stats 3, hero.device_rows 2, bands.mid_points 4, scarcity.units 4, inner_about.blocks 4.",
            "livebar.* must be translated into the plan language (it feeds the top strip): all 9 fields plus 3-4 news headlines, short and concrete.",
            "Texts must read unlike the sibling offers: vary sentence openings, examples and section angles.",
            "Hero CTAs, eyebrows, section h2 wording and the submit button must be phrased freshly for THIS offer — never copy boilerplate like 'EMPIEZA HOY'/'Solicitar acceso' from sibling offers.",
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
              "sections.facts.points": 4, "sections.portal.cards": 3,
              "bands.side_stats": 3, "bands.side_labels": 3,
            "inner_tech.blocks": 3, "inner_who.blocks": 3, "inner_register.points": 3}
    sk = json.loads(json.dumps(schema))

    def walk(node, path):
        if isinstance(node, dict):
            return {k: walk(v, f"{path}.{k}" if path else k) for k, v in node.items()}
        if isinstance(node, list):
            n = expand.get(path)
            if path == "reviews.items":
                tmpl = node[0] if node and isinstance(node[0], dict) else {}
                photos = list(plan.get("photos") or [])[:3]
                out = []
                for i in range(3):
                    item = json.loads(json.dumps(tmpl))
                    item["photo"] = photos[i] if i < len(photos) else ""
                    item["name"] = ""          # model invents the persona (any geo)
                    item["g"] = ""             # f|m, must match the photo
                    item["city"] = ""
                    item["tenure"] = ""
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


def ledger_errors(hv: dict) -> list[str]:
    """Hero mock panel: the model writes the caption and the numbers; these checks only
    verify it did not forget them or leave them out of balance."""
    errs = []
    note = str(hv.get("device_note", "") or "").strip()
    if not note:
        errs.append("hero.device_note is empty — write the caption that marks the mock panel "
                    "as an illustration, in the plan language")
    elif content_gen.PLACEHOLDER_NOTE.search(note):
        errs.append("hero.device_note reads as placeholder data ('sample data'/'demo data'/…) — "
                    "phrase it as an illustration of the interface in the plan language")
    elif len(note) < 6:
        errs.append(f"hero.device_note is too short ('{note}') — one clear caption line")
    rows = [r for r in (hv.get("device_rows") or []) if isinstance(r, dict)]
    if len(rows) != 2:
        errs.append(f"hero.device_rows has {len(rows)} entries, need 2")
    else:
        bal = content_gen.parse_money(hv.get("device_bal_v") or hv.get("device_bal") or "")
        vals = [content_gen.parse_money(r.get("vv") or r.get("v") or "") for r in rows]
        if bal and all(v is not None for v in vals) and abs(sum(vals) - bal) > 0.02:
            errs.append(f"hero.device_rows do not add up: {vals[0]:,.2f} + {vals[1]:,.2f} != "
                        f"hero.device_bal {bal:,.2f} — make the two rows sum to the headline balance")
    return errs


def _pack_get(pack: dict, path: str):
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


def missing_fragment_keys(pack: dict, plan: dict) -> list:
    """Every {{c:…}} key a rendered fragment needs must exist and be non-empty.

    Copy is never topped up from the English bank for a non-English site (that shipped
    an English portal block on a Slovenian page), so the model has to write those keys
    itself — this is the list it gets back for the repair pass.
    """
    out = []
    for slot in plan["layout"]["section_order"]:
        var = (plan["layout"].get("variants") or {}).get(slot) or ""
        canon = assemble.CANON.get(slot) or f"blk-{slot}"
        cand = ROOT / "blocks" / (f"blk-{slot}-{var}.html" if var else f"{canon}.html")
        if not cand.exists():
            cand = ROOT / "blocks" / f"{canon}.html"
        if not cand.exists():
            continue
        for path in sorted(set(re.findall(r"\{\{c:([\w.]+)\}\}", cand.read_text(encoding="utf-8")))):
            if path.startswith("ui.aria_"):
                continue          # assembled from UI_L10N defaults, not model copy
            if not str(_pack_get(pack, path) or "").strip():
                out.append(path)
    return out


def validate(pack: dict, plan: dict, brief_data: dict) -> list[str]:
    try:
        errs = list(assemble.validate_content(pack, plan, strict=True))
    except Exception as e:            # a broken shape must become a repair instruction,
        errs = [f"content pack structure invalid ({type(e).__name__}: {e})"]   # not a traceback
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
    _brand = plan["params"]["brand"].lower()
    _hero = pack.get("hero") or {}
    for _f in ("h1_rest", "h1_accent"):
        if _brand and _brand in str(_hero.get(_f) or "").lower():
            errs.append(f"hero.{_f} repeats the brand — the h1 prints it in .brand-line already; "
                        f"write the rest of the sentence / a 2-4 word accent instead")
    # hero ledger mock: the model authors the caption and the numbers, the gate only
    # checks it did not forget — a placeholder caption or rows that do not add up go
    # straight back as a repair instruction
    errs += ledger_errors(pack.get("hero") or {})
    # English boilerplate inside a translated pack (the model loves "All rights reserved"
    # and "Bank transfer"): name the path and let the repair pass rewrite it
    if plan["params"].get("lang") != "en":
        _leak = re.compile(r"\b(all rights reserved|bank transfer|back to home|page not found|"
                           r"terms of service|privacy policy|read more|learn more|sign up|"
                           r"get started|how it works)\b", re.I)

        def _leaks(node, path=""):
            if isinstance(node, str):
                m = _leak.search(node)
                if m:
                    out.append(f"{path}: English boilerplate '{m.group(0)}'")
            elif isinstance(node, dict):
                for k, v in node.items():
                    _leaks(v, f"{path}.{k}".strip("."))
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    _leaks(v, f"{path}.{i}")

        out = []
        _leaks(pack)
        if out:
            errs.append("English left in a translated pack: " + "; ".join(out[:6]))

    _miss = missing_fragment_keys(pack, plan)
    if _miss:
        errs.append("fragments need these content keys (missing or empty): "
                    + ", ".join(_miss[:12]))
    # pages assembled outside the section fragments (legal, thanks, footer, meta) are
    # not covered by the fragment scan — a missing legal body used to fall back to an
    # English stub on a translated site
    _extra = [k for k in ("meta.title_home", "meta.description", "footer.tagline",
                          "footer.disclaimer", "footer.risk_line", "legal.terms",
                          "legal.privacy", "thanks.eyebrow", "thanks.h1", "thanks.lead",
                          "ui.terms_title", "ui.privacy_title", "ui.not_found_title",
                          "ui.not_found_back", "ui.back_home",
                          "footer.terms_label", "footer.privacy_label", "footer.rights",
                          "footer.pay_chips",
                          "page_labels.about", "page_labels.who", "page_labels.contact",
                          "page_labels.register")
              if not str(_pack_get(pack, k) or "").strip()]
    if _extra:
        errs.append("these page-level keys are missing or empty: " + ", ".join(_extra))
    # deposit rule: keep in sync with tools/seo_audit.py dep_pat — meta/og/JSON-LD text
    # (meta.description feeds the JSON-LD org.description) must never mention a deposit
    dep_pat = re.compile(r"(€\s?250\b|250\s?€|min(?:imum)?\s?deposit|min(?:imální|minimāl)|100\s?000\s?Ft|100000\s?Ft)")
    for mkey in ("description", "og_description", "keywords"):
        mval = str((pack.get("meta") or {}).get(mkey) or "")
        hit = dep_pat.findall(mval)
        if hit:
            errs.append(f"meta.{mkey} mentions a deposit ({hit[0]}) — deposit lives only "
                        f"in bands.form_consent <small>; rephrase without amounts/deposit words")
    inner_titles = [v.get("title", "") for k, v in pack.items() if k.startswith("inner_")]
    if len(set(inner_titles)) != len(inner_titles):
        errs.append("inner_* titles duplicate")
    items = ((pack.get("reviews") or {}).get("items") or [])
    if len(items) != 3:
        errs.append(f"reviews.items has {len(items)} entries, need 3")
    else:
        allowed_photos = set(brief_data["persona_policy"]["women_photos"] +
                             brief_data["persona_policy"]["men_photos"])
        used = set(brief_data["persona_policy"].get("names_already_used_by_other_offers_do_not_reuse") or [])
        for it in items:
            name = (it.get("name") or "").strip()
            photo = it.get("photo") or ""
            if len(name) < 3 or not re.search(r"[^\W\d_]", name, re.UNICODE):
                errs.append(f"review name missing/invalid: '{name}'")
                continue
            if name.lower() in used:
                errs.append(f"persona name reused from another offer: {name}")
            if photo not in allowed_photos:
                errs.append(f"review photo not in shortlist: {photo}")
            g = (it.get("g") or "").strip().lower()
            if g not in ("f", "m"):
                errs.append(f"{name}: g must be 'f' or 'm'")
            elif g == "f" and not photo.startswith("p-women"):
                errs.append(f"{name}: g=f needs a p-women photo")
            elif g == "m" and not photo.startswith("p-men"):
                errs.append(f"{name}: g=m needs a p-men photo")
            if not str(it.get("city") or "").strip():
                errs.append(f"{name}: city empty")
            if not str(it.get("tenure") or "").strip():
                errs.append(f"{name}: tenure empty")
        if len({it.get("name") for it in items}) != len(items):
            errs.append("review names repeat")
        if len({(it.get("city") or "").strip().lower() for it in items}) < len(items):
            errs.append("review cities must be 3 different places of the geo")
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
    # no duplicated headings anywhere on the page (h1/h2 reused across sections)
    heads = []

    def _collect(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("h2", "h1") and isinstance(v, str) and v.strip():
                    heads.append(" ".join(v.split()).lower())
                else:
                    _collect(v)
        elif isinstance(node, list):
            for v in node:
                _collect(v)

    _collect({k: pack[k] for k in pack
              if k not in ("meta", "ui", "bands", "legal", "footer", "thanks", "livebar")})
    dup = sorted({h for h in heads if heads.count(h) > 1})
    if dup:
        errs.append("duplicate headings across sections: " + "; ".join(dup[:3]))
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
            merged = {k: (merge(v, b[k]) if k in b else v) for k, v in a.items()}
            for k, v in b.items():
                if k not in merged:        # keep model slots the skeleton does not know
                    merged[k] = v
            return merged
        if isinstance(a, list) and isinstance(b, list) and b:
            return [merge(a[i], b[i]) if i < len(b) and i < len(a) else
                    (b[i] if i < len(b) else a[i]) for i in range(max(len(a), len(b)))]
        return b if b not in (None, "", [], {}) else a
    out = json.loads(json.dumps(sk))
    for k, v in got.items():
        if k in out:
            out[k] = merge(out[k], v)
        else:
            # the model answered a slot the skeleton has no shape for: keep it instead
            # of dropping it (that is how a whole portal section used to disappear
            # between repair passes). validation reports the shape if it is wrong.
            out[k] = v
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


def normalize_contacts(pack: dict, plan: dict) -> None:
    """Contacts belong to the offer, not to the model's imagination.

    Older packs can leave another geo's fallbacks (contatti@… / +39… on a .es site);
    they shipped in both the office block and the Organization JSON-LD. Overwrite with
    the domain's own address and a phone that matches the plan country.
    """
    meta = pack.get("meta")
    if not isinstance(meta, dict):
        pack["meta"] = meta = {}
    c = assemble.contacts_for(plan, pack)
    if str(meta.get("email") or "").strip().lower() != c["email"]:
        print(f"· contacts: e-mail set to {c['email']} (pack had {meta.get('email') or '—'})")
    if str(meta.get("telephone") or "").strip() != c["telephone"]:
        print(f"· contacts: phone set to {c['telephone']} (pack had {meta.get('telephone') or '—'})")
    meta["email"], meta["telephone"] = c["email"], c["telephone"]
    if isinstance(pack.get("office"), dict):
        assemble.office_defaults(pack, plan)


def prepare_and_validate(pack: dict, plan: dict, brief_data: dict) -> list[str]:
    normalize_contacts(pack, plan)
    return validate(pack, plan, brief_data)


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

    try:   # newer fragment keys (glance, stats labels) — top up from the bank
        _l10n = ROOT / "resources" / "content-l10n.json"
        _bank = content_gen.merged_bank(json.loads(_l10n.read_text(encoding="utf-8")),
                                        plan["params"]["lang"])
        _lang = plan["params"]["lang"]
        # the bank may only fill copy when it actually holds that language: it/cs/es are
        # complete, everything else is English master copy and would leak into the page
        _copy_ok = _lang == "en" or content_gen.bank_coverage(
            json.loads(_l10n.read_text(encoding="utf-8")), _lang)[0] == 100
        _fixed = content_gen.topup_new_keys(pack, _bank, copy=_copy_ok)
        if _fixed:
            print("· topped up missing keys: " + ", ".join(_fixed))
    except Exception:
        pass

    errs = prepare_and_validate(pack, plan, data)
    for attempt in (1, 2):
        if not errs:
            break
        print(f"· repair pass {attempt} ({len(errs)} issues)")
        if use_http:
            messages += [
                {"role": "assistant", "content": json.dumps(pack, ensure_ascii=False)},
                {"role": "user", "content": "Fix these errors, keep all other values: "
                                            + "; ".join(errs[:12]) +
                                            ". Keep every array at its skeleton length — never null, never an "
                                            "empty array. Return ONLY the corrected "
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
        errs = prepare_and_validate(pack, plan, data)

    if errs and all("device_rows do not add up" in e for e in errs):
        # the copy is fine, only the arithmetic is off — balance the second row locally
        # instead of throwing away a pack the model otherwise wrote well
        if content_gen.reconcile_ledger(pack):
            print("· ledger rows rebalanced against the headline (model arithmetic slip)")
            out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
            errs = prepare_and_validate(pack, plan, data)
    if errs:
        die("LLM pack still invalid: " + "; ".join(errs[:8]))
    # contacts are deterministic — persist whatever the normalizer settled on
    normalize_contacts(pack, plan)
    out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
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
