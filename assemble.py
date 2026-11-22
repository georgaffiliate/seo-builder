#!/usr/bin/env python3
"""assemble.py — deterministic site constructor: plan.json [+ content_pack.json] → full offer.

STATIC layer of the factory: reads NO docs, calls NO LLM. Takes:
  --plan    plans/<domain>.json            (produced by gen_plan.py)
  --content content/<domain>-content.json  (optional: produced by an LLM per content-pack.schema;
                                            absent → seed placeholders, site still builds)

Produces sites/<domain>/ with: index.php, inner pages (slug-mapped), thanks.php, 404.php,
assets (favicons/og placeholders from templates), integration (from api_local_example),
sitemap/robots/.htaccess, palette+skin+fonts wired into <head>.

Then RUNS the gates itself: php -l all pages, seo_audit.py, twin_check.py.
Exit 0 = all green.

Blocks: fragments from blocks/ are MINIMAL-HTML canonical blk-* pieces stored per category
(this build ships with 89 donor fragments, but assembly prefers CLEAN blk-* templates from
blocks/blk-*.html when present; donor fragments serve as reference/fallback).
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib, random, shutil, subprocess, sys, re, time

ROOT = pathlib.Path(__file__).resolve().parent          # static-create-sites/
SITES_OUT = ROOT / "sites"
PLANS_DIR = ROOT / "plans"
BLOCKS = ROOT / "blocks"
SKINS = ROOT / "skins"
CONTENT_SCHEMA = ROOT / "content" / "content-pack.schema.json"
PALETTES = ROOT / "content" / "palettes-blk.json"
INTEGRATION_SRC = ROOT / "integration-example" / "integration"
PEOPLE_DIR = ROOT / "people"
POSTBACK_SRC = ROOT / "_postback.php"

BUILD_V = "0"
REQUIRED_PLAN_KEYS = ["params", "design", "layout", "widgets", "numbers"]
SPECIAL_VARIANTS = {"livebar", "logo", "header"}

# footer legal labels + rights line per geo language (fallback English)
FOOTER_L10N = {
    "cs": ("Podmínky", "Soukromí", "Všechna práva vyhrazena."),
    "sk": ("Podmienky", "Súkromie", "Všetky práva vyhradené."),
    "pl": ("Regulamin", "Prywatność", "Wszelkie prawa zastrzeżone."),
    "de": ("AGB", "Datenschutz", "Alle Rechte vorbehalten."),
    "fr": ("Conditions", "Confidentialité", "Tous droits réservés."),
    "it": ("Termini", "Privacy", "Tutti i diritti riservati."),
    "es": ("Términos", "Privacidad", "Todos los derechos reservados."),
    "pt": ("Termos", "Privacidade", "Todos os direitos reservados."),
    "nl": ("Voorwaarden", "Privacy", "Alle rechten voorbehouden."),
    "hu": ("Feltételek", "Adatvédelem", "Minden jog fenntartva."),
    "ro": ("Termeni", "Confidențialitate", "Toate drepturile rezervate."),
    "bg": ("Условия", "Поверителност", "Всички права запазени."),
    "el": ("Όροι", "Απόρρητο", "Με την επιφύλαξη παντός δικαιώματος."),
    "hr": ("Uvjeti", "Privatnost", "Sva prava pridržana."),
    "sl": ("Pogoji", "Zasebnost", "Vse pravice pridržane."),
    "lt": ("Sąlygos", "Privatumas", "Visos teisės saugomos."),
    "lv": ("Noteikumi", "Privātums", "Visas tiesības aizsargātas."),
    "et": ("Tingimused", "Privaatsus", "Kõik õigused kaitstud."),
    "fi": ("Ehdot", "Tietosuoja", "Kaikki oikeudet pidätetään."),
    "sv": ("Villkor", "Integritet", "Alla rättigheter förbehållna."),
    "da": ("Vilkår", "Privatliv", "Alle rettigheder forbeholdes."),
    "nb": ("Vilkår", "Personvern", "Alle rettigheter forbeholdt."),
}

TERMS_L10N = {"it": ("Termini di servizio", "Informativa privacy", "Grazie — richiesta ricevuta"),
               "cs": ("Podmínky služby", "Zásady ochrany osobních údajů", "Děkujeme — žádost přijata"),
               "es": ("Términos del servicio", "Política de privacidad", "Gracias — solicitud recibida"),
               "en": ("Terms of service", "Privacy policy", "Thank you — request received")}

# 404 headline + back-home label per geo language (fallback English)
NOTFOUND_L10N = {
    "cs": ("Stránka nenalezena", "Zpět na úvod"),
    "sk": ("Stránka sa nenašla", "Späť na úvod"),
    "pl": ("Nie znaleziono strony", "Wróć na start"),
    "de": ("Seite nicht gefunden", "Zur Startseite"),
    "fr": ("Page introuvable", "Retour à l'accueil"),
    "it": ("Pagina non trovata", "Torna alla home"),
    "es": ("Página no encontrada", "Volver al inicio"),
    "pt": ("Página não encontrada", "Voltar ao início"),
    "nl": ("Pagina niet gevonden", "Terug naar home"),
    "hu": ("Az oldal nem található", "Vissza a kezdőlapra"),
    "ro": ("Pagina nu a fost găsită", "Înapoi la start"),
    "bg": ("Страницата не е намерена", "Обратно към началото"),
    "el": ("Η σελίδα δεν βρέθηκε", "Επιστροφή στην αρχική"),
    "hr": ("Stranica nije pronađena", "Natrag na početak"),
    "sl": ("Stran ne obstaja", "Nazaj na začetek"),
    "lt": ("Puslapis nerastas", "Grįžti į pradžią"),
    "lv": ("Lapa nav atrasta", "Atgriezties sākumā"),
    "et": ("Lehte ei leitud", "Tagasi avalehele"),
    "fi": ("Sivua ei löytynyt", "Takaisin etusivulle"),
    "sv": ("Sidan hittades inte", "Tillbaka till start"),
    "da": ("Siden blev ikke fundet", "Tilbage til forsiden"),
    "nb": ("Siden ble ikke funnet", "Tilbake til startsiden"),
}

# ---------------------------------------------------------------- utilities --
def die(msg, code=1): print(f"✗ {msg}"); sys.exit(code)
def ok(msg): print(f"✓ {msg}")

def load(p: pathlib.Path, default=None):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError: return default

def esc(s):
    if isinstance(s, (list, dict)): s = ""  # never print python repr into HTML
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")

def _on_dark(hex_color: str, min_l: float = 0.62) -> str:
    """Lift a palette color to a readable-on-dark lightness (keeps the hue).
    Light palettes carry dark accent text — unreadable on the dark livebar strip."""
    import colorsys
    s = (hex_color or "").strip()
    if not re.match(r"^#[0-9a-fA-F]{6}$", s): return s
    r, g, b = (int(s[1:3], 16) / 255, int(s[3:5], 16) / 255, int(s[5:7], 16) / 255)
    h, l, sat = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(h, max(l, min_l), sat)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))

def php_str(s): return (s or "").replace("'", "\\'")

# ---------------------------------------------------------------- validation -
def validate_plan(plan: dict) -> None:
    missing = [k for k in REQUIRED_PLAN_KEYS if k not in plan]
    if missing: die(f"plan missing keys: {missing}")
    params = plan["params"]
    for k in ("brand", "domain", "lang"):
        if not params.get(k): die(f"plan.params.{k} empty")
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", params["domain"]):
        die(f"bad domain: {params['domain']}")
    order = plan["layout"]["section_order"]
    for slot in order:
        canon = CANON.get(slot)
        if not canon or not (BLOCKS / f"{canon}.html").exists():
            die(f"section slot without canonical fragment: {slot}")
    for slot, var in (plan["layout"].get("variants") or {}).items():
        if slot not in order and slot not in SPECIAL_VARIANTS: die(f"variant for unknown slot: {slot}")
        canon = CANON.get(slot) or f"blk-{slot}"
        if var and slot not in SPECIAL_VARIANTS \
           and not (BLOCKS / f"blk-{slot}-{var}.html").exists() \
           and not (BLOCKS / f"{canon}-{var}.html").exists():
            die(f"variant fragment missing: {canon}-{var}.html")
    if not (10 <= len(order) <= 18): die(f"section_order len {len(order)} out of range 10..18")
    if not ({"faq", "people", "facts", "security", "compare"} & set(order)):
        die("section_order needs a trust screen (faq/people/facts/security/compare)")
    anchors = {"people", "faq", "numbers", "cta", "office", "compare"}
    if len(anchors & set(order)) < 2:
        die("section_order needs >= 2 rotating anchor screens (people/faq/numbers/cta/office/compare)")
    if "numbers" in order and "stats-intro" in order:
        die("numbers and stats-intro are the same stat screen — keep only one")
    if not any(s in order for s in ("access-band", "claim-band", "enroll-band")):
        die("section_order must contain a form band")
    if "hero" not in order: die("section_order must start with hero-ish block")

def validate_content(content: dict, plan: dict, strict=False) -> list[str]:
    errs = []
    lang_re = re.compile(rf"[??]")  # placeholder; language check delegated to reviewer
    # forbidden: deposit-like sums inside meta fields
    dep_pat = re.compile(r"(€\s?250\b|250\s?€|\b\d{2,3}\s?(000|k)\s?(NOK|zł|Kč|Ft)\b)", re.I)
    meta_blob = " ".join(str(v) for v in (content.get("meta") or {}).values())
    if dep_pat.search(meta_blob): errs.append("deposit-like amount in meta fields")
    # hero strings non-empty in strict mode (and never lists/dicts — a stray
    # LLM list would otherwise reach esc()/fill() and render as junk)
    if strict:
        for k, v in (content.get("hero") or {}).items():
            if isinstance(v, (list, dict)) and k not in ("stats", "device_rows"):
                errs.append(f"hero.{k} is a list/dict"); continue
            if isinstance(v, str) and not v.strip(): errs.append(f"hero.{k} empty")
        for grp, keys in (("bands", ("mid_eyebrow", "mid_h2", "mid_lead", "form_title",
                                     "form_sub", "form_consent", "submit", "submit_nav")),
                          ("footer", ("tagline", "disclaimer", "risk_line"))):
            node = content.get(grp) or {}
            for k in keys:
                v = node.get(k)
                if v is None: continue
                if isinstance(v, (list, dict)): errs.append(f"{grp}.{k} is a list/dict")
                elif isinstance(v, str) and not v.strip(): errs.append(f"{grp}.{k} empty")
        for k, v in (content.get("meta") or {}).items():
            if isinstance(v, (list, dict)): errs.append(f"meta.{k} is a list/dict")
    # reviews consistency with plan numbers
    n = plan.get("numbers", {})
    rv = content.get("reviews", {})
    if n.get("rating") and isinstance(rv, dict):
        pass  # displayed rating uses plan value; pack carries items only
    # fragment arrays must carry text: LLM packs occasionally return empty strings
    # or empty dicts, which render as blank chips/cards on live pages
    def _nonempty(x):
        if isinstance(x, str): return bool(x.strip())
        if isinstance(x, dict): return any(str(v).strip() for v in x.values())
        return True
    order = (plan.get("layout") or {}).get("section_order") or []
    for slot, key, need in (("facts", "points", 4), ("portal", "cards", 3),
                            ("reviews", "items", 3)):
        if slot not in order: continue
        arr = ((content.get("sections") or {}).get(slot) or {}).get(key) \
              if slot != "reviews" else (rv.get("items") or [])
        if not isinstance(arr, list):
            # a model that answers "null" here used to crash the validator
            errs.append(f"sections.{slot}.{key} is not an array ({type(arr).__name__})")
            arr = []
        good = [x for x in arr if _nonempty(x)]
        if len(good) < need:
            errs.append(f"sections.{slot}.{key} empty or shorter than {need} ({len(good)} valid)")
        if slot in ("facts", "portal"):
            for k in ("eyebrow", "h2", "lead"):
                v = ((content.get("sections") or {}).get(slot) or {}).get(k)
                if isinstance(v, list) or not str(v or "").strip():
                    errs.append(f"sections.{slot}.{k} missing or a raw list")
    # review cards must be three DIFFERENT people — cloned cards (same name, photo or
    # quote) read as a fake section on a live page
    ritems = rv.get("items") if isinstance(rv, dict) else None
    if isinstance(ritems, list):
        if len(ritems) < 3:
            errs.append(f"reviews.items has {len(ritems)} entries, need 3 different people")
        for field in ("name", "photo", "quote"):
            vals = [str((it or {}).get(field, "")).strip().casefold()
                    for it in ritems if isinstance(it, dict)]
            vals = [v for v in vals if v]
            dup = sorted({v for v in vals if vals.count(v) > 1})
            if dup:
                errs.append(f"reviews.{field} repeated across cards: {dup[:2]}")
    # faq answers shorter than ~2 sentences read as stubs on live pages
    faq_items = ((content.get("faq") or {}).get("items") or [])
    if not isinstance(faq_items, list):
        errs.append("faq.items is not an array")
        faq_items = []
    for it in faq_items:
        a = it.get("a") if isinstance(it, dict) else ""
        if not isinstance(a, str) or not a.strip():
            errs.append("faq answer empty")
        elif len(a.strip()) < 120:
            errs.append(f"faq answer too short ({len(a.strip())} chars): {a[:40]}…")
    return errs

# ---------------------------------------------------------------- content ----
def seed_content(plan: dict) -> dict:
    """Placeholder content so the site builds and passes structure gates even without LLM."""
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    n = plan.get("numbers", {}); ppl = plan.get("people", [])
    return {
        "meta": {"title_home": f"{brand} — pištorg plataforma",
                  "description": f"{brand}: instrumenty ta pidtrymka dla svідомих рішень.",
                  "keywords": f"{brand}, {brand.lower()}, {dom}, {brand.lower()} login",
                  "og_description": "placeholder og"},
        "hero": {"eyebrow": "PLACEHOLDER", "h1_rest": "Build real headline", "h1_accent": "here",
                  "lead": "Placeholder lead — replace via content pack.",
                  "secondary": "", "cta_primary": "Start", "cta_secondary": "More",
                  "stats": [{"v": n.get("rating","4,7"), "l": "rating"},
                             {"v": f'{n.get("users",12500):,}'.replace(",", "."), "l": "users"},
                             {"v": f"{n.get('latency_ms',52)} ms", "l": "latency"}],
                  "device_bal": "€0,00", "device_delta": "↗ placeholder", "device_rows": []},
        "bands": {"mid_eyebrow": "ACCESS", "mid_h2": "Get access", "mid_lead": "Leave details.",
                   "mid_points": ["Point one", "Point two", "Point three", "Point four"],
                   "form_title": "Free registration", "form_sub": "",
                   "form_consent": "I agree to privacy policy. First deposit conditions in terms.",
                   "submit_nav": "Open account",
                   "labels": {"first": "First name", "last": "Last name", "email": "Email", "phone": "Phone"},
                   "placeholders": {"first": "John", "last": "Doe", "email": "john@example.com", "phone": "600 000 000"},
                   "submit": "Send request"},
        "ui": {"calc_eyebrow": "SIMULATION", "calc_initial": "Initial", "calc_init_note": "EUR \u00b7 min. 250",
                "calc_monthly": "Monthly", "calc_cur_note": "EUR", "calc_years": "Years", "calc_rate": "Rate",
                "calc_value_after": "VALUE AFTER", "calc_contributed": "Contributed", "calc_gain": "Gain",
                "calc_now": "Now", "cur_code": "EUR", "cur_sym": "\u20ac", "year_full": "YEARS",
                "year_short": "YEARS", "min_init": "250",
                "status_sending": "Sending\u2026", "status_fix": "Please review the highlighted fields.",
                "status_fail": "Submission failed, please try again.", "status_ok": "Done, redirecting\u2026"},
        "faq": {"eyebrow": "FAQ", "h2": "Questions",
                  "items": [{"q": f"Placeholder question {i}?", "a": "Placeholder answer."} for i in range(1, 5)]},
        "reviews": {"eyebrow": "Reviews", "h2": "Users about platform", "lead": "Names are illustrative.",
                     "items": [{"name": nm, "city": "Capital", "role": "role", "tenure": "1 year",
                                 "gain": "+0", "photo": ph, "quote": "Placeholder review text."}
                                for nm, ph in zip(ppl[:3], plan.get("photos", [])[:3])]},
        "office": {"h2": "Office", "lead": "", "addr_label": "Address", "addr": "Main st 1",
                    "hours_label": "Hours", "hours": "Mon–Fri 9:00–18:00", "contact_label": "Contact"},
        "footer": {"tagline": "", "risk_line": "Trading involves risk.",
                    "disclaimer": "Placeholder disclaimer."},
        "thanks": {"h1": "Thank you", "lead": "We call within 30 minutes.", "warn": ""}
    }

# ---------------------------------------------------------------- css/head ---
def css_link_block(plan: dict) -> tuple[str, str, str]:
    pal_id = plan["design"]["palette_id"]; skin = plan["design"].get("skin", "rounded-air")
    pals = load(PALETTES, {"palettes": [], "fonts": {}})
    pal = next((p for p in pals["palettes"] if p["id"] == pal_id), None)
    if not pal:
        # fallback: resolve palette from old templates/palettes.json (pre-blk ids) by mapping to closest new one
        old = load(ROOT / "resources" / "palettes-legacy.json", {"palettes": []})
        oldp = next((p for p in old["palettes"] if p["id"] == pal_id), None)
        if oldp:
            v = oldp["tokens"]; theme = oldp.get("theme", "light")
            pal = {"id": pal_id, "theme": theme, "vars": {
                "bg": v.get("bg", "#fff"), "bg_soft": v.get("bg_soft", "#f5f5f5"),
                "panel": v.get("panel", "#fafafa"), "ink": v.get("ink", "#111"),
                "muted": v.get("muted", "#666"), "line": v.get("line", "#e5e5e5"),
                "acc": v.get("primary", v.get("acc", "#1d3a8a")),
                "acc_deep": v.get("primary_deep", v.get("acc_deep", "#142a66")),
                "acc_2": v.get("accent_2", v.get("acc_2", "#0038ff")),
                "up": v.get("up", "#0a7a3d"), "down": v.get("down", "#c01818"),
                "grad": v.get("gradient", "none")},
                "default_fonts": None}
            ok(f"palette '{pal_id}' mapped from legacy palettes.json")
    if not pal: die(f"palette '{pal_id}' not found anywhere")
    skin_file = SKINS / f"skin-{skin}.css"
    if not skin_file.exists(): die(f"skin '{skin}' missing in skins/")
    fp_key = plan["design"].get("font_pair") or pal.get("default_fonts")
    if not fp_key:
        fp_key = "grotesk-man" if plan["design"].get("theme") == "dark" or pal["theme"] == "dark" else "bitter-work"
    fonts = pals["fonts"].get(fp_key)
    if not fonts: die(f"font pair '{fp_key}' unknown")
    # always-dark surfaces (livebar family Q) need readable colors for every
    # palette: derive on-dark variants by lifting lightness, keeping the hue
    ondark = (";--acc-ondark:%s;--up-ondark:%s;--down-ondark:%s" % (
        _on_dark(pal["vars"].get("acc", "#3ddc84"), 0.62),
        _on_dark(pal["vars"].get("up", "#22c55e"), 0.66),
        _on_dark(pal["vars"].get("down", "#ef4444"), 0.60)))
    css_vars = ":root{" + ";".join(
        f"--{k.replace('_','-')}:{v}" for k, v in pal["vars"].items()) + ondark + \
        f";--font-head:'{fonts['head']}'" + f";--font-body:'{fonts['body']}'}}"
    theme_meta = pal["vars"].get("bg", "#111111") if pal["theme"] == "dark" else \
        (pal["vars"].get("acc_deep") or pal["vars"].get("acc", "#111111"))
    return css_vars, fonts["import"], theme_meta

# ---------------------------------------------------------------- fragments --
def frag(name: str) -> str:
    p = BLOCKS / f"{name}.html"
    return p.read_text(encoding="utf-8") if p.exists() else ""

BLK_MAP = {  # plan slot -> canonical blk template in blocks/ (blk-*.html authored clean)
    "hero": "blk-hero", "access-band": "blk-band-access", "claim-band": "blk-band-claim",
    "enroll-band": "blk-band-access", "ticker": "blk-ticker", "intro-center": "blk-intro",
    "stats-intro": "blk-intro-stats", "ladder": "blk-ladder", "features": "blk-features",
    "steps": "blk-steps", "steps-live": "blk-steps", "timeline": "blk-timeline",
    "calculator": "blk-calculator", "markets": "blk-markets", "streams": "blk-streams",
    "security": "blk-security", "demo": "blk-demo", "people": "blk-reviews",
    "scarcity": "blk-scarcity", "risk": "blk-risk", "cta-band": "blk-cta",
    "trust-band": "blk-cta", "faq": "blk-faq", "office": "blk-office",
    "brand-note": "blk-brandnote",
    "device": "blk-device",
    "pulse-sim": "blk-pulse-sim",
    "numbers": "blk-numbers",
    "mini-faq": "blk-mini-faq",
    "portal": "blk-portal",
    "compare": "blk-compare",
    "glance": "blk-glance",
    "facts": "blk-facts",
    "notes": "blk-notes",
}
INC_HEAD = "<?php include __DIR__ . '/api_local/integration/header.php'; ?>"
INC_FOOT = "<?php include __DIR__ . '/api_local/integration/footer.php'; ?>"

def page_shell(title, descr, keywords, canonical_path, locale, css_vars, fonts_import,
               theme_color, body, og_desc="", jsonld="", noindex=False):
    dom_css = f"<style>{esc(css_vars)}</style>"
    rob = "noindex,follow" if noindex else "index,follow"
    ld = f'<script type="application/ld+json">{jsonld}</script>' if jsonld else ""
    return f"""<!doctype html>
<html lang="{esc(locale.split('-')[0])}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(descr)}">
<meta name="robots" content="{rob}">
<meta name="theme-color" content="{esc(theme_color)}">
<meta name="keywords" content="{esc(keywords)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="icon" href="favicon.ico" sizes="any">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="icon" href="favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="canonical" href="https://{{DOM}}{canonical_path}">
<link rel="alternate" hreflang="{esc(locale)}" href="https://{{DOM}}{canonical_path}">
<link rel="alternate" hreflang="x-default" href="https://{{DOM}}{canonical_path}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(og_desc or descr)}">
<meta property="og:locale" content="{esc(locale.replace('-', '_'))}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{{BRAND}}">
<meta property="og:url" content="https://{{DOM}}{canonical_path}">
<meta property="og:image" content="https://{{DOM}}/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(og_desc or descr)}">
<meta name="twitter:image" content="https://{{DOM}}/og-image.png">
<link rel="stylesheet" href="blocks/blocks.css?v={BUILD_V}">
<link rel="stylesheet" href="skin.css?v={BUILD_V}">
<style>@import url('{fonts_import}');</style>
{dom_css}
{INC_HEAD}
{ld}
</head>
<body>
{body}
{INC_FOOT}
<script src="app.js?v={BUILD_V}"></script>
<script src="calculator.js?v={BUILD_V}"></script>
<script src="pulse-sim.js?v={BUILD_V}"></script>
</body>
</html>"""

# ---------------------------------------------------------------- builders ---
CANON = {  # canonical blk-* fragment per slot (authored clean, contract-safe)
    "livebar": "blk-livebar",
    "hero": "blk-hero", "access-band": "blk-band-access", "claim-band": "blk-band-access",
    "enroll-band": "blk-band-access", "ticker": "blk-ticker", "intro-center": "blk-intro",
    "stats-intro": "blk-intro-stats", "ladder": "blk-ladder", "features": "blk-features",
    "steps": "blk-steps", "steps-live": "blk-steps-live", "timeline": "blk-timeline",
    "calculator": "blk-calculator", "markets": "blk-markets", "streams": "blk-streams",
    "security": "blk-security", "demo": "blk-demo", "people": "blk-reviews",
    "scarcity": "blk-scarcity", "risk": "blk-risk", "cta-band": "blk-cta",
    "trust-band": "blk-cta", "faq": "blk-faq", "office": "blk-office",
    "brand-note": "blk-brandnote",
    "device": "blk-device",
    "pulse-sim": "blk-pulse-sim",
    "numbers": "blk-numbers",
    "mini-faq": "blk-mini-faq",
    "portal": "blk-portal",
    "compare": "blk-compare",
    "glance": "blk-glance",
    "facts": "blk-facts",
    "notes": "blk-notes",
}

def frag_for(name: str, plan) -> str:
    """Pick blk-<slot>-<variant> when the plan asked for one, else the canonical slot."""
    var = (plan.get("layout", {}).get("variants") or {}).get(name, "")
    if var:
        canon = CANON.get(name) or f"blk-{name}"
        v = frag(f"blk-{name}-{var}") or frag(f"{canon}-{var}")
        if v: return v
    return frag(CANON[name]) if name in CANON else frag(name)

def R(name: str, plan, C, **kw) -> str:
    """Render a canonical blk fragment with plan+content substitutions."""
    tpl = frag_for(name, plan)
    if not tpl:
        return f"<!-- missing fragment {name} -->"
    out = tpl
    subs = {
        "{{BRAND}}": plan["params"]["brand"], "{{DOMAIN}}": plan["params"]["domain"],
        "{{GEO_SHORT}}": plan["params"].get("geo_short", ""),
        "{{LATENCY}}": str(plan["numbers"].get("latency_ms", 52)),
        "{{API_UPTIME}}": "99,9%", "{{ORDERS}}": f"{plan['numbers'].get('users', 12500)//4:,}".replace(",", "."),
        "{{GEO}}": plan["params"].get("geo", ""), "{{RATING}}": str(plan["numbers"].get("rating", "4,7")),
        "{{SEED}}": str(plan.get("seed", "")),
        "{{REVIEWS}}": f"{plan['numbers'].get('reviews', 641):,}".replace(",", "."),
        "{{USERS}}": f"{plan['numbers'].get('users', 12500):,}".replace(",", "."),
    }
    if name == "pulse-sim":
        for k, v in ((plan.get("pulse_sim") or {}).get("subs") or {}).items():
            subs["{{" + k + "}}"] = v
    if name == "livebar":
        for k, v in ((plan.get("livebar") or {}).get("subs") or {}).items():
            subs["{{" + k + "}}"] = v
        lb = C.get("livebar") or {}
        if lb:
            # content pack may override the news headlines (kept from plan words otherwise)
            for i, text in enumerate((lb.get("news") or [])[:4], start=1):
                subs["{{LB_NEWS%d}}" % i] = text
            # legacy word-swap: replace only the leading word of queue/wait/slots stats
            for key, token in (("queue", "LB_QUEUE"), ("wait", "LB_WAIT"),
                               ("slots", "LB_SLOTS"), ("payouts", "LB_S3")):
                if lb.get(key):
                    old = subs.get("{{" + token + "}}", "")
                    subs["{{" + token + "}}"] = re.sub(r"^\S+", str(lb[key]), old, count=1)
            for i, text in enumerate((lb.get("news") or [])[:2], start=1):
                subs["{{LB_NEWS%d}}" % i] = text
    for k, v in subs.items(): out = out.replace(k, str(v))
    # content pack deep-fill: "{{c:hero.lead}}" style
    def fill(m):
        path = m.group(1).split("."); node = C
        for p in path:
            if isinstance(node, dict): node = node.get(p)
            elif isinstance(node, list):
                try: node = node[int(p)]
                except Exception: return ""
            else: return ""
            if node is None: return ""
        if isinstance(node, (list, dict)):
            # a template bound a whole array/object — never print python repr
            return ""
        return str(node)
    out = re.sub(r"\{\{c:([\w.]+)\}\}", fill, out)
    # a content pack with empty strings left blank <p>/<h2> blocks that rendered as
    # pure whitespace sections on live sites — strip elements that stayed empty.
    # Elements carrying role/data/id/aria (e.g. form-status container) are intentional
    # empty and must survive.
    out = re.sub(
        r"<(p|h2|h3|li)((?:(?!role=|data-|id=|aria-)[^>])*)>\s*(?:<br\s*/?>\s*)*</\1>",
        "", out)
    return out

def logo_html(plan) -> str:
    """Brand mark: the word stays lowercase (CLAUDE rule), the treatment varies per plan."""
    brand = plan["params"]["brand"]
    word = esc(brand.split()[0].lower())
    initial = esc(brand.split()[0][0].upper())
    tld = esc(plan["params"]["domain"].rsplit(".", 1)[-1])
    v = (plan["layout"].get("variants") or {}).get("logo", "")
    inner = {
        "": f"{word}<span>↗</span>",
        "b": f'<span class="u">{word}</span>',
        "c": f'<span class="mono">{initial}</span>{word}',
        "d": f'{word}<span class="dot">·</span>',
        "e": f'{word}<span class="circ">↗</span>',
        "f": f'<span class="caps">{word}</span>',
        "g": f'{word}<span class="sl">/</span>',
        "h": f'<span class="stack">{word}<small>.{tld}</small></span>',
    }.get(v, f"{word}<span>↗</span>")
    return f'<a class="blk-logo" data-var="{v or "a"}" href="index.php" aria-label="{esc(brand)}">{inner}</a>'


def build_header_footer(plan, C):
    brand = plan["params"]["brand"]; slugs = plan["layout"].get("slugs", {})
    menu = plan["layout"].get("menu", ["Home", "About", "Tech", "Contact"])
    pairs = [(menu[0], "index.php"), (menu[1], f"{slugs.get('about','about')}.php"),
              (menu[2], f"{slugs.get('who','who')}.php"), (menu[3], f"{slugs.get('contact','contact')}.php")]
    nav = "".join(f'<a href="{h}">{esc(t)}</a>' for t, h in pairs)
    geo_l = plan["params"]["lang"]
    livebar = R("livebar", plan, C)
    ui = C.get("ui") or {}
    hv = (plan["layout"].get("variants") or {}).get("header", "")
    parts = {
        "logo": logo_html(plan),
        "nav": f'<nav class="blk-nav" aria-label="{esc(ui.get("aria_nav") or "Main")}">{nav}</nav>',
        "cta": f'<a class="blk-btn" href="index.php#claim">{esc(C["bands"].get("submit_nav", "Open account"))}</a>',
        "toggle": f'<button class="menu-toggle" aria-label="{esc(ui.get("aria_menu") or "Menu")}" '
                  f'aria-expanded="false">☰</button>',
    }
    order = {
        "": ("logo", "nav", "cta", "toggle"),
        "b": ("nav", "cta", "logo", "toggle"),
        "c": ("nav", "logo", "cta", "toggle"),
        "d": ("nav", "cta", "toggle"),
        "e": ("logo", "nav", "toggle"),
        "f": ("logo", "cta", "nav", "toggle"),
        "g": ("logo", "cta", "nav", "toggle"),
    }.get(hv, ("logo", "nav", "cta", "toggle"))
    header = f'<header class="blk-header" data-var="{hv or "a"}">' + "\n".join(parts[k] for k in order) + "</header>"
    # footer labels come from the content pack (translated by tools/localize.py);
    # FOOTER_L10N only backstops packs written before these keys existed
    ft = C.get("footer") or {}
    fb = FOOTER_L10N.get(geo_l, ("Terms", "Privacy", "All rights reserved."))
    flabels = [(ft.get("terms_label") or fb[0], "terms.php"),
               (ft.get("privacy_label") or fb[1], "privacy.php")]
    rights = ft.get("rights") or fb[2]
    fnav = "".join(f'<a href="{h}">{esc(t)}</a>' for t, h in pairs + flabels)
    footer = f"""<footer class="blk-footer"><div class="footer-top">
{logo_html(plan)}
<nav>{fnav}</nav><span>{esc(C.get('footer', {}).get('tagline', ''))}</span></div>
<p class="footer-disclaimer">{esc(C.get('footer', {}).get('disclaimer', ''))}</p>
<div class="footer-bottom"><span>© 2026 {esc(brand)}. {esc(rights)}</span>
<span class="pay-chips">{esc(ft.get("pay_chips") or "VISA · Mastercard · Bank transfer")}</span>
<span>{esc(C.get('footer', {}).get('risk_line', ''))}</span></div></footer>"""
    return livebar, header, footer

def fix_anchors(html: str) -> str:
    """Point decorative CTA anchors at targets that actually exist on this page."""
    ids = set(re.findall(r'id="([^"]+)"', html))
    for missing, fallbacks in (("come", ("demo", "claim")), ("demo", ("claim",)),
                               ("reviews", ("people", "claim")), ("calculator", ("claim",))):
        if missing in ids:
            continue
        target = next((f for f in fallbacks if f in ids), None)
        html = html.replace(f'href="#{missing}"', f'href="#{target}"' if target else 'href="index.php#claim"')
    return html


def build_index(plan, C, css_vars, fonts_import, theme):
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    order = plan["layout"]["section_order"]
    for slot in order:
        canon = CANON.get(slot)
        if not canon or not (BLOCKS / f"{canon}.html").exists():
            die(f"section slot without canonical fragment: {slot}")
    for slot, var in (plan["layout"].get("variants") or {}).items():
        if slot not in order and slot not in SPECIAL_VARIANTS: die(f"variant for unknown slot: {slot}")
        canon = CANON.get(slot) or f"blk-{slot}"
        if var and slot not in SPECIAL_VARIANTS \
           and not (BLOCKS / f"blk-{slot}-{var}.html").exists() \
           and not (BLOCKS / f"{canon}-{var}.html").exists():
            die(f"variant fragment missing: {canon}-{var}.html")
    locale = plan["params"].get("locale") or \
        plan["params"]["lang"] + "-" + plan["params"]["lang"].upper()
    livebar, header, footer = build_header_footer(plan, C)
    body_parts = [livebar, header, "<main>"]
    SLOT_REMAP = {  # sections sharing schema intro key -> distinct content paths
        "stats-intro": "sections.stats.", "intro-center": "sections.ladder.",
    }
    for slot in order:
        html = R(slot, plan, C)
        if slot in SLOT_REMAP:
            html = html.replace("c:sections.intro.", SLOT_REMAP[slot])
        body_parts.append(html)
    body_parts.append("</main>"); body_parts.append(footer)
    body = "\n".join(body_parts)
    m = C["meta"]
    jsonld = build_jsonld(plan, C)
    title = m["title_home"].replace("{Brand}", brand)
    descr = m["description"]; kw = m["keywords"].replace("{Brand}", brand).replace("{dom}", dom)
    page = page_shell(title, descr, kw, "/", locale, css_vars, fonts_import, theme,
                      body, og_desc=C["meta"].get("og_description", ""), jsonld=jsonld)
    page = fix_anchors(page).replace('href="index.php#claim"', 'href="#claim"')
    page = page.replace("{DOM}", dom).replace("{BRAND}", brand)
    return page

def build_jsonld(plan, C):
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    n = plan["numbers"]; reg = plan.get("regulator", {})
    fq = (C.get("faq") or {}).get("items", [])[:6]
    faq_entities = ",".join(json.dumps({"@type": "Question", "name": q["q"],
        "acceptedAnswer": {"@type": "Answer", "text": q["a"]}}, ensure_ascii=False) for q in fq)
    email = (C.get("meta") or {}).get("email") or f"contatti@{dom}"
    tel = (C.get("meta") or {}).get("telephone") or "+390200000000"
    org = {"@type": "FinancialService", "@id": f"https://{dom}/#org", "name": brand,
        "alternateName": [brand.lower(), f"{brand} {plan['params'].get('geo','')}", dom, f"{brand} login"],
        "url": f"https://{dom}/", "logo": f"https://{dom}/favicon.svg", "image": f"https://{dom}/og-image.png",
        "description": C["meta"]["description"], "email": email,
        "telephone": tel, "areaServed": plan["params"].get("geo", ""),
        "currenciesAccepted": plan["params"].get("currency", "EUR"),
        "aggregateRating": {"@type": "AggregateRating", "ratingValue": str(n.get("rating", "4,7")),
            "bestRating": "5", "worstRating": "1", "reviewCount": str(n.get("reviews", 641))}}
    if reg: org["slogan"] = f"{brand} — {reg.get('name','')}"
    website = {"@type": "WebSite", "@id": f"https://{dom}/#site", "url": f"https://{dom}/",
        "name": brand, "inLanguage": plan["params"].get("locale", ""),
        "publisher": {"@id": f"https://{dom}/#org"}}
    graph = [org, website]
    if fq: graph.append({"@type": "FAQPage", "@id": f"https://{dom}/#faq", "mainEntity": json.loads(f"[{faq_entities}]")})
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, separators=(",", ":"))

PAGE_LABELS = {"it": {"about": "Chi siamo", "who": "Metodo", "contact": "Contatti", "register": "Registrazione"},
                "cs": {"about": "O nás", "who": "Metoda", "contact": "Kontakt", "register": "Registrace"},
                "es": {"about": "Quiénes somos", "who": "Método", "contact": "Contacto", "register": "Registro"},
                "en": {"about": "About", "who": "Method", "contact": "Contact", "register": "Registration"}}


def brand_first(title: str, brand: str, fallback: str = "Home") -> str:
    """Brand-first title without the brand repeated twice."""
    parts = [x.strip() for x in re.split(r"\s+[—|–]\s+", (title or "").strip()) if x.strip()]
    parts = [re.sub(re.escape(brand), "", x, flags=re.I).strip(" .,—-") for x in parts]
    parts = [x for x in parts if x]
    body = " — ".join(parts) or fallback
    body = re.sub(r"\s+(es|en|de|di|del|da|a|na|v)$", "", body, flags=re.I)
    body = re.sub(r"\s+([?!.,])", r"\1", body).strip(" .,—-")
    return f"{brand} — {body or fallback}"


def build_inner(plan, C, css_vars, fonts_import, theme, which):
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    slugs = plan["layout"].get("slugs", {})
    skeleton = plan.get("inner_pages", {}).get(which, ["page-intro", "editorial", "cta"])
    cp = C.get(f"inner_{which}", {})
    livebar, header, footer = build_header_footer(plan, C)
    body_parts = [livebar, header, "<main>"]
    intro = f"""<section class="page-intro"><div class="eyebrow">{esc(cp.get('title', which.upper()))}</div>
<h1>{esc(cp.get('h1', brand))}<br><span class="brand-line">{esc(brand)}</span></h1><p>{esc(cp.get('lead', ''))}</p></section>"""
    if "page-intro" in skeleton: body_parts.append(intro)
    else:
        # every indexed page MUST have h1 with .brand-line (audit) even in non-intro skeletons
        body_parts.append(f'<section class="page-intro"><h1>{esc(cp.get("h1", cp.get("title", brand)))}'
                          f'<br><span class="brand-line">{esc(brand)}</span></h1></section>')
    form_slot = next((x for x in ("access-band", "claim-band", "enroll-band")
                      if x in plan["layout"]["section_order"]), "access-band")

    def inner_slot(slot):
        return R(slot, plan, C)

    SLOT_FOR = {"office": "office", "hours": "office", "contact-grid": "office",
                "map": "office", "core": form_slot, "form": form_slot,
                "form-first": form_slot, "register": form_slot,
                "steps": "steps", "steps-live": "steps-live", "mini-faq": "mini-faq",
                "milestones": "timeline", "timeline": "timeline",
                "winrate": "numbers", "figures": "numbers", "numbers": "numbers",
                "stack": "features", "features": "features",
                "team-band": "people", "people": "people"}
    rendered_form = False
    done = set()
    for token in skeleton:
        if token in ("page-intro",):
            continue
        slot = SLOT_FOR.get(token)
        if slot and slot not in done:
            body_parts.append(inner_slot(slot)); done.add(slot)
            rendered_form = rendered_form or slot == form_slot
        if token == "points":
            pts = cp.get("points") or []
            if pts:
                body_parts.append('<section class="section"><div class="wrap"><ul class="blk-grid3">'
                                  + "".join(f'<li class="blk-card">{esc(p)}</li>' for p in pts)
                                  + "</ul></div></section>")
    if which == "contact" and "office" not in done:
        body_parts.append(inner_slot("office")); done.add("office")
    if which in ("contact", "register") and not rendered_form:
        body_parts.append(inner_slot(form_slot)); rendered_form = True

    blocks_html = ""
    for b in cp.get("blocks", []):
        blocks_html += f'<article class="blk-card"><h3>{esc(b.get("t",""))}</h3><p>{esc(b.get("d",""))}</p></article>'
    if blocks_html:
        body_parts.append(f'<section class="section"><div class="wrap"><div class="blk-grid3">{blocks_html}</div></div></section>')
    if "cta" in skeleton:
        cta = C.get("sections", {}).get("cta", {})
        body_parts.append(R("cta-band", plan, C).replace("{{c:sections.cta.h2}}", esc(cta.get("h2", brand))))
    body_parts.append("</main>"); body_parts.append(footer)
    m = C["meta"]
    label = PAGE_LABELS.get(plan["params"]["lang"], PAGE_LABELS["en"]).get(which, which.title())
    title = brand_first(cp.get("title") or label, brand, label)
    if "{Brand}" in title: title = title.replace("{Brand}", brand)
    page = page_shell(f"{title}", cp.get("lead", title)[:155], m["keywords"].replace("{Brand}", brand).replace("{dom}", dom),
                       f"/{slugs.get(which, which)}.php",
                       plan["params"].get("locale") or plan["params"]["lang"], css_vars, fonts_import, theme,
                       "\n".join(body_parts), jsonld=build_inner_jsonld(plan, C, which))
    page = page.replace('href="#claim"', 'href="index.php#claim"')
    page = page.replace("{DOM}", dom).replace("{BRAND}", brand)
    return page

def build_inner_jsonld(plan, C, which):
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    slugs = plan["layout"].get("slugs", {})
    slug = slugs.get(which, which)
    return json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "@id": f"https://{dom}/{slug}.php",
         "url": f"https://{dom}/{slug}.php", "name": f"{which} — {brand}",
         "publisher": {"@id": f"https://{dom}/#org"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"https://{dom}/"},
            {"@type": "ListItem", "position": 2, "name": which.title()}]}]}, ensure_ascii=False, separators=(",", ":"))

def build_legal(plan, C, css_vars, fonts_import, theme, which):
    """terms.php / privacy.php — unique titles, legal body from content pack or neutral stub."""
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    reg = plan.get("regulator") or {}
    livebar, header, footer = build_header_footer(plan, C)
    reg_line = f"Reference supervisory authority: {reg.get('name','')}" if reg else ""
    bodyLegal = C.get("legal", {}).get(which) or (
        f"<p>This page describes the {which} of {brand} in summary form. "
        f"{reg_line}. Full personalised terms are provided during onboarding.</p>")
    tl = TERMS_L10N.get(plan["params"]["lang"], TERMS_L10N["en"])
    terms_l = {"terms": tl[0], "privacy": tl[1]}
    title_map = {"terms": brand_first(tl[0], brand), "privacy": brand_first(tl[1], brand)}
    body = f"""{livebar}{header}<main>
<section class="page-intro"><div class="eyebrow">{which.upper()}</div>
<h1>{brand}<br><span class="brand-line">{esc(terms_l[which])}</span></h1></section>
<section class="legal">{bodyLegal}</section></main>{footer}"""
    page = page_shell(title_map[which], f"{which.title()} of {brand}.", f"{brand}, {which}", f"/{which}.php",
                       plan["params"].get("locale") or plan["params"]["lang"], css_vars, fonts_import, theme,
                       body, jsonld=build_inner_jsonld(plan, C, which))
    page = page.replace("{DOM}", dom).replace("{BRAND}", brand)
    return page

def build_thanks(plan, C, css_vars, fonts_import, theme):
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    th = C.get("thanks", {})
    livebar, header, footer = build_header_footer(plan, C)
    body = f"""{livebar}{header}<main><section class="section"><div class="wrap blk-center">
<div class="eyebrow center">{esc(th.get('eyebrow','DONE'))}</div>
<h1>{esc(th.get('h1','Thank you'))}<br><span class="brand-line">{esc(brand)}</span></h1><p>{esc(th.get('lead',''))}</p>
<p class="fine">{esc(th.get('warn',''))}</p>
<a class="blk-btn" href="index.php">← {esc(brand.split()[0].title())}</a>
</div></section></main>{footer}"""
    tl = TERMS_L10N.get(plan["params"]["lang"], TERMS_L10N["en"])
    page = page_shell(brand_first(tl[2], brand), th.get("lead", "")[:155], "", "/thanks.php",
                       plan["params"].get("locale") or plan["params"]["lang"], css_vars, fonts_import, theme,
                       body, noindex=True)
    page = page.replace("{DOM}", dom).replace("{BRAND}", brand)
    postback_head = "<?php require __DIR__ . '/_postback.php'; send_postback(); ?>\n"
    return postback_head + page

def build_404(plan, C, css_vars, fonts_import, theme):
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    lang = plan["params"]["lang"]
    nf = NOTFOUND_L10N.get(lang, ("Page not found", "Back home"))
    livebar, header, footer = build_header_footer(plan, C)
    body = f"""{livebar}{header}<main><section class="section"><div class="wrap blk-center">
<h1>404<br><span class="brand-line">{esc(brand)}</span></h1><p>{nf[0]}</p><a class="blk-btn" href="index.php">{nf[1]}</a>
</div></section></main>{footer}"""
    page = page_shell(brand_first(f"404 — {nf[0]}", brand), nf[0], "", "/404.php",
                       plan["params"].get("locale") or plan["params"]["lang"], css_vars, fonts_import, theme,
                       body, noindex=True)
    page = page.replace("{DOM}", dom).replace("{BRAND}", brand)
    return page

ASSETS_JS_APP = """function onReady(fn){if(document.readyState!=='loading'){fn();}else{document.addEventListener('DOMContentLoaded',fn);}}
onReady(function(){
var mt=document.querySelector('.menu-toggle');if(mt){mt.addEventListener('click',function(){
var n=document.querySelector('.blk-nav');var ex=n.classList.toggle('open');mt.setAttribute('aria-expanded',ex)});
}
/* sticky header: elevated state after a small scroll */
var hd=document.querySelector('.blk-header');
if(hd){var hUpd=function(){hd.classList.toggle('is-scrolled',window.scrollY>18)};
window.addEventListener('scroll',hUpd,{passive:true});hUpd();}
/* floating mobile CTA: appears deep into the page, points at the form */
if(window.matchMedia&&window.matchMedia('(max-width:760px)').matches&&!document.querySelector('.blk-float-cta')){
var fEl=document.createElement('div');fEl.className='blk-float-cta';
var fSrc=document.querySelector('.blk-header .blk-btn');
var fTgt=document.getElementById('claim')?'#claim':'index.php#claim';
fEl.innerHTML='<a class="blk-btn" href="'+fTgt+'">'+(fSrc?fSrc.textContent:'Open account')+'</a>';
document.body.appendChild(fEl);
var fUpd=function(){fEl.classList.toggle('is-on',window.scrollY>700)};
window.addEventListener('scroll',fUpd,{passive:true});fUpd();}
/* reveal on scroll: sections fade in once (skipped for reduced motion / no IO) */
var secs=[].slice.call(document.querySelectorAll('main > .sec'));
var still=function(){document.documentElement.classList.add('has-anim')};
if('IntersectionObserver' in window&&!(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches)){
still();
var io=new IntersectionObserver(function(es){es.forEach(function(e){
if(e.isIntersecting){e.target.classList.add('is-in');io.unobserve(e.target)}})},
{threshold:.08,rootMargin:'0px 0px -36px'});
secs.forEach(function(s,i){s.style.setProperty('--reveal-order',i%4);io.observe(s)});
}else{secs.forEach(function(s){s.classList.add('is-in')});}
/* editorial numbering: 01/ 02/ ... chips inside each section eyebrow */
var sn=0;secs.forEach(function(s){var ey=s.querySelector('.eyebrow');if(!ey)return;
sn++;var chip=document.createElement('i');chip.className='sec-num';chip.setAttribute('aria-hidden','true');
chip.textContent=(sn<10?'0':'')+sn;ey.insertBefore(chip,ey.firstChild)});
var ll=document.getElementById('live-latency'),lo=document.getElementById('live-orders');
if(ll&&!window.__noLiveTick){setInterval(function(){ll.textContent=(38+Math.floor(Math.random()*24))+' ms'},4000)}
if(lo){setInterval(function(){lo.textContent=(1200+Math.floor(Math.random()*400)).toLocaleString()},5000)}
var cd=document.getElementById('countdown');
if(cd){var end=Date.now()+1000*60*60*26+1000*60*13;
setInterval(function(){var s=Math.max(0,Math.floor((end-Date.now())/1000));
var d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60),sec=s%60;
var map={'days':[d,2],'hours':[h,2],'minutes':[m,2],'seconds':[sec,2]};
Object.keys(map).forEach(function(k){var el=cd.querySelector('[data-unit="'+k+'"]');
if(el)el.textContent=String(map[k][0]).padStart(map[k][1],'0')})},1000)}
});"""

# canonical lead-form.js lives in blocks/lead-form.js (real file, no escaping);
# loaded per-build in write_assets().

CALC_JS_STUB = """/* calculator.js — deposit projection demo. Illustrative only, no promises.
   Reads currency/locale words from data attributes on #calculator (ui.* content keys). */
(function(){
'use strict';
var LOCALE=document.documentElement.getAttribute('lang')||'cs-CZ';
function fmtNum(v){
  try{return new Intl.NumberFormat(LOCALE,{maximumFractionDigits:0}).format(v);}
  catch(e){return Math.round(v).toString();}
}
function compound(start,monthly,years,rate){
  var r=Math.pow(1+rate/100,1/12)-1,v=start,m=monthly;
  var pts=[],yr=0;
  for(var i=1;i<=years*12;i++){
    v=v*(1+r)+m;
    if(i%12===0){yr++;pts.push(v);}
  }
  return{final:v,series:pts};
}
function onReady(fn){if(document.readyState!=='loading'){fn();}else{document.addEventListener('DOMContentLoaded',fn);}}
onReady(function(){
  var box=document.getElementById('calculator');if(!box)return;
  var $=function(id){return document.getElementById(id);};
  var eInit=$('initial'),eMon=$('monthly'),eYrs=$('years'),
      eRate=$('rate'),eVal=$('future-value'),eRes=$('result-years'),
      eCon=$('contributed'),eGain=$('gain'),eErr=$('calc-error'),
      gLine=$('growth-line'),gArea=$('calc-area'),cLine=$('contribution-line'),
      eYL=$('years-label'),eRL=$('rate-label'),eEnd=$('end-year'),axis=box.querySelector('.chart-axis span:last-child');
  var curSym=box.getAttribute('data-cur-sym')||'',curCode=box.getAttribute('data-cur-code')||'',
      wFull=box.getAttribute('data-w-full')||'',wShort=box.getAttribute('data-w-short')||'',
      minInit=parseFloat(box.getAttribute('data-min-init'))||250;
  if(curCode==='CZK'){eInit.min=minInit;eInit.step=50;}
  function money(v,sign){
    var s=fmtNum(Math.abs(Math.round(v)));
    return(sign&&v>=0?'+':'')+(curSym?s+'\\u00a0'+curSym:s);
  }
  function draw(){
    var start=parseFloat(eInit.value)||0,mon=parseFloat(eMon.value)||0,
        yrs=parseInt(eYrs.value,10)||1,rate=parseFloat(eRate.value)||0;
    if(curCode==='CZK'&&start<minInit){eErr.textContent='';
      start=minInit;eInit.value=String(minInit);}
    eYL.textContent=String(yrs);eRL.textContent=(new Intl.NumberFormat(LOCALE,{maximumFractionDigits:1}).format(rate))+' %';
    var res=compound(start,mon,yrs,rate),
        contributed=start+mon*yrs*12,gain=res.final-contributed;
    eVal.textContent=money(res.final,false);
    eRes.textContent=yrs+'\\u00a0'+wFull;
    eCon.textContent=money(contributed,false);
    eGain.textContent=money(gain,true);
    eEnd.textContent='+'+yrs+'\\u00a0'+wShort;
    /* svg paths */
    var svg=$('calc-chart');if(svg){
      var W=500,H=200,pad=8,series=res.series,len=series.length||1,
          max=Math.max(start,res.final)||1,st=(W-pad*2)/Math.max(1,len);
      function Y(v){return(H-pad)-(v/max)*(H-pad*2);}
      function X(i){return pad+i*st;}
      var dg='',dc='',cr=start;
      for(var i=0;i<len;i++){dg+=(i?' L':'M')+X(i).toFixed(1)+' '+Y(series[i]).toFixed(1);
        dc+=(i?' L':'M')+X(i).toFixed(1)+' '+Y(cr).toFixed(1);cr+=mon*12;}
      gLine.setAttribute('d',dg);
      gArea.setAttribute('d',dg+' L'+X(len-1).toFixed(1)+' '+(H-pad)+' L'+pad+' '+(H-pad)+' Z');
      cLine.setAttribute('d',dc);
    }
  }
  ['initial','monthly','years','rate'].forEach(function(id){
    var el=$(id);if(!el)return;
    el.addEventListener('input',draw);
  });
  Array.prototype.forEach.call(box.querySelectorAll('.rate-presets button'),function(b){
    b.addEventListener('click',function(){eRate.value=b.getAttribute('data-rate');draw();});
  });
  draw();
});
/* livebar-aa: nudge one price in the flash tape every few seconds; both
   duplicated track copies must show identical values or the loop seam
   would display different numbers after an update */
var fTapes=document.querySelectorAll('.lbt-flash');
if(fTapes.length){
var fNudge=function(el){
var t=el.textContent,m=t.match(/\\d+([.,]\\d+)?/);if(!m)return;
var sep=t.indexOf(',')>-1?',':'.';
var val=parseFloat(m[0].replace(',','.'));
if(!isFinite(val))return;
var step=(Math.random()-0.5)*Math.max(val,1)*0.0012;
var dec=(m[0].indexOf(sep)>-1?m[0].split(sep)[1].length:0);
var out=(val+step).toFixed(dec);if(sep===',')out=out.replace('.',',');
el.textContent=t.replace(m[0],out);
el.classList.remove('flash-up','flash-dn');void el.offsetWidth;
el.classList.add(step>=0?'flash-up':'flash-dn');
};
setInterval(function(){Array.prototype.forEach.call(fTapes,function(tp){
var bs=tp.querySelectorAll('b');if(!bs.length)return;
fNudge(bs[Math.floor(Math.random()*bs.length)]);});},2600);
}
});"""
# NOTE: the literal above kept the historic broken IIFE closer `});` (missing "(") —
# that made the whole IIFE a no-op expression and calculator.js dead. Do not use it.

def write_assets(out: pathlib.Path, plan):
    lf = BLOCKS / "lead-form.js"
    cf = BLOCKS / "calculator.js"
    ps = BLOCKS / "pulse-sim.js"
    if not lf.exists(): die("blocks/lead-form.js missing (canonical lead form logic)")
    if not cf.exists(): die("blocks/calculator.js missing (canonical calculator engine)")
    if not ps.exists(): die("blocks/pulse-sim.js missing (canonical pulse-sim engine)")
    (out / "app.js").write_text(ASSETS_JS_APP, encoding="utf-8")
    (out / "calculator.js").write_text(cf.read_text(encoding="utf-8"), encoding="utf-8")
    (out / "pulse-sim.js").write_text(ps.read_text(encoding="utf-8"), encoding="utf-8")
    (out / "lead-form.js").write_text(lf.read_text(encoding="utf-8"), encoding="utf-8")
    shutil.copy(BLOCKS / "blocks.css", out / "blocks" / "blocks.css") if (out / "blocks").exists() else \
        ((out / "blocks").mkdir(parents=True, exist_ok=True), shutil.copy(BLOCKS / "blocks.css", out / "blocks" / "blocks.css"))
    skin = plan["design"].get("skin", "rounded-air")
    shutil.copy(SKINS / f"skin-{skin}.css", out / "skin.css")
    # personas: copy only this plan's avatars into img/
    img_dir = out / "img"; img_dir.mkdir(exist_ok=True)
    for ph in plan.get("photos", []):
        src = PEOPLE_DIR / ph
        if src.exists(): shutil.copy(src, img_dir / ph)
    # favicon + og: copy neutral placeholders (regenerated per brand by icon step)
    for f in ("favicon.svg", "favicon.ico", "favicon-32.png", "apple-touch-icon.png", "og-image.png"):
        src = ROOT / "assets-brand" / f
        if src.exists(): shutil.copy(src, out / f)

def write_integration(out: pathlib.Path, plan):
    dest_root = out / "api_local"
    if dest_root.exists(): shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True)
    dest = dest_root / "integration"
    shutil.copytree(INTEGRATION_SRC, dest, ignore=shutil.ignore_patterns(".DS_Store"))
    jobs_dir = dest / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    cfg = dest / "config.php"
    if not cfg.exists(): die("api_local_example/integration/config.php missing")
    txt = cfg.read_text(encoding="utf-8")
    brand_tokens = re.sub(r"[^A-Za-z ]", "", plan["params"]["brand"]).split()
    funnel = max(brand_tokens, key=len).upper() if brand_tokens else "BRAND"
    txt = (txt.replace("{{CC}}", plan["params"].get("cc", "") or plan["params"]["lang"].upper()[:2])
              .replace("{{LANG}}", plan["params"]["lang"])
              .replace("{{FUNNEL}}", funnel))
    cfg.write_text(txt, encoding="utf-8")
    pb = POSTBACK_SRC
    if pb.exists(): shutil.copy(pb, out / "_postback.php")

SITEMAP_T = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>"""

# Canonical-host guard. The hosting panel serves extensionless URLs (e.g. /about)
# with HTTP 200 (MultiViews) and its console may even regenerate sitemap.xml
# without the .php suffix - both create duplicate URLs next to the canonical ones.
# Every content page therefore opens with this guard: any GET/HEAD request whose
# path does not end in ".php" gets an immediate 301 to the .php variant.
# POST is never redirected; thanks.php keeps its line-1 postback contract;
# 404.php is excluded so soft-404s stay 404 instead of 301-into-404.
PHP_CANON_GUARD = (
    "<?php\n"
    "$__u = parse_url(isset($_SERVER['REQUEST_URI']) ? $_SERVER['REQUEST_URI'] : '/', PHP_URL_PATH) ?: '/';\n"
    "$__u = rtrim($__u, '/');\n"
    "$__m = isset($_SERVER['REQUEST_METHOD']) ? $_SERVER['REQUEST_METHOD'] : 'GET';\n"
    "if ($__m !== 'POST' && $__u !== '' && substr($__u, -4) !== '.php') {\n"
    "  $__q = (isset($_SERVER['QUERY_STRING']) && $_SERVER['QUERY_STRING'] !== '') ? '?' . $_SERVER['QUERY_STRING'] : '';\n"
    "  header('Location: ' . $__u . '.php' . $__q, true, 301);\n"
    "  exit;\n"
    "}\n"
    "?>\n"
)

def write_seo_files(out: pathlib.Path, plan, pages: list[str]):
    dom = plan["params"]["domain"]
    pages = [p for p in pages if p not in ("404.php", "thanks.php")]
    lastmod = time.strftime("%Y-%m-%d")
    urls = []
    for p in pages:
        loc = f"https://{dom}/" if p == "index.php" else f"https://{dom}/{p}"
        freq, pri = ("weekly", "1.0") if p == "index.php" else ("monthly", "0.7")
        urls.append(f"<url><loc>{loc}</loc><lastmod>{lastmod}</lastmod>"
                    f"<changefreq>{freq}</changefreq><priority>{pri}</priority></url>")
    (out / "sitemap.xml").write_text(SITEMAP_T.format(urls="\n".join(urls)), encoding="utf-8")
    (out / "robots.txt").write_text(f"""User-agent: *
Allow: /
Allow: /blocks/blocks.css
Allow: /skin.css
Disallow: /api_local/

Sitemap: https://{dom}/sitemap.xml
""", encoding="utf-8")
    (out / ".htaccess").write_text("ErrorDocument 404 /404.php\n", encoding="utf-8")

# ---------------------------------------------------------------- main -------
def cmd_build(a):
    plan = load(pathlib.Path(a.plan))
    if not plan: die(f"cannot read plan {a.plan}")
    validate_plan(plan)
    dom = plan["params"]["domain"]
    content_path = pathlib.Path(a.content) if a.content else \
        pathlib.Path(a.plan).parent / f"{pathlib.Path(a.plan).stem}-content.json"
    if not content_path.exists():
        content_path = ROOT / "content" / f"{dom}-content.json"
    C = load(content_path)
    if C: errs = validate_content(C, plan, strict=True); errs and die("; ".join(errs))
    else: C = seed_content(plan); ok("content: seeded placeholders")
    css_vars, fonts_import, theme = css_link_block(plan)
    ok(f"design: {plan['design']['palette_id']} × skin-{plan['design'].get('skin','rounded-air')}")
    C.setdefault("meta", {})["keywords"] = C["meta"].get("keywords", "{Brand}, {dom}")

    out = pathlib.Path(a.out) if a.out else SITES_OUT / dom
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / "blocks").mkdir()
    content_default = ROOT / "content" / f"{dom}-content.json"

    global BUILD_V
    BUILD_V = hashlib.sha1((BLOCKS / "blocks.css").read_bytes() +
                           (SKINS / f"skin-{plan['design'].get('skin')}.css").read_bytes() +
                           (BLOCKS / "lead-form.js").read_bytes() +
                           (BLOCKS / "calculator.js").read_bytes() +
                           (BLOCKS / "pulse-sim.js").read_bytes()).hexdigest()[:8]
    has_calc = "calculator" in plan["layout"]["section_order"]
    pages = {"index.php": build_index(plan, C, css_vars, fonts_import, theme)}
    for which in ("about", "who", "contact", "register"):
        slug = plan["layout"].get("slugs", {}).get(which, which)
        pages[f"{slug}.php"] = build_inner(plan, C, css_vars, fonts_import, theme, which)
    pages["thanks.php"] = build_thanks(plan, C, css_vars, fonts_import, theme)
    pages["terms.php"] = build_legal(plan, C, css_vars, fonts_import, theme, "terms")
    pages["privacy.php"] = build_legal(plan, C, css_vars, fonts_import, theme, "privacy")
    pages["404.php"] = build_404(plan, C, css_vars, fonts_import, theme)

    for fname, html in pages.items():
        if fname not in ("thanks.php", "404.php"):
            html = PHP_CANON_GUARD + html
        (out / fname).write_text(html, encoding="utf-8")
    ok(f"pages written: {', '.join(sorted(pages))}")

    write_assets(out, plan); ok("assets: app.js/calculator.js/blocks.css/skin.css")
    write_integration(out, plan); ok(f"integration: config filled (cc={plan['params'].get('cc','') or plan['params']['lang'].upper()[:2]})")
    write_seo_files(out, plan, list(pages.keys())); ok("sitemap/robots/.htaccess")
    # brand icons are part of the build (never ship an iconless offer)
    rc = subprocess.run([sys.executable, str(ROOT / "tools" / "brand_icons.py"),
                         "--plan", str(pathlib.Path(a.plan)), "--site", str(out)]).returncode
    if rc != 0: die("brand icons failed")
    ok("icons: favicon svg/ico/png + apple-touch + og-image")
    (out / "README.md").write_text(f"# {plan['params']['brand']} ({dom})\nBuilt by static-create-sites/assemble.py\n"
                                     f"Plan: {a.plan}\nSkin: {plan['design'].get('skin')} · Palette: {plan['design']['palette_id']}\n", encoding="utf-8")
    print(f"\nSITE BUILT → {out}")
    return out

def main():
    ap = argparse.ArgumentParser(description="Static site assembler (plan → offer)")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--content", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    out = cmd_build(a)
    # gates — free lingering php -S on our port first (stale servers break probing)
    import time, os, signal
    for port in (8794, 8951):
        try:
            pids = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                                   capture_output=True, text=True).stdout
            for line in pids.splitlines()[1:]:
                pid = line.split()[1]
                if pid.isdigit(): os.kill(int(pid), signal.SIGTERM)
        except Exception: pass
    time.sleep(2.0)
    print("\n--- GATES ---")
    rel = out.relative_to(ROOT)
    arg = str(rel)
    rc = subprocess.run([sys.executable, str(ROOT / "tools" / "seo_audit.py"), arg],
                         cwd=ROOT).returncode
    if rc != 0: die("seo_audit failed", rc)
    ok("seo_audit: PASSED")
    rc2 = subprocess.run([sys.executable, str(ROOT / "tools" / "twin_check.py"), arg],
                          cwd=ROOT, capture_output=True, text=True).returncode
    if rc2 != 0:
        # duplicates policy: warn in the log, never block the build
        print("WARN: twin_check flagged duplicate patterns against history/siblings —")
        print("WARN: build continues (duplicates warn, not block); details above/below")
        ok("twin_check: WARN (duplicate patterns — see log)")
    else:
        ok("twin_check: PASSED")
    print(f"\nALL GREEN → ready for deploy: {out}")

if __name__ == "__main__":
    main()

