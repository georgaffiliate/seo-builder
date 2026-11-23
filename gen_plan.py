#!/usr/bin/env python3
"""gen_plan.py (static-create-sites edition) — seed-deterministic site planner.

Standalone: reads only resources inside static-create-sites/. History = plans/*.json here.

Axes decided (validated against history so neighbours never repeat):
  palette (15) × skin (6, geometry language) × font pair (12) × hero (7) ×
  section order 10–16 (constraints) × widgets G1–G5 × inner skeletons × slugs ×
  menu words × number bins (disjoint ranges) × personas + portrait photos × regulator.

Usage:
  python3 gen_plan.py --brand "Pheira Voltreksc" --lang it --domain pheira-voltreksc.site
  python3 gen_plan.py --brand "X" --lang nb --domain x.site --seed 42 [--cc NO]
  python3 gen_plan.py --brand "X" --lang it --domain x.site --build   # plan → content → site → gates → icons → lint → profile

Output: plans/<domain>.json (+ human summary). Exit 1 if nothing valid in 200 retries.
With --build the chain continues: content pack, assemble+gates, brand icons, JS syntax,
static mobile lint and profiles/<domain>.json registration (deploy stays manual).
"""
from __future__ import annotations
import argparse, datetime, hashlib, itertools, json, os, pathlib, random, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent          # static-create-sites/
# Country codes people type instead of the language code. Without this every
# language-keyed table (404 page, footer, aria, menus) falls back to English.
LANG_ALIASES = {
    # Europe
    "si": "sl", "cz": "cs", "gr": "el", "dk": "da", "se": "sv", "no": "nb",
    "ua": "uk", "at": "de", "ch": "de", "be": "nl", "gb": "en", "ie": "en",
    # Americas / Oceania / Africa (English markets)
    "au": "en", "nz": "en", "za": "en", "ng": "en", "ke": "en", "ca": "en",
    # Asia
    "jp": "ja", "cn": "zh", "hk": "zh", "sg": "en", "my": "ms", "ph": "tl",
    "in": "hi", "ge": "ka", "az": "az",
    # Latin America
    "br": "pt", "mx": "es", "pe": "es", "il": "he",
}

# Languages that write decimals with a comma ("1.084,20"). The strip, ticker and
# calculator all format through these two helpers, so a page never mixes 1,084.2 and
# 1.084,2 side by side.
COMMA_DECIMAL = {
    "it", "de", "es", "fr", "pl", "cs", "sk", "sl", "hr", "hu", "ro", "bg", "tr",
    "pt", "nl", "da", "nb", "no", "sv", "fi", "et", "lv", "lt", "el", "uk", "ru",
    "sr", "mk", "bs", "sq", "az", "ka", "ca",
}


def decimal_comma(lang: str) -> bool:
    return (lang or "").lower() in COMMA_DECIMAL
PLANS = ROOT / "plans"
PALETTES_F = ROOT / "content" / "palettes-blk.json"
REG_F = ROOT / "resources" / "regulators.json"
BLOG_TOPICS_F = ROOT / "resources" / "blog-topics.json"
PEOPLE_DIR = ROOT / "people"

# ---------------------------------------------------------------- registries --
WIDGET_GROUPS = {
    "G1": ["ticker-static", "livebar-counter", "tape-marquee", "markets-strip",
            "price-board", "listino-rows", "heatmap", "tile-flip", "odometer"],
    "G2": ["countdown-plates", "countdown-bar", "countdown-ring", "flip-clock", "progress-intake"],
    "G3": ["none", "demo-line", "demo-bars", "sentiment-gauge", "book-ladder",
            "pulse-sim", "calculator"],
    "G4": ["faq-accordion", "faq-list", "faq-grid", "faq-split"],
    "G5": ["stats-band", "quick-answer", "rating-summary", "rating-band"],
}
SKINS = ["rounded-air", "sharp-flat", "brutalist-block", "glass-soft",
          "classic-border", "dense-terminal"]
# Hero concepts: each one is a composition with its own evidence (claims / quote /
# steps / band), rendered by blocks/blk-hero-<letter>.html. The concept avoids the
# last two plans; the letter is what assemble renders.
HEROES = ["hero-statement", "hero-proof", "hero-steps", "hero-band", "hero-review"]
HERO_LETTER = {"hero-statement": "d", "hero-proof": "e", "hero-steps": "f",
               "hero-band": "g", "hero-review": "h"}
FORM_BANDS = ["access-band", "claim-band", "enroll-band"]
SECTION_POOL = ["intro-center", "features", "steps", "steps-live", "markets", "ladder",
                 "streams", "security", "demo", "risk", "cta-band", "trust-band",
                 "ticker", "timeline", "stats-intro",
                 "numbers", "portal", "compare", "glance",
                 "facts", "notes", "mini-faq"]
# Recognisable "screens" that rotate between offers: a plan picks 2-3 of them and
# never repeats the ones the previous plan / same-brand sibling already shows, so
# two offers of one factory visibly have DIFFERENT screens (human and Google view).
ANCHOR_TYPES = ("people", "faq", "numbers", "cta", "office", "compare")
TYPE_OF = {"claim-band": "band", "access-band": "band", "enroll-band": "band",
           "trust-band": "cta", "cta-band": "cta", "intro-center": "intro", "stats-intro": "intro",
           "steps-live": "steps", "brand-note": "brandnote"}
def types_of(order): return {TYPE_OF.get(t, t) for t in order}
VARIANTS = {  # structural fragment variants per slot ("" = canonical file, always allowed)
    "claim-band": ["b", "c", "d", "e"], "access-band": ["b", "c", "d", "e"],
    "enroll-band": ["b", "c", "d", "e"],
    "features": ["b", "c"],
    "people": ["b", "c", "e", "f", "g", "h"],   # d renders quotes without portraits
    "steps": ["b"], "faq": ["b"], "cta-band": ["b", "c"],
    "ladder": ["b", "c"], "office": ["b", "c"], "brand-note": ["b", "c"], "timeline": ["b"],
    "scarcity": ["b"], "markets": ["b", "c"], "ticker": ["b", "c"], "intro-center": ["b", "c"],
    "risk": ["b"], "security": ["b"], "streams": ["b"], "demo": ["b"],
    # only structurally DIFFERENT strips are drawn: marquee, news, centered tape,
    # ledger tape, rows, meters, board, sparkline tape, static chips. The rest of the
    # old b..y ids were the same marquee with another border — they stay renderable
    # for historical plans but are never picked for a new site.
    "livebar": ["a", "f", "j", "k", "m", "n", "t", "z", "ac", "ad", "ae", "af"],
    "logo": ["b", "c", "d", "e", "f", "g", "h"],
    # b (logo + CTA in the middle of the row) is retired: the CTA landed between
    # the mark and the menu. It still renders for historical plans, never picked.
    "header": ["c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m"],
    "form": ["b", "c", "d"],
    "footer": ["b", "c", "d", "e", "f"],
}

LIVEBAR_L10N = {lg: b["_livebar"] for lg, b in json.loads(
    (ROOT / "resources" / "content-l10n.json").read_text(encoding="utf-8")).items()
    if isinstance(b, dict) and b.get("_livebar")}
PULSE_L10N = {lg: b["_pulse"] for lg, b in json.loads(
    (ROOT / "resources" / "content-l10n.json").read_text(encoding="utf-8")).items()
    if isinstance(b, dict) and b.get("_pulse")}

NAME_BANK = {
    "it": ["Giulia F.", "Marco T.", "Elena B.", "Luca R.", "Chiara M.", "Davide S.", "Sara P.",
           "Alessandro V.", "Martina G.", "Federico L.", "Beatrice C.", "Simone D.", "Valentina A.",
           "Roberta N.", "Stefano Z.", "Ilaria M.", "Pietro B.", "Camilla R.", "Matteo C.",
           "Francesca T.", "Gabriele P.", "Alessia D."],
    "cs": ["Jana Nováková", "Tomáš Dvořák", "Lucie Horáková", "Martin Svoboda", "Petra Králová",
           "Jan Vaněk", "Tereza Bláhová", "Ondřej Marek", "Klára Petrová", "Filip Eduard",
           "Hana Volková", "Pavel Němec", "Markéta Šimková", "Radek Bartoš", "Eva Malá",
           "Jiří Konečný", "Barbora Jelínková", "Adam Šťastný", "Veronika Dušková", "Michal Rychlý",
           "Iva Sedláčková", "Lukáš Beneš", "Denisa Kopecká", "Vojtěch Havel", "Alena Fialová",
           "Karel Procházka", "Nikola Vávrová", "Tomáš Jelínek", "Simona Řeháková", "David Kříž",
           "Zuzana Bílková", "Patrik Černý", "Lenka Musilová", "Daniel Vlk", "Iveta Zemanová",
           "Robin Kvasnička", "Šárka Vlčková", "Aleš Kahoun", "Naděžda Šulcová", "Marek Toman"],
    "nb": ["Ingrid B.", "Lars H.", "Kari S.", "Erik Johansen", "Anne Lie", "Odd Nordmann",
           "Silje Aksnes", "Truls Moe", "Hanne Vik", "Bjørn Stølsmark", "Mari Foss", "Anders Dahl",
           "Nora Kvam", "Espen Rugland", "Thea Lunde", "Sindre Aas", "Live Berg", "Håkon Ruud",
           "Mia Solheim", "Jonas Fosse", "Ida Bakken"],
    "fallback": ["Anna K.", "Peter M.", "Sofia L.", "David R.", "Emma S.", "Thomas B.", "Lucia V.",
                 "Mark D.", "Nina P.", "Oskar H.", "Clara W.", "Viktor J.", "Ines T.", "Ruben F.",
                 "Maja N.", "Anton G."],
}
FEMALE_FIRST = {
    "it": {"Giulia","Elena","Chiara","Sara","Martina","Beatrice","Valentina","Roberta",
           "Francesca","Alessia","Ilaria","Camilla"},
    "cs": {"Jana","Lucie","Petra","Tereza","Klára","Hana","Markéta","Eva","Barbora","Veronika",
           "Iva","Denisa","Alena","Nikola","Simona","Naděžda","Šárka","Zdeňka","Jitka","Lenka",
           "Zuzana","Iveta"},
    "nb": {"Ingrid","Kari","Anne","Silje","Hanne","Mari","Nora","Thea","Live","Mia","Ida"},
    "fallback": {"Anna","Sofia","Emma","Lucia","Nina","Clara","Ines","Maja"},
}
MALE_FIRST = {
    "it": {"Marco","Luca","Davide","Alessandro","Federico","Simone","Stefano","Pietro","Matteo","Gabriele"},
    "cs": {"Tomáš","Martin","Jan","Ondřej","Filip","Pavel","Radek","Jiří","Adam","Michal","Lukáš",
           "Vojtěch","Karel","David","Patrik","Daniel","Robin","Aleš","Marek"},
    "nb": {"Lars","Erik","Odd","Truls","Bjørn","Anders","Espen","Sindre","Håkon","Jonas"},
    "fallback": {"Peter","David","Thomas","Mark","Oskar","Viktor","Ruben","Anton"},
}

NUM_BINS = {
    "reviews": [(400,900),(900,1500),(1500,2400),(2400,3400)],
    "users":   [(4000,9000),(9000,16000),(16000,26000),(26000,40000)],
    "latency": [(36,45),(45,52),(52,60),(60,70)],
    "ratings": ["4,5","4,6","4,7","4,8"],
}
CC_CURRENCY = {"JP": "JPY", "KR": "KRW", "IN": "INR", "BR": "BRL", "MX": "MXN",
               "PE": "PEN", "ZA": "ZAR", "NG": "NGN", "KE": "KES", "MY": "MYR",
               "SG": "SGD", "HK": "HKD", "PH": "PHP", "CA": "CAD", "AU": "AUD",
               "NZ": "NZD", "GB": "GBP", "IE": "EUR", "CH": "CHF", "TR": "TRY",
               "GE": "GEL", "AZ": "AZN", "IL": "ILS", "TH": "THB", "AE": "AED",
               "US": "USD", "CN": "CNY", "PL": "PLN", "CZ": "CZK", "HU": "HUF",
               "SE": "SEK", "NO": "NOK", "DK": "DKK", "RO": "RON", "BG": "BGN"}

LANG2CC = {"it":"IT","pl":"PL","cs":"CZ","sk":"SK","hu":"HU","nl":"NL","sl":"SI","de":"DE",
            "fr":"FR","es":"ES","pt":"PT","ro":"RO","bg":"BG","el":"GR","sv":"SE","da":"DK",
            "fi":"FI","nb":"NO","nn":"NO","et":"EE","lv":"LV","lt":"LT","en":"GB",
            "ja":"JP","ko":"KR","hi":"IN","ms":"MY","tl":"PH","zh":"CN","th":"TH",
            "he":"IL","ka":"GE","az":"AZ","uk":"UA","sr":"RS","hr":"HR","tr":"TR"}

# ---------------------------------------------------------------- helpers ----
def rng_from(seed:int)->random.Random: return random.Random(seed)
def load(p:pathlib.Path, default=None):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError: return default

def palettes()->list[dict]:
    raw=load(PALETTES_F,{})
    out=[]
    for p in raw.get("palettes",[]):
        dk=p.get("default_fonts"); f=raw.get("fonts",{}).get(dk,{})
        out.append({"id":p["id"],"theme":p.get("theme","light"),"vars":p["vars"],
                     "good_skins":p.get("good_skins",SKINS),
                     "font_pair":dk,"font_head":f.get("head",""),"font_body":f.get("body","")})
    return out

def regulator(lang:str, cc:str="")->dict|None:
    regs=(load(REG_F,{}) .get("regulators") or {})
    code=(cc or LANG2CC.get(lang,"")).upper()
    return {"country":code,**regs[code]} if code and code in regs else None

def load_history()->list[dict]:
    """Past plans in THIS product: plans/*.json, normalized."""
    out=[]
    for f in sorted(PLANS.glob("*.json")):
        d=load(f,{})
        if not isinstance(d,dict) or not d.get("params"): continue
        out.append({
            "domain": d["params"].get("domain",""),
            "brand": (d["params"].get("brand","") or "").lower(),
            "palette": d.get("design",{}).get("palette_id",""),
            "skin": d.get("design",{}).get("skin",""),
            "hero": d.get("layout",{}).get("hero",""),
            "order": d.get("layout",{}).get("section_order",[]),
            "variants": d.get("layout",{}).get("variants",{}) or {},
            "slugs": set((d.get("layout",{}).get("slugs",{}) or {}).values()),
            "inner": tuple(sorted(tuple(v) for v in (d.get("inner_pages") or {}).values())),
            "menu": tuple(d.get("layout",{}).get("menu",[]) or []),
            "widgets": set((d.get("widgets") or {}).values()),
            "combo": (d.get("design",{}).get("skin",""), d.get("design",{}).get("palette_id","")),
            "people": d.get("people",[]) or [],
            "photos": d.get("photos",[]) or [],
            "bins": (d.get("numbers",{}).get("reviews_bin"), d.get("numbers",{}).get("users_bin"),
                     tuple(d.get("numbers",{}).get("latency_bin") or ())),
            "blog_topics": [str(t.get("id") or "") for t in
                            ((d.get("blog") or {}).get("topics") or []) if isinstance(t, dict)],
        })
    return out

def seq_overlap(a:list,b:list)->float:
    n=min(len(a),len(b))
    return sum(1 for x,y in itertools.islice(zip(a,b),n) if x==y)/max(n,1)

def jac(a:set,b:set)->float:
    return len(a&b)/max(1,len(a|b))

def novel_need(hist:list)->int:
    """Required unseen section types: 3 normally, but never more than the pool allows."""
    near=set()
    for h in hist[-3:]:
        near |= types_of(h["order"])
    pool_types={TYPE_OF.get(t, t) for t in SECTION_POOL}   # hero + form band always present
    free=len(pool_types - near)
    return min(3, max(0, free))

def anchors_of(od:list)->set:
    return types_of(od) & set(ANCHOR_TYPES)

def rotating_anchors(od: list) -> set:
    """Anchor screens that must rotate. `people` is now on every offer (social proof),
    so it is structural and never counts as a shared/duplicated anchor."""
    return anchors_of(od) - {"people"}


def order_ok(od:list,hist:list,brand:str="")->bool:
    """Hard structural separation from the nearest plans and same-brand siblings."""
    types=types_of(od); anch=rotating_anchors(od)
    for h in hist[-3:]:
        if h["order"] and jac(types,types_of(h["order"]))>=0.65: return False
    for h in hist[:-3]:
        if h["order"] and jac(types,types_of(h["order"]))>=0.72: return False
    for h in hist[-2:]:
        if h["order"] and seq_overlap(od,h["order"])>=0.5: return False
    # anchors rotate: at most one shared with the previous plan or the last sibling
    if hist[-1:] and len(anch & rotating_anchors(hist[-1]["order"]))>1: return False
    sib=next((h for h in reversed(hist)
              if h.get("brand")==brand and h["order"] and h.get("domain")), None)
    if sib and len(anch & rotating_anchors(sib["order"]))>1: return False
    near=set()
    for h in hist[-3:]:
        near |= types_of(h["order"])
    if hist and len(types-near)<novel_need(hist): return False
    return True

def structure_score(od:list,hist:list,brand:str="")->float:
    types=types_of(od); anch=rotating_anchors(od); sc=0.0
    for h in hist[-3:]:
        if not h["order"]: continue
        sc+=1.0-jac(types,types_of(h["order"]))
        sc+=(1.0-seq_overlap(od,h["order"]))*0.6
    sc+=0.25*len(types-{t for h in hist[-1:] for t in types_of(h["order"])})
    sib=next((h for h in reversed(hist) if h.get("brand")==brand and h.get("order")), None)
    if sib:
        sc+=0.4*len(set(ANCHOR_TYPES)-rotating_anchors(sib["order"]))  # fresh anchors bonus
        sc-=0.6*len(anch & rotating_anchors(sib["order"]))            # shared screens penalty
    return sc

def bins_pick(rng,key,taken):
    bins=list(NUM_BINS[key]); rng.shuffle(bins)
    fresh=[b for b in bins if b not in taken]
    return (fresh or bins)[0]

# ---------------------------------------------------------------- builder ----
BLOG_HUB_POOLS = {
    "it": ["guide", "risorse", "approfondimenti"],
    "cs": ["pruvodce", "clanky", "zdroje"],
    "es": ["guias", "recursos", "articulos"],
    "en": ["guides", "resources", "insights"],
    "de": ["ratgeber", "ressourcen", "wissen"],
    "fr": ["guides", "ressources", "articles"],
    "pl": ["poradniki", "artykuly", "zasoby"],
    "pt": ["guias", "recursos", "artigos"],
    "fallback": ["guides", "resources", "insights"],
}


def build_blog_block(rng, args, hist: list, base_slugs: set[str] | None = None) -> dict | None:
    """3–5 article briefs + a structural style + a real hub slug.

    Topic ids used by the last five plans are skipped first, so a fleet does not
    publish the same guide over and over. Dates are fixed here (not by the model):
    they are deterministic, never in the future, and survive a rebuild.
    """
    raw = load(BLOG_TOPICS_F, {}) or {}
    bank = [t for t in (raw.get("topics") or []) if isinstance(t, dict) and t.get("id")]
    if not bank:
        return None
    used = {tid for h in hist[-5:] for tid in (h.get("blog_topics") or [])}
    fresh = [t for t in bank if t["id"] not in used]
    rng.shuffle(fresh)
    need = min(rng.randint(3, 5), len(bank))
    picks = fresh[:need]
    if len(picks) < need:
        # the recent plans already used most of the bank: fill from the least recently
        # used topics instead of shrinking the blog to one article
        last = {}
        for age, h in enumerate(reversed(hist)):
            for tid in (h.get("blog_topics") or []):
                last.setdefault(tid, age)
        rest = [t for t in bank if t not in picks]
        rng.shuffle(rest)
        rest.sort(key=lambda t: last.get(t["id"], 999), reverse=True)
        picks += rest[:need - len(picks)]
    style = rng.choice(["a", "b", "c"])
    pool = [s for s in BLOG_HUB_POOLS.get(args.lang, BLOG_HUB_POOLS["fallback"])
            if s not in (base_slugs or set())]
    hub_slug = (pool or BLOG_HUB_POOLS["fallback"])[0]
    today = datetime.date.today()
    topics = []
    for i, t in enumerate(picks):
        day = today - datetime.timedelta(days=rng.randint(4, 70) + i * 7)
        topics.append({"id": t["id"], "intent": t.get("intent", ""),
                       "angle": t.get("angle", ""), "keywords": t.get("keywords") or [],
                       "date": day.isoformat()})
    return {"enabled": True, "style": style, "hub_slug": hub_slug,
            "count": len(topics), "topics": topics}


ARCHETYPES = {"clear-operator", "calm-analyst", "quiet-desk", "market-observer"}
TONES = {"pragmatic", "plain", "sober", "factual"}
INNER_SKELETONS = {
    "about": [["page-intro", "editorial", "cta"], ["page-intro", "milestones", "editorial", "winrate", "cta"], ["page-intro", "manifest", "timeline", "principles", "cta"]],
    "contact": [["form-first", "hours", "map"], ["page-intro", "cards", "consult"], ["page-intro", "contact-grid", "office"]],
    "register": [["benefits", "core"], ["core", "points"], ["steps", "core", "mini-faq"]],
    "who": [["page-intro", "team-band", "features", "numbers", "cta"], ["page-intro", "pipeline", "compare", "cta"], ["page-intro", "stack", "figures", "cta"]],
}
MENU_POOLS = {
    "cs": [["Domů", "Program", "Technologie", "Kontakt"], ["Úvod", "Jak to funguje", "Motor", "Napište nám"], ["Domů", "O projektu", "Metoda", "Kontakt"]],
    "it": [["Home", "Panoramica", "Strumenti", "Aiuto"], ["Inizio", "Come funziona", "Motore", "Scrivici"], ["Home", "Metodo", "Piattaforma", "Supporto"], ["Home", "Programma", "Tecnologia", "Contatti"]],
    "es": [["Inicio", "Programa", "Tecnología", "Contacto"], ["Inicio", "Cómo funciona", "Método", "Escríbenos"],
           ["Inicio", "Quiénes somos", "Plataforma", "Soporte"], ["Inicio", "Proyecto", "Motor", "Contáctanos"]],
    "fallback": [["Home","About","Tech","Contact"],["Home","Method","Platform","Support"],["Home","About","Tools","Contact"]]
}
SLUG_POOLS = {
    "cs": {"about": ["o-nas", "o-projektu", "pribeh"], "contact": ["kontakt", "podpora", "spojeni"], "register": ["registrace", "ucet", "zalozit-ucet"], "who": ["pro-koho", "komu-pomahame", "profily", "uzivatele"]},
    "it": {"about": ["chi-siamo", "progetto", "programma", "redazione"], "contact": ["contatti", "parliamo", "scrivici", "supporto"], "register": ["accesso", "inizia", "iscrizione", "registrati"], "who": ["per-chi", "a-chi-serve", "profili", "utenti"]},
    "es": {"about": ["equipo", "quienes-somos", "sobre-nosotros", "proyecto"],
           "contact": ["contacto", "hablanos", "escribenos", "soporte"],
           "register": ["registro", "empezar", "crear-cuenta", "unete"],
           "who": ["para-quien", "a-quien-se-dirige", "perfiles", "usuarios"]},
    "fallback": {"about": ["about","project"], "who": ["who-its-for","audience","for-whom"],
                 "contact": ["contact","contacts"], "register": ["register","open-account"]}
}

def pick_people(rng, lang: str, hist: list) -> list:
    """Three personas for the plan: unused names first, then the least used ones.

    The old code took only the unused names, so once a long history used up the bank a
    plan shipped with a single persona (and the reviews section had nobody to show)."""
    nb = NAME_BANK.get(lang, NAME_BANK["fallback"])
    used = [n for h in hist for n in (h.get("people") or [])]
    counts = {n: used.count(n) for n in nb}
    fresh = [n for n in nb if counts[n] == 0]
    if len(fresh) < 3:
        fresh += sorted((n for n in nb if counts[n] > 0), key=lambda n: counts[n])
    return sorted(rng.sample(fresh, k=min(3, len(fresh))))


def pick_variant(rng, key: str, pool: list, hist: list, lookback: int = 3) -> str:
    """Variant that did not appear in the last `lookback` plans (falls back to the pool)."""
    recent = {(h.get("variants") or {}).get(key, "") for h in hist[-lookback:]}
    fresh = [v for v in pool if v not in recent]
    return rng.choice(fresh or pool)


def build_plan(rng, args, hist)->dict|None:
    last2=hist[-2:]
    # palette: ≠ neighbours, and (skin,palette) combo globally unused
    used_pal={h["palette"] for h in last2}
    used_combo={h["combo"] for h in hist}
    pals=[p for p in palettes()]
    pool=[p for p in pals if p["id"] not in used_pal
           and rng.choice(p["good_skins"]) is not None] or pals
    rng.shuffle(pool)
    chosen=None
    for p in pool:
        skin_opts=[s for s in p["good_skins"] if s not in {h["skin"] for h in last2}] or SKINS
        rng.shuffle(skin_opts)
        for s in skin_opts:
            if (s,p["id"]) not in used_combo:
                chosen=(p,s); break
        if chosen: break
    if not chosen:
        # paint budget (all skin+palette combos) is used up: reuse, but stay away
        # from the two neighbours — the caller logs this as a WARN, not a failure
        reused=True
        pool=[p for p in pals if p["id"] not in used_pal] or pals
        rng.shuffle(pool)
        for p in pool:
            s_opts=[s for s in p["good_skins"] if s not in {h["skin"] for h in last2}] or list(p["good_skins"]) or SKINS
            chosen=(p, s_opts[0]); break
        if not chosen: return None
    else:
        reused=False
    pal, skin=chosen

    # hero ≠ neighbours
    used_hero={h["hero"] for h in last2}
    hero=rng.choice(sorted(set(HEROES)-used_hero) or HEROES)

    # widgets: least-used across history, set must differ from every prior plan
    usage={g:{} for g in WIDGET_GROUPS}
    for h in hist:
        for g,opts in WIDGET_GROUPS.items():
            for o in opts:
                if o in h["widgets"]: usage[g][o]=usage[g].get(o,0)+1
    lastw = hist[-1]["widgets"] if hist else set()
    widgets={}
    for g,opts in WIDGET_GROUPS.items():
        ranked=sorted(opts,key=lambda o:(usage[g].get(o,0), opts.index(o)))
        fresh=[o for o in ranked if o not in lastw and o != "none"]
        pick=(fresh or ranked)[0]
        if pick=="none":
            demos=[o for o in ranked if o!="none"]
            if demos and rng.random()>0.25: pick=demos[0]
        widgets[g]=pick
    allsets={frozenset(h["widgets"]) for h in hist if h["widgets"]}
    tries=0
    while frozenset(widgets.values()) in allsets and tries<8:
        g=WIDGET_GROUPS[rng.choice(sorted(WIDGET_GROUPS))]
        widgets[g]=rng.choice(WIDGET_GROUPS[g]); tries+=1

    # calculator / pulse-sim are G3 draws, not permanent screens — the plan forces one
    # only when asked (--calculator on|off, --pulse on|off)
    if getattr(args, "calculator", "auto") == "on":
        widgets["G3"] = "calculator"
    elif getattr(args, "pulse", "auto") == "on":
        widgets["G3"] = "pulse-sim"
    elif getattr(args, "calculator", "auto") == "off" and widgets["G3"] == "calculator":
        widgets["G3"] = "demo-line"
    elif getattr(args, "pulse", "auto") == "off" and widgets["G3"] == "pulse-sim":
        widgets["G3"] = "demo-line"

    # section order: prefer slot TYPES unused by neighbours and same-brand siblings,
    # hard structural caps. hero + form band are the only fixed screens; everything
    # else rotates so no two offers share their screen set.
    neigh=hist[-3:]
    neigh_types={t for h in neigh for t in types_of(h["order"])}
    prev_types=types_of(hist[-1]["order"]) if hist and hist[-1]["order"] else set()
    brand=(args.brand or "").lower()
    sib=next((h for h in reversed(hist)
              if h.get("brand")==brand and h["domain"]!=args.domain and h["order"]), None)
    sib_types=types_of(sib["order"])-{"hero","band"} if sib else set()
    banned=prev_types|sib_types                      # screens these two already show
    pool_types={}
    for slot in SECTION_POOL:
        pool_types.setdefault(TYPE_OF.get(slot, slot), []).append(slot)
    novel=[t for t in pool_types if t not in banned]
    stale=[t for t in pool_types if t in banned]     # emergency filler only
    anchor_pool=[t for t in ANCHOR_TYPES if t not in banned]
    rng.shuffle(novel); rng.shuffle(stale); rng.shuffle(anchor_pool)
    order=None; best=None
    for attempt in range(80):
        relax=attempt>=40          # pools exhausted: reuse fillers, keep anchors fresh
        fillers=novel + (stale if relax else [])
        form_band=rng.choice(FORM_BANDS)
        od=["hero", form_band]
        # calculator / pulse-sim are G3 widgets: present only when G3 drew them
        if widgets["G3"] == "calculator": od.append("calculator")
        elif widgets["G3"] == "pulse-sim": od.append("pulse-sim")
        want=rng.randint(5,8)
        fresh_n=min(len(novel),max(novel_need(hist),rng.randint(3,5)))
        picked=novel[:fresh_n]+rng.sample(stale,k=min(len(stale),want-fresh_n)) if relax \
            else novel[:fresh_n]+[t for t in stale if t not in sib_types][:max(0,want-fresh_n)]
        rng.shuffle(picked)
        extras=[rng.choice(pool_types[t]) for t in picked]
        for s in extras:
            if s not in od: od.append(s)
        if widgets["G1"] in {"markets-strip","price-board","listino-rows","heatmap","tile-flip"} \
           and not ({"markets","ticker","ladder"} & {TYPE_OF.get(x,x) for x in od}):
            cand=[s for t in ("markets","ticker","ladder") for s in pool_types.get(t,[])
                  if relax or t not in banned]
            if cand: od.append(rng.choice(cand))
        # anchors: 2-3 recognisable screens, none shared with prev plan / sibling
        picked_a=anchor_pool[:rng.choice((2,2,3))]
        if len(picked_a)<2:              # anchor pool drained by long sibling chains
            rest=[t for t in ANCHOR_TYPES if t not in picked_a]
            rng.shuffle(rest); picked_a+=rest[:2-len(picked_a)]
        for a in picked_a:
            if a not in {TYPE_OF.get(x,x) for x in od}:
                od.append(rng.choice(pool_types[a]) if a in pool_types else a)
        # trust proof: social proof is not optional — every offer carries the reviews
        # screen (a site without a single review reads as a thin template)
        have={TYPE_OF.get(x,x) for x in od}
        if "people" not in have:
            od.insert(min(len(od), rng.randint(3, 8)), "people")
        if "scarcity" not in od and rng.random()<0.8: od.insert(rng.randrange(3,len(od)-2),"scarcity")
        # numbers and stats-intro are the same "stat screen" family: never both
        if "numbers" in od and "stats-intro" in od: od.remove("stats-intro")
        if rng.random()<0.6: od.append("brand-note")
        seen=set(); od=[x for x in od if not (x in seen or seen.add(x))][:16]
        if len(od)<10: continue
        if not ({"people","faq","facts","security","compare"} & set(od)): continue
        # the form band rotates: 35% right after the hero, 65% one to three screens deeper
        od.remove(form_band)
        pos=rng.choices((1,2,3,4),weights=(35,30,20,15))[0]
        od.insert(min(pos,max(1,len(od)-4)),form_band)
        score=structure_score(od,hist,brand)
        if best is None or score>best[0]: best=(score,od)
        if order_ok(od,hist,brand): order=od; break
    if order is None and best: order=best[1]
    if order is None: return None

    # vertical variants: most slots deviate from neighbours, canonical stays possible
    variants={}
    BAND_SLOTS = ("access-band", "claim-band", "enroll-band")

    def _hist_variant(h, slot):
        """Variant a plan used for this slot. The three form-band names render the SAME
        fragment family, so a sibling's 'claim-band: c' must block 'access-band: c'."""
        hv = h.get("variants") or {}
        if slot in hv:
            return hv.get(slot, "")
        if slot in BAND_SLOTS:
            for b in BAND_SLOTS:
                if b in hv:
                    return hv.get(b, "")
        return ""

    used_var={s:{_hist_variant(h, s) for h in hist[-3:]} for s in VARIANTS}
    for slot in order:
        opts=VARIANTS.get(slot)
        if not opts: continue
        pool=[v for v in opts if v not in used_var.get(slot,())]
        rng.shuffle(pool)
        if pool and rng.random()<0.8: variants[slot]=pool[0]
        elif rng.random()<0.45: variants[slot]=rng.choice(opts)

    # livebar strip: a second structural axis (not a page section, always present)
    variants["livebar"]=pick_variant(rng, "livebar", VARIANTS["livebar"], hist, 2)
    variants["logo"]=pick_variant(rng, "logo", VARIANTS["logo"], hist, 3)
    # header/footer are the shell every page repeats: keep them away from the last few
    # offers instead of only avoiding the single most recent plan
    variants["header"]=pick_variant(rng, "header", VARIANTS["header"], hist, 5)
    variants["footer"]=pick_variant(rng, "footer", VARIANTS["footer"], hist, 5)
    variants["form"]=pick_variant(rng, "form", VARIANTS["form"], hist, 2)
    # hero: the concept decides the fragment, so the label in layout.hero and what
    # assemble renders can never drift apart (they did: 7 concepts, 3 fragments)
    variants["hero"]=HERO_LETTER[hero]
    livebar=build_livebar(rng, variants["livebar"], args.lang,
                          (args.cc or LANG2CC.get(args.lang,"")).upper())
    # people-e is a rating-summary screen: same stat family as the numbers screen — never both
    if variants.get("people")=="e" and "numbers" in order: order.remove("numbers")
    def drop_slot(slot):
        """Remove a screen AND its variant — a variant for a missing slot fails assembly."""
        if slot in order:
            order.remove(slot)
        variants.pop(slot, None)

    # calculator prints the intro heading (sections.intro.h2/lead): two intro screens
    # on one page would repeat the same paragraph verbatim
    if "calculator" in order:
        for extra in [s for s in ("intro-center", "intro", "stats-intro") if s in order]:
            drop_slot(extra)
    # one Q/A screen per page: faq, mini-faq and compare all bind faq.items —
    # two of them on one page read as a duplicated block (seen live)
    for extra in [s for s in ("faq", "compare", "mini-faq") if s in order][1:]:
        drop_slot(extra)
    # exclusions above may shorten the order below the structural minimum — top up
    if len(order)<10:
        for s in ("notes","ticker","streams","glance","timeline"):
            if s not in order: order.append(s)
            if len(order)>=10: break
    # module screens (portal, facts) sit in the filler pool, so the same "what the
    # platform gives you" block showed up on offer after offer — rotate them against
    # the two previous plans and the same-brand sibling
    _recent = set()
    for _h in hist[-2:]:
        _recent |= set(_h.get("order") or [])
    _sib = next((_h for _h in reversed(hist)
                 if _h.get("brand") == args.brand.lower() and _h.get("order")), None)
    if _sib:
        _recent |= set(_sib["order"])
    for _slot in ("portal", "facts"):
        if _slot not in order or _slot not in _recent:
            continue
        # first choice: a filler nobody used recently; fallback: any filler not on the
        # page yet (a repeat further back is better than the same block everywhere)
        for _pool in ([a for a in ("streams", "notes", "glance", "timeline", "ticker", "ladder")
                       if a not in _recent],
                      ("streams", "notes", "glance", "timeline", "ticker", "ladder")):
            _done = False
            for _alt in _pool:
                if _alt in order:
                    continue
                if _slot == "facts" and not ({"faq", "people", "security", "compare"} & set(order)):
                    _done = True
                    break            # facts may be the only trust screen on the page
                order[order.index(_slot)] = _alt
                _done = True
                break
            if _done:
                break

    # dedupe pass above can swallow anchors (compare dropped next to faq, numbers
    # dropped next to people-e). Assemble refuses a page with fewer than two, so make
    # sure the order always carries them instead of failing at the very end.
    def _anchors():
        return [t for t in order if t in ANCHOR_TYPES]

    if len(_anchors()) < 2:
        for cand in ("numbers", "people", "office", "cta", "compare"):
            if cand in order: continue
            if cand == "compare" and ("faq" in order or "mini-faq" in order): continue
            if cand == "numbers" and "stats-intro" in order: continue
            if len(order) >= 18:                      # keep the 10..18 budget
                for filler in ("streams", "notes", "ticker", "glance", "timeline"):
                    if filler in order and filler not in ANCHOR_TYPES:
                        drop_slot(filler)
                        break
                else:
                    break
            order.append(cand)
            if len(_anchors()) >= 2: break

    inner={pg:rng.choice(v) for pg,v in sorted(INNER_SKELETONS.items())}
    for _ in range(10):
        sig=tuple(sorted(tuple(v) for v in inner.values()))
        if all(sig!=h["inner"] for h in hist[-2:] if h["inner"]): break
        inner={pg:rng.choice(v) for pg,v in sorted(INNER_SKELETONS.items())}
    menus=list(MENU_POOLS.get(args.lang,MENU_POOLS["fallback"]))
    freshm=[m for m in menus if tuple(m) not in {h["menu"] for h in hist[-2:]}]
    menu=rng.choice(freshm or menus)
    spool=dict(SLUG_POOLS.get(args.lang,SLUG_POOLS["fallback"]))
    used_all={sl for h in hist for sl in h["slugs"]}
    used_sets=[h["slugs"] for h in hist if h["slugs"]]
    def pick_slugs():
        out={}
        for pg,opts in sorted(spool.items()):
            fresh=[o for o in sorted(opts) if o not in used_all]
            out[pg]=rng.choice(fresh or sorted(opts))
        return out
    slugs=pick_slugs()
    for _ in range(12):
        if set(slugs.values()) not in used_sets: break
        slugs=pick_slugs()

    # numbers from bins ≠ previous plans' bins
    def _bin(v):
        return tuple(v) if isinstance(v, list) else (v or ())
    taken_r={_bin(h["bins"][0]) for h in hist}; taken_u={_bin(h["bins"][1]) for h in hist}
    taken_l={_bin(h["bins"][2]) for h in hist if len(h["bins"])>2 and h["bins"][2]}
    rb=bins_pick(rng,"reviews",taken_r); ub=bins_pick(rng,"users",taken_u)
    lb=bins_pick(rng,"latency",taken_l)
    _rating = rng.choice(sorted(NUM_BINS["ratings"]))
    if not decimal_comma(args.lang):
        _rating = _rating.replace(",", ".")      # 4,7 → 4.7 on en/ja/zh offers
    numbers={"rating":_rating,"reviews":rng.randint(*rb),
              "reviews_bin":list(rb),"users":rng.randint(*ub),"users_bin":list(ub),
              "latency_ms":round(rng.uniform(*lb)),"latency_bin":[round(lb[0]),round(lb[1])]}

    # personas + portraits (fresh names while the bank has them)
    people=pick_people(rng,args.lang,hist)
    bank=sorted(PEOPLE_DIR.glob("p-*.jpg")) if PEOPLE_DIR.exists() else []
    used_ph={ph for h in hist for ph in h["photos"]}
    free=[f.name for f in bank if f.name not in used_ph] or [f.name for f in bank]
    # pair portraits by gender: women's names get p-women-*, others p-men-*
    fem=FEMALE_FIRST.get(args.lang,FEMALE_FIRST["fallback"])
    def _is_woman(n): return n.split()[0].split("-")[0] in fem
    idx_w=[i for i,n in enumerate(people) if _is_woman(n)]
    idx_m=[i for i in range(len(people)) if i not in idx_w]
    pw=[f for f in free if f.startswith("p-women")]; pm=[f for f in free if f.startswith("p-men")]
    rng.shuffle(pw); rng.shuffle(pm)
    photos=[""]*len(people)
    for i,idx in enumerate(idx_w+idx_m):
        pool=pw if i<len(idx_w) else pm
        if not pool: pool=(pm or pw)
        if pool: photos[idx]=pool.pop()
    if any(p=="" for p in photos):
        photos=sorted(rng.sample(free,k=min(len(people),len(free))))

    plan = {
        "seed":args.seed, "product":"static-create-sites",
        "params":{"brand":args.brand,"geo":args.geo,"geo_short":(args.cc or LANG2CC.get(args.lang,"")).upper(),
            "lang":args.lang,"locale":f"{args.lang}-{(args.cc or LANG2CC.get(args.lang,args.lang.upper())).upper()}",
            "domain":args.domain,"currency":args.currency,"cc":(args.cc or LANG2CC.get(args.lang,"")).upper()},
        "identity":{"archetype":rng.choice(sorted(ARCHETYPES)),"tone":rng.choice(sorted(TONES))},
        "_combo_reused":reused,
        "regulator":regulator(args.lang, args.cc or ""),
        "design":{"palette_id":pal["id"],"theme":pal["theme"],"skin":skin,
                   "font_pair":pal["font_pair"],"fonts":{"head":pal["font_head"],"body":pal["font_body"]}},
        "layout":{"hero":hero,"section_order":order,"variants":variants,"menu":menu,"slugs":slugs},
        "structure":{"order_hash":hashlib.sha1(("|".join(order)).encode()).hexdigest()[:10],
                      "variant_hash":hashlib.sha1(("|".join(f"{k}:{v}" for k,v in sorted(variants.items()))).encode()).hexdigest()[:10],
                      "novel_slots":sorted(set(order)-{t for h in hist[-1:] for t in h["order"]})},
        "inner_pages":inner,"widgets":widgets,"numbers":numbers,"people":people,"photos":photos,
        "livebar":livebar,
        "content_hint":f"content/{args.domain}-content.json",
    }
    if getattr(args, "blog", False):
        bl = build_blog_block(rng, args, hist, set(plan["layout"]["slugs"].values()))
        if bl:
            plan["blog"] = bl
    if widgets["G3"] == "pulse-sim":
        plan["pulse_sim"] = build_pulse_sim(rng, args.lang)
    return plan

# --------------------------------------------------------------- livebar ------
def _fmt_num(v: float, lang: str, dec: int = 2) -> str:
    comma = decimal_comma(lang)
    space = lang in ("cs", "pl", "fr", "ru", "uk", "sv", "fi", "no", "nb",
                     "da", "sl", "hr", "hu", "lv", "lt", "et", "sk")
    whole = " " if space else ("." if comma else ",")
    body = f"{v:,.{dec}f}"
    return (body.replace(",", "T").replace(".", "D")
                .replace("T", whole).replace("D", "," if comma else "."))


# Instrument ranges per tape variant: (symbol, lo, hi, decimals).
# b–j = family Q (dark quelton-style tape), k–y = family L (light ledger strip).
def _livebar_data(variant: str) -> list:
    sets = {
        "a": [("BTC/EUR", 42_000, 61_000, 0), ("ETH/EUR", 1_900, 3_300, 0),
              ("DAX 40", 17_200, 19_400, 0), ("FTSE MIB", 32_400, 34_900, 0),
              ("Brent", 72, 93, 2), ("EUR/USD", 1.05, 1.12, 4)],
        "b": [("EUR/USD", 1.05, 1.12, 4), ("GBP/USD", 1.24, 1.30, 4),
              ("USD/JPY", 141, 154, 2), ("EUR/GBP", 0.84, 0.88, 4),
              ("USD/CHF", 0.88, 0.93, 4), ("AUD/USD", 0.63, 0.68, 4)],
        "c": [("BTC/EUR", 42_000, 61_000, 0), ("ETH/EUR", 1_900, 3_300, 0),
              ("SOL/EUR", 125, 195, 2), ("XRP/EUR", 0.41, 0.79, 4),
              ("ADA/EUR", 0.31, 0.58, 4), ("DOT/EUR", 5.2, 8.9, 2)],
        "d": [("FTSE MIB", 32_400, 34_900, 0), ("DAX 40", 17_200, 19_400, 0),
              ("CAC 40", 7_300, 7_900, 0), ("IBEX 35", 10_300, 11_100, 0),
              ("S&P 500", 5_100, 5_400, 0), ("NASDAQ 100", 18_100, 18_900, 0)],
        "e": [("Brent", 72, 93, 2), ("WTI", 67, 89, 2), ("Gas TTF", 26, 44, 2),
              ("Oro", 2_120, 2_480, 0), ("Argento", 24, 31, 2), ("Rame", 3.9, 4.7, 2)],
        "k": [("BTC/EUR", 42_000, 61_000, 0), ("DAX 40", 17_200, 19_400, 0),
              ("FTSE MIB", 32_400, 34_900, 0), ("S&P 500", 5_100, 5_400, 0),
              ("EUR/USD", 1.05, 1.12, 4), ("Oro", 2_120, 2_480, 0)],
        "l": [("EUR/USD", 1.05, 1.12, 4), ("EUR/GBP", 0.84, 0.88, 4),
              ("EUR/CHF", 0.93, 0.99, 4), ("EUR/JPY", 155, 172, 2),
              ("EUR/PLN", 4.21, 4.36, 4), ("EUR/CZK", 24.9, 25.5, 2)],
        "s": [("DOGE/EUR", 0.12, 0.25, 4), ("LINK/EUR", 11.2, 18.6, 2),
              ("AVAX/EUR", 28, 44, 2), ("ATOM/EUR", 6.2, 10.8, 2),
              ("NEAR/EUR", 4.1, 8.7, 2), ("ARB/EUR", 0.71, 1.28, 4)],
        "p": [("FTSE MIB", 32_400, 34_900, 0), ("SOL/EUR", 125, 195, 2),
              ("TTF", 26, 44, 2), ("CAC 40", 7_300, 7_900, 0),
              ("XRP/EUR", 0.41, 0.79, 4), ("Brent", 72, 93, 2)],
        "q": [("Brent", 72, 93, 2), ("WTI", 67, 89, 2), ("Gas TTF", 26, 44, 2),
              ("PSV", 88, 118, 2), ("CO2 EUA", 62, 79, 2), ("Carbone", 96, 128, 2)],
        "r": [("Oro", 2_120, 2_480, 0), ("Argento", 24, 31, 2), ("Platino", 890, 1_010, 0),
              ("Palladio", 910, 1_090, 0), ("Rame", 3.9, 4.7, 2), ("Oro/Argento", 81, 92, 1)],
    }.get(variant, [])
    return sets


def _spark_points(rng, up: bool) -> str:
    """Polyline points for a tiny livebar sparkline (viewBox 0 0 54 16)."""
    y = 11 if up else 5
    pts = []
    for x in range(0, 55, 9):
        y = max(2, min(14, y + rng.randint(-3, 3) + (-1 if up else 1)))
        pts.append(f"{x},{y}")
    return " ".join(pts)


def build_livebar(rng, variant: str, lang: str, geo_short: str) -> dict:
    """Content for the top strip variant; words are localised, numbers are seeded.

    Token contract for every blk-livebar fragment (a + b..y):
      {{LB_LIVE}}                    strip label next to the marker
      {{LB_S1K}}..{{LB_S3K}} / V    up to three static stats (key/value)
      {{LB1S}}..{{LB6S}} / V / C / D six tape items (label, value, change, dir class)
      {{LB1SP}}..{{LB6SP}}            sparkline polyline points (variant z only)
      {{LB1VOL}}..{{LB6VOL}}          volume tag (variant ab only)
      {{LB_NEWS1}}..{{LB_NEWS4}}     news headlines (content pack may override)
      {{GEO_SHORT}}                  global token (plan param)
    """
    L = LIVEBAR_L10N.get(lang) or LIVEBAR_L10N["en"]
    comma = decimal_comma(lang)

    def num(lo, hi, dec=2):
        return _fmt_num(rng.uniform(lo, hi), lang, dec)

    def api_uptime():
        return _fmt_num(99.9 + rng.randint(1, 9) / 100, lang, 2) + "%"

    def chg(lo=-1.2, hi=2.4, dec=2):
        c = rng.uniform(lo, hi)
        return (f"{c:+.{dec}f}".replace(".", "," if comma else "."),
                "up" if c >= 0 else "dn")

    def q_six(data):
        """Six quote rows from (symbol, lo, hi, dec) tuples."""
        rows = []
        for sym, lo, hi, dec in data:
            c, d = chg()
            rows.append((sym, num(lo, hi, dec), c, d))
        return rows

    hh, mm = rng.randint(8, 17), rng.randint(0, 59)
    clock = f"{hh:02d}:{mm:02d}"
    stats, items, live, extra = [], [], L["live"], {}

    if variant in ("a", "k"):
        items = q_six(_livebar_data(variant))
        stats = [(L["latency"], f"{rng.randint(28, 62)} ms"), ("API", api_uptime()),
                 (L["orders"], f"{rng.randint(1_800, 4_200):,}".replace(",", " "))]
    elif variant == "b":
        items = q_six(_livebar_data("b"))
        live = L["fx"]
        stats = [(L["spread"], f"{num(0.0, 0.8, 1)} pip"), ("API", api_uptime()),
                 (L["orders"], f"{rng.randint(1_800, 4_200):,}".replace(",", " "))]
    elif variant == "c":
        items = q_six(_livebar_data("c"))
        live = f"{L['crypto']} · 24/7"
        stats = [(L["volume"], f"{num(0.8, 4.0, 1)} Mld"), ("API", api_uptime()),
                 (L["orders"], f"{rng.randint(1_800, 4_200):,}".replace(",", " "))]
    elif variant == "d":
        items = q_six(_livebar_data("d"))
        live = L["indices"]
        stats = [(L["spread"], f"{num(0.0, 1.2, 1)} pt"), ("API", api_uptime()),
                 (L["orders"], f"{rng.randint(1_800, 4_200):,}".replace(",", " "))]
    elif variant == "e":
        items = q_six(_livebar_data("e"))
        live = L["commod"]
        stats = [(L["source"], "flow int."), ("API", api_uptime()),
                 (L["volume"], f"{num(0.4, 2.2, 1)} Mld")]
    elif variant == "f":
        live = L["news_tag"]
        news = list(L["news"])[:4]
        extra = {f"LB_NEWS{i+1}": t for i, t in enumerate(news)}
        items = [(t, clock, "", "") for i, t in enumerate(news)] \
              + [("", "", "", ""), ("", "", "", "")]
        stats = [(L["updated"], clock), ("API", api_uptime()), ("", "")]
    elif variant == "g":
        live = L["sessions"]
        offsets = [9, 10, 0, 1, -5, 1]
        states = [("open", "up"), ("closed", "dn"), ("preopen", ""), ("open", "up"),
                  ("closed", "dn"), ("preopen", "")]
        for city, off, (st, cls) in zip(L["cities"], offsets, states):
            lt = (hh + off) % 24
            items.append((city, f"{lt:02d}:{mm:02d}", L[st], cls))
        stats = [("Sessioni aperte", str(rng.randint(1, 4))), (L["updated"], clock), ("", "")]
    elif variant == "h":
        live = L["sentiment"]
        pct = rng.randint(30, 75)
        fg = L["greed"] if pct >= 50 else L["fear"]
        longs, shorts = rng.randint(50, 65), 100 - rng.randint(50, 65)
        items = [("Fear & Greed", str(pct), fg, "up" if pct >= 50 else "dn"),
                 ("Long/Short", f"{longs} / {100 - longs}", "", ""),
                 ("VIX", num(11, 22, 1), L["volatility"], ""),
                 ("Bull ratio", num(0.4, 0.7, 2), "", ""),
                 ("Funding", f"{num(0.005, 0.05, 3)}%", "", ""),
                 ("Spread BTP–Bund", f"{rng.randint(90, 160)} bp", "", "")]
        stats = [(L["updated"], clock), ("API", api_uptime()), ("", "")]
    elif variant == "i":
        live = L["system"]
        pct = rng.randint(52, 99)
        items = [(L["platform"], "ONLINE", "99", "up"),
                 (L["gateway"], f"99,9{rng.randint(1, 9)}%", "100", "up"),
                 (L["support"], f"< {rng.randint(2, 9)} min", "", ""),
                 (L["queue"], str(rng.randint(14, 48)), "", ""),
                 (L["slots"], str(rng.randint(3, 9)), "", ""),
                 ("Verifiche/giorno", f"{rng.randint(700, 1_500):,}".replace(",", "."), "", "")]
        stats = [("Uptime", api_uptime()), (L["latency"], f"{rng.randint(28, 62)} ms"), ("", "")]
    elif variant == "j":
        live = "LIVE"
        items = q_six(_livebar_data("a"))[:4]
        stats = [("", ""), ("", ""), ("", "")]
    elif variant == "l":
        items = q_six(_livebar_data("l"))
        live = f"{L['fx']} · EUR"
        stats = [(L["spread"], f"{num(0.0, 0.8, 1)} pip"), (L["updated"], clock), ("", "")]
    elif variant == "m":
        live = L["bonds"]
        bonds = [("BTP 10Y", 3.6, 4.2, 3), ("Bund 10Y", 1.9, 2.6, 3), ("OAT 10Y", 2.7, 3.2, 3),
                 ("Bonos 10Y", 3.1, 3.6, 3), ("Gilt 10Y", 3.5, 4.3, 3), ("UST 10Y", 4.0, 4.5, 3)]
        for sym, lo, hi, dec in bonds:
            v = num(lo, hi, dec) + "%"
            bp = rng.randint(1, 9)
            items.append((sym, v, f"{'+' if rng.random() < .5 else '−'}{bp} bp",
                          "up" if bp <= 4 else "dn"))
        stats = [("BTP–Bund", f"{rng.randint(90, 160)} bp"), (L["updated"], clock), ("", "")]
    elif variant == "n":
        live = L["macro"]
        items = [("Tasso BCE", f"{num(3.5, 4.5, 2)}%", "", ""), ("Infl. eurozona", f"{num(1.8, 3.2, 1)}%", "", ""),
                 ("PMI", num(48, 53, 1), "", ""), ("Disoccupazione", f"{num(6.2, 7.8, 1)}%", "", ""),
                 ("GDP", f"+{num(0.1, 1.2, 1)}%", "up", "up"), ("Spread", f"{rng.randint(90, 160)} bp", "", "")]
        stats = [(L["updated"], clock), ("API", api_uptime()), ("", "")]
    elif variant == "o":
        live = L["calendar"]
        times = [f"{rng.randint(8, 16):02d}:{rng.choice(['00', '15', '30', '45'])}" for _ in range(4)]
        items = [(ev, t, "", "") for ev, t in zip(L["calendar_events"][:4], times)]
        stats = [("Sessioni aperte", str(rng.randint(1, 4))), (L["updated"], clock), ("", "")]
    elif variant == "p":
        live = L["movers"]
        data = _livebar_data("p")
        up = data[:3]
        dn = data[3:]
        for sym, lo, hi, dec in up:
            c = rng.uniform(1.5, 4.8)
            items.append((sym, num(lo, hi, dec), f"+{c:.2f}".replace(".", ","), "up"))
        for sym, lo, hi, dec in dn:
            c = rng.uniform(1.5, 4.8)
            items.append((sym, num(lo, hi, dec), f"−{c:.2f}".replace(".", ","), "dn"))
        stats = [(L["updated"], clock), ("API", api_uptime()), ("", "")]
    elif variant == "q":
        items = q_six(_livebar_data("q"))
        live = L["energy"]
        stats = [(L["source"], "flow int."), ("API", api_uptime()), ("", "")]
    elif variant == "r":
        items = q_six(_livebar_data("r"))
        live = L["metals"]
        stats = [(L["volume"], f"{num(0.2, 1.6, 1)} Mld"), (L["updated"], clock), ("", "")]
    elif variant == "s":
        items = q_six(_livebar_data("s"))
        live = L["altcoin"]
        stats = [(L["volume"], f"{num(0.8, 4.0, 1)} Mld"), ("API", api_uptime()),
                 (L["orders"], f"{rng.randint(1_800, 4_200):,}".replace(",", " "))]
    elif variant == "t":
        live = L["throughput"]
        items = [("Tick/s", f"{rng.randint(28, 46)}k", "", ""), ("Punti dati/s", f"{rng.randint(2, 4)}k", "", ""),
                 ("Uptime", api_uptime(), "", ""), ("Motori dati", str(rng.randint(6, 9)), "", ""),
                 ("Latenza", f"{rng.randint(28, 62)} ms", "", ""), ("Code attive", str(rng.randint(2, 6)), "", "")]
        stats = [("Uptime", api_uptime()), (L["latency"], f"{rng.randint(28, 62)} ms"), ("", "")]
    elif variant == "u":
        live = L["clocks"]
        offsets = [9, 10, 0, 1, -5, 1]
        for city, off in zip(L["cities"], offsets):
            lt = (hh + off) % 24
            items.append((city, f"{lt:02d}:{mm:02d}", f"UTC{off:+d}", ""))
        stats = [("UTC", f"{hh:02d}:{mm:02d}"), ("Sessioni aperte", str(rng.randint(1, 4))), ("", "")]
    elif variant == "v":
        live = L["earnings"]
        times = [f"{rng.randint(8, 16):02d}:{rng.choice(['00', '30'])}" for _ in range(4)]
        items = [(co, t, L["report"], "") for co, t in zip(L["earnings_co"][:4], times)]
        stats = [("Trimestre", f"Q{rng.randint(1, 4)}"), (L["updated"], clock), ("", "")]
    elif variant == "w":
        live = L["history"]
        items = [(t, "", "", "") for t in L["history_facts"][:4]]
        stats = [(L["updated"], clock), ("", ""), ("", "")]
    elif variant == "x":
        live = L["volatility"]
        meters = [("BTC", 2.1, 4.5), ("DAX 40", 0.5, 1.3), ("Oro", 0.4, 1.1),
                  ("EUR/USD", 0.2, 0.6), ("NASDAQ", 0.9, 2.0), ("Brent", 0.8, 2.2)]
        for sym, lo, hi in meters:
            vol = rng.uniform(lo, hi)
            items.append((sym, f"{num(vol, vol, 1)} %", str(int(vol * 18)), ""))
        stats = [("VIX", num(11, 22, 1)), (L["updated"], clock), ("", "")]
    elif variant == "y":
        live = L["verified"]
        names = NAME_BANK.get(lang, NAME_BANK["fallback"])
        picked = rng.sample(names, 6)
        for nm in picked:
            items.append((nm, f"★ {num(4.5, 5.0, 1)}", L["verified"], "up"))
        stats = [(L["media"], num(4.6, 4.9, 1)), (L["recensioni"], f"{rng.randint(480, 980):,}".replace(",", ".")), ("", "")]

    elif variant in ("z", "aa", "ab", "ac"):
        # structural 2.0 family (searched production patterns): z = TradingView-style
        # sparkline tape, aa = Beamline-style flash tape (app.js nudges prices),
        # ab = Bloomberg-style volume + arrows, ac = static chip strip (no motion).
        items = q_six(_livebar_data("b" if variant in ("z", "aa") else "k"))
        live = L["fx"] if variant != "ac" else L["movers"]
        stats = [(L["spread"], f"{num(0.0, 0.8, 1)} pip"), ("API", api_uptime()),
                 (L["orders"], f"{rng.randint(1_800, 4_200):,}".replace(",", " "))]
        if variant == "z":
            for i, it in enumerate(items):
                extra[f"LB{i+1}SP"] = _spark_points(rng, it[3] == "up")
        elif variant == "ab":
            for i in range(6):
                extra[f"LB{i+1}VOL"] = f"Vol {rng.choice([12, 24, 38, 46, 61, 87])}M"

    elif variant in ("ad", "ae"):
        # compact one-line macro strip: n's figures without the stacked meters
        live = L["macro"]
        items = [("Tasso BCE", f"{num(3.5, 4.5, 2)}%", "", ""), ("Infl. eurozona", f"{num(1.8, 3.2, 1)}%", "", ""),
                 ("PMI", num(48, 53, 1), "", ""), ("Disoccupazione", f"{num(6.2, 7.8, 1)}%", "", ""),
                 ("GDP", f"+{num(0.1, 1.2, 1)}%", "up", "up"), ("Spread", f"{rng.randint(90, 160)} bp", "", "")]
        stats = [(L["updated"], clock), ("API", api_uptime()), ("", "")]
    elif variant == "af":
        live = L["live"]
        items = q_six(_livebar_data("a"))
        stats = [(L["latency"], f"{rng.randint(28, 62)} ms"), ("API", api_uptime()),
                 (L["orders"], f"{rng.randint(1_800, 4_200):,}".replace(",", " "))]

    subs = {"LB_LIVE": live, "GEO_SHORT": geo_short}
    for i in range(3):
        k, v = stats[i] if i < len(stats) else ("", "")
        subs[f"LB_S{i+1}K"] = k
        subs[f"LB_S{i+1}V"] = v
    for i in range(6):
        it = items[i] if i < len(items) else ("", "", "", "up")
        subs[f"LB{i+1}S"], subs[f"LB{i+1}V"], subs[f"LB{i+1}C"], subs[f"LB{i+1}D"] = it
    subs.update(extra)
    return {"variant": variant, "subs": subs}


# ------------------------------------------------------------- pulse-sim -----
# Instruments for the G3 market-pulse simulator. Prices are illustrative,
# seeded per plan (JS redraws from data-price/data-seed; nothing is live).
PULSE_ASSETS = [  # (tag, symbol, lo, hi, decimals)
    ("SPX", "S&P 500", 5_700, 6_300, 2),
    ("FX", "EUR / USD", 1.05, 1.12, 4),
    ("XAU", "GOLD", 2_120, 2_680, 2),
    ("CRYPTO", "BTC / USD", 57_000, 98_000, 2),
]

def build_pulse_sim(rng, lang: str) -> dict:
    """Token subs for blk-pulse-sim.html: localized words + seeded instrument prices.

    Token contract: {{PS_EYEBROW}} {{PS_H2}} {{PS_TITLE}} {{PS_LIVE_NOTE}}
      {{PS_R1..R3}} range tabs, {{PS_A1..A4_{SYM,TAG,NAME,PRICE,DEC,SEED}}}.
    data-price stays dot-formatted so JS parseFloat always parses it.
    """
    L = PULSE_L10N.get(lang) or PULSE_L10N["en"]
    seeds = rng.sample(range(3, 99), len(PULSE_ASSETS))
    subs = {
        "PS_EYEBROW": rng.choice(sorted(L["eyebrows"])),
        "PS_H2": rng.choice(sorted(L["h2"])),
        "PS_TITLE": L["title"],
        "PS_NOTE": L["note"], "PS_LIVE_NOTE": L["note"],
        "PS_R1": L["r1"], "PS_R2": L["r2"], "PS_R3": L["r3"],
    }
    for i, (tag, sym, lo, hi, dec) in enumerate(PULSE_ASSETS, start=1):
        name = L["gold"] if tag == "XAU" else sym
        subs[f"PS_A{i}_SYM"] = name
        subs[f"PS_A{i}_TAG"] = tag
        subs[f"PS_A{i}_NAME"] = name
        subs[f"PS_A{i}_PRICE"] = f"{rng.uniform(lo, hi):.{dec}f}"
        subs[f"PS_A{i}_DEC"] = str(dec)
        subs[f"PS_A{i}_SEED"] = str(seeds[i - 1])
    return {"subs": subs}


# ---------------------------------------------------------------- validate ---
def validate(plan,hist)->list[str]:
    errs=[]; last2=hist[-2:]
    ws=frozenset(plan["widgets"].values())
    for h in hist:
        if h["widgets"] and ws==frozenset(h["widgets"]):
            errs.append(f"widget set equals {h['domain']}"); break
    if any(h["palette"]==plan["design"]["palette_id"] for h in last2): errs.append("palette repeats neighbour")
    if any(h["skin"]==plan["design"]["skin"] for h in last2): errs.append("skin repeats neighbour")
    # shell = header + footer: identical shell on consecutive offers is the most visible
    # similarity a visitor notices (every page repeats it)
    shell=(plan["layout"]["variants"].get("header",""),plan["layout"]["variants"].get("footer",""))
    for h in hist[-3:]:
        hv=h.get("variants") or {}
        if shell[0] and (hv.get("header",""),hv.get("footer",""))==shell:
            errs.append(f"header+footer shell repeats {h['domain']}"); break
    # NOTE: skin+palette combo reuse is NOT an error any more (paint budget of
    # 90 combos exhausts at site #91) — gen_plan logs it as a WARN instead
    if last2 and all(seq_overlap(plan["layout"]["section_order"],h["order"])>=0.6 for h in last2):
        errs.append("section order too close")
    used_people={n for h in hist for n in h["people"]}
    bank_size=len(NAME_BANK.get(plan["params"]["lang"],NAME_BANK["fallback"]))
    if len(used_people)+3<=bank_size and used_people & set(plan["people"]):
        errs.append("persona reused")
    lay=plan["layout"]; types=types_of(lay["section_order"])
    if "people" not in lay["section_order"]:
        errs.append("no reviews screen (people) — social proof is required")
    if len(rotating_anchors(lay["section_order"])) < 1:
        errs.append("no rotating anchor besides people")
    if len([t for t in lay["section_order"] if t in ("faq", "compare", "mini-faq")]) > 1:
        errs.append("more than one Q/A screen")
    if "numbers" in lay["section_order"] and "stats-intro" in lay["section_order"]:
        errs.append("numbers and stats-intro together")
    for h in hist[-3:]:
        if h["order"] and jac(types,types_of(h["order"]))>=0.65:
            errs.append(f"section inventory too close to {h['domain']}"); break
    for h in hist[:-3]:
        if h["order"] and jac(types,types_of(h["order"]))>=0.72:
            errs.append(f"section inventory too close to older plan {h['domain']}"); break
    near=set()
    for h in hist[-3:]:
        near |= types_of(h["order"])
    if hist and len(types-near)<novel_need(hist): errs.append("too few section types unused nearby")
    sib=next((h for h in reversed(hist)
              if h.get("brand")==plan["params"]["brand"].lower()
              and h["domain"]!=plan["params"]["domain"] and h["order"]), None)
    if sib:
        shared=anchors_of(types) & anchors_of(types_of(sib["order"]))
        if len(shared)>1:
            errs.append(f"sibling shares screens {sorted(shared)} with {sib['domain']}")
        if seq_overlap(lay["section_order"],sib["order"])>=0.5:
            errs.append(f"section order too close to sibling {sib['domain']}")
    if hist and set(lay["slugs"].values())==hist[-1]["slugs"]: errs.append("slug set equals previous plan")
    if any(set(lay["slugs"].values())==h["slugs"] for h in hist[:-1]): errs.append("slug set used before")
    sig=tuple(sorted(tuple(v) for v in plan["inner_pages"].values()))
    if any(sig==h["inner"] for h in hist[-2:] if h["inner"]): errs.append("inner skeletons repeat neighbour")
    if hist and tuple(lay["menu"])==hist[-1]["menu"]: errs.append("menu wording repeats neighbour")
    if hist and plan["widgets"]==hist[-1]["widgets"]: errs.append("widgets repeat neighbour")
    var=lay.get("variants") or {}
    if hist and var and var==hist[-1]["variants"]: errs.append("variant map equals previous plan")
    for h in hist[-2:]:
        hv=h["variants"]
        if var and hv:
            shared=set(var)&set(hv)
            same=sum(1 for k in shared if var[k]==hv[k])
            if shared and same/len(shared) > 0.70: errs.append("variants too close to neighbour")
    bl = plan.get("blog")
    if bl:
        topics = bl.get("topics") or []
        if bl.get("style") not in ("a", "b", "c"):
            errs.append("blog style must be a|b|c")
        if not 3 <= len(topics) <= 5:
            errs.append(f"blog needs 3..5 topics, got {len(topics)}")
        if len({t.get("id") for t in topics}) != len(topics):
            errs.append("blog topics repeat")
        hub_slug = bl.get("hub_slug")
        if not hub_slug or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(hub_slug)):
            errs.append(f"blog hub_slug is invalid: {hub_slug!r}")
        elif hub_slug in set((plan.get("layout", {}).get("slugs") or {}).values()):
            errs.append(f"blog hub_slug '{hub_slug}' collides with a page slug")
    return errs

def sync_plan_from_content(plan: dict, content_f: pathlib.Path) -> list[str]:
    """Keep personas/photos/numbers aligned with an existing content pack on re-runs."""
    try:
        pack = json.loads(content_f.read_text(encoding="utf-8"))
        items = pack["reviews"]["items"]
        plan["people"] = [i["name"] for i in items]
        plan["photos"] = [i["photo"] for i in items]
        plan["numbers"]["users"] = int(re.sub(r"[^\d]", "", str(pack["hero"]["stats"][1]["v"])))
        plan["numbers"]["latency_ms"] = int(re.sub(r"[^\d]", "", str(pack["hero"]["stats"][2]["v"])))
        return ["people/photos/numbers synced from content"]
    except Exception:
        return []


# ---------------------------------------------------------------- main -------
def step(title):
    print(f"\n--- {title} ---")


def step_run(title, cmd, cwd=None):
    step(title)
    rc = subprocess.run(cmd, cwd=str(cwd or ROOT)).returncode
    if rc != 0:
        print(f"✗ {title} failed (exit {rc})")
        sys.exit(rc)


BANK_F = ROOT / "resources" / "content-l10n.json"


def bank_coverage(lang: str) -> int:
    """Share of the English master copy the language bank covers (100 = usable as is)."""
    sys.path.insert(0, str(ROOT / "tools"))
    import content_gen
    return content_gen.bank_coverage(json.loads(BANK_F.read_text(encoding="utf-8")), lang)[0]


def plan_lang_ready(lang: str) -> bool:
    """True when menu labels, top-strip words and slugs already exist in this language."""
    return lang in MENU_POOLS and lang in LIVEBAR_L10N and lang in SLUG_POOLS


def content_route(plan_data: dict, offline: bool = False, translate: bool = False) -> str:
    """Where the copy comes from.

    Default: 'invent' — the model writes the whole pack itself in the plan language
    from the brief (unique copy per build; that is the point of the factory).

    --translate: 'localize' — English master pack, model only rewrites it (cheaper,
    structure guaranteed by the program).
    --offline (tests / no API key): 'bank' — exact strings from content-l10n.json.
    """
    if offline:
        return "bank"
    return "localize" if translate else "invent"


def run_build(domain, force, with_llm=False, offline=False, translate=False, ship_anyway=False):
    """content → assemble(+gates) → icons → js syntax → mobile lint → profile. Deploy stays manual."""
    plan = PLANS / f"{domain}.json"
    content = ROOT / "content" / f"{domain}-content.json"
    site = ROOT / "sites" / domain

    plan_data = json.loads(plan.read_text(encoding="utf-8"))
    lang = (plan_data["params"].get("lang") or "en").lower()
    route = content_route(plan_data, offline, translate)

    if route == "invent":
        step("CONTENT PACK (LLM writes the copy)")
        llm_cmd = [sys.executable, str(ROOT / "tools" / "llm_content.py"),
                   "--plan", str(plan), "--out", str(content)]
        if os.environ.get("LLM_MODEL"):
            llm_cmd += ["--model", os.environ["LLM_MODEL"]]
        if os.environ.get("LLM_PROVIDER"):
            llm_cmd += ["--provider", os.environ["LLM_PROVIDER"]]
        if subprocess.run(llm_cmd).returncode != 0:
            print("! model pack failed — falling back to master copy + translation")
            route = "localize"
        elif lang != "en" and not plan_lang_ready(lang):
            # menu / top strip / slugs may still be the English fallback
            step_run(f"LOCALIZE plan strings → {lang}",
                     [sys.executable, str(ROOT / "tools" / "localize.py"),
                      "--plan", str(plan), "--content", str(content), "--plan-only"])

    if route == "localize":
        step_run("CONTENT PACK (English master)",
                 [sys.executable, str(ROOT / "tools" / "content_gen.py"),
                  "--plan", str(plan), "--out", str(content), "--force",
                  "--source-lang", "en"])
        step("LOCALIZE → " + lang)
        rc = subprocess.run([sys.executable, str(ROOT / "tools" / "localize.py"),
                             "--plan", str(plan), "--content", str(content),
                             "--lang", lang], cwd=str(ROOT)).returncode
        if rc != 0:
            if not ship_anyway:
                print(f"✗ translation to {lang} failed — fix the pack or rerun with --ship-anyway")
                sys.exit(rc)
            print("! localization failed — building from the English master (--ship-anyway)")
    elif route == "bank":
        cmd = [sys.executable, str(ROOT / "tools" / "content_gen.py"),
               "--plan", str(plan), "--out", str(content)]
        if force:
            cmd.append("--force")
        step_run("CONTENT PACK (bank)", cmd)

    if not offline:
        # validator findings go back to the model once more (exact keys, exact problems)
        # instead of shipping weak copy or relaxing the rule
        step_run("CONTENT REPAIR",
                 [sys.executable, str(ROOT / "tools" / "repair_content.py"),
                  "--plan", str(plan), "--content", str(content)])

    if (plan_data.get("blog") or {}).get("enabled"):
        step(f"BLOG CONTENT ({len(plan_data['blog'].get('topics') or [])} articles)")
        bcmd = [sys.executable, str(ROOT / "tools" / "blog_content.py"), "--plan", str(plan)]
        if offline:
            bcmd.append("--offline")
        if os.environ.get("LLM_MODEL"):
            bcmd += ["--model", os.environ["LLM_MODEL"]]
        if os.environ.get("LLM_PROVIDER"):
            bcmd += ["--provider", os.environ["LLM_PROVIDER"]]
        rc = subprocess.run(bcmd, cwd=str(ROOT)).returncode
        if rc != 0:
            print("✗ blog content failed — build stopped (the classic build is untouched)")
            sys.exit(rc)

    asm_cmd = [sys.executable, str(ROOT / "assemble.py"), "--plan", str(plan), "--content", str(content)]
    rc = subprocess.run(asm_cmd, cwd=str(ROOT)).returncode
    if rc != 0 and ship_anyway:
        print("! gates failed — retrying in ship-anyway mode (issues become warnings)")
        rc = subprocess.run(asm_cmd + ["--ship-anyway"], cwd=str(ROOT)).returncode
    if rc != 0:
        # errors stay errors while the factory is being tested: a shipped page with a
        # known defect is worse than a red build
        print("✗ build failed — see the issues above (use --ship-anyway to publish anyway)")
        sys.exit(rc)
    step_run("BRAND ICONS", [sys.executable, str(ROOT / "tools" / "brand_icons.py"),
                             "--plan", str(plan), "--site", str(site)])

    step("JS SYNTAX")
    js = sorted(site.glob("*.js"))
    bad = [p.name for p in js if subprocess.run(["node", "--check", str(p)]).returncode != 0]
    if bad:
        print(f"✗ node --check failed: {', '.join(bad)}")
        sys.exit(1)
    print(f"✓ node --check ok ({len(js)} files)")

    step_run("MOBILE LINT", [sys.executable, str(ROOT / "tools" / "mobile_lint.py"), str(site)])
    step_run("PROFILE", [sys.executable, str(ROOT / "tools" / "profile_write.py"),
                         "--plan", str(plan), "--content", str(content)])

    step("READY")
    print(f"site    : {site}")
    print(f"profile : {ROOT / 'profiles' / (domain + '.json')}")
    print("deploy  : manual (see CLAUDE.md), .htaccess is rejected by the panel — expected")
    print("manual  : DNS, IP whitelist, real-device 360/390/768 look")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--brand",required=True); ap.add_argument("--lang",required=True)
    ap.add_argument("--domain",required=True); ap.add_argument("--geo",default="")
    ap.add_argument("--cc",default="",help="ISO country override (NO/IT/…); default: from --lang")
    ap.add_argument("--currency",default="",
                    help="ISO currency; default follows the country (JPY for JP, GBP for GB, …)")
    ap.add_argument("--seed",type=int,default=0)
    ap.add_argument("--force",action="store_true")
    ap.add_argument("--calculator",choices=("auto","on","off"),default="auto",
                    help="calculator (G3 widget): on/off forces it, auto follows the G3 draw")
    ap.add_argument("--pulse",choices=("auto","on","off"),default="auto",
                    help="pulse-sim (G3 market simulator): on/off forces it, auto follows the G3 draw")
    ap.add_argument("--build",action="store_true",help="run content → assemble → icons → lint → profile")
    ap.add_argument("--offline",action="store_true",
                    help="build copy from the language bank only (tests / no API key)")
    ap.add_argument("--ship-anyway",action="store_true",
                    help="publish even when the gates still list issues (they become WARN); "
                         "off by default — a red build is better than a broken page")
    ap.add_argument("--translate",action="store_true",
                    help="English master copy + translation instead of the model writing "
                         "the copy itself (cheaper, structure guaranteed)")
    ap.add_argument("--with-llm",action="store_true",
                    help="kept for compatibility: the model writing the pack is the default; "
                         "implies --build")
    ap.add_argument("--blog",action="store_true",
                    help="add the optional guides layer: 3-5 articles from the topic bank + a "
                         "teaser section on the home page (classic build is unchanged without it)")
    ap.add_argument("--llm-model",default="",help="override model id for --with-llm (default from resources/llm.json)")
    ap.add_argument("--llm-provider",default="",choices=("", "auto", "http", "cli"),
                    help="transport for --with-llm (default auto: HTTP when key exists)")
    a=ap.parse_args()
    a.lang = LANG_ALIASES.get(a.lang.lower(), a.lang.lower())
    a.cc = (a.cc or LANG2CC.get(a.lang, "")).upper()
    if not a.currency:
        a.currency = CC_CURRENCY.get(a.cc, "EUR")
    if not a.seed:
        a.seed=int(hashlib.sha256((a.domain+a.brand).encode()).hexdigest()[:8],16)%10_000_000
    hist0=[h for h in load_history() if h["domain"]!=a.domain]
    chosen=None; first_errs=[]; fallback=None
    for bump in range(200):
        rng=rng_from(a.seed+bump)
        cand=build_plan(rng,a,hist0)
        if not cand: continue
        if bump==0 or not fallback: fallback=(cand,first_errs or validate(cand,hist0))
        errs=validate(cand,hist0)
        if not errs: chosen=cand; chosen["seed"]=a.seed+bump; break
        if bump==0: first_errs=errs
    if not chosen:
        if fallback:
            chosen=fallback[0]; chosen["seed"]=a.seed
            chosen["_warnings"]=[f"validation not fully satisfied (duplicate-pattern policy: warn, not block): {'; '.join(fallback[1]) or '—'}"]
            print("WARN: no candidate passed every uniqueness check after 200 retries —")
            print(f"WARN: proceeding with best-effort plan (warnings: {first_errs})")
        else:
            print(f"FAILED: no valid plan in 200 retries; {first_errs}"); sys.exit(1)
    if chosen.pop("_combo_reused",False):
        w="paint combo (skin+palette) already used in history — reused per duplicates-warn policy"
        chosen.setdefault("_warnings",[]).append(w)
        print("WARN: "+w)
    if a.blog and not chosen.get("blog"):
        print(f"✗ --blog requested but {BLOG_TOPICS_F.relative_to(ROOT)} has no usable topics")
        sys.exit(1)
    content_f = ROOT / "content" / f"{a.domain}-content.json"
    if content_f.exists() and not a.force:
        sync = sync_plan_from_content(chosen, content_f)
        if sync: chosen["_synced"] = sync
    PLANS.mkdir(exist_ok=True)
    out=PLANS/f"{a.domain}.json"
    out.write_text(json.dumps(chosen,ensure_ascii=False,indent=1),encoding="utf-8")
    d=chosen
    print(f"PLAN OK -> {out.relative_to(ROOT)}  (seed {d['seed']})")
    print(f"  palette  : {d['design']['palette_id']}  ×  skin-{d['design']['skin']}")
    print(f"  fonts    : {d['design']['fonts']['head']} / {d['design']['fonts']['body']}")
    print(f"  hero     : {d['layout']['hero']}")
    print(f"  order    : {' -> '.join(d['layout']['section_order'])}")
    print(f"  widgets  : "+" ".join(f"{g}:{w}" for g,w in sorted(d['widgets'].items())))
    print(f"  numbers  : rating {d['numbers']['rating']} · reviews {d['numbers']['reviews']} · users {d['numbers']['users']} · {d['numbers']['latency_ms']} ms")
    print(f"  people   : {', '.join(d['people'])}" + (f"  · photos: {', '.join(d['photos'])}" if d['photos'] else ""))
    if d.get("regulator"): print(f"  regulator: {d['regulator']['name']} ({d['regulator']['country']})")
    print(f"  variants : {' '.join(f'{k}:{v}' for k,v in sorted(d['layout'].get('variants',{}).items())) or '—'}")
    print(f"  novel    : {', '.join(d['structure']['novel_slots']) or '—'}")
    print(f"  slugs    : {d['layout']['slugs']}")
    if d.get("blog"):
        bl = d["blog"]
        print(f"  blog     : style {bl.get('style')} · hub {bl.get('hub_slug') or 'guides'}.php · "
              f"{len(bl.get('topics') or [])} articles · "
              + ", ".join(t.get("id", "") for t in (bl.get("topics") or [])))
    if d.get("_warnings"): print("  WARN:",d["_warnings"])
    if a.llm_model:
        os.environ["LLM_MODEL"] = a.llm_model
    if a.llm_provider:
        os.environ["LLM_PROVIDER"] = a.llm_provider
    if a.with_llm:
        run_build(a.domain, a.force, offline=a.offline, translate=a.translate,
                  ship_anyway=a.ship_anyway)
    elif a.build:
        run_build(a.domain, a.force, offline=a.offline, translate=a.translate,
                  ship_anyway=a.ship_anyway)

if __name__=="__main__": main()
