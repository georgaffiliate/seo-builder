#!/usr/bin/env python3
"""selftest.py — infrastructure self-check for static-create-sites.
Verifies: fragments complete, CSS sane, palettes valid, plan generator feeds assembler,
assembled site passes gates. Run after ANY change to blocks/skins/assemble.
"""
import json, pathlib, re, subprocess, sys, hashlib

ROOT = pathlib.Path(__file__).resolve().parent.parent   # static-create-sites
REPO = ROOT.parent
FAIL = []

def chk(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: FAIL.append(msg)

print("== 1. fragments")
blks = sorted((ROOT / "blocks").glob("blk-*.html"))
chk(len(blks) >= 20, f"canonical blk-fragments present ({len(blks)})")
chk((ROOT / "blocks" / "blocks.css").exists(), "blocks.css present")
need_frag = {"blk-hero", "blk-band-access", "blk-faq", "blk-reviews", "blk-scarcity",
              "blk-cta", "blk-office", "blk-brandnote", "blk-calculator", "blk-livebar",
              "blk-pulse-sim"}
names = {b.stem for b in blks}
chk(need_frag <= names, f"critical fragments: {sorted(need_frag - names) or 'all present'}")
# form contract inside fragments (hidden identity fields live server-side in api.php)
fa = (ROOT / "blocks" / "blk-band-access.html").read_text()
for token in ("lead-form", "api_local/integration/api.php", "js-lead-phone",
              "form-submit", "form-error", "form-status"):
    chk(token in fa, f"form contract: {token}")

for _of in (ROOT / "blocks").glob("blk-office*.html"):
    chk("{{c:office.eyebrow}}" in _of.read_text(), f"{_of.name}: office eyebrow localised")

chk("{{c:sections.markets.disclaimer}}" in (ROOT / "blocks" / "blk-markets.html").read_text()
    and "{{c:sections.markets.disclaimer}}" in (ROOT / "blocks" / "blk-markets-b.html").read_text(),
    "markets disclaimer comes from content (no English caption)")
chk("{{c:hero.device_label}}" in (ROOT / "blocks" / "blk-hero.html").read_text(), "hero ledger label from content")
# no hardcoded copy in fragments: everything the visitor reads or hears comes from the pack
_pay = {"visa", "mastercard", "sepa", "sepa/visa"}
_hard = {}
for _f in (ROOT / "blocks").glob("blk-*.html"):
    _h = _f.read_text(encoding="utf-8")
    _h = re.sub(r"<(script|style)\b.*?</\1>", " ", _h, flags=re.S | re.I)
    _h = re.sub(r"<!--.*?-->", " ", _h, flags=re.S)
    _h = re.sub(r"[\w.+-]+@(?:\{\{[^}]*\}\}|[\w.-]+)", " ", _h)   # mailto:info@domain is not copy
    _h = re.sub(r"\{\{[^}]*\}\}", " ", _h)
    _words = {w.lower() for w in re.findall(r"[^\W\d_]{3,}", re.sub(r"<[^>]+>", " ", _h), re.UNICODE)}
    _left = _words - _pay
    if _left:
        _hard[_f.name] = sorted(_left)[:4]
chk(not _hard, f"no hardcoded copy in fragments ({'; '.join(f'{k}: {v}' for k, v in list(_hard.items())[:3]) or 'clean'})")
# review cards must be different people — pack level and page level
_clone = {"reviews": {"items": [{"name": "Pedro M.", "photo": "img/p-men-63.jpg",
                                 "quote": "Sem pop-ups.", "city": "Lisboa", "tenure": "3 meses"}] * 3},
          "sections": {}, "hero": {}, "bands": {}, "meta": {}, "faq": {"items": []}}
_clone_plan = {"numbers": {}, "params": {"brand": "X", "domain": "x.site"},
               "layout": {"section_order": []}}
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import assemble as _asm3, seo_audit as _sa2, llm_content as _lc
chk(any("reviews.photo repeated" in e for e in _asm3.validate_content(_clone, _clone_plan, strict=True)),
    "validator rejects cloned review cards")
_clone_html = ('<article class="row-item quote-row"><img class="avatar" src="img/p-men-63.jpg">'
               '<h3>Pedro M.</h3><p>Sem pop-ups.</p></article>') * 3
chk(_sa2.audit_review_avatars(_clone_html) == ["img/p-men-63.jpg"],
    "audit flags the same review portrait used twice")
# the same instrument written differently must still be recognised (strip vs ticker)
# page self-heal: duplicated paragraph dropped, aria-hidden copy kept, brand unglued
_dup = ('<p>The same long paragraph that must appear only once in the final page.</p>'
        '<article aria-hidden="true"><p>The same long paragraph that must appear only once in the final page.</p></article>'
        '<p>The same long paragraph that must appear only once in the final page.</p>')
# form layout is its own axis
_cf_plan = ROOT / "plans" / "selftest-calc.site.json"
__import__("subprocess").run([sys.executable, str(ROOT / "gen_plan.py"), "--brand", "FormAxis",
                              "--lang", "it", "--domain", "selftest-calc.site",
                              "--seed", "909", "--force"], capture_output=True, cwd=ROOT)
_cd = json.loads(_cf_plan.read_text()) if _cf_plan.exists() else {}
chk(_cd.get("layout", {}).get("variants", {}).get("form") in ("", "b", "c", "d"),
    "form layout variant chosen")
_cf_plan.unlink(missing_ok=True)

# every offer carries the reviews screen (social proof is not a rotation option)
_pp2 = ROOT / "plans" / "selftest-people.site.json"
__import__("subprocess").run([sys.executable, str(ROOT / "gen_plan.py"), "--brand", "PeopleSel",
                             "--lang", "it", "--domain", "selftest-people.site",
                             "--seed", "808", "--force"], capture_output=True, cwd=ROOT)
if _pp2.exists():
    _ppd = json.loads(_pp2.read_text()); _pp2.unlink()
    chk("people" in _ppd["layout"]["section_order"],
        "every plan carries the reviews screen")
else:
    chk(False, "every plan carries the reviews screen")
# validator findings are turned into a targeted repair request (keys, not the whole pack)
import repair_content as _rc
_keys = _rc.suspects(["faq answer too short (3 chars): Sì.…",
                      "office.addr_label is a sentence, use a short label: Indirizzo completo"])
chk("faq.items.0.a" in _keys and "office.addr_label" in _keys,
    "repair stage maps validator findings to exact keys")
_healed = _asm3.self_heal_page(_dup, "Acme")
chk(_healed.count("The same long paragraph") == 2 and 'aria-hidden="true"' in _healed and
    "Acme" in _asm3.self_heal_page("<p>oAcme panel</p>", "Acme"),
    "page self-heal: duplicate paragraph dropped, brand spacing fixed")
chk(_sa2.audit_market_prices("<td>BTC/EUR</td><td>87.450</td> <td>BTC/EUR</td><td>87.450</td>") == {}
    and _sa2.audit_market_prices("<td>BTC/EUR</td><td>87.450</td> <td>BTC/EUR</td><td>5.320,50</td>") != {}
    and _sa2.audit_market_prices("EUR/USD 500 miliardi e EUR/USD 1,0842") == {},
    "price gate: same symbol twice is caught, prose numbers are not a quote")
chk(bool(set(_asm3._sym_keys("BTC / EUR")) & set(_asm3._sym_keys("BTC/EUR"))) and
    bool(set(_asm3._sym_keys("XAU/EUR")) & set(_asm3._sym_keys("GOLD/EUR"))) and
    bool(set(_asm3._sym_keys("DAX 40")) & set(_asm3._sym_keys("DAX40"))),
    "instrument symbols match across spellings (BTC / EUR, XAU↔GOLD, DAX 40)")
_slider = ('<article class="rev-card"><p>“Quote long enough to be counted here.”</p>'
           '<img class="avatar" src="img/p-men-63.jpg"></article>'
           '<article class="rev-card" aria-hidden="true"><p>“Quote long enough to be counted here.”</p>'
           '<img class="avatar" src="img/p-men-63.jpg" alt=""></article>')
chk(_sa2.audit_review_avatars(_slider) == [] and _sa2.audit_duplicate_paragraphs(_slider) == [],
    "slider's aria-hidden copies are not counted as repeats")
# the LLM schema must describe every key the fragments render, otherwise the model is
# asked for a slot it never sees a shape for (that is how portal.cards came back null)
_schema_doc = json.loads((ROOT / "content" / "content-pack.schema.json").read_text())
_derived = {"hero.device_bal_v", "hero.device_cur", "hero.device_cur_code", "hero.device_pct"}


def _schema_has(path):
    node = _schema_doc
    for part in path.split("."):
        if part.isdigit():
            if not isinstance(node, list) or not node:
                return False
            node = node[0]
            continue
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


_missing_schema = set()
for _f in (ROOT / "blocks").glob("blk-*.html"):
    for _p in set(re.findall(r"\{\{c:([\w.]+)\}\}", _f.read_text(encoding="utf-8"))):
        _base = ".".join(x for x in _p.split(".") if not x.isdigit())
        if _p in _derived or _base in _derived or _p.endswith(".vv"):
            continue
        if not _schema_has(_p):
            _missing_schema.add(_base)
chk(not _missing_schema,
    f"schema covers every fragment key ({sorted(_missing_schema)[:4] if _missing_schema else 'complete'})")
# a repair pass must not drop sections the skeleton happens to miss
_sk = {"sections": {"stats": {"rating": "x"}}, "hero": {}}
_got = {"sections": {"stats": {"rating": "4,6"}, "portal": {"cards": ["a", "b", "c"]}}, "hero": {}}
chk(_lc.merge_skeleton(_sk, _got)["sections"].get("portal", {}).get("cards") == ["a", "b", "c"],
    "repair merge keeps model slots the skeleton lacks")
# a long plan history must not shrink the persona trio to one
sys.path.insert(0, str(ROOT)); import gen_plan as _gp
_worn = [{"people": ["Anna K.", "Peter M.", "Sofia L.", "David R.", "Emma S."]},
         {"people": ["Ines T.", "Nina P.", "Luca R.", "Sara P."]}] * 4
chk(len(_gp.pick_people(__import__("random").Random(3), "pt", _worn)) == 3,
    "personas stay at 3 after the name bank is used up")
# routing: model writes the copy by default; translation and bank are opt-in
_pp = {"params": {"lang": "pt"}}
chk(len(_gp.VARIANTS["header"]) >= 9 and len(_gp.VARIANTS["footer"]) >= 5,
    f"shell pools: {len(_gp.VARIANTS['header'])} headers × {len(_gp.VARIANTS['footer'])} footers")
# every generated plan must satisfy the assembler's own structural rules
_ap = ROOT / "plans" / "selftest-anchors.site.json"
__import__("subprocess").run([sys.executable, str(ROOT / "gen_plan.py"), "--brand", "AnchorSel",
                             "--lang", "si", "--domain", "selftest-anchors.site",
                             "--seed", "777", "--force"], capture_output=True, cwd=ROOT)
if _ap.exists():
    _apd = json.loads(_ap.read_text()); _ap.unlink()
    try:
        _asm3.validate_plan(_apd)
        _plan_ok = True
    except SystemExit:
        _plan_ok = False
    chk(_plan_ok, "generated plan passes assemble.validate_plan (anchors, order budget)")
else:
    chk(False, "generated plan passes assemble.validate_plan (anchors, order budget)")

chk(_gp.pick_variant(__import__("random").Random(1), "header", ["b", "c", "d"], 
                     [{"variants": {"header": "b"}}] * 5, 5) in ("c", "d"),
    "header variant avoids the last five plans")
# a removed screen must take its variant with it, or assembly dies on "unknown slot"
_calc_plan = ROOT / "plans" / "selftest-calc-dup.site.json"
_rc = __import__("subprocess").run([sys.executable, str(ROOT / "gen_plan.py"), "--brand", "CalcDup",
                                    "--lang", "it", "--domain", "selftest-calc-dup.site",
                                    "--calculator", "on", "--seed", "71", "--force"],
                                   capture_output=True, cwd=ROOT)
_pd = json.loads(_calc_plan.read_text()) if _calc_plan.exists() else {}
_lay = _pd.get("layout", {})
_stray = [k for k in (_lay.get("variants") or {}) if k not in ("logo", "header", "footer", "livebar", "form")
          and k not in (_lay.get("section_order") or [])]
chk(_rc.returncode == 0 and _pd and not _stray,
    f"no variant left behind for a dropped screen ({_stray or 'clean'})")
_calc_plan.unlink(missing_ok=True)
# menu words are localised: no English leftovers in a non-English nav pool
_eng = {"start", "about", "contact", "tech", "method", "platform", "support", "tools", "login"}
_bad_menus = [f"{lg}:{w}" for lg, rows in _gp.MENU_POOLS.items() if lg != "fallback"
              for r in rows for w in r if w.lower() in _eng]
chk(not _bad_menus, f"menu pools are localised ({_bad_menus[:3] or 'clean'})")
# number formatting follows the language: comma decimals for tr/de/it…, dot for en/ja
# a quote pair is an instrument: BTC/EUR must not borrow the BTC/JPY price
chk(_asm3._sym_pair("BTC/EUR") != _asm3._sym_pair("BTC/JPY")
    and _asm3._sym_pair("XAU/EUR") == _asm3._sym_pair("GOLD/EUR")
    and _asm3._sym_pair("BTC / EUR") == _asm3._sym_pair("BTC/EUR"),
    "symbol pairs keep the quote currency (no BTC/EUR ← BTC/JPY price)")
_lb_ja = _gp.build_livebar(__import__("random").Random(2), "a", "ja", "JP")["subs"]
_lb_de = _gp.build_livebar(__import__("random").Random(2), "a", "de", "DE")["subs"]
chk("." in _lb_ja.get("LB_S2V", "") and "," in _lb_de.get("LB_S2V", ""),
    "API uptime follows the language separators")
chk(_gp.decimal_comma("tr") and _gp.decimal_comma("de") and _gp.decimal_comma("fr")
    and not _gp.decimal_comma("en") and not _gp.decimal_comma("ja")
    and _gp._fmt_num(1234.5, "tr") == "1.234,50" and _gp._fmt_num(1234.5, "en") == "1,234.50",
    "decimal separators follow the plan language")
# FAQ length is script-aware: CJK says as much in half the characters
_ja_plan = {"params": {"lang": "ja", "brand": "X", "domain": "x.site"},
            "layout": {"section_order": []}, "numbers": {}}
_en_plan = {"params": {"lang": "en", "brand": "X", "domain": "x.site"},
            "layout": {"section_order": []}, "numbers": {}}
_ja_ans = "はい。画面表示・メール・電話サポートのすべてを日本語で対応しています。平日の日中は担当者が回答します。"
_en_ans = "Yes. Screen display, email and phone support are all available in the language."
def _faq_errs(pl, ans):
    pack = {"faq": {"items": [{"q": "q", "a": ans}]}, "hero": {}, "bands": {}, "meta": {},
            "sections": {}, "reviews": {"items": []}, "office": {}}
    return [e for e in _asm3.validate_content(pack, pl, strict=True) if "faq answer" in e]
chk(not _faq_errs(_ja_plan, _ja_ans) and _faq_errs(_en_plan, "Too short."),
    "FAQ length threshold follows the script")
# page-level figures (numbers band) follow the language too
chk(_asm3.fmt_int(1234, "ja") == "1,234" and _asm3.fmt_int(1234, "de") == "1.234"
    and _asm3.api_uptime("ja") == "99.9%" and _asm3.api_uptime("de") == "99,9%",
    "numbers band figures follow the language separators")
# money follows the language and the currency (yen never gets cents)
import content_gen as _cgen
chk(_cgen.fmt_amount(1234.5, "EUR", True, "de") == "1.234,50"
    and _cgen.fmt_amount(1234.5, "EUR", True, "en") == "1,234.50"
    and _cgen.fmt_amount(41250, "JPY", False, "ja") == "41,250"
    and _cgen.fmt_amount(41250, "JPY", True, "ja") == "41,250",
    "money formatting follows language and currency")
chk(_gp.CC_CURRENCY.get("JP") == "JPY" and _gp.CC_CURRENCY.get("GB") == "GBP",
    "currency defaults to the country")
chk(_gp.LANG_ALIASES.get("gb") == "en" and _gp.LANG_ALIASES.get("mx") == "es"
    and _gp.LANG_ALIASES.get("si") == "sl",
    "country codes resolve to a language")
chk(_gp.content_route(_pp) == "invent" and
    _gp.content_route(_pp, translate=True) == "localize" and
    _gp.content_route(_pp, offline=True) == "bank",
    "copy route: invent by default, --translate / --offline opt-in")

print("== 6c. blog layer (--blog)")
import copy as _copy
import blog_assemble as _ba
_bp = ROOT / "plans" / "selftest-blog.site.json"
_bf = ROOT / "content" / "selftest-blog.site-blog.json"
_subprocess = __import__("subprocess")
_subprocess.run([sys.executable, str(ROOT / "gen_plan.py"), "--brand", "BlogSel",
                 "--lang", "it", "--domain", "selftest-blog.site", "--seed", "5151",
                 "--blog", "--force"], capture_output=True, cwd=ROOT)
if _bp.exists():
    _bd = json.loads(_bp.read_text())
    _bt = (_bd.get("blog") or {}).get("topics") or []
    chk(3 <= len(_bt) <= 5, f"--blog draws 3..5 topics ({len(_bt)})")
    chk((_bd.get("blog") or {}).get("style") in ("a", "b", "c"),
        f"--blog picks one of 3 structural styles ({(_bd.get('blog') or {}).get('style')})")
    chk(all(str(t.get("date", "")) <= __import__("datetime").date.today().isoformat() for t in _bt),
        "--blog article dates are never in the future")
    _r = _subprocess.run([sys.executable, str(ROOT / "tools" / "blog_content.py"),
                          "--plan", str(_bp), "--offline"], capture_output=True, text=True, cwd=ROOT)
    _pack = json.loads(_bf.read_text()) if _bf.exists() else {}
    _berrs = _ba.validate_blog(_bd, _pack) if _pack else ["no pack"]
    chk(_r.returncode == 0 and not _berrs,
        f"offline blog pack is structure-valid ({_berrs[:2] or 'ok'})")
    if _pack:
        _broken = _copy.deepcopy(_pack)
        _broken["articles"][1]["slug"] = _broken["articles"][0]["slug"]
        chk(any("duplicated" in e for e in _ba.validate_blog(_bd, _broken)),
            "blog gate rejects a duplicate article slug")
        _broken2 = _copy.deepcopy(_pack)
        _broken2["articles"][0]["date"] = "2099-01-01"
        chk(any("future" in e for e in _ba.validate_blog(_bd, _broken2)),
            "blog gate rejects a future article date")
        _prose = _copy.deepcopy(_pack)
        _prose["articles"][0]["sections"][0]["p"][0] += " A short to-do list helps."
        chk(not _ba.validate_blog(_bd, _prose),
            "blog gate does not mistake the prose word 'to-do' for a TODO token")
        _tok = _copy.deepcopy(_pack)
        _tok["articles"][0]["sections"][0]["p"][0] += " Write to {brand}."
        _tok_errs = _ba.validate_blog(_bd, _tok)
        chk(any("template token" in e and "articles.0" in e for e in _tok_errs),
            f"blog gate names the path of a leftover template token ({_tok_errs[:1]})")
        _long = _copy.deepcopy(_pack)
        _long["articles"][0]["title"] = "Titolo " + "molto lungo " * 5
        chk(any("brand prefix" in e for e in _ba.validate_blog(_bd, _long)),
            "blog gate rejects a title whose brand-prefixed <title> exceeds 70 chars")
        _cjk = _copy.deepcopy(_pack)
        _cjk["articles"][0]["sections"][0]["p"][0] += " stop stretto允许 posizione"
        _cjk_errs = _ba.validate_blog(_bd, _cjk)
        chk(any("cjk script" in e for e in _cjk_errs),
            f"blog gate rejects foreign-script characters ({_cjk_errs[:1]})")
        chk(_ba.fmt_blog_date("2026-10-06", "it") == "6 ottobre 2026",
            "blog dates render in the site language (6 ottobre 2026)")
        _hub = (_bd.get("blog") or {}).get("hub_slug")
        chk(bool(_hub) and bool(__import__("re").fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(_hub))),
            f"--blog plan carries a valid hub slug ({_hub})")
        _art = _pack["articles"][0]
        _ld = json.loads(_ba.article_jsonld(_bd, _pack, _art,
                                            f"https://selftest-blog.site/{_art['slug']}.php",
                                            f"https://selftest-blog.site/img/{_art['slug']}.png"))
        _post = next(x for x in _ld["@graph"] if x.get("@type") == "BlogPosting")
        chk(bool(_post.get("image", {}).get("url")) and bool(_post.get("publisher", {}).get("logo")),
            "BlogPosting carries image + full publisher (name/logo)")
        _hld = json.loads(_ba.hub_jsonld(_bd, _pack, "https://selftest-blog.site/guide.php"))
        chk(any(x.get("@type") == "ItemList" for x in _hld["@graph"]),
            "hub JSON-LD carries a top-level ItemList")
    _bp.unlink(missing_ok=True)
    _bf.unlink(missing_ok=True)
else:
    chk(False, "--blog plan generated")

print("== 6d. blog pages live under /blog/")
_asm_b = sys.modules.get("assemble")
chk(getattr(_asm_b, "BLOG_DIR", "") == "blog", "BLOG_DIR is 'blog'")
_reb = _asm_b.rebase_relative
chk(_reb('<a href="index.php">x</a>') == '<a href="../index.php">x</a>',
    "rebase: root links gain ../")
chk(_reb('<img src="img/blog-a.png">') == '<img src="../img/blog-a.png">',
    "rebase: article covers gain ../")
chk(_reb('<a href="guides.php">x</a>', {"guides.php"}) == '<a href="guides.php">x</a>',
    "rebase: links inside the silo stay local")
chk(_reb('<a href="#part-1">x</a>') == '<a href="#part-1">x</a>'
    and _reb('href="https://example.com/a"') == 'href="https://example.com/a"'
    and _reb('href="mailto:a@b.c"') == 'href="mailto:a@b.c"',
    "rebase: anchors, absolute and mailto links untouched")
_bsrc = (ROOT / "blog_assemble.py").read_text()
chk('f"/{A.BLOG_DIR}/{slug}.php"' in _bsrc and 'f"/{A.BLOG_DIR}/{hub_slug}.php"' in _bsrc,
    "blog canonical URLs are built with BLOG_DIR")
chk('f"https://{dom}/{A.BLOG_DIR}/{hub_slug}.php"' in _bsrc
    and 'f"https://{dom}/{A.BLOG_DIR}/{a[\'slug\']}.php"' in _bsrc,
    "blog/hub JSON-LD URLs carry the directory")
chk("A.rebase_relative(page, local)" in _bsrc,
    "blog pages rebase shell links for the subdirectory")
# a model that answers null for an array must produce a repair instruction, not a traceback
_broken = {"sections": {"facts": {"points": None}, "portal": {"cards": None}},
           "reviews": {"items": None}, "faq": {"items": None},
           "hero": {}, "bands": {}, "meta": {}}
_broken_plan = {"numbers": {}, "params": {"brand": "X", "domain": "x.site"},
                "layout": {"section_order": ["facts", "portal", "reviews"]}}
sys.path.insert(0, str(ROOT)); import assemble as _asm2
try:
    _be = _asm2.validate_content(_broken, _broken_plan, strict=True)
    chk(any("not an array" in e for e in _be), "validator reports null arrays instead of crashing")
except Exception as e:
    chk(False, f"validator crashed on null arrays ({type(e).__name__}: {e})")
chk("{{c:sections.stats.}}" not in (ROOT / "blocks" / "blk-intro-stats.html").read_text()
    and "{{c:sections.stats.reviews}}" in (ROOT / "blocks" / "blk-intro-stats.html").read_text()
    and all(f"{{{{c:sections.stats.{k}}}}}" in (ROOT / "blocks" / "blk-numbers.html").read_text()
            for k in ("rating", "reviews", "orders", "api")),
    "stats labels from content")

print("== 1b. structural variant coverage")
import re as _re
gen_src = (ROOT / "gen_plan.py").read_text()
vblock = gen_src.split("VARIANTS = {")[1].split("}")[0]
CANON_HINT = {"claim-band": "band-access", "access-band": "band-access", "enroll-band": "band-access",
              "cta-band": "cta", "brand-note": "brandnote", "intro-center": "intro"}
pairs = _re.findall(r'"([a-z\-]+)": \[([^\]]*)\]', vblock)
chk(len(pairs) >= 12, f"variant registry slots: {len(pairs)}")
for slot, vs in pairs:
    variants = _re.findall(r'"([a-z])"', vs)
    chk(len(variants) >= 1, f"{slot}: has variants")
    if slot in ("logo", "header", "footer", "form"):   # rendered by assemble, no fragment
        chk(len(variants) >= 3, f"{slot}: several variants")
        continue
    for v in variants:
        if v == "a":                  # canonical shell renders from the canon file
            continue
        cand = [ROOT / "blocks" / f"blk-{slot}-{v}.html",
                ROOT / "blocks" / f"blk-{CANON_HINT.get(slot, slot)}-{v}.html"]
        chk(any(c.exists() for c in cand), f"{slot}-{v}: fragment exists")
chk(CANON_HINT.keys() <= {s for s, _ in pairs} | set(CANON_HINT), "canon fallbacks declared")

print("== 2. blocks.css sanity")
css = (ROOT / "blocks" / "blocks.css").read_text()
chk("@media(max-width:700px)" in css, "mobile breakpoint 700px")
chk("@media(max-width:1000px)" in css, "tablet breakpoint 1000px")
chk("prefers-reduced-motion" in css, "reduced-motion respected")
chk(css.count("{") == css.count("}"), "braces balanced")

print("== 2b. every section fragment declares a structure token")
for b in blks:
    if b.stem.startswith("blk-livebar"):
        continue
    head = b.read_text().split(">", 1)[0]
    chk(" sec-" in head, f"{b.name}: sec-* token on root")

print("== 2c. no later single-class rule may override a section-root layout")
# root class sets of every section fragment (the layout contract lives on the root)
root_sets = []
for b in blks:
    head = b.read_text().split(">", 1)[0]
    m = _re.search(r'class="([^"]+)"', head)
    if m:
        root_sets.append(set(m.group(1).split()))
css_rules = [(i, sel, body) for i, (sel, body) in enumerate(
    _re.findall(r"(?m)^(\.[\w-]+)\{([^}]*)\}", css), 1)]
layout_roots = [(i, sel[1:]) for i, sel, body in css_rules
                if "display:" in body and any(sel[1:] in rs for rs in root_sets)]
def _is_modifier(cls, other):
    co = [rs for rs in root_sets if cls in rs]
    return 0 < sum(other in rs for rs in co) < len(co)

for idx, cls in layout_roots:
    later = [(i, sel) for i, sel, body in css_rules
             if i > idx and "display:" in body and _re.fullmatch(r"\.[\w-]+", sel)
             and any(sel[1:] in rs and cls in rs for rs in root_sets)
             and not _is_modifier(cls, sel[1:])]
    chk(not later, f".{cls}: display not overridden later by {[s for _, s in later] or 'nothing'}")

print("== 2d. row-item handles both authoring shapes")
chk(".row-item>h3" in css and ".row-item>p" in css, "flat h3/p pinned to the content column")
chk("grid-column:1/-1" in css, "labelled rows never squeeze content into the label column")
chk(".row-item:has(>b)" in css and ".row-item:has(>img)" in css, "label column keyed to label presence")
flat_rows = [b.name for b in blks
             if _re.search(r'class="row-item[^"]*">(?:\s*<b>[^<]*</b>)?\s*<h3', b.read_text())]
chk(bool(flat_rows), f"flat row-item fragments covered ({', '.join(flat_rows) or 'none'})")

chk(".centered-hero{display:block" in css, "centred hero overrides the two-column grid")
chk(".centered-hero .center-band{max-width" in css, "centred hero keeps a readable measure")
chk(".center-band>p" in css and "margin-inline:auto" in css.split(".center-band>p,")[1][:120],
    "centred bands centre their width-limited children")
chk(".centered-hero{display:block" in css, "centred hero cannot inherit a two-column grid")

print("== 2e. hero variants have no empty second column")
def _top_children(frag):
    body = frag.read_text().split(">", 1)[1]
    return len(_re.findall(r"(?m)^  <[a-z]", body))

for _hf in sorted((ROOT / "blocks").glob("blk-hero*.html")):
    centered = "centered-hero" in _hf.read_text()
    kids = _top_children(_hf)
    chk(centered or kids >= 2, f"{_hf.name}: two-column hero has a second column ({kids})")
    chk(not centered or "display:block" in css, f"{_hf.name}: centred hero is single-column")

print("== 3. skins")
skins = sorted((ROOT / "skins").glob("skin-*.css"))
chk(len(skins) >= 6, f"six skins present ({len(skins)})")
for s in skins:
    t = s.read_text()
    chk(not re.search(r"[а-яіїєґА-ЯІЇЄҐ]", t), f"{s.name}: latin-only comments")
    chk(":root{" in t and "--r-card" in t, f"{s.name}: overrides geometry")

print("== 4. palettes")
pals = json.loads((ROOT / "content" / "palettes-blk.json").read_text())
chk(len(pals["palettes"]) >= 12, f"{len(pals['palettes'])} palettes")
need_keys = {"bg", "bg_soft", "panel", "ink", "muted", "line", "acc", "acc_deep", "acc_2"}
for p in pals["palettes"]:
    chk(need_keys <= set(p["vars"]), f"{p['id']}: token-complete")
chk(len(pals["fonts"]) >= 8, f"{len(pals['fonts'])} font pairs")

print("== 4b. persona genders fully classified")
sys.path.insert(0, str(ROOT)); import gen_plan as _gp
for _lg, _names in _gp.NAME_BANK.items():
    _fem = _gp.FEMALE_FIRST.get(_lg, set())
    _men = _gp.MALE_FIRST.get(_lg, set())
    _firsts = {n.split()[0].split("-")[0] for n in _names}
    chk(_firsts <= (_fem | _men), f"{_lg}: all {len(_firsts)} first names classified")
    chk(not (_firsts & _fem & _men), f"{_lg}: no name in both gender sets")

print("== 5. people bank")
people = list((ROOT / "people").glob("p-*.jpg"))
chk(len(people) >= 100, f"avatars: {len(people)}")
hashes = {hashlib.md5(pathlib.Path(f).read_bytes()).hexdigest() for f in people[:20]}
chk(len(hashes) == 20, "sampled avatars unique (full-file md5)")

print("== 6. content schema")
sch = json.loads((ROOT / "content" / "content-pack.schema.json").read_text())
for k in ("meta", "hero", "bands", "faq", "reviews", "footer"):
    chk(k in sch, f"schema section: {k}")

print("== 6a. content language bank")
bank = json.loads((ROOT / "resources" / "content-l10n.json").read_text())
for lg in ("it", "cs", "en"):
    chk(lg in bank and {"meta", "hero", "bands", "ui", "faq", "footer"} <= set(bank[lg]), f"{lg}: bank complete")
chk("EUR" in bank.get("fx", {}) and "IT" in bank.get("capital", {}), "fx + capital maps present")

print("== 6b. canonical js invoke safety (IIFE closer must actually CALL the fn)")
for js in ("lead-form.js", "calculator.js", "pulse-sim.js"):
    src = (ROOT / "blocks" / js).read_text()
    chk(src.rstrip().endswith("})();"), f"{js}: IIFE invoked (()();) closer")
    chk("})(();" not in src and "}());" not in src[:0], f"{js}: malformed closer absent")

print("== 7. end-to-end build (smoke)")
plan_f = ROOT / "plans" / "selftest-e2e.site.json"
r = subprocess.run([sys.executable, str(ROOT / "gen_plan.py"), "--brand", "Selftest E2E",
                     "--lang", "it", "--domain", "selftest-e2e.site", "--seed", "777"],
                    capture_output=True, text=True, cwd=ROOT)
chk(r.returncode == 0, f"gen_plan smoke: rc={r.returncode}")
_p = json.loads(plan_f.read_text()) if plan_f.exists() else {}
chk(_p and "blog" not in _p, "classic plan (no --blog) carries no blog block — old flow untouched")
_lb = (_p.get("livebar") or {}).get("variant")
_lb_css = (ROOT / "blocks" / "blocks.css").read_text()
chk(all(f".blk-livebar.{c}" in _lb_css for c in ("lb-board", "lb-rows", "lb-meters")),
    "livebar structural families styled (board/rows/meters)")
chk(_lb in {"b", "d", "f", "g", "h", "i", "j",
            "k", "l", "m", "n", "o", "p", "r",
            "t", "u", "v", "w", "x", "y",
            "z", "aa", "ab", "ac", "ad", "ae", "af"}, f"livebar variant chosen ({_lb})")
chk(bool((_p.get("livebar") or {}).get("subs")), "livebar subs present in plan")
if _p:
    sys.path.insert(0, str(ROOT)); import assemble as _asm
    for _lv in ("b", "c", "d", "e", "f", "g", "h"):
        _plan = json.loads(json.dumps(_p)); _plan["layout"]["variants"]["logo"] = _lv
        _h = _asm.logo_html(_plan)
        chk(f'data-var="{_lv}"' in _h and "{{" not in _h, f"logo-{_lv} renders")
    _p2 = json.loads(json.dumps(_p)); _p2["layout"]["variants"]["header"] = ""
    _hh = _asm.build_header_footer(_p2, {"bands": {}})[1]
    chk('href="index.php#claim"' in _hh, "header CTA reaches the home form from any page")
    chk(_asm.fix_anchors('<a href="#come"></a><i id="demo"></i>').count('href="#demo"') == 1,
        "dead #come anchor retargeted to the demo section")
    chk(_asm.fix_anchors('<a href="#come"></a>').count('href="index.php#claim"') == 1,
        "anchor without any target falls back to the home form")
    for _hv in ("b", "c", "d", "e", "f", "g"):
        _plan = json.loads(json.dumps(_p)); _plan["layout"]["variants"]["header"] = _hv
        _hv_html = _asm.build_header_footer(_plan, {"bands": {}})[1]
        chk(f'data-var="{_hv}"' in _hv_html and "blk-nav" in _hv_html and "menu-toggle" in _hv_html,
            f"header-{_hv} renders shell")
        if _hv == "d":
            chk("blk-logo" not in _hv_html, "header-d drops the logo")
        if _hv == "e":
            chk("blk-btn" not in _hv_html, "header-e drops the CTA")
    for _fv in ("b", "c", "d", "e", "f"):
        _plan = json.loads(json.dumps(_p)); _plan["layout"]["variants"]["footer"] = _fv
        _fh = _asm.footer_html(_plan, {"bands": {}, "footer": {}})
        chk(f'data-var="{_fv}"' in _fh and "{{" not in _fh, f"footer-{_fv} renders shell")
    # page labels (terms/privacy/404/thanks) come from the pack, not from a language table
    _c404 = {"ui": {"not_found_title": "ZZZ404-SAYFA", "not_found_back": "ZZZ404-GERI",
                    "aria_nav": "n", "aria_menu": "m"},
             "bands": {"submit_nav": "Go"}, "footer": {}, "meta": {}}
    chk(_asm.page_nav_label(_p, {"page_labels": {"about": "YYY-about"}}, "about") == "YYY-about",
        "nav label comes from the pack's page_labels, not from a language table")
    _h404 = _asm.build_404(_p, _c404, "", "", "#000")
    chk("ZZZ404-SAYFA" in _h404 and "ZZZ404-GERI" in _h404,
        "404 copy comes from the content pack (any language)")
    for _v in ("b", "d", "f", "g", "h", "i", "j",
           "k", "l", "m", "n", "o", "p", "r",
           "t", "u", "v", "w", "x", "y",
           "z", "aa", "ab", "ac"):
        import random as _rd, gen_plan as _gp
        _subs = _gp.build_livebar(_rd.Random(9), _v, "it", _p["params"].get("geo_short", ""))["subs"]
        _plan = json.loads(json.dumps(_p)); _plan["livebar"] = {"variant": _v, "subs": _subs}
        _plan["layout"]["variants"]["livebar"] = _v
        _html = _asm.R("livebar", _plan, {})
        chk("{{" not in _html and "blk-livebar" in _html, f"livebar-{_v} renders fully")
content_f = ROOT / "content" / "selftest-e2e.site-content.json"
r1c = subprocess.run([sys.executable, str(ROOT / "tools" / "content_gen.py"),
                       "--plan", str(plan_f), "--out", str(content_f), "--force"],
                      capture_output=True, text=True, cwd=ROOT)
chk(r1c.returncode == 0, f"content_gen smoke: rc={r1c.returncode} {r1c.stdout[-120:] if r1c.returncode else ''}")
pack = json.loads(content_f.read_text()) if content_f.exists() else {}
blob = json.dumps(pack, ensure_ascii=False)
chk(bool(pack) and not any(t in blob for t in ("{brand}", "{domain}", "{city}", "{deposit}", "{{c:")),
    "content pack placeholders resolved")
chk("<small>" in pack.get("bands", {}).get("form_consent", ""), "deposit wrapped in <small>")
for path, n in {"faq.items": 5, "sections.features.cards": 6, "reviews.items": 3,
                "sections.ladder.rows": 4, "hero.device_rows": 2}.items():
    node = pack
    for part in path.split("."):
        node = node.get(part, {}) if isinstance(node, dict) else {}
    chk(isinstance(node, list) and len(node) >= n, f"content array {path} >= {n}")
# the hero ledger mock must add up and must not advertise itself as "sample data"
_hh = pack.get("hero", {}) or {}
_hrows = [r for r in _hh.get("device_rows", []) if isinstance(r, dict)]
try:
    _sum = sum(float(r.get("vv", "")) for r in _hrows)
    _bal = float(_hh.get("device_bal_v", ""))
except (TypeError, ValueError):
    _sum = _bal = -1.0
chk(len(_hrows) == 2 and abs(_sum - _bal) <= 0.02,
    f"hero mock rows add up to the balance ({_sum:.2f} vs {_bal:.2f})")
chk(not any(t in blob.lower() for t in ("sample data", "dati di esempio", "ukázková data",
                                        "dati demo", "demo data")),
    "hero mock caption does not say 'sample data'")
# the same rules apply to rendered pages (audit gate) and to model-written packs
sys.path.insert(0, str(ROOT / "tools"))
import content_gen as _cg, seo_audit as _sa, llm_content as _lc
_llm_ok = {"device_note": "Ilustración · vista previa de la interfaz", "device_bal_v": "12000.00",
           "device_cur": "€", "device_cur_code": "EUR",
           "device_rows": [{"n": "Renta variable europea", "vv": "7000.00", "v": "€7.000,00"},
                           {"n": "Liquidez en euros", "vv": "5000.00", "v": "€5.000,00"}]}
_llm_bad = json.loads(json.dumps(_llm_ok))
_llm_bad["device_note"] = "Illustration · sample data"
_llm_bad["device_rows"][1].update({"vv": "4000.00", "v": "€4.000,00"})
chk(not _lc.ledger_errors(_llm_ok), "LLM contract: a written caption + balanced rows pass")
_bad_errs = _lc.ledger_errors(_llm_bad)
chk(len(_bad_errs) == 2, f"LLM contract: placeholder caption + unbalanced rows rejected ({len(_bad_errs)})")
_llm_missing = {"device_bal_v": "12000.00", "device_rows": _llm_ok["device_rows"]}
chk(any("device_note is empty" in e for e in _lc.ledger_errors(_llm_missing)),
    "LLM contract: forgotten caption is caught")
_fixed_llm = {"hero": json.loads(json.dumps(_llm_bad))}
chk(bool(_cg.reconcile_ledger(_fixed_llm))
    and abs(sum(float(r["vv"]) for r in _fixed_llm["hero"]["device_rows"]) - 12000) <= 0.02
    and _fixed_llm["hero"]["device_rows"][1]["n"] == "Liquidez en euros",
    "last resort: rows rebalanced, model labels kept")
chk(bool(_sa.audit_mock_panel(
    '<div class="ledger" role="img"><div class="ledger-head"><span>€14.933,25</span></div>'
    '<div class="ledger-row"><b>a</b><small>x</small><span>€8.935,91</span><em>+1,8%</em></div>'
    '<div class="ledger-row"><b>b</b><small>y</small><span>€3.014,21</span><em>+0,5%</em></div></div>')),
    "audit flags a ledger whose parts do not add up")
chk(not _sa.audit_mock_panel(
    '<div class="ledger"><div class="ledger-head"><span>€12.000,00</span></div>'
    '<div class="ledger-row"><b>a</b><small>x</small><span>€8.000,00</span></div>'
    '<div class="ledger-row"><b>b</b><small>y</small><span>€4.000,00</span></div></div>'),
    "audit accepts a ledger whose parts add up")
chk(bool(_sa.PLACEHOLDER_NOTE.search("Illustration · sample data")),
    "audit catches 'sample data' captions")
# language rule: a bank that covers the copy only partly must never ship a mixed page
_bank_all = json.loads(_cg.L10N.read_text(encoding="utf-8"))
chk(all(_cg.bank_coverage(_bank_all, lg)[0] == 100 for lg in ("it", "cs", "es")),
    "it/cs/es banks cover 100% of the copy")
# universal route: any language = en master copy + LLM translation layer
import localize as _lz
_src = {"content.hero.lead": "Bitnova keeps listings in one workspace.",
        "content.bands.form_consent": "Deposit <small>{deposit}</small> after 30 days.",
        "plan.layout.slugs.about": "about"}
_ok_tr = {"content.hero.lead": "A Bitnova reúne os listados num só espaço.",
          "content.bands.form_consent": "Depósito <small>{deposit}</small> após 30 dias.",
          "plan.layout.slugs.about": "sobre-nos"}
chk(not _lz.validate(_src, _ok_tr, "pt", "Bitnova", "bitnova-pt.site"),
    "localize: a faithful translation passes")
_bad_cases = {
    "placeholder dropped": dict(_ok_tr, **{"content.bands.form_consent": "Depósito <small>250</small> após 30 dias."}),
    "numbers changed": dict(_ok_tr, **{"content.bands.form_consent": "Depósito <small>{deposit}</small> após 40 dias."}),
    "brand lost": dict(_ok_tr, **{"content.hero.lead": "A empresa reúne os listados num só espaço."}),
    "slug not ascii": dict(_ok_tr, **{"plan.layout.slugs.about": "Sobre Nós"}),
    "not translated": dict(_ok_tr, **{"content.hero.lead": "Bitnova keeps listings in one workspace."}),
}
_bad_ok = all(_lz.validate(_src, case, "pt", "Bitnova", "bitnova-pt.site") for case in _bad_cases.values())
chk(_bad_ok, f"localize: {len(_bad_cases)} bad translations rejected")
chk(_lz.needs_translation("content.hero.lead", "Keeps listings") and
    not _lz.needs_translation("content.hero.device_rows.0.s", "MIX-GL") and
    not _lz.needs_translation("content.meta.email", "info@bitnova-pt.site"),
    "localize: copy is translated, tickers/emails are not")
chk(not _lz.needs_translation("content.meta.keywords", "Bitnova, bitnova login") and
    not _lz.needs_translation("content.sections.markets.rows.2.sym", "INDEX EU") and
    _lz.mark_eyebrow("BITNOVA · PT", "Bitnova") and _lz.mark_eyebrow("ALIAS · SI", "Alias Test") and
    not _lz.mark_eyebrow("PLATFORM", "Bitnova") and
    _lz.needs_translation("content.sections.risk.eyebrow", "RISKS") and
    _lz.needs_translation("content.legal.privacy", "<p>Rights via info@{domain}.</p>"),
    "localize: mark eyebrows stay, upper-case copy and legal text are translated")
_labels = {"content.ui.aria_menu": "Menu", "content.sections.ladder.rows.0.k": "Base",
           "content.sections.ladder.rows.1.k": "Pro"}
chk(not _lz.validate(_labels, dict(_labels), "pt", "Bitnova"),
    "localize: a label that reads the same in both languages is accepted")
_reordered = {"content.hero.device_delta": "↗ 2,4% in the last 30 days"}
# Japanese may add small counters ("3つの手順") but never invent a figure
chk(not _lz.validate({"x.y": "Three steps"}, {"x.y": "3つのステップ"}, "ja")
    and bool(_lz.validate({"x.y": "Three steps"}, {"x.y": "100つのステップ"}, "ja")),
    "localize: counters allowed, invented figures rejected")
_cf = {"params": {"brand": "Acme", "lang": "ja", "domain": "x.site"},
       "layout": {"slugs": {}, "menu": ["a", "b", "c", "d"], "variants": {}}}
_cfc = {"footer": {"rights": "© 2026 Acme. All rights reserved."},
        "bands": {"submit_nav": "x"}, "ui": {"aria_nav": "n", "aria_menu": "m"}}
# builder API: a live process handle must never reach json.dumps (that was a 502)
sys.path.insert(0, str(ROOT / "server"))
import api as _bapi
_pub = _bapi.Handler._job_public(object.__new__(_bapi.Handler),
                                 {"job_id": "x", "status": "running", "log": [], "_proc": object()})
chk("_proc" not in _pub and json.dumps(_pub) is not None,
    "builder API response strips live handles (no Popen in JSON)")
chk("All rights reserved" not in _asm3.footer_html(_cf, _cfc),
    "an English rights line is dropped on a translated site")
chk(not _lz.validate(_reordered, {"content.hero.device_delta": "Son 30 günde ↗ %2,4"}, "tr")
    and bool(_lz.validate(_reordered, {"content.hero.device_delta": "Son günde ↗ %2,4"}, "tr")),
    "localize: reordered numbers pass, a dropped figure fails")
_partial_bank = json.loads(json.dumps(_bank_all))
_partial_bank["es"] = {"hero": {"device_label": "Cuenta operativa"}}   # 1 key instead of 235
try:
    import contextlib as _ctx, io as _io
    with _ctx.redirect_stdout(_io.StringIO()):      # the refusal prints its own ✗ line
        _cg.build({"params": {"lang": "es"}}, _partial_bank)
    _partial_refused = False
except SystemExit:
    _partial_refused = True
_pcov = _cg.bank_coverage(_partial_bank, "es")[0]
chk(_partial_refused, f"partial bank ({_pcov}%) refuses to build a mixed-language page")
r2 = subprocess.run([sys.executable, str(ROOT / "assemble.py"), "--plan", str(plan_f),
                     "--content", str(content_f)], capture_output=True, text=True, cwd=ROOT)
ok_build = "ALL GREEN" in r2.stdout
chk(ok_build, f"assemble e2e: {'GREEN' if ok_build else r2.stdout[-300:]}")
_site = ROOT / "sites" / "selftest-e2e.site"
for _pg in _site.glob("*.php"):
    if _pg.name.startswith("_") or _pg.name in ("404.php", "thanks.php"):
        continue
    _txt = __import__("re").sub(r"<[^>]+>", " ", _pg.read_text())
    chk(len(_txt.split()) > 120, f"{_pg.name}: has real content ({len(_txt.split())} words)")
for _pg in _site.glob("*.php"):
    if _pg.name.startswith("_") or _pg.name == "404.php":
        continue
    _t = __import__("re").search(r"<title>([^<]*)</title>", _pg.read_text()).group(1).lower()
    chk(_t.startswith("selftest"), f"{_pg.name}: brand-first title")
    chk('class="brand-line"' in _pg.read_text(), f"{_pg.name}: h1 brand-line")
for _pg in _site.glob("*.php"):
    if _pg.name in ("404.php",) or _pg.name.startswith("_"):
        continue
    if "lead-form" in _pg.read_text() and "js-lead-phone" not in _pg.read_text():
        chk(False, f"{_pg.name}: lead-form without phone input")
_idx = ROOT / "sites" / "selftest-e2e.site" / "index.php"
if _idx.exists():
    _html = _idx.read_text()
    chk("{{LB" not in _html and "{{c:" not in _html, "no raw placeholders in hero/livebar")
    chk('class="blk-livebar' in _html, "livebar rendered")
    chk(f'data-var="{_lb}"' in _html, "chosen livebar variant rendered")
r4 = subprocess.run([sys.executable, str(ROOT / "tools" / "brand_icons.py"),
                     "--plan", str(plan_f), "--site", str(ROOT / "sites" / "selftest-e2e.site")],
                    capture_output=True, text=True, cwd=ROOT)
chk(r4.returncode == 0 and (ROOT / "sites" / "selftest-e2e.site" / "favicon.svg").exists(), "brand icons generated")
_fav = (ROOT / "sites" / "selftest-e2e.site" / "favicon.svg").read_text()
chk("<svg" in _fav and "viewBox=\"0 0 64 64\"" in _fav, "favicon is a real svg mark")
_arrow_plan = json.loads(json.dumps(_p)); _arrow_plan["layout"]["variants"]["logo"] = "e"
_tmp_plan = ROOT / "plans" / "selftest-arrow-logo.site.json"
_tmp_plan.write_text(json.dumps(_arrow_plan))
subprocess.run([sys.executable, str(ROOT / "tools" / "brand_icons.py"), "--plan", str(_tmp_plan),
                "--site", str(ROOT / "sites" / "selftest-e2e.site")], capture_output=True, cwd=ROOT)
chk("↗" in (ROOT / "sites" / "selftest-e2e.site" / "favicon.svg").read_text(), "logo-e favicon uses the arrow glyph")
_tmp_plan.unlink()
r5 = subprocess.run([sys.executable, str(ROOT / "tools" / "mobile_lint.py"),
                     "sites/selftest-e2e.site"], capture_output=True, text=True, cwd=ROOT)
chk(r5.returncode == 0, f"mobile lint passes: {r5.stdout[-160:] if r5.returncode else 'ok'}")
print("== 7b. calculator is switchable")
for mode, want, dom in (("off", False, "selftest-nocalc.site"), ("on", True, "selftest-calc.site")):
    pf = ROOT / "plans" / f"{dom}.json"
    rr = subprocess.run([sys.executable, str(ROOT / "gen_plan.py"), "--brand", "CalcSwitch",
                          "--lang", "it", "--domain", dom, "--calculator", mode],
                         capture_output=True, text=True, cwd=ROOT)
    _pl = json.loads(pf.read_text()) if pf.exists() else {}
    has = "calculator" in _pl.get("layout", {}).get("section_order", [])
    g3 = _pl.get("widgets", {}).get("G3")
    chk(rr.returncode == 0 and has is want and (g3 == "calculator") is want,
        f"--calculator {mode}: section {'present' if want else 'absent'}, G3={g3}")
    if pf.exists(): pf.unlink()

print("== 7c. pulse-sim is switchable")
for mode, want, dom in (("off", False, "selftest-nopulse.site"), ("on", True, "selftest-pulse.site")):
    pf = ROOT / "plans" / f"{dom}.json"
    rr = subprocess.run([sys.executable, str(ROOT / "gen_plan.py"), "--brand", "PulseSwitch",
                          "--lang", "it", "--domain", dom, "--pulse", mode],
                         capture_output=True, text=True, cwd=ROOT)
    _pl = json.loads(pf.read_text()) if pf.exists() else {}
    has = "pulse-sim" in _pl.get("layout", {}).get("section_order", [])
    g3 = _pl.get("widgets", {}).get("G3")
    subs = ((_pl.get("pulse_sim") or {}).get("subs") or {})
    ok_subs = all(("{{" not in str(v)) and str(v).strip() for v in subs.values()) if want else True
    chk(rr.returncode == 0 and has is want and (g3 == "pulse-sim") is want and ok_subs,
        f"--pulse {mode}: section {'present' if want else 'absent'}, G3={g3}, subs clean")
    if pf.exists(): pf.unlink()

print("== 8. anti-twin gate really fires")
import shutil as _sh
built = ROOT / "sites" / "selftest-e2e.site"
clone = ROOT / "sites" / "selftest-e2e-clone.site"
if clone.exists(): _sh.rmtree(clone)
_sh.copytree(built, clone)
r3 = subprocess.run([sys.executable, str(ROOT / "tools" / "twin_check.py"),
                      "sites/selftest-e2e-clone.site"], capture_output=True, text=True, cwd=ROOT)
chk(r3.returncode == 1, f"clone of a fresh site is rejected (rc={r3.returncode})")
_sh.rmtree(clone)

print("== 9. consecutive plans differ structurally")
def _plan(dom, seed):
    f = ROOT / "plans" / f"{dom}.json"
    subprocess.run([sys.executable, str(ROOT / "gen_plan.py"), "--brand", "Difftest",
                     "--lang", "cs", "--domain", dom, "--currency", "CZK",
                     "--seed", str(seed)], capture_output=True, cwd=ROOT)
    return json.loads(f.read_text()) if f.exists() else {}

def _types(o):
    m = {"claim-band": "band", "access-band": "band", "enroll-band": "band", "trust-band": "cta",
         "cta-band": "cta", "intro-center": "intro", "stats-intro": "intro", "steps-live": "steps",
         "brand-note": "brandnote"}
    return {m.get(t, t) for t in o}

p1 = _plan("difftest-a.site", 4242)
p2 = _plan("difftest-b.site", 4343)
for f in ("difftest-a.site", "difftest-b.site"):
    q = ROOT / "plans" / f"{f}.json"
    if q.exists(): q.unlink()
chk(bool(p1) and bool(p2), "two plans generated")
if p1 and p2:
    ta, tb = _types(p1["layout"]["section_order"]), _types(p2["layout"]["section_order"])
    j = len(ta & tb) / max(1, len(ta | tb))
    chk(j < 0.72, f"section inventory differs ({j:.0%})")
    chk(len(ta - tb) >= 2, f"new section types present ({len(ta - tb)})")
    chk(p1["layout"].get("variants") != p2["layout"].get("variants"), "variant maps differ")
    chk(set(p1["layout"]["slugs"].values()) != set(p2["layout"]["slugs"].values()), "slug sets differ")

print("== 10. anchors and form position rotate")
FORM_SLOTS = ("access-band", "claim-band", "enroll-band")
ANCHORS = {"people", "faq", "numbers", "cta", "office", "compare"}
forms_at, anchor_sets = [], []
for _s in range(6):
    _f = ROOT / "plans" / f"rot-test-{_s}.site.json"
    subprocess.run([sys.executable, str(ROOT / "gen_plan.py"), "--brand", "RotTest",
                    "--lang", "it", "--domain", f"rot-test-{_s}.site", "--seed", str(7000 + _s)],
                   capture_output=True, cwd=ROOT)
    _pl = json.loads(_f.read_text()) if _f.exists() else {}
    if not _pl:
        continue
    _o = _pl["layout"]["section_order"]
    _band = next((s for s in _o if s in FORM_SLOTS), None)
    if _band:
        forms_at.append(_o.index(_band))
    _m = {"cta-band": "cta", "trust-band": "cta"}
    anchor_sets.append({_m.get(s, s) for s in _o if _m.get(s, s) in ANCHORS})
for _s in range(6):   # cleanup after the whole chain: siblings must see each other
    _f = ROOT / "plans" / f"rot-test-{_s}.site.json"
    if _f.exists(): _f.unlink()
chk(len(forms_at) >= 4 and len(set(forms_at)) > 1,
    f"form band position rotates across plans (positions: {forms_at})")
_ov = [len(a & b) for a, b in zip(anchor_sets, anchor_sets[1:])]
chk(len(anchor_sets) >= 4 and max(_ov, default=0) <= 1,
    f"anchor screens rotate between consecutive plans (max overlap {max(_ov, default=0)})")

# cleanup
import shutil
out = ROOT / "sites" / "selftest-e2e.site"
if out.exists(): shutil.rmtree(out)
if plan_f.exists(): plan_f.unlink()
if content_f.exists(): content_f.unlink()

print()
if FAIL:
    print(f"SELFTEST FAILED: {len(FAIL)}"); [print("  ✗", f) for f in FAIL]; sys.exit(1)
print("SELFTEST PASSED — infrastructure healthy")
