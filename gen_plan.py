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
import argparse, hashlib, itertools, json, os, pathlib, random, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent          # static-create-sites/
PLANS = ROOT / "plans"
PALETTES_F = ROOT / "content" / "palettes-blk.json"
REG_F = ROOT / "resources" / "regulators.json"
PEOPLE_DIR = ROOT / "people"

# ---------------------------------------------------------------- registries --
WIDGET_GROUPS = {
    "G1": ["ticker-static", "livebar-counter", "tape-marquee", "markets-strip",
            "price-board", "listino-rows", "heatmap", "tile-flip", "odometer"],
    "G2": ["countdown-plates", "countdown-bar", "countdown-ring", "flip-clock", "progress-intake"],
    "G3": ["none", "demo-line", "demo-bars", "sentiment-gauge", "book-ladder", "calculator"],
    "G4": ["faq-accordion", "faq-list", "faq-grid", "faq-split"],
    "G5": ["stats-band", "quick-answer", "rating-summary", "rating-band"],
}
SKINS = ["rounded-air", "sharp-flat", "brutalist-block", "glass-soft",
          "classic-border", "dense-terminal"]
HEROES = ["hero-split-terminal", "hero-phone", "hero-dash", "hero-converter",
          "hero-centered", "hero-kpis", "hero-watchlist"]
FORM_BANDS = ["access-band", "claim-band", "enroll-band"]
SECTION_POOL = ["intro-center", "features", "steps", "steps-live", "markets", "ladder",
                 "streams", "security", "demo", "risk", "cta-band", "trust-band",
                 "ticker", "timeline", "stats-intro",
                 "numbers", "portal", "compare", "glance",
                 "facts", "notes", "mini-faq", "device"]
TYPE_OF = {"claim-band": "band", "access-band": "band", "enroll-band": "band",
           "trust-band": "cta", "cta-band": "cta", "intro-center": "intro", "stats-intro": "intro",
           "steps-live": "steps", "brand-note": "brandnote"}
def types_of(order): return {TYPE_OF.get(t, t) for t in order}
VARIANTS = {  # structural fragment variants per slot ("" = canonical file, always allowed)
    "hero": ["b", "c"], "claim-band": ["b", "c"], "access-band": ["b", "c"], "enroll-band": ["b", "c"],
    "features": ["b", "c"], "people": ["b", "c"], "steps": ["b"], "faq": ["b"], "cta-band": ["b", "c"],
    "ladder": ["b", "c"], "office": ["b", "c"], "brand-note": ["b", "c"], "timeline": ["b"],
    "scarcity": ["b"], "markets": ["b", "c"], "ticker": ["b", "c"], "intro-center": ["b", "c"],
    "risk": ["b"], "security": ["b"], "streams": ["b"], "demo": ["b"],
    "livebar": ["b", "c", "d", "e", "f", "g", "h", "i", "j"],
    "logo": ["b", "c", "d", "e", "f", "g", "h"],
    "header": ["b", "c", "d", "e", "f", "g"],
}

LIVEBAR_L10N = {lg: b["_livebar"] for lg, b in json.loads(
    (ROOT / "resources" / "content-l10n.json").read_text(encoding="utf-8")).items()
    if isinstance(b, dict) and b.get("_livebar")}

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
LANG2CC = {"it":"IT","pl":"PL","cs":"CZ","sk":"SK","hu":"HU","nl":"NL","sl":"SI","de":"DE",
            "fr":"FR","es":"ES","pt":"PT","ro":"RO","bg":"BG","el":"GR","sv":"SE","da":"DK",
            "fi":"FI","nb":"NO","nn":"NO","et":"EE","lv":"LV","lt":"LT","en":"GB"}

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
            "bins": (d.get("numbers",{}).get("reviews_bin"), d.get("numbers",{}).get("users_bin")),
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
    pool_types={TYPE_OF.get(t, t) for t in SECTION_POOL}   # hero/faq/people are always present
    free=len(pool_types - near)
    return min(3, max(0, free))

def order_ok(od:list,hist:list)->bool:
    """Hard structural separation from the nearest plans."""
    types=types_of(od)
    for h in hist[-3:]:
        if h["order"] and jac(types,types_of(h["order"]))>=0.65: return False
    for h in hist[:-3]:
        if h["order"] and jac(types,types_of(h["order"]))>=0.72: return False
    for h in hist[-2:]:
        if h["order"] and seq_overlap(od,h["order"])>=0.5: return False
    near=set()
    for h in hist[-3:]:
        near |= types_of(h["order"])
    if hist and len(types-near)<novel_need(hist): return False
    return True

def structure_score(od:list,hist:list)->float:
    types=types_of(od); sc=0.0
    for h in hist[-3:]:
        if not h["order"]: continue
        sc+=1.0-jac(types,types_of(h["order"]))
        sc+=(1.0-seq_overlap(od,h["order"]))*0.6
    sc+=0.25*len(types-{t for h in hist[-1:] for t in types_of(h["order"])})
    return sc

def bins_pick(rng,key,taken):
    bins=list(NUM_BINS[key]); rng.shuffle(bins)
    fresh=[b for b in bins if b not in taken]
    return (fresh or bins)[0]

# ---------------------------------------------------------------- builder ----
ARCHETYPES = {"clear-operator", "calm-analyst", "quiet-desk", "market-observer"}
TONES = {"pragmatic", "plain", "sober", "factual"}
INNER_SKELETONS = {
    "about": [["page-intro", "editorial", "cta"], ["page-intro", "milestones", "editorial", "winrate", "cta"], ["page-intro", "manifest", "timeline", "principles", "cta"]],
    "contact": [["form-first", "hours", "map"], ["page-intro", "cards", "consult"], ["page-intro", "contact-grid", "office"]],
    "register": [["benefits", "core"], ["core", "points"], ["steps", "core", "mini-faq"]],
    "who": [["page-intro", "team-band", "features", "numbers", "cta"], ["page-intro", "pipeline", "compare", "cta"], ["page-intro", "stack", "figures", "cta"]],
}
MENU_POOLS = {
    "cs": [["Domů", "Program", "Technologie", "Kontakt"], ["Start", "Jak to funguje", "Motor", "Napište nám"], ["Domů", "O projektu", "Metoda", "Kontakt"]],
    "it": [["Home", "Panoramica", "Strumenti", "Aiuto"], ["Start", "Come funziona", "Motore", "Scrivici"], ["Home", "Metodo", "Piattaforma", "Supporto"], ["Home", "Programma", "Tecnologia", "Contatti"]],
    "es": [["Home", "Program", "Technology", "Contacts"]],
    "fallback": [["Home","About","Tech","Contact"],["Home","Method","Platform","Support"],["Home","About","Tools","Contact"]]
}
SLUG_POOLS = {
    "cs": {"about": ["o-nas", "o-projektu", "pribeh"], "contact": ["kontakt", "podpora", "spojeni"], "register": ["registrace", "ucet", "zalozit-ucet"], "who": ["jak-pracujeme", "jak-to-funguje", "metoda"]},
    "it": {"about": ["chi-siamo", "progetto", "programma", "redazione"], "contact": ["contatti", "parliamo", "scrivici", "supporto"], "register": ["accesso", "inizia", "iscrizione", "registrati"], "who": ["come-lavoriamo", "metodo", "motore", "piattaforma"]},
    "es": {"about": ["team"], "contact": ["talk-to-us"], "register": ["get-started"], "who": ["method"]},
    "fallback": {"about": ["about","project"], "who": ["how-it-works","method"],
                 "contact": ["contact","contacts"], "register": ["register","open-account"]}
}

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
    if not chosen: return None
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

    if getattr(args, "calculator", "auto") == "on":
        widgets["G3"] = "calculator"
    elif getattr(args, "calculator", "auto") == "off" and widgets["G3"] == "calculator":
        widgets["G3"] = "demo-line"

    # section order: prefer slot TYPES unused by neighbours, hard structural caps
    neigh=hist[-3:]
    neigh_types={t for h in neigh for t in types_of(h["order"])}
    pool_types={}
    for slot in SECTION_POOL:
        pool_types.setdefault(TYPE_OF.get(slot, slot), []).append(slot)
    novel=[t for t in pool_types if t not in neigh_types]
    stale=[t for t in pool_types if t in neigh_types]
    rng.shuffle(novel); rng.shuffle(stale)
    order=None; best=None
    for _ in range(80):
        od=["hero"]+[rng.choice(FORM_BANDS)]
        # calculator is a G3 widget: present only when G3 drew it
        if widgets["G3"] == "calculator": od.append("calculator")
        want=rng.randint(6,9)
        fresh_n=min(len(novel),max(novel_need(hist),rng.randint(3,6)))
        picked=novel[:fresh_n]+rng.sample(stale,k=min(len(stale),want-fresh_n))
        rng.shuffle(picked)
        extras=[rng.choice(pool_types[t]) for t in picked]
        for s in extras:
            if s not in od: od.append(s)
        if "people" not in od: od.append("people")
        if "scarcity" not in od and rng.random()<0.8: od.insert(rng.randrange(3,len(od)-2),"scarcity")
        od+=["faq"]
        if rng.random()<0.85: od.append("office")
        if rng.random()<0.6: od.append("brand-note")
        seen=set(); od=[x for x in od if not (x in seen or seen.add(x))][:16]
        if len(od)<10: continue
        if "people" not in od or "faq" not in od: continue
        if widgets["G1"] in {"markets-strip","price-board","listino-rows","heatmap","tile-flip"} \
           and not ({"markets","ticker","ladder"} & set(od)):
            od.insert(rng.randrange(3,len(od)-4),"markets")
        score=structure_score(od,hist)
        if best is None or score>best[0]: best=(score,od)
        if order_ok(od,hist): order=od; break
    if order is None and best: order=best[1]
    if order is None: return None

    # vertical variants: most slots deviate from neighbours, canonical stays possible
    variants={}
    used_var={s:{h["variants"].get(s,"") for h in hist[-3:]} for s in VARIANTS}
    for slot in order:
        opts=VARIANTS.get(slot)
        if not opts: continue
        pool=[v for v in opts if v not in used_var.get(slot,())]
        rng.shuffle(pool)
        if pool and rng.random()<0.8: variants[slot]=pool[0]
        elif rng.random()<0.45: variants[slot]=rng.choice(opts)

    # livebar strip: a second structural axis (not a page section, always present)
    lb_pool=[v for v in VARIANTS["livebar"] if not hist or v != hist[-1]["variants"].get("livebar")]
    variants["livebar"]=rng.choice(lb_pool)
    logo_pool=[v for v in VARIANTS["logo"] if not hist or v != hist[-1]["variants"].get("logo")]
    variants["logo"]=rng.choice(logo_pool)
    hdr_pool=[v for v in VARIANTS["header"] if not hist or v != hist[-1]["variants"].get("header")]
    variants["header"]=rng.choice(hdr_pool)
    livebar=build_livebar(rng, variants["livebar"], args.lang,
                          (args.cc or LANG2CC.get(args.lang,"")).upper())

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
    rb=bins_pick(rng,"reviews",taken_r); ub=bins_pick(rng,"users",taken_u)
    lb=bins_pick(rng,"latency",{()})
    numbers={"rating":rng.choice(sorted(NUM_BINS["ratings"])),"reviews":rng.randint(*rb),
              "reviews_bin":list(rb),"users":rng.randint(*ub),"users_bin":list(ub),
              "latency_ms":round(rng.uniform(*lb)),"latency_bin":[round(lb[0]),round(lb[1])]}

    # personas + portraits (never reused across plans)
    nb=NAME_BANK.get(args.lang,NAME_BANK["fallback"])
    used_n={n for h in hist for n in h["people"]}
    avail=[n for n in nb if n not in used_n] or nb
    people=sorted(rng.sample(avail,k=min(3,len(avail))))
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

    return {
        "seed":args.seed, "product":"static-create-sites",
        "params":{"brand":args.brand,"geo":args.geo,"geo_short":(args.cc or LANG2CC.get(args.lang,"")).upper(),
            "lang":args.lang,"locale":f"{args.lang}-{(args.cc or LANG2CC.get(args.lang,args.lang.upper())).upper()}",
            "domain":args.domain,"currency":args.currency,"cc":(args.cc or LANG2CC.get(args.lang,"")).upper()},
        "identity":{"archetype":rng.choice(sorted(ARCHETYPES)),"tone":rng.choice(sorted(TONES))},
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

# --------------------------------------------------------------- livebar ------
def _fmt_num(v: float, lang: str, dec: int = 2) -> str:
    whole = " " if lang == "cs" else "."
    body = f"{v:,.{dec}f}"
    return (body.replace(",", "T").replace(".", "D")
                .replace("T", whole).replace("D", "," if lang in ("it", "cs") else "."))


def build_livebar(rng, variant: str, lang: str, geo_short: str) -> dict:
    """Content for the top strip variant; rows are numbers only, words are localised."""
    L = LIVEBAR_L10N.get(lang) or LIVEBAR_L10N["en"]
    sets = {
        "b": [("EUR/USD", 1.07, 1.10, 4), ("EUR/GBP", 0.84, 0.87, 4), ("EUR/CHF", 0.93, 0.96, 4)],
        "c": [("BTC/EUR", 82_000, 94_000, 0), ("ETH/EUR", 2_900, 3_400, 0), ("SOL/EUR", 130, 165, 2)],
        "d": [("FTSEMIB", 33_800, 34_900, 0), ("DAX", 17_900, 18_600, 0), ("S&P 500", 5_100, 5_320, 0)],
        "e": [("ORO", 2_180, 2_360, 0), ("BRENT", 74, 82, 2), ("RAME", 8_900, 9_400, 0)],
        "f": [], "g": [], "h": [], "i": [], "j": [],
    }
    rows = []
    for sym, lo, hi, dec in sets.get(variant, []):
        chg = rng.uniform(-1.2, 2.4)
        rows.append({"s": sym, "v": _fmt_num(rng.uniform(lo, hi), lang, dec),
                     "c": f"{chg:+.2f}".replace(".", ",") + "%",
                     "d": "up" if chg >= 0 else "dn"})
    subs = {"GEO_SHORT": geo_short}
    for i in range(4):
        r = rows[i] if i < len(rows) else {"s": "", "v": "", "c": "", "d": "up"}
        subs.update({f"LB{i+1}S": r["s"], f"LB{i+1}V": r["v"],
                     f"LB{i+1}C": r["c"], f"LB{i+1}D": r["d"]})
    news = list(L["news"])
    pct = rng.randint(52, 71)
    subs.update({
        "LB_TAG": L["crypto"] if variant == "c" else L["bull"],
        "LB_LABEL": L["commod"], "LB_SESSION": L["session"],
        "LB_CLOCK": f"{rng.randint(0, 3):02d}:{rng.randint(10, 59):02d}:{rng.randint(10, 59):02d}",
        "LB_NEWS1": news[0], "LB_NEWS2": news[1],
        "LB_TIME": f"{rng.randint(8, 17):02d}:{rng.randint(0, 59):02d}",
        "LB_S1": f"API {rng.choice(['OK', 'OK', '42 ms'])}",
        "LB_S2": f"DB {rng.choice(['OK', 'OK', 'sync'])}",
        "LB_S3": f"{L['payouts']} OK",
        "LB_BULL": f"{L['bull']} {pct}%", "LB_BEAR": f"{L['bear']} {100 - pct}%",
        "LB_PCT": str(pct),
        "LB_QUEUE": f"{L['queue']} {rng.randint(14, 48)}",
        "LB_WAIT": f"{L['wait']} {rng.randint(4, 19)} min",
        "LB_SLOTS": f"{rng.randint(3, 9)} {L['slots']}",
    })
    return {"variant": variant, "subs": subs}


# ---------------------------------------------------------------- validate ---
def validate(plan,hist)->list[str]:
    errs=[]; last2=hist[-2:]
    ws=frozenset(plan["widgets"].values())
    for h in hist:
        if h["widgets"] and ws==frozenset(h["widgets"]):
            errs.append(f"widget set equals {h['domain']}"); break
    if any(h["palette"]==plan["design"]["palette_id"] for h in last2): errs.append("palette repeats neighbour")
    if any(h["skin"]==plan["design"]["skin"] for h in last2): errs.append("skin repeats neighbour")
    if any(h["combo"]==(plan["design"]["skin"],plan["design"]["palette_id"]) for h in hist):
        errs.append("skin+palette combo used before")
    if last2 and all(seq_overlap(plan["layout"]["section_order"],h["order"])>=0.6 for h in last2):
        errs.append("section order too close")
    used_people={n for h in hist for n in h["people"]}
    bank_size=len(NAME_BANK.get(plan["params"]["lang"],NAME_BANK["fallback"]))
    if len(used_people)+3<=bank_size and used_people & set(plan["people"]):
        errs.append("persona reused")
    lay=plan["layout"]; types=types_of(lay["section_order"])
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


def run_build(domain, force, with_llm=False):
    """content → assemble(+gates) → icons → js syntax → mobile lint → profile. Deploy stays manual."""
    plan = PLANS / f"{domain}.json"
    content = ROOT / "content" / f"{domain}-content.json"
    site = ROOT / "sites" / domain

    if with_llm:
        step("CONTENT PACK (LLM)")
        llm_cmd = [sys.executable, str(ROOT / "tools" / "llm_content.py"),
                   "--plan", str(plan), "--out", str(content)]
        if os.environ.get("LLM_MODEL"):
            llm_cmd += ["--model", os.environ["LLM_MODEL"]]
        if os.environ.get("LLM_PROVIDER"):
            llm_cmd += ["--provider", os.environ["LLM_PROVIDER"]]
        rc = subprocess.run(llm_cmd).returncode
        if rc != 0:
            print("! LLM pack failed — falling back to the language bank")
            step_run("CONTENT PACK (bank fallback)",
                     [sys.executable, str(ROOT / "tools" / "content_gen.py"),
                      "--plan", str(plan), "--out", str(content), "--force"])
    else:
        cmd = [sys.executable, str(ROOT / "tools" / "content_gen.py"), "--plan", str(plan), "--out", str(content)]
        if force:
            cmd.append("--force")
        step_run("CONTENT PACK", cmd)
    step_run("ASSEMBLE + GATES",
             [sys.executable, str(ROOT / "assemble.py"), "--plan", str(plan), "--content", str(content)])
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
    ap.add_argument("--currency",default="EUR"); ap.add_argument("--seed",type=int,default=0)
    ap.add_argument("--force",action="store_true")
    ap.add_argument("--calculator",choices=("auto","on","off"),default="auto",
                    help="calculator (G3 widget): on/off forces it, auto follows the G3 draw")
    ap.add_argument("--build",action="store_true",help="run content → assemble → icons → lint → profile")
    ap.add_argument("--with-llm",action="store_true",
                    help="model writes the content pack (and picks personas/numbers); implies --build")
    ap.add_argument("--llm-model",default="",help="override model id for --with-llm (default from resources/llm.json)")
    ap.add_argument("--llm-provider",default="",choices=("", "auto", "http", "cli"),
                    help="transport for --with-llm (default auto: HTTP when key exists)")
    a=ap.parse_args()
    if not a.seed:
        a.seed=int(hashlib.sha256((a.domain+a.brand).encode()).hexdigest()[:8],16)%10_000_000
    hist0=[h for h in load_history() if h["domain"]!=a.domain]
    chosen=None; first_errs=[]
    for bump in range(200):
        rng=rng_from(a.seed+bump)
        cand=build_plan(rng,a,hist0)
        if not cand: continue
        errs=validate(cand,hist0)
        if not errs: chosen=cand; chosen["seed"]=a.seed+bump; break
        if bump==0: first_errs=errs
    if not chosen:
        if a.force and cand: chosen=cand; chosen["_warnings"]=first_errs
        else: print(f"FAILED: no valid plan in 200 retries; {first_errs}"); sys.exit(1)
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
    if d.get("_warnings"): print("  WARN:",d["_warnings"])
    if a.llm_model:
        os.environ["LLM_MODEL"] = a.llm_model
    if a.llm_provider:
        os.environ["LLM_PROVIDER"] = a.llm_provider
    if a.with_llm:
        run_build(a.domain, a.force, with_llm=True)
    elif a.build:
        run_build(a.domain, a.force)

if __name__=="__main__": main()
