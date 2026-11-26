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
              "blk-pulse-sim", "blk-guide", "blk-appshot", "blk-partners",
              "blk-demo-c", "blk-demo-d", "blk-demo-e", "blk-demo-f",
              "blk-markets-d", "blk-markets-e", "blk-markets-f", "blk-markets-g"}
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
    chk("appshot" in _ppd["layout"]["section_order"]
        and (_ppd.get("appshot") or {}).get("file")
        and len(_ppd.get("trust_badges") or []) >= 4,
        "every plan carries an app-shot photo and form trust badges")
else:
    chk(False, "every plan carries the reviews screen")
# validator findings are turned into a targeted repair request (keys, not the whole pack)
import repair_content as _rc
_keys = _rc.suspects(["faq answer too short (3 chars): Sì.…",
                      "office.addr_label is a sentence, use a short label: Indirizzo completo"])
chk("faq.items.0.a" in _keys and "office.addr_label" in _keys,
    "repair stage maps validator findings to exact keys")
_op = {"office": {"addr_label": "Correo de contacto disponible en tu panel.",
                  "hours_label": "Horario"}}
_asm3.office_defaults(_op, {"params": {"lang": "it", "geo": ""}})
chk(len(_op["office"]["addr_label"].split()) <= 3
    and not _op["office"]["addr_label"].endswith("."),
    "office captions are truncated to a 1-3 word label without a model call")
_healed = _asm3.self_heal_page(_dup, "Acme")
chk(_healed.count("The same long paragraph") == 2 and 'aria-hidden="true"' in _healed and
    "Acme" in _asm3.self_heal_page("<p>oAcme panel</p>", "Acme"),
    "page self-heal: duplicate paragraph dropped, brand spacing fixed")
chk(_sa2.audit_market_prices("<td>BTC/EUR</td><td>87.450</td> <td>BTC/EUR</td><td>87.450</td>") == {}
    and _sa2.audit_market_prices("<td>BTC/EUR</td><td>87.450</td> <td>BTC/EUR</td><td>5.320,50</td>") != {}
    and _sa2.audit_market_prices("EUR/USD 500 miliardi e EUR/USD 1,0842") == {}
    and _sa2.audit_market_prices("<td>BTC/EUR</td><td>87.450</td> "
                                 "<span>BTC/EUR<small>+2,4 %</small></span>") == {},
    "price gate: same symbol twice is caught, prose/percent numbers are not a quote")
chk(_asm3._num("+2.4%") == 2.4 and _asm3._num("-0,8 %") == -0.8
    and _asm3._num("87.450") == 87450 and _asm3._num("1.0842") == 1.0842
    and _asm3._num("2.930,80") == 2930.8,
    "number parser: decimals and thousands both resolved")
chk(_sa2.audit_stats_captions(
        '<section><div class="wrap stats-band"><div><strong>9.4k</strong>'
        '<span>reviews</span></div></div>'
        '<div class="wrap widget-embed"><div class="dw-scale">'
        '<span>0</span><span>50</span><span>100</span></div></div></section>') == []
    and _sa2.audit_stats_captions(
        '<div class="wrap stats-band"><div><span>1234</span></div></div>') == ["1234"],
    "stats captions stop at the band, not at an embedded gauge scale")
import content_gen as _cg
chk({k: v.strip() for k, v in _cg.PHONE_CC.items()} == _asm3.PHONE_CC,
    "phone prefixes: assemble mirrors content_gen (non-EU countries included)")
_tel_tr = _asm3.contacts_for({"params": {"domain": "x.com.tr", "cc": "TR"}, "seed": 7},
                             {"meta": {}})["telephone"]
chk(_tel_tr.startswith("+90 "),
    f"contacts: a TR offer gets a +90 number, not the '+00' placeholder ({_tel_tr})")
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
_stray = [k for k in (_lay.get("variants") or {}) if k not in ("logo", "header", "footer", "livebar", "form", "first_screen")
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
        chk("hub_slug" not in (_bd.get("blog") or {}),
            "hub is fixed at /blog/index.php (no per-plan hub slug)")
        _art = _pack["articles"][0]
        _ld = json.loads(_ba.article_jsonld(_bd, _pack, _art,
                                            f"https://selftest-blog.site/blog/{_art['slug']}.php",
                                            f"https://selftest-blog.site/img/{_art['slug']}.png"))
        _post = next(x for x in _ld["@graph"] if x.get("@type") == "BlogPosting")
        chk(bool(_post.get("image", {}).get("url")) and bool(_post.get("publisher", {}).get("logo")),
            "BlogPosting carries image + full publisher (name/logo)")
        _hld = json.loads(_ba.hub_jsonld(_bd, _pack, "https://selftest-blog.site/blog/index.php"))
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
chk('f"/{A.BLOG_DIR}/{slug}.php"' in _bsrc and 'f"/{A.BLOG_DIR}/{A.BLOG_HUB}"' in _bsrc,
    "blog canonical URLs are built with BLOG_DIR + BLOG_HUB")
chk('f"https://{dom}/{A.BLOG_DIR}/{A.BLOG_HUB}"' in _bsrc
    and 'f"https://{dom}/{A.BLOG_DIR}/{a[\'slug\']}.php"' in _bsrc,
    "blog/hub JSON-LD URLs carry the directory")
chk(getattr(_asm_b, "BLOG_HUB", "") == "index.php",
    "hub is the directory landing page (/blog/index.php)")
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

print("== 1d. interactive widget layer")
import gen_plan as _gpw
_wdir = ROOT / "widgets"
_wcss = _wdir / "widgets.css"; _wjs = _wdir / "widgets.js"
chk(_wcss.exists() and _wjs.exists(), "widget library css/js present")
_wt = _wcss.read_text()
chk(_wt.count("{") == _wt.count("}"), "widgets.css braces balanced")
_wj = _wjs.read_text()
for _wid in ("demo-line", "demo-bars", "sentiment-gauge", "book-ladder"):
    chk(f'data-widget="{_wid}"' in _wj, f"widgets.js mounts {_wid}")
_rendered = set(_gpw.G3_DEMO_LAYOUTS) | {"calculator", "pulse-sim"}
chk(set(_gpw.WIDGET_GROUPS["G3"]) - {"none"} <= _rendered,
    "every G3 draw has a real section renderer")
for _g3, _var in _gpw.G3_DEMO_LAYOUTS.items():
    chk(_g3 in _gpw.WIDGET_GROUPS["G3"], f"G3 registry keeps {_g3}")
    chk((ROOT / "blocks" / f"blk-demo-{_var}.html").exists(),
        f"{_g3}: block blk-demo-{_var} exists")
for _g1, _mvar in _gpw.G1_MARKET_LAYOUTS.items():
    chk(_g1 in _gpw.WIDGET_GROUPS["G1"], f"G1 registry keeps {_g1}")
    chk((ROOT / "blocks" / f"blk-markets-{_mvar}.html").exists(),
        f"{_g1}: block blk-markets-{_mvar} exists")

print("== 1c. widget repeat breaker")
import random as _rnd, gen_plan as _gp
_old_groups = _gp.WIDGET_GROUPS
_gp.WIDGET_GROUPS = {"G1": ["a", "b"]}
try:
    _out = _gp.break_widget_repeat(_rnd.Random(7), {"G1": "a"}, {frozenset({"a"})})
    chk(_out == {"G1": "b"},
        f"identical widget set is re-drawn, not crashed (got {_out})")
    chk(all(isinstance(k, str) for k in _out), "widget group keys stay strings")
finally:
    _gp.WIDGET_GROUPS = _old_groups

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
for path, n in {"faq.items": 12, "sections.features.cards": 6, "reviews.items": 3,
                "sections.guide.items": 6, "sections.appshot.points": 3,
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
chk(not _lz.needs_translation("content.scarcity.units.2", "min"),
    "localize: universal unit 'min' is not sent for translation")
chk(not _lz.needs_translation("content.office.addr", "Park Avenue 162, 2775 København")
    and _lz.needs_translation("content.office.hours", "Mon–Fri 09:00–18:00"),
    "localize: street addresses are kept, opening hours are still translated")
chk(not _lz.needs_translation("content.hero.device_bal", "23.898,23 CHF")
    and not _lz.needs_translation("content.hero.device_rows.0.v", "66 ms")
    and _lz.needs_translation("content.bands.mid_lead", "Buy 100 CHF today"),
    "localize: money/metric values are not translated, real sentences still are")
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
# a failed chunk must ask only the strings that failed — the full-chunk repeat is what
# turned one bad line into 15+ minutes of a 538-string pack
_calls = []


def _fake_ask(cfg, key, use_http, lang, payload, errors=None, brand=""):
    _calls.append(sorted(payload))
    if len(_calls) == 1:
        return {"content.a": "Alfa", "content.b": "Deposit thirty days"}   # b лишився англійським
    return {"content.b": "Depozyt trzydzieści dni"}


_orig_ask = _lz.ask
_lz.ask = _fake_ask
try:
    _tout, _terr = _lz.translate({"model": "x"}, "k", True, "pl",
                                 {"content.a": "Alpha copy here", "content.b": "Deposit thirty days"},
                                 brand="Acme")
finally:
    _lz.ask = _orig_ask
chk(_tout.get("content.b") == "Depozyt trzydzieści dni" and not _terr
    and _calls[1] == ["content.b"],
    "localize: a repair pass asks only the failed strings")
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
    _order = _pl.get("layout", {}).get("section_order", [])
    _we = _pl.get("layout", {}).get("widget_embed") or {}
    has = ("calculator" in _order) or (_we.get("kind") == "calculator")
    g3 = _pl.get("widgets", {}).get("G3")
    chk(rr.returncode == 0 and has is want and (g3 == "calculator") is want,
        f"--calculator {mode}: calculator {'present' if want else 'absent'}, G3={g3}")
    if pf.exists(): pf.unlink()

print("== 7c. pulse-sim is switchable")
for mode, want, dom in (("off", False, "selftest-nopulse.site"), ("on", True, "selftest-pulse.site")):
    pf = ROOT / "plans" / f"{dom}.json"
    rr = subprocess.run([sys.executable, str(ROOT / "gen_plan.py"), "--brand", "PulseSwitch",
                          "--lang", "it", "--domain", dom, "--pulse", mode],
                         capture_output=True, text=True, cwd=ROOT)
    _pl = json.loads(pf.read_text()) if pf.exists() else {}
    _order = _pl.get("layout", {}).get("section_order", [])
    _we = _pl.get("layout", {}).get("widget_embed") or {}
    has = ("pulse-sim" in _order) or (_we.get("kind") == "pulse-sim")
    g3 = _pl.get("widgets", {}).get("G3")
    subs = ((_pl.get("pulse_sim") or {}).get("subs") or {})
    ok_subs = all(("{{" not in str(v)) and str(v).strip() for v in subs.values()) if want else True
    chk(rr.returncode == 0 and has is want and (g3 == "pulse-sim") is want and ok_subs,
        f"--pulse {mode}: pulse-sim {'present' if want else 'absent'}, G3={g3}, subs clean")
    if pf.exists(): pf.unlink()

print("== 7d. G3 widget is embedded, not a separate screen")
for _g3, _var in _gp.G3_DEMO_LAYOUTS.items():
    dom = f"selftest-g3-{_var}.site"
    pf = ROOT / "plans" / f"{dom}.json"
    rr = subprocess.run([sys.executable, str(ROOT / "gen_plan.py"), "--brand", "G3Draw",
                          "--lang", "it", "--domain", dom, "--interactive", _g3],
                         capture_output=True, text=True, cwd=ROOT)
    _pl = json.loads(pf.read_text()) if pf.exists() else {}
    _order = _pl.get("layout", {}).get("section_order", [])
    _we = _pl.get("layout", {}).get("widget_embed") or {}
    chk(rr.returncode == 0 and _pl.get("widgets", {}).get("G3") == _g3
        and _we.get("kind") == _g3 and _we.get("slot") in _order
        and _we.get("variant") == _var and "demo" not in _order,
        f"--interactive {_g3}: embedded in {_we.get('slot')} (variant {_var}), no demo screen")
    if pf.exists(): pf.unlink()

print("== 7e. G1 live market draws render their own layout")
for _g1, _mvar in _gp.G1_MARKET_LAYOUTS.items():
    dom = f"selftest-g1-{_mvar}.site"
    pf = ROOT / "plans" / f"{dom}.json"
    rr = subprocess.run([sys.executable, str(ROOT / "gen_plan.py"), "--brand", "G1Draw",
                          "--lang", "it", "--domain", dom, "--market", _g1],
                         capture_output=True, text=True, cwd=ROOT)
    _pl = json.loads(pf.read_text()) if pf.exists() else {}
    _order = _pl.get("layout", {}).get("section_order", [])
    _v = (_pl.get("layout", {}).get("variants") or {}).get("markets")
    _me = _pl.get("layout", {}).get("market_embed") or {}
    ok = (("markets" in _order and _v == _mvar)
          or (_me.get("kind") == _g1 and _me.get("slot") in _order and _me.get("variant") == _mvar))
    chk(rr.returncode == 0 and _pl.get("widgets", {}).get("G1") == _g1 and ok,
        f"--market {_g1}: markets section or embedded board (variant {_mvar})")
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
# people and faq are structural (every offer carries both); rotation is about the
# remaining recognisable screens
ANCHORS = {"numbers", "cta", "office", "compare"}
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
chk(len(forms_at) >= 4 and set(forms_at) == {1},
    f"form band is always the first screen after the hero (positions: {forms_at})")
_ov = [len(a & b) for a, b in zip(anchor_sets, anchor_sets[1:])]
chk(len(anchor_sets) >= 4 and max(_ov, default=0) <= 1,
    f"anchor screens rotate between consecutive plans (max overlap {max(_ov, default=0)})")

print("== 11. schema fixtures never ship as copy")
# live bug on ing-rendement.xyz (nl): the countdown band rendered as "…" h2/lead/CTA
# and its four captions as the Ukrainian schema example "днів", because the skeleton
# repeats schema fixtures and "…" passed every "non-empty" check.
_schema = json.loads((ROOT / "content" / "content-pack.schema.json").read_text(encoding="utf-8"))
_fp = {"params": {"brand": "Fixturebrand", "domain": "fixture.site", "lang": "nl"},
       "numbers": {"rating": "4,6"},
       "layout": {"section_order": ["scarcity"], "variants": {}}, "photos": []}
_sk = _lc.skeleton(_schema, _fp, {})
chk(not re.search(r"[А-Яа-яЁёЇїІіЄєҐґ]", json.dumps(_sk["scarcity"], ensure_ascii=False)),
    "skeleton scarcity block carries no Cyrillic fixture")
chk(all(u == "" for u in _sk["scarcity"]["units"]), "skeleton units are empty slots, not a repeated label")
chk(_sk["bands"]["mid_points"] == [""] * 4, "scalar list fixtures are not duplicated")
chk(_sk["hero"]["proof"]["claims"] == [""] * 3, "foreign-language list fixtures are not duplicated")
_raw = _lc.merge_skeleton(_sk, {})          # the model skipped the scarcity slot entirely
chk(any("placeholder fixtures" in e for e in _asm3.validate_content(_raw, _fp, strict=True)),
    "validator rejects a pack that kept the '…' fixtures")
_scrubbed = _lc.scrub_placeholders(_raw)
chk("scarcity.h2" in _scrubbed and not _raw["scarcity"]["h2"].strip(),
    "ellipsis fixtures are emptied before validation")
chk(any("scarcity" in e for e in _asm3.validate_content(_raw, _fp, strict=True)),
    "emptied scarcity copy is reported as missing, not shipped")
_bad_units = json.loads(json.dumps(_raw))
_bad_units["scarcity"] = {"eyebrow": "Toegang", "h2": "Aanmelden sluit binnenkort",
                          "lead": "Uw aanvraag komt in de wachtrij.", "btn": "Aanmelden",
                          "units": ["днів", "днів", "днів", "днів"]}
_e = _asm3.validate_content(_bad_units, _fp, strict=True)
chk(any("another alphabet" in e for e in _e) and any("repeats a label" in e for e in _e),
    "Ukrainian countdown captions on an nl pack are rejected")
_live_html = ('<html lang="nl"><body><h2>…</h2><p>Toegang</p>'
              '<div class="countdown" id="countdown"><div><b>02</b><small>днів</small></div>'
              '<div><b>13</b><small>днів</small></div></div></body></html>')
chk(bool(_sa2.audit_placeholder_text({"/": (200, _live_html)})), "audit sees '…' rendered as copy")
chk(bool(_sa2.audit_countdown_labels(_live_html, "nl")), "audit sees broken countdown captions")
chk(not _sa2.audit_countdown_labels('<div class="countdown"><small>dagen</small>'
                                    '<small>uur</small><small>min</small><small>sec</small></div>', "nl"),
    "audit passes real countdown captions")

# live failure (dk-spornadike.site): inner_product came back in card shape (no
# 'paragraphs', 350/450 words). The whole pack was re-sent twice, then thrown away.
# The validator's inner-page findings now get their own small repair call.
_ik, _irest = _lc.inner_page_errors(["inner_product has 350 words, needs >= 450",
                                     "inner_offer.sections.4 needs h2 + paragraph",
                                     "hub.lead is empty"])
chk(_ik == ["inner_product", "inner_offer"] and _irest == ["hub.lead is empty"],
    "inner-page errors are separated from pack-level ones")
chk(_lc.inner_page_errors(["inner_about.blocks is empty"])[0] == [],
    "short inner pages are not mistaken for the long editorial pages")
chk(_lc.wants_inner_repair(["inner_product has 286 words, needs >= 390",
                            "brand_note.eyebrow empty"], True) == ["inner_product"],
    "a leftover empty key does not block the targeted long-page repair")
_hp = {"meta": {"title_home": "A title without the brand " + "and more words " * 4},
       "hero": {"h1_rest": "theoAcme platform"}}
_lc.self_heal(_hp, {"params": {"brand": "Acme"}})
chk(_hp["meta"]["title_home"].startswith("Acme ") and len(_hp["meta"]["title_home"]) <= 70,
    "self-heal: title_home gains the brand and fits 70 chars without a model call")
chk(_hp["hero"]["h1_rest"] == "theo Acme platform",
    "self-heal: a glued brand gets its space back")
_sp = {"sections": {"stats": {"rating": "4,5", "reviews": "Recensioni verificate",
                              "orders": "3158", "api": "Uptime API"}}}
_lc._heal_stats(_sp, {"params": {"lang": "it"}})
_sstats = _sp["sections"]["stats"]
chk(not any(re.search(r"\d", _sstats[k]) for k in ("rating", "orders"))
    and len({_sstats[k].casefold() for k in ("rating", "reviews", "orders", "api")}) == 4,
    "self-heal: numeric stats captions fall back to the language bank")
_tp = {"inner_product": {"title": "Stessa pagina", "h1": "Piattaforma unica"},
       "inner_offer": {"title": "Stessa pagina", "h1": "Come funziona"}}
_lc._heal_inner_titles(_tp)
chk(_tp["inner_product"]["title"] != _tp["inner_offer"]["title"],
    "self-heal: duplicate inner titles fall back to each page h1")
_sc = {"scarcity": {"units": ["Vagas desta semana", "Pedidos aprovados hoje",
                              "Aprovação rápida", "Vagas no lote atual"]}}
_lc._heal_scarcity(_sc, {"params": {"lang": "pt"}})
chk(_sc["scarcity"]["units"] == ["dias", "horas", "min", "seg"],
    "self-heal: countdown phrases become four time labels")
_ic = {"sections": {"features": {"cards": [{"ic": "🕘"}]}}}
_lc._heal_icons(_ic)
chk(_ic["sections"]["features"]["cards"][0]["ic"] == "◆",
    "self-heal: emoji card icon becomes a monochrome glyph")
_cat = {"meta": {"title_home": "PNAF — plataforma de investimento",
                 "category": "PNAF investimento 24/7"}}
_lc._heal_category(_cat, {"params": {"brand": "PNAF"}})
chk("category" not in _cat["meta"]
    or _lc.meta_titles._ok_category(_cat["meta"]["category"], "PNAF"),
    "self-heal: an invalid meta.category is derived without the brand or dropped")
_qt = {"hero": {"proof": {"quote": "Uso a PNAF todos os dias para acompanhar o mercado."}}}
_lc._heal_quote(_qt, {"params": {"brand": "PNAF"}})
chk("PNAF" not in _qt["hero"]["proof"]["quote"],
    "self-heal: the hero quote no longer repeats the brand")
_none_patch = {}
import repair_content as _repair_mod
_repair_mod._set(_none_patch, "thanks.eyebrow", "OBRIGADO")
chk(_none_patch.get("thanks", {}).get("eyebrow") == "OBRIGADO",
    "repair: a missing/None branch can be created by a patch")
chk(_lc.repair_targets(["faq answer too short (1 chars): ……",
                        "persona name reused from another offer: Ana K."])
    == ["faq.items", "reviews.items"],
    "object repair targets only the objects the validator named")
chk(_lc.repair_targets(["duplicate headings across sections: come funziona"]) == ["sections"],
    "cross-section findings fall back to the sections object, not the whole pack")
_pk_obj = {"faq": {"items": [{"q": "x", "a": "y"}]}, "meta": {"title_home": "Acme x"}}
_oobj = _lc.http_pack
_lc.http_pack = lambda cfg, key, messages, *a, **k: (
    json.dumps({"faq.items": [{"q": "Question here?", "a": "Answer here."}]}), "stop")
try:
    _n_obj = _lc.repair_objects(_pk_obj, {"params": {"lang": "it"}}, {},
                                ["faq answer too short"], ["faq.items"], {"model": "stub"}, "KEY")
finally:
    _lc.http_pack = _oobj
chk(_n_obj == 1 and _pk_obj["faq"]["items"][0]["a"] == "Answer here.",
    "object repair patches the named array and leaves the rest untouched")
import repair_content as _rc
chk(_rc.suspects(["faq answer too short (1 chars)"])[0] == "faq.items",
    "repair_content turns aggregate findings into an object target")
_pk_rc = {"faq": {"items": [{"q": "x", "a": "y"}]}}
_rc._set(_pk_rc, "faq.items", [{"q": "Q", "a": "A"}])
chk(_pk_rc["faq"]["items"][0]["a"] == "A",
    "repair_content applies an array patch instead of stringifying it")
_isk = {"inner_product": {"title": "", "h1": "", "lead": "",
                          "sections": [{"h2": "", "paragraphs": ["", ""],
                                        "bullets": ["", "", ""]}],
                          "faq": [{"q": "", "a": ""}]}}
_ipack = {}
_iorig = _lc.http_pack
_lc.http_pack = lambda cfg, key, messages, *a, **k: (
    json.dumps({"inner_product": {"title": "T", "sections": [
        {"h2": "H", "paragraphs": ["p1", "p2"], "bullets": ["a", "b", "c"]}]}}), "stop")
try:
    _ifix = _lc.repair_inner_pages(_ipack, {"params": {"lang": "da"}}, {"language": "da"},
                                   _isk, ["inner_product has 350 words"], ["inner_product"],
                                   {"model": "stub"}, "KEY")
finally:
    _lc.http_pack = _iorig
chk(list(_ifix) == ["inner_product"] and _ipack["inner_product"]["sections"][0]["h2"] == "H",
    "long-page repair patches only the rejected page")
_norm = _lc._normalize_inner_page({"sections": [{"h2": "Kop", "p": ["Een", "Twee"],
                                                 "points": ["a", "b"]}]})
chk(_norm["sections"][0]["paragraphs"] == ["Een", "Twee"]
    and _norm["sections"][0]["bullets"] == ["a", "b"],
    "long-page repair maps p/points aliases to paragraphs/bullets")
_ipack2 = {"inner_product": {"title": "Keep", "sections": [{"h2": "H", "paragraphs": ["p"]}]}}
_lc.http_pack = lambda cfg, key, messages, *a, **k: (
    json.dumps({"inner_product": {"title": "Empty", "sections": []}}), "stop")
try:
    _iempty = _lc.repair_inner_pages(_ipack2, {"params": {"lang": "da"}}, {"language": "da"},
                                     _isk, ["inner_product has 0 words"], ["inner_product"],
                                     {"model": "stub"}, "KEY")
finally:
    _lc.http_pack = _iorig
chk(_iempty == {} and _ipack2["inner_product"]["title"] == "Keep",
    "an empty long-page answer never replaces the page already in the pack")
_rp_lead = ("Questa sezione spiega in modo concreto il punto, con esempi pratici su "
            "costi, rischi e passaggi successivi che una persona deve conoscere.")
_rp_pack = {
    "meta": {"title_home": "X — Y"},
    "sections": {
        "guide": {"h2": "Guida", "eyebrow": "GUIDA", "lead": _rp_lead,
                  "items": [{"t": f"Tema {i}", "d": _rp_lead + " Numero %d." % i}
                            for i in range(6)]},
        "risk": {"h2": "Rischio", "eyebrow": "RISCHI", "lead": _rp_lead,
                 "rows": [{"t": "Rischio uno", "d": _rp_lead}]},
        "portal": {"h2": "Portale", "eyebrow": "AREA", "lead": _rp_lead,
                   "cards": [{"k": "Card", "t": "Titolo card", "d": _rp_lead}]},
        "notes": {"h2": "Note", "eyebrow": "NOTE", "lead": _rp_lead},
        "timeline": {"h2": "Timeline", "eyebrow": "PERCORSO", "lead": _rp_lead},
        "scarcity": {"h2": "Scarsità", "eyebrow": "ACCESSO", "lead": _rp_lead},
    },
    "faq": {"h2": "Domande",
            "items": [{"q": f"Domanda numero {i}?",
                       "a": "Risposta lunga numero %d che spiega il punto in due frasi "
                            "complete e concrete: cosa controllare, quanto costa davvero e "
                            "quali dettagli vengono spesso dimenticati." % i}
                      for i in range(12)]},
    "inner_tech": {"title": "Tecnologia", "h1": "Tecnologia", "lead": _rp_lead,
                   "blocks": [{"t": f"Blocco {i}", "d": _rp_lead} for i in range(3)]},
}
_rp = _lc.rescue_inner_pages(_rp_pack)
_rp_ok = (all(_lc._inner_words(_rp[k]) >= floor for k, floor in
              (("inner_product", 390), ("inner_offer", 390), ("inner_faq", 540)))
          and all(len(_rp[k].get("sections") or []) >= n for k, n in
                  (("inner_product", 5), ("inner_offer", 5), ("inner_faq", 2)))
          and all(len(_rp[k].get("faq") or []) >= n for k, n in
                  (("inner_product", 6), ("inner_offer", 6), ("inner_faq", 12))))
chk(_rp_ok, "rescue builder meets the long-page floors from the pack's own copy")
_home_heads = _lc._pack_headings(_rp_pack)
chk(not any(s["h2"].casefold() in _home_heads for p in _rp.values()
            for s in (p.get("sections") or [])),
    "rescue builder never repeats a heading already on the site")


print("== 12. a cut blog pack is recovered, not replaced by the offline bank")
# live failure: the provider cut a 4-article Dutch pack at char 18 830 while
# finish_reason still said "stop" — the build then wrote the offline placeholder pack.
import blog_content as _bc
_full = {"hub": {"eyebrow": "Gidsen", "title": "Gidsen voor beleggers", "lead": "Korte uitleg"},
         "articles": [{"topic": t, "slug": f"{t}-slug", "title": f"Titel {t}",
                       "sections": [{"h2": "Kop van de sectie", "p": ["Een alinea."]}],
                       "related": [f"{o}-slug"]}
                      for t, o in (("a", "b"), ("b", "a"))]}
_raw = json.dumps(_full, ensure_ascii=False, indent=1)
chk(_bc.parse_pack(_raw) == _full, "a complete blog pack parses as-is")
_part = _bc.parse_pack(_raw[:len(_raw) // 2 + 40])
chk(_part is not None and len(_part.get("articles") or []) < 2,
    "a cut pack is salvaged up to the cut (not thrown away)")
_blog_plan = {"params": {"brand": "Blogfix", "domain": "blogfix.site", "lang": "nl"},
              "blog": {"enabled": True, "style": "a",
                       "topics": [{"id": "a", "date": "2026-01-01"},
                                  {"id": "b", "date": "2026-02-02"},
                                  {"id": "c", "date": "2026-03-03"}]}}
chk([t["id"] for t in _bc.missing_topics(_blog_plan, _part or {})] == ["b", "c"],
    "topics the cut answer lost are listed for a follow-up")
_half = {"articles": [{"topic": "a", "slug": "a-slug", "sections": [{"h2": "Kop", "p": ["x"]}],
                       "faq": [{"q": "Vraag?", "a": "Antwoord."}]},
                      {"topic": "b", "slug": "b-slug", "sections": [], "faq": []}]}
chk(_bc.prune_incomplete(_half) == 1 and [a["topic"] for a in _half["articles"]] == ["a"]
    and [t["id"] for t in _bc.missing_topics(_blog_plan, _half)] == ["b", "c"],
    "a half-written article is dropped and asked for again")
_got = {"articles": [{"topic": "a", "slug": "a-slug", "title": "Titel a", "related": ["zzz"]}]}
_bc.add_articles(_blog_plan, _got, [{"topic": "c", "slug": "c-slug", "title": "Titel c"}])
chk([a["topic"] for a in _got["articles"]] == ["a", "c"], "follow-up articles keep the plan order")
chk(all(a["related"] and "zzz" not in a["related"] for a in _got["articles"]),
    "related slugs are re-pointed at real articles")
# the retry path: first answer cut, compact answer complete
_orig_http = _bc.L.http_pack
_seq = [("{oops — not json", "stop"),
        (json.dumps(_full, ensure_ascii=False), "stop")]
_bc.L.http_pack = lambda cfg, key, messages, *a, **k: _seq.pop(0) if _seq else ("", "stop")
try:
    _pack, _ = _bc.ask_model(_blog_plan, _bc.brief(_blog_plan),
                             {"model": "stub", "base_url": "http://stub"}, "http", "KEY")
finally:
    _bc.L.http_pack = _orig_http
chk(isinstance(_pack, dict) and len(_pack["articles"]) == 2,
    "a cut answer triggers one compact retry and recovers the pack")
# the other two shapes the same model produced: a raw newline inside a string value
# (live: "Invalid control character ... char 25 541") and a dangling comma
_sloppy = '{"hub":{"title":"A\nB","lead":"x",},"articles":[{"topic":"a","slug":"a",},],}'
chk(_lc.extract_json(_sloppy)["hub"]["lead"] == "x",
    "raw newlines inside strings and trailing commas are parsed, not rejected")
_orig2 = _bc.L.http_pack
_bc.L.http_pack = lambda cfg, key, messages, *a, **k: ('{"hub":{"eyebrow":"Gidsen","title":"Gidsen",'
                                                      '"lead":"Korte uitleg"}}', "stop")
try:
    _hub = _bc.ask_hub(_blog_plan, _bc.brief(_blog_plan), {"model": "stub"}, "KEY")
finally:
    _bc.L.http_pack = _orig2
chk(_hub.get("eyebrow") == "Gidsen", "the hub-only seed call returns the hub labels")

# regression (live: dk-spornadike.site): a 378-word article killed the build after two
# whole-pack repair passes. Two guards now exist: a 3% word-target floor, and per-article
# repair that rewrites only the article the gate rejected.
chk(_ba.body_word_floor("it") == 320 and _ba.body_word_target("it") == 380
    and _ba.body_word_floor("ja") < _ba.body_word_target("ja"),
    "blog word target has a ±60-word tolerance floor for every language")
_by, _pl = _bc.article_error_map(["articles[3] body is 378 words, needs >= 369",
                                  "hub.lead is empty"])
chk(_by == {3: ["articles[3] body is 378 words, needs >= 369"]} and _pl == ["hub.lead is empty"],
    "validator errors split into per-article buckets and pack-level ones")


def _shrink(art, target):
    """Trim paragraphs (never below 11 words) until the article body hits target."""
    while _bc.article_words(art) > target:
        changed = False
        for sec in art.get("sections") or []:
            for i in range(len(sec.get("p") or [])):
                toks = str(sec["p"][i]).split()
                if len(toks) > 10:
                    sec["p"][i] = " ".join(toks[:-1])
                    changed = True
                if _bc.article_words(art) <= target:
                    return
        if not changed:
            return


_tol_plan = {"seed": 1, "params": {"brand": "Blogfix", "domain": "blogfix.site", "lang": "nl"},
             "blog": {"enabled": True, "style": "a",
                      "topics": [{"id": t, "date": f"2026-0{i + 1}-01"}
                                 for i, t in enumerate(("a", "b", "c"))]}}
_tol_pack = _bc.offline_pack(_tol_plan)
_shrink(_tol_pack["articles"][0], 372)
chk(_bc.article_words(_tol_pack["articles"][0]) == 372
    and not _ba.validate_blog(_tol_plan, _tol_pack),
    "a 372-word article (within the floor) passes the blog gate")
_one = _bc.offline_pack(_tol_plan)
_one["articles"] = _one["articles"][:1]
_one["articles"][0]["related"] = []
chk(not _ba.validate_blog(_tol_plan, _one),
    "one good article is a valid blog pack (a broken one can be dropped)")
_shrink(_tol_pack["articles"][0], 300)
chk(any("body is" in e and "articles[0]" in e
        for e in _ba.validate_blog(_tol_plan, _tol_pack)),
    "an article under the floor is still rejected")
_rep_plan = {"params": {"brand": "Blogfix", "domain": "blogfix.site", "lang": "nl"},
             "blog": {"enabled": True, "style": "a",
                      "topics": [{"id": "a", "date": "2026-01-01"},
                                 {"id": "b", "date": "2026-02-02"}]}}
_rep_pack = {"hub": {}, "articles": [
    {"topic": "a", "slug": "a-old", "title": "A", "sections": [], "related": ["b-keep"]},
    {"topic": "b", "slug": "b-keep", "title": "B",
     "sections": [{"h2": "Kop van de sectie", "p": ["Een alinea."]}], "related": ["a-old"]}]}
_orig_ask = _bc.ask_article
_bc.ask_article = lambda *a, **k: {"topic": "a", "slug": "a-new", "title": "A nieuw",
                                   "sections": [{"h2": "Nieuwe kop hier",
                                                 "p": ["Een nieuwe alinea met genoeg woorden om "
                                                       "als een echte paragraaf te tellen in deze "
                                                       "test, zodat de structuurcheck hem "
                                                       "accepteert en de rest van het artikel "
                                                       "ongemoeid blijft in de pakketcontrole."]}],
                                   "faq": [{"q": "Vraag een?", "a": "Antwoord een."},
                                           {"q": "Vraag twee?", "a": "Antwoord twee."}],
                                   "related": ["b-keep"]}
try:
    _fixed_n = _bc.repair_articles(_rep_plan, _rep_pack, {}, {}, "KEY", {0: ["bad"]}, 380)
finally:
    _bc.ask_article = _orig_ask
chk(_fixed_n == 1 and _rep_pack["articles"][0]["slug"] == "a-new"
    and _rep_pack["articles"][1]["slug"] == "b-keep",
    "per-article repair rewrites the failing article and keeps the rest untouched")
chk(_rep_pack["articles"][1]["related"] == ["a-new"],
    "related slugs follow the rewritten article")
_pol_plan = {"params": {"brand": "Blogfix", "domain": "blogfix.site", "lang": "it"}}
_pol = {"articles": [{
    "title": "Titolo " + "molto lungo " * 7,
    "h1": "Breve",
    "excerpt": "Corto.",
    "read_min": 1,
    "sections": [{"h2": "Kop van de sectie",
                  "p": ["Una frase abbastanza lunga da essere un paragrafo completo."]}],
    "takeaways": ["uno", "due"]}]}
_bc.polish_pack(_pol_plan, _pol)
_pa = _pol["articles"][0]
chk(18 <= len(_pa["title"]) <= 72
    and len(_ba.A.brand_first(_pa["title"], "Blogfix")) <= 70,
    "blog polish: a long title is trimmed to the 70-char brand budget")
chk(12 <= len(_pa["h1"]) <= 90 and 60 <= len(_pa["excerpt"]) <= 190,
    "blog polish: short h1/excerpt are filled from the article body")
chk(_pa["read_min"] >= 2, "blog polish: read_min is computed from the body words")
_take2 = _bc.offline_pack(_tol_plan)
for _a2 in _take2["articles"]:
    _a2["takeaways"] = _a2["takeaways"][:2]
chk(not _ba.validate_blog(_tol_plan, _take2),
    "two takeaways are accepted (three are requested, not required)")
_reuse_pack = _bc.offline_pack(_tol_plan)
_reuse_pack["hub"]["title"] = "Gidsen voor de praktijk"
_tmp_blog = ROOT / "content" / "_selftest-blog-reuse.json"
_tmp_blog.write_text(json.dumps(_reuse_pack, ensure_ascii=False), encoding="utf-8")
try:
    chk(_gp.blog_is_reusable(_tmp_blog, _tol_plan),
        "an existing valid blog pack is reported reusable (no LLM call on rebuild)")
    _fb_pack = json.loads(json.dumps(_reuse_pack))
    _fb_pack["_offline_fallback"] = True
    _tmp_blog.write_text(json.dumps(_fb_pack, ensure_ascii=False), encoding="utf-8")
    chk(not _gp.blog_is_reusable(_tmp_blog, _tol_plan),
        "the offline blog placeholder is never reused on a rebuild")
    _tmp_blog.write_text(json.dumps(_bc.offline_pack(_tol_plan), ensure_ascii=False),
                         encoding="utf-8")
    chk(not _gp.blog_is_reusable(_tmp_blog, _tol_plan),
        "a legacy placeholder without the marker is still recognised and regenerated")
finally:
    _tmp_blog.unlink(missing_ok=True)

chk(_gp.content_is_reusable(plan_f, content_f),
    "an existing valid content pack is reported reusable (resume after a late failure)")
_cp_lang = json.loads(content_f.read_text(encoding="utf-8"))
_cp_lang.setdefault("meta", {})["content_lang"] = "enx"
_tmp_cp = ROOT / "content" / "_selftest-content-lang.json"
_tmp_cp.write_text(json.dumps(_cp_lang, ensure_ascii=False), encoding="utf-8")
try:
    chk(not _gp.content_is_reusable(plan_f, _tmp_cp),
        "a content pack written for another language is not reused")
finally:
    _tmp_cp.unlink(missing_ok=True)


print("\n== meta titles (brand-first + hook)")
sys.path.insert(0, str(ROOT / "tools"))
import meta_titles as _mt
_BRAND = "Aurevia Capital"
_got = _mt.variants(
    _BRAND, "en",
    facts=["Free demo first", "No hidden fees", "3 steps"],
    sentences=["Aurevia Capital puts market data, tools and a personal area in one place. "
               "Registration follows a clear route."],
    cta="Start now", n=6)
chk(bool(_got), "meta: variants generated without a model")
chk(all(v.title.lower().startswith(_BRAND.lower()) for v in _got),
    "meta: every title starts with the funnel name")
chk(all(len(v.title) <= _mt.TITLE_HARD for v in _got), "meta: title within the hard limit")
chk(any("AI investment platform" in v.title for v in _got),
    "meta: category phrase right after the name")
chk(all(_mt.DESC_MIN - 20 <= len(v.description) <= _mt.DESC_MAX + 10 for v in _got),
    "meta: description inside the length window")
chk(any(re.search(r"\d", v.title) for v in _got), "meta: at least one numbered hook")
_dirty = _mt.variants(_BRAND, "en", facts=["guaranteed profit", "risk-free returns"],
                      sentences=["Short."], cta="")
chk(all("guaranteed" not in v.title.lower() and "risk-free" not in v.title.lower()
        for v in _dirty), "meta: compliance words never reach a title")
_kind = _mt.lint("Best platform", "Lorem ipsum dolor sit amet, consectetur adipiscing elit sed do.",
                 _BRAND)
chk(any(lvl == "ERR" for lvl, _m in _kind), "meta: lint blocks a placeholder / non-brand title")
_pack = json.loads(content_f.read_text(encoding="utf-8"))
_pp = json.loads(plan_f.read_text(encoding="utf-8"))["params"]
_pv = _mt.pack_variants(_pack, _pp["brand"], _pp.get("lang", "en"), n=3)
chk(bool(_pv) and all(v.description for v in _pv),
    "meta: a real content pack yields complete title+description pairs")
_ja = _mt.variants("Supertrader", "ja", categories=["投資プラットフォーム"],
                   facts=["無料デモ"],
                   sentences=["Supertraderは市場データと個人エリアを一画面にまとめています。"],
                   cta="始める", n=3)
chk(bool(_ja) and all(_mt._width(v.title) <= _mt.TITLE_HARD for v in _ja),
    "meta: CJK titles are measured by SERP width, not character count")
chk(any("投資プラットフォーム" in v.title for v in _ja),
    "meta: a category written by the model in any language is used as-is")
chk(not _mt._ok_category("Best platform", _BRAND)
    and not _mt._ok_category("SuperTrader app", "SuperTrader")
    and _mt._ok_category("investing platform", _BRAND),
    "meta: slogan or brand inside the category is rejected")
chk(_mt.pack_category({"meta": {"category": "investing platform"}}, _BRAND)
    == "investing platform", "meta: meta.category from the pack wins over the bank")
_desc150 = ("Quotes, alerts and a free demo before any deposit. Three steps to request access, "
            "no monthly account fee, and the delay is printed next to every price.")
_fake = json.dumps({"variants": [{
    "title": _BRAND + " — AI investment platform, 3 steps", "description": _desc150,
    "h1_rest": "See price, spread and fee", "h1_accent": "before you click buy"}]})
_pk2 = json.loads(json.dumps(_pack))
_pv2 = _mt.with_llm(lambda _m: _fake, _BRAND, "en", categories=["AI investment platform"],
                    facts=["3 steps"], sentences=[_desc150], cta="Start now", n=3)
chk(bool(_pv2) and bool(_pv2[0].h1_rest),
    "meta: a model-written H1 is kept and ranked above a template title")
_mt.apply_to_pack(_pk2, _pv2[0])
chk(_pk2["hero"].get("h1_rest") == _pv2[0].h1_rest
    and _pk2["meta"]["title_home"] == _pv2[0].title,
    "meta: applying a variant writes hero.h1_rest and meta.title_home")
chk(_mt.lint_h1(_BRAND + " wins", "every day", _BRAND)[0][0] == "ERR",
    "meta: an H1 that repeats the brand is rejected")
_on = _mt.score_h1("See price, spread and fee", "before you click buy",
                   _BRAND, "AI investment platform")[0]
_off = _mt.score_h1("Start building wealth", "right now",
                    _BRAND, "AI investment platform")[0]
chk(_on > _off, "meta: an H1 with a market word outranks a pure-emotion H1")

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
