#!/usr/bin/env python3
"""content_gen.py — deterministic content pack builder (plan → content/<domain>-content.json).

Fills the whole content-pack schema from resources/content-l10n.json so a site never
ships with placeholder copy. Copy varies per domain via a seed derived from the plan
seed + domain, so siblings stay below the 20% text overlap mark.

Usage:
  python3 tools/content_gen.py --plan plans/<domain>.json [--out content/<domain>-content.json] [--force]

Exit 1 when the plan lacks a language bank (falls back to en with a warning) or the
generated pack fails assemble's own validate_content().
"""
from __future__ import annotations
import argparse, json, pathlib, random, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
L10N = ROOT / "resources" / "content-l10n.json"

PHONE_CC = {"IT": "+39 ", "CZ": "+420 ", "SK": "+421 ", "PL": "+48 ", "DE": "+49 ",
            "AT": "+43 ", "FR": "+33 ", "BE": "+32 ", "NL": "+31 ", "ES": "+34 ",
            "PT": "+351 ", "HU": "+36 ", "RO": "+40 ", "BG": "+359 ", "GR": "+30 ",
            "HR": "+385 ", "SI": "+386 ", "LT": "+370 ", "LV": "+371 ", "EE": "+372 ",
            "FI": "+358 ", "SE": "+46 ", "DK": "+45 ", "NO": "+47 ", "IE": "+353 "}
ZIP_RE = re.compile(r"^[A-Za-z0-9 -]{2,8}$")
# captions that advertise a mock panel as placeholder data (mirrored in tools/seo_audit.py)
PLACEHOLDER_NOTE = re.compile(
    r"sample data|dati di esempio|datos de ejemplo|ukazkov[aá] data|uk[aá]zkov[aá] data|"
    r"demo-?gegevens|prikazni podatki|przyk[lł]adowe dane|donn[eé]es d'exemple|"
    r"beispieldaten|dati demo|demo data|dane demonstracyjne", re.I)


def die(m):
    print(f"✗ {m}")
    sys.exit(1)


def pick(rng, v, ctx):
    if isinstance(v, list):
        v = rng.choice(v)
    if isinstance(v, str):
        return v.replace("{pct}", ctx.get("pct", "1,0")).format(**ctx)
    return v


CHOICE_KEYS = {"title", "h1", "description", "og", "h1_rest", "h1_accent", "lead", "secondary",
               "cta_primary", "cta_secondary", "eyebrow", "h2", "mid_eyebrow", "mid_h2",
               "mid_lead", "form_title", "form_sub", "submit_nav", "btn", "stat_rating",
               "stat_users", "stat_latency", "device_delta", "asset_1", "asset_2"}


def deep(rng, node, ctx, key=""):
    if isinstance(node, dict):
        return {k: deep(rng, v, ctx, k) for k, v in node.items()}
    if isinstance(node, list):
        if key in CHOICE_KEYS and node and isinstance(node[0], str):
            return pick(rng, node, ctx)
        return [deep(rng, v, ctx, key) for v in node]
    return pick(rng, node, ctx)


def fmt_amount(value: float, cur: str, decimals: bool = False) -> str:
    thousands = " " if cur in ("HUF", "CZK", "PLN", "SEK", "NOK", "DKK", "RON") else "."
    if cur == "HUF":
        return f"{int(round(value, -2)):,}".replace(",", " ")
    body = f"{value:,.2f}" if decimals else f"{value:,.0f}"
    return (body.replace(",", "T").replace(".", "D")
                .replace("T", thousands).replace("D", ","))


def bank_coverage(bank_all: dict, lang: str) -> tuple[int, list[str]]:
    """Percent of the en key set the language bank covers + the missing key paths.

    A partial bank is the worst case: merged over en it ships a page that is half
    translated — Spanish livebar and menu next to an English hero, form and FAQ."""
    def _walk(node, path=""):
        out = {}
        for k, v in node.items():
            kp = f"{path}.{k}" if path else k
            if isinstance(v, dict):
                out.update(_walk(v, kp))
            else:
                out[kp] = v
        return out
    en = _walk(bank_all.get("en") or {})
    if not en:
        return 100, []
    missing = sorted(set(en) - set(_walk(bank_all.get(lang) or {})))
    return int(round(100 * (len(en) - len(missing)) / len(en))), missing


def merged_bank(bank_all: dict, lang: str) -> dict:
    """deep merge: lang bank wins per key, en fills everything missing
    (thin/partial banks must never crash the fallback path)"""
    def _merge(en: dict, loc: dict) -> dict:
        out = {**en, **loc}
        for k, v in loc.items():
            if isinstance(v, dict) and isinstance(en.get(k), dict):
                out[k] = _merge(en[k], v)
        return out
    _en = bank_all.get("en") or {}
    _src = bank_all.get(lang) or {}
    return _merge(_en, _src) if _src else _en


def build(plan: dict, bank_all: dict) -> dict:
    p = plan["params"]
    lang = p["lang"]
    # never mix two languages on one page: a bank that covers the copy only partly
    # would leave English hero/form/FAQ next to local livebar — refuse and say what to do.
    # A language with no bank at all still falls back to en on purpose (documented policy).
    if lang != "en" and (bank_all.get(lang) or {}):
        cov, missing = bank_coverage(bank_all, lang)
        if cov < 100:
            die(f"language bank '{lang}' covers {cov}% of the copy ({len(missing)} keys missing: "
                f"{', '.join(missing[:5])}, …)\n"
                f"  merged over en it ships half-translated pages (local top strip, English body).\n"
                f"  fix one of: finish resources/content-l10n.json:{lang} · "
                f"run gen_plan.py --with-llm (model writes the whole pack in '{lang}') · "
                f"--lang en for a deliberately English site")
    bank = merged_bank(bank_all, lang)
    cc = (p.get("cc") or "").upper()
    cur = (p.get("currency") or "EUR").upper()
    sym = {"EUR": "€", "CZK": "Kč", "PLN": "zł", "HUF": "Ft", "NOK": "kr",
           "SEK": "kr", "DKK": "kr", "RON": "lei", "BGN": "лв"}.get(cur, cur)
    rate = float(bank_all.get("fx", {}).get(cur, 1))
    dep_num = round(250 * rate)

    def money(value: float, currency: str, decimals: bool = False) -> str:
        body = fmt_amount(value, currency, decimals)
        if currency == "EUR":
            return f"{sym}{body}"
        return f"{body} {sym}" if sym.isalpha() else f"{sym}{body}"

    deposit = money(dep_num, cur)

    city = (p.get("geo") or bank_all.get("capital", {}).get(cc) or
            (bank.get("contacts", {}).get("cities", {}) or {}).get(cc) or "Capital")
    brand = p["brand"]
    dom = p["domain"]
    geo = p.get("geo") or city
    funnel = max(brand.split(), key=len).upper().replace("-", "")
    rng = random.Random(f"{plan.get('seed', 0)}:{dom}:content")

    ctx = {"brand": brand, "brand_lower": brand.lower(), "brand_upper": funnel,
           "domain": dom, "geo": geo, "geo_short": p.get("geo_short") or cc or lang.upper(),
           "city": city, "regulator": (plan.get("regulator") or {}).get("name", ""),
           "deposit": deposit, "cur_sym": sym, "cur_code": cur}

    # contacts (unique across siblings: street + seeded number + seeded phone)
    street = rng.choice(bank["contacts"]["streets"])
    num = rng.randint(12, 189)
    zipc = (f"{rng.randint(10, 99)}-{rng.randint(100, 999)}" if cc == "PL" else
            f"{rng.randint(1000, 9999)}-{rng.randint(100, 999)}" if cc == "PT" else
            f"{rng.randint(10000, 99999)}" if cc in ("IT", "FR", "DE", "ES", "CZ", "SK", "HU",
                                                     "RO", "BG", "GR", "HR", "SI", "LT", "LV",
                                                     "EE", "FI", "SE", "DK", "NO") else
            f"{rng.randint(1000, 9999)}")
    addr = f"{street} {num}, {zipc} {city}"
    prefix = PHONE_CC.get(cc, "+00 ")
    phone = prefix + " ".join(str(rng.randint(100, 999)) for _ in range(2)) + f" {rng.randint(1000, 9999)}"
    email = f"info@{dom}"

    # the ledger mock shows a total plus its parts, so the parts must add up to the
    # headline: a panel that does not sum reads as invented data, not as an illustration
    _bal = round(rng.uniform(8_000, 26_000) * rate, 2)
    _pct = rng.uniform(0.8, 3.6)
    _r1 = round(_bal * rng.uniform(0.45, 0.65), 2)
    _r2 = round(_bal - _r1, 2)

    content = {
        "meta": {
            "title_home": pick(rng, bank["meta"]["title"], ctx),
            "description": pick(rng, bank["meta"]["description"], ctx),
            "keywords": pick(rng, bank["meta"]["keywords"], ctx),
            "og_description": pick(rng, bank["meta"]["og"], ctx),
            "email": email,
            "telephone": phone,
        },
        "hero": {
            "eyebrow": pick(rng, bank["hero"]["eyebrow"], ctx),
            "h1_rest": pick(rng, bank["hero"]["h1_rest"], ctx),
            "h1_accent": pick(rng, bank["hero"]["h1_accent"], ctx),
            "lead": pick(rng, bank["hero"]["lead"], ctx),
            "secondary": pick(rng, bank["hero"]["secondary"], ctx),
            "cta_primary": pick(rng, bank["hero"]["cta_primary"], ctx),
            "cta_secondary": pick(rng, bank["hero"]["cta_secondary"], ctx),
            "stats": [
                {"v": plan["numbers"]["rating"], "l": pick(rng, bank["hero"]["stat_rating"], ctx)},
                {"v": f"{plan['numbers']['users']:,}".replace(",", " "), "l": pick(rng, bank["hero"]["stat_users"], ctx)},
                {"v": f"{plan['numbers']['latency_ms']} ms", "l": pick(rng, bank["hero"]["stat_latency"], ctx)},
            ],
            "device_label": pick(rng, bank["hero"]["device_label"], ctx),
            "device_tag1": pick(rng, bank["hero"].get("device_tag1", "AI"), ctx),
            "device_risk": pick(rng, bank["hero"].get("device_risk", ""), ctx),
            "device_safe": pick(rng, bank["hero"].get("device_safe", ""), ctx),
            "trust_label": pick(rng, bank["hero"].get("trust_label", ""), ctx),
            "device_bal": money(_bal, cur, True),
            "device_bal_v": f"{_bal:.2f}",
            "device_cur": sym,
            "device_cur_code": cur,
            "device_pct": f"{_pct:.1f}",
            "device_aria": pick(rng, bank["hero"]["device_aria"], ctx),
            "device_note": pick(rng, bank["hero"]["device_note"], ctx),
            "device_delta": pick(rng, bank["hero"]["device_delta"],
                                  {**ctx, "pct": f"{_pct:.1f}".replace(".", ",")}),
            "device_rows": [
                {"n": pick(rng, bank["hero"]["asset_1"], ctx), "s": "MIX-GL",
                 "v": money(_r1, cur, True), "vv": f"{_r1:.2f}", "d": f"+{rng.uniform(0.4, 2.2):.1f}%".replace(".", ",")},
                {"n": pick(rng, bank["hero"]["asset_2"], ctx), "s": "BND-EU",
                 "v": money(_r2, cur, True), "vv": f"{_r2:.2f}", "d": f"+{rng.uniform(0.1, 0.9):.1f}%".replace(".", ",")},
            ],
        },
        "bands": deep(rng, {k: bank["bands"][k] for k in
                           ("mid_eyebrow", "mid_h2", "mid_lead", "mid_points", "form_title", "form_sub",
                            "form_consent", "submit_nav", "labels", "placeholders", "submit")}, ctx),
        "ui": deep(rng, bank["ui"], ctx),
        "sections": deep(rng, bank["sections"], ctx),
        "reviews": {
            "eyebrow": pick(rng, bank["reviews"]["eyebrow"], ctx),
            "h2": pick(rng, bank["reviews"]["h2"], ctx),
            "lead": pick(rng, bank["reviews"]["lead"], ctx),
            "items": [],
        },
        "scarcity": deep(rng, bank["scarcity"], ctx),
        "faq": deep(rng, bank["faq"], ctx),
        "office": {"eyebrow": pick(rng, bank["office"].get("eyebrow", "OFFICE"), ctx), "h2": pick(rng, bank["office"]["h2"], ctx),
                   "lead": pick(rng, bank["office"]["lead"], ctx),
                   "addr_label": bank["office"]["addr_label"], "addr": addr,
                   "hours_label": bank["office"]["hours_label"],
                   "hours": rng.choice(bank["contacts"]["hours"]),
                   "contact_label": bank["office"]["contact_label"]},
        "brand_note": deep(rng, bank["brand_note"], ctx),
        "livebar": {**{k: pick(rng, bank["_livebar"][k], ctx) for k in
                        ("crypto", "commod", "session", "bull", "bear", "queue",
                         "wait", "slots", "payouts")},
                    "news": [pick(rng, x, ctx) for x in bank["_livebar"]["news"][:4]]},
    }

    # currency-driven calculator values must match the plan currency
    content["ui"].update({"cur_code": cur, "cur_sym": sym, "min_init": str(dep_num),
                          "calc_cur_note": cur})

    # form_consent must keep the deposit inside <small>
    consent = content["bands"]["form_consent"]
    if "<small>" not in consent:
        consent = consent.replace(deposit, f"<small>{deposit}</small>", 1)
    content["bands"]["form_consent"] = consent

    month_word = {"it": "questo mese", "cs": "tento měsíc", "en": "this month"}.get(lang, "this month")
    quotes = list(bank["reviews"]["quotes"])
    rng.shuffle(quotes)
    roles = list(bank["reviews"]["roles"]); rng.shuffle(roles)
    tenures = list(bank["reviews"]["tenures"]); rng.shuffle(tenures)
    city_bank = (bank.get("contacts", {}).get("cities", {}) or {}).get(cc)
    if isinstance(city_bank, list):
        cities = list(city_bank); rng.shuffle(cities)
    else:
        cities = [city_bank or city]          # no geo city bank → capital only (LLM path fills real ones)
    # three DIFFERENT people: duplicating one persona across the review cards reads as a
    # fake section (identical name, photo and quote three times) — refuse instead
    people = list(plan.get("people") or [])
    photos = list(plan.get("photos") or [])
    if len(people) < 3:
        die(f"plan carries {len(people)} persona(s); the reviews section needs 3 different "
            f"people — regenerate the plan (gen_plan pick_people) or run with --with-llm")
    for i, (name, photo) in enumerate(zip(people[:3], photos[:3])):
        content["reviews"]["items"].append({
            "name": name, "city": cities[i % len(cities)], "role": roles[i % len(roles)],
            "tenure": tenures[i % len(tenures)],
            "gain": f"+{money(rng.uniform(180, 1_900) * rate, cur)} {month_word}",
            "photo": photo, "quote": quotes[i % len(quotes)]})

    for which, key in (("about", "inner_about"), ("tech", "inner_tech"),
                       ("who", "inner_who"), ("contact", "inner_contact"),
                       ("register", "inner_register")):
        node = deep(rng, bank[key], ctx)
        content[key] = node

    content["legal"] = {k: v.format(**ctx) for k, v in bank["legal"].items()}
    content["footer"] = {k: v.format(**ctx) for k, v in bank["footer"].items()}
    content["thanks"] = {k: v.format(**ctx) for k, v in bank["thanks"].items()}

    # sections not present in a bank section set get defaults so any order builds
    for slot in ("intro", "ladder", "features", "steps", "markets", "security", "risk",
                 "streams", "cta", "demo", "glance", "stats", "notes", "facts", "portal"):
        if slot not in content["sections"]:
            content["sections"][slot] = deep(rng, bank["sections"][slot], ctx)

    # newer fragment keys (glance, stats labels) must exist even in packs that were
    # generated before they were introduced — top up from the merged bank
    topup_new_keys(content, bank)

    # every array used by fragments must be long enough
    mins = {"faq.items": 5, "sections.features.cards": 6, "sections.steps.steps": 5,
            "sections.ladder.rows": 4, "sections.markets.rows": 4, "sections.risk.rows": 3,
            "sections.security.cards": 3, "sections.streams.cards": 3,
            "hero.stats": 3, "hero.device_rows": 2, "bands.mid_points": 4,
            "reviews.items": 3, "scarcity.units": 4, "inner_about.blocks": 4,
            "sections.facts.points": 4, "sections.portal.cards": 3,
            "bands.side_stats": 3, "bands.side_labels": 3}
    for path, n in mins.items():
        node = content
        for part in path.split("."):
            node = node[part]
        if isinstance(node, str):
            raise SystemExit(f"min-array path is a string: {path}")
        while len(node) < n:
            if path == "reviews.items":
                die("reviews.items shorter than 3 — cloning a review card is never acceptable")
            node.append(node[len(node) % max(1, len(node))])
    return content


def topup_new_keys(content: dict, bank: dict) -> list[str]:
    """Fill content keys that older packs / partial LLM answers may miss."""
    fixed = []
    stats = content.setdefault("sections", {}).setdefault("stats", {})
    for k in ("rating", "reviews", "orders", "api"):
        if not str(stats.get(k, "")).strip():
            stats[k] = (bank.get("sections", {}).get("stats", {}) or {}).get(k, k)
            fixed.append(f"sections.stats.{k}")
    gl = content.setdefault("sections", {}).setdefault("glance", {})
    for k in ("eyebrow", "h2"):
        if not str(gl.get(k, "")).strip():
            gl[k] = (bank.get("sections", {}).get("glance", {}) or {}).get(k, "")
            fixed.append(f"sections.glance.{k}")
    # facts / portal have their own slots now — never fall back to bands.mid_points.
    # LLM packs may return the arrays filled with empty strings / empty dicts:
    # those pass a naive presence check but render as blank chips and cards.
    def _nonempty(x):
        if x is None: return False          # str(None) == "None" is not content
        if isinstance(x, str): return bool(x.strip())
        if isinstance(x, dict): return any(_nonempty(v) for v in x.values())
        return True

    def _blank(x):
        return x is None or (isinstance(x, str) and not x.strip())
    sec_bank = bank.get("sections", {})
    SCALAR_KEYS = ("eyebrow", "h2", "lead")
    for slot in ("facts", "portal"):
        node = content.setdefault("sections", {}).setdefault(slot, {})
        src = sec_bank.get(slot, {}) or {}
        for k, default in src.items():
            if k in SCALAR_KEYS:
                # bank stores variant LISTS for these (deep() picks one); topup is
                # deterministic and takes the first — a raw list must never reach HTML
                cur = node.get(k, "")
                if isinstance(cur, list):
                    node[k] = cur[0] if cur else ""
                    if node[k] != cur: fixed.append(f"sections.{slot}.{k}")
                    cur = node[k]
                if _blank(cur):
                    node[k] = default[0] if isinstance(default, list) and default else default
                    fixed.append(f"sections.{slot}.{k}")
                continue
            if not isinstance(default, list):
                cur = node.get(k, "")
                if isinstance(cur, list):
                    node[k] = cur[0] if cur else ""
                    if node[k] != cur: fixed.append(f"sections.{slot}.{k}")
                    cur = node[k]
                if _blank(cur):
                    node[k] = default
                    fixed.append(f"sections.{slot}.{k}")
                continue
            # array slot (facts.points / portal.cards): items with no text are
            # replaced item-wise, wholesale when nothing usable remains
            fill = [dict(x) if isinstance(x, dict) else x for x in default]
            cur = node.get(k) or []
            cleaned = [x for x in cur if _nonempty(x)]
            if not cleaned:
                node[k] = fill
                fixed.append(f"sections.{slot}.{k}")
                continue
            out = []
            for i, x in enumerate(cur):
                if _nonempty(x): out.append(x)
                elif i < len(fill): out.append(fill[i])
            while len(out) < len(fill):
                out.append(fill[len(out) % len(fill)])
            node[k] = out[:len(fill)]
            if node[k] != cur:
                fixed.append(f"sections.{slot}.{k}")
    # an empty notes section rendered as blank space on live sites — never again
    nt = content.setdefault("sections", {}).setdefault("notes", {})
    src = sec_bank.get("notes", {}) or {}
    for k in ("lead", "note"):
        if not str(nt.get(k, "")).strip():
            nt[k] = src.get(k, "")
            fixed.append(f"sections.notes.{k}")
    # band-side stats: packs generated before these keys existed would render the
    # filler empty (or worse, leave raw {{c:...}} in the HTML)
    bd = content.setdefault("bands", {})
    bsrc = bank.get("bands", {}) or {}
    for k in ("side_stats", "side_labels"):
        val = bd.get(k) or []
        if not isinstance(val, list) or len([x for x in val if str(x).strip()]) < 3:
            bd[k] = [str(x) for x in (bsrc.get(k) or [])][:3]
            fixed.append(f"bands.{k}")
    if not str(bd.get("side_note", "")).strip():
        bd["side_note"] = str(bsrc.get("side_note", ""))
        fixed.append("bands.side_note")
    # hero device-sim numeric twins: LLM packs carry only the formatted strings;
    # derive data-bal/data-cur/data-pct so the widget JS never parses locales
    h = content.setdefault("hero", {})
    bal = str(h.get("device_bal", "") or "")
    if bal.strip() and not str(h.get("device_bal_v", "") or "").strip():
        m = re.search(r"[\d][\d\s.,]*", bal)
        if m:
            t = re.sub(r"[^\d.,]", "", m.group(0))
            a, b = t.rfind(","), t.rfind(".")
            if a > -1 and b > -1:                       # both seps → last is decimal
                t2 = (t.replace(".", "").replace(",", ".") if a > b
                      else t.replace(",", "").replace(" ", ""))
            elif max(a, b) > -1 and len(t) - max(a, b) - 1 == 3 and re.search(r"[.,]\d{3}$", t) and not re.match(r"^[01][.,]", t):
                t2 = re.sub(r"[.,]", "", t)             # lone sep + 3 digits → thousands
            else:
                t2 = t.replace(",", ".")
            try:
                h["device_bal_v"] = f"{float(t2):.2f}"
                fixed.append("hero.device_bal_v")
            except ValueError:
                pass
        m2 = re.match(r"^(\D+)", bal)
        if m2 and m2.group(1).strip():
            h["device_cur"] = m2.group(1).strip()[:3]
            fixed.append("hero.device_cur")
            code = {"€": "EUR", "Kč": "CZK", "zł": "PLN", "Ft": "HUF",
                    "kr": "SEK", "kr.": "DKK", "lei": "RON", "Kc": "CZK"}.get(
                        m2.group(1).strip(), "EUR")
            h["device_cur_code"] = code
            fixed.append("hero.device_cur_code")
    dlt = str(h.get("device_delta", "") or "")
    if dlt.strip() and not str(h.get("device_pct", "") or "").strip():
        m3 = re.search(r"(\d+[.,]\d+|\d+)\s*%", dlt)
        if m3:
            h["device_pct"] = m3.group(1).replace(",", ".")
            fixed.append("hero.device_pct")
    return fixed


def parse_money(s) -> float | None:
    """'€8.935,91' / '3 014,21 Kč' / '14,933.25 $' → float (locale-agnostic)."""
    t = re.sub(r"[^\d.,]", "", str(s or ""))
    if not t:
        return None
    m = re.search(r"[.,](\d{1,2})$", t)
    try:
        if m:
            body = t[: -len(m.group(0))].replace(".", "").replace(",", "")
            return float(f"{body or '0'}.{m.group(1)}")
        return float(t.replace(".", "").replace(",", ""))
    except ValueError:
        return None


def reconcile_ledger(content: dict) -> list[str]:
    """Hero ledger mock: row 1 + row 2 must equal the headline balance.

    Only the numbers of the second row are rewritten (labels stay the model's); the LLM
    path asks the model for a repair pass first and calls this as the last resort so a
    single arithmetic slip never dumps an otherwise good pack.
    """
    h = content.get("hero") or {}
    rows = [r for r in (h.get("device_rows") or []) if isinstance(r, dict)]
    if len(rows) < 2:
        return []
    total = parse_money(h.get("device_bal_v") or h.get("device_bal") or "")
    first = parse_money(rows[0].get("vv") or rows[0].get("v") or "")
    if total is None or first is None or not 0 < first < total:
        return []
    rest = round(total - first, 2)
    cur_code = str(h.get("device_cur_code") or "EUR")
    cur_sym = str(h.get("device_cur") or "")
    rows[1]["vv"] = f"{rest:.2f}"
    body = fmt_amount(rest, cur_code, True)
    if cur_code == "EUR":
        rows[1]["v"] = f"{cur_sym or '€'}{body}"
    elif cur_sym.isalpha():
        rows[1]["v"] = f"{body} {cur_sym}"
    else:
        rows[1]["v"] = f"{cur_sym}{body}"
    return ["hero.device_rows.1"]


def main():
    ap = argparse.ArgumentParser(description="plan → content pack")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--source-lang", default="",
                    help="build the pack in this bank language instead of the plan language "
                         "(master English copy for tools/localize.py)")
    a = ap.parse_args()
    plan = json.loads(pathlib.Path(a.plan).read_text(encoding="utf-8"))
    if a.source_lang:
        plan = json.loads(json.dumps(plan))
        plan["params"]["lang"] = a.source_lang
    dom = plan["params"]["domain"]
    out = pathlib.Path(a.out) if a.out else ROOT / "content" / f"{dom}-content.json"
    if out.exists() and not a.force:
        pack = json.loads(out.read_text(encoding="utf-8"))
        bank_all = json.loads(L10N.read_text(encoding="utf-8"))
        bank = merged_bank(bank_all, plan["params"]["lang"])
        fixed = topup_new_keys(pack, bank)
        if fixed:
            out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"· content kept, topped up missing keys: {', '.join(fixed)}")
        else:
            print(f"· content exists, kept: {out.relative_to(ROOT)} (use --force to rewrite)")
        return
    bank_all = json.loads(L10N.read_text(encoding="utf-8"))
    if plan["params"]["lang"] not in bank_all:
        print(f"! no {plan['params']['lang']} bank — falling back to en copy")
    content = build(plan, bank_all)

    sys.path.insert(0, str(ROOT))
    import assemble
    errs = assemble.validate_content(content, plan, strict=True)
    if errs:
        die("; ".join(errs))
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
    words = len(re.findall(r"\w+", json.dumps(content, ensure_ascii=False)))
    print(f"CONTENT OK -> {out if not out.is_relative_to(ROOT) else out.relative_to(ROOT)}  ({words} words, {plan['params']['lang']}, deposit {content['bands']['form_consent'].count('<small>')}x small)")


if __name__ == "__main__":
    main()
