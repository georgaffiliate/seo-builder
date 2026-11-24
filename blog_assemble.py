#!/usr/bin/env python3
"""blog_assemble.py — renders the optional blog layer of an offer.

A plan built with `gen_plan.py --blog` carries `plan.blog` (style a|b|c + 3–5 topic
briefs). The model writes `content/<domain>-blog.json`; this module turns it into:

  * a teaser section on the home page (links every article, so none is an orphan);
  * one article page per entry at /<slug>.php.

The shell is the offer's own: livebar + header + footer come from
assemble.build_header_footer(), the palette/skin/fonts come from the plan. Nothing
about the classic build changes when `plan.blog` is absent.

Imported lazily from assemble.cmd_build (assemble imports this module only when the
plan asks for a blog), so the classic flow never touches blog code.

Three structural styles, not recolours:
  a — editorial single column with a takeaway box;
  b — magazine split with a sticky table of contents;
  c — compact numbered brief with a facts row.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import pathlib
import re
import shutil
import subprocess

import assemble as A

BLOG_STYLES = ("a", "b", "c")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RESERVED_SLUGS = {"index", "thanks", "404", "_postback", "privacy", "terms",
                  "api_local", "sitemap", "robots"}
DEPOSIT_RE = re.compile(r"(€\s?250\b|250\s?€|min(?:imum)?\s?deposit|100\s?000\s?Ft)", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I)
TOKEN_PATTERNS = (
    (re.compile(r"\{\{|\}\}"), "double-brace template"),
    (re.compile(r"\{(?:brand|domain|city|deposit)\}", re.I), "template token"),
    (re.compile(r"\bTODO\b"), "TODO marker"),
    (re.compile(r"\bPLACEHOLDER\b", re.I), "PLACEHOLDER marker"),
)
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF]")
HTML_RE = re.compile(r"</?[a-z][^>]*>", re.I)

# Month names used in the visible byline/teaser (ISO stays in <time datetime> and sitemap).
# Languages outside this map fall back to 06.10.2026, which is still local enough.
BLOG_MONTHS = {
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
           "agosto", "settembre", "ottobre", "novembre", "dicembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "cs": ["ledna", "února", "března", "dubna", "května", "června", "července",
           "srpna", "září", "října", "listopadu", "prosince"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"],
    "pl": ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca",
           "sierpnia", "września", "października", "listopada", "grudnia"],
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
           "agosto", "setembro", "outubro", "novembro", "dezembro"],
}

# A site in one script must not ship characters from a foreign script (the live bug
# was a Chinese 允许 inside an Italian article). Cyrillic/Greek/CJK sites keep their
# own script; every other site is Latin-only.
SCRIPT_RANGES = {
    "cjk": re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]"),
    "cyrillic": re.compile(r"[\u0400-\u04ff]"),
    "greek": re.compile(r"[\u0370-\u03ff]"),
    "arabic": re.compile(r"[\u0600-\u06ff\u0750-\u077f]"),
    "hebrew": re.compile(r"[\u0590-\u05ff]"),
    "georgian": re.compile(r"[\u10a0-\u10ff]"),
    "armenian": re.compile(r"[\u0530-\u058f]"),
}



def _words(text: str) -> int:
    return len(re.findall(r"\w+", str(text or ""), re.UNICODE))


def _cjk(lang: str) -> bool:
    return (lang or "").lower() in ("ja", "zh", "ko")


def fmt_blog_date(iso: str, lang: str) -> str:
    """'2026-10-06' → '6 ottobre 2026' (it) / '6 October 2026' (en) / '06.10.2026'."""
    try:
        d = _dt.date.fromisoformat(str(iso or ""))
    except ValueError:
        return str(iso or "")
    months = BLOG_MONTHS.get((lang or "en").lower())
    if months:
        return f"{d.day} {months[d.month - 1]} {d.year}"
    return d.strftime("%d.%m.%Y")


def _allowed_scripts(lang: str) -> set[str]:
    lang = (lang or "").lower()
    if lang in ("ru", "uk", "bg", "sr", "mk"):
        return {"latin", "cyrillic"}
    if lang == "el":
        return {"latin", "greek"}
    if lang in ("zh", "ja", "ko"):
        return {"latin", "cjk"}
    if lang == "ka":
        return {"latin", "georgian"}
    if lang == "he":
        return {"latin", "hebrew"}
    if lang == "ar":
        return {"latin", "arabic"}
    return {"latin"}


def _iter_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _iter_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_strings(v)


def validate_blog(plan: dict, B: dict) -> list[str]:
    """Content gate for content/<domain>-blog.json.

    Runs before assembly (blog_content.py) and again in assemble.cmd_build, so a
    hand-edited file cannot bypass it. Returns human-readable errors.
    """
    errs: list[str] = []
    blog = plan.get("blog") or {}
    topics = blog.get("topics") or []
    lang = plan["params"].get("lang", "en")
    brand = plan["params"]["brand"]
    today = _dt.date.today().isoformat()
    base_slugs = set((plan.get("layout", {}).get("slugs") or {}).values()) | RESERVED_SLUGS

    if not B or not isinstance(B, dict):
        return ["blog pack is empty"]
    hub = B.get("hub") or {}
    for key in ("eyebrow", "title", "lead", "toc_label", "takeaways_label",
                "related_title", "min_read_label", "faq_label",
                "facts_sections_label", "facts_words_label"):
        if not str(hub.get(key) or "").strip():
            errs.append(f"hub.{key} is empty")
    arts = B.get("articles") or []
    if not isinstance(arts, list):
        return ["blog.articles is not an array"]
    if len(arts) != len(topics):
        errs.append(f"articles: {len(arts)} entries, plan asked for {len(topics)}")
    if not 3 <= len(arts) <= 5:
        errs.append(f"articles: {len(arts)} entries, expected 3..5")

    want_ids = [str(t.get("id") or "") for t in topics]
    got_ids = [str((a or {}).get("topic") or "") for a in arts]
    if sorted(want_ids) != sorted(got_ids):
        errs.append(f"article topics do not match the plan brief: {got_ids} vs {want_ids}")

    seen_slugs, seen_titles, seen_paras = set(), set(), {}
    allowed_related = {str((a or {}).get("slug") or "").strip() for a in arts}
    for i, raw in enumerate(arts):
        a = raw or {}
        tag = f"articles[{i}]"
        slug = str(a.get("slug") or "").strip()
        if not SLUG_RE.fullmatch(slug):
            errs.append(f"{tag}.slug is not a lowercase hyphenated slug: '{slug}'")
        elif slug in base_slugs:
            errs.append(f"{tag}.slug '{slug}' collides with an existing page")
        elif slug in seen_slugs:
            errs.append(f"{tag}.slug '{slug}' is duplicated")
        seen_slugs.add(slug)
        title = str(a.get("title") or "").strip()
        h1 = str(a.get("h1") or "").strip()
        excerpt = str(a.get("excerpt") or "").strip()
        if not 18 <= len(title) <= 72:
            errs.append(f"{tag}.title length {len(title)} (18..72)")
        final_title = A.brand_first(title, brand)
        if len(final_title) > 70:
            errs.append(f"{tag}.title becomes {len(final_title)} chars with the brand prefix "
                        f"(max 70) — shorten it by {len(final_title) - 70}: “{final_title}”")
        if title.casefold() in seen_titles:
            errs.append(f"{tag}.title duplicates another article")
        seen_titles.add(title.casefold())
        if not 12 <= len(h1) <= 90:
            errs.append(f"{tag}.h1 length {len(h1)} (12..90)")
        if not (40 if _cjk(lang) else 60) <= len(excerpt) <= 190:
            errs.append(f"{tag}.excerpt length {len(excerpt)} (60..190)")
        date = str(a.get("date") or "").strip()
        if not DATE_RE.fullmatch(date) or date > today or date < "2020-01-01":
            errs.append(f"{tag}.date must be an ISO date not in the future: '{date}'")
        if not str(a.get("author") or "").strip():
            errs.append(f"{tag}.author is empty")
        if not str(a.get("author_role") or "").strip():
            errs.append(f"{tag}.author_role is empty")
        try:
            if int(a.get("read_min") or 0) < 2:
                errs.append(f"{tag}.read_min must be >= 2")
        except (TypeError, ValueError):
            errs.append(f"{tag}.read_min is not a number")

        take = a.get("takeaways") or []
        if not isinstance(take, list) or len([x for x in take if str(x).strip()]) < 3:
            errs.append(f"{tag}.takeaways needs >= 3 points")

        secs = a.get("sections") or []
        if not isinstance(secs, list) or not 3 <= len(secs) <= 7:
            errs.append(f"{tag}.sections needs 3..7 blocks")
            secs = []
        heads = set()
        words = 0
        for j, sec in enumerate(secs):
            if not isinstance(sec, dict):
                errs.append(f"{tag}.sections[{j}] is not an object")
                continue
            h2 = str(sec.get("h2") or "").strip()
            if not 8 <= len(h2) <= 90:
                errs.append(f"{tag}.sections[{j}].h2 length {len(h2)} (8..90)")
            key = h2.casefold()
            if key in heads:
                errs.append(f"{tag}.sections[{j}].h2 repeats inside the article: {h2[:40]}")
            heads.add(key)
            paras = sec.get("p") or []
            if not isinstance(paras, list) or not 1 <= len(paras) <= 5:
                errs.append(f"{tag}.sections[{j}].p needs 1..5 paragraphs")
                paras = []
            for k, para in enumerate(paras):
                text = str(para or "").strip()
                if len(text) < 40:
                    errs.append(f"{tag}.sections[{j}].p[{k}] is too short ({len(text)} chars)")
                norm = " ".join(re.sub(r"\W+", " ", text.casefold()).split())
                if len(norm) >= 60:
                    if norm in seen_paras:
                        errs.append(f"{tag}.sections[{j}].p[{k}] repeats a paragraph from "
                                    f"{seen_paras[norm]}")
                    seen_paras[norm] = f"{tag}.sections[{j}].p[{k}]"
                words += _words(text)
            pts = sec.get("points") or []
            if pts and (not isinstance(pts, list) or len(pts) < 2 or len(pts) > 6):
                errs.append(f"{tag}.sections[{j}].points needs 2..6 bullets")
            elif isinstance(pts, list):
                for p in pts:
                    if len(str(p or "").strip()) < 12:
                        errs.append(f"{tag}.sections[{j}].points has a too-short bullet")
                    words += _words(p)
            words += _words(h2)
        min_words = 220 if _cjk(lang) else 380
        if words < min_words:
            errs.append(f"{tag} body is {words} words, needs >= {min_words}")

        faq = a.get("faq") or []
        if not isinstance(faq, list) or not 2 <= len(faq) <= 5:
            errs.append(f"{tag}.faq needs 2..5 entries")
            faq = []
        for k, item in enumerate(faq):
            q = str((item or {}).get("q") or "").strip()
            ans = str((item or {}).get("a") or "").strip()
            if len(q) < 10:
                errs.append(f"{tag}.faq[{k}].q is too short")
            if len(ans) < (45 if _cjk(lang) else 90):
                errs.append(f"{tag}.faq[{k}].a is too short ({len(ans)} chars)")

        related = a.get("related") or []
        if not isinstance(related, list) or not related:
            errs.append(f"{tag}.related needs at least 1 other slug")
        else:
            for r in related:
                if r not in allowed_related or r == slug:
                    errs.append(f"{tag}.related points to an unknown/self slug: {r}")

    blob = json.dumps(B, ensure_ascii=False)
    if DEPOSIT_RE.search(blob):
        errs.append("blog pack mentions a deposit amount — deposit lives only in the form band")
    _token_hits = 0
    for path, text in _walk_paths(B):
        for rx, label in TOKEN_PATTERNS:
            m = rx.search(text)
            if not m:
                continue
            snippet = " ".join(text[max(0, m.start() - 35):m.end() + 35].split())
            errs.append(f"{path}: {label} {m.group(0)!r} in “{snippet}”")
            _token_hits += 1
            break
        if _token_hits >= 3:
            break
    if EMOJI_RE.search(blob):
        errs.append("emoji in the blog pack (copy uses monochrome glyphs only)")
    for path, text in _walk_paths(B):
        if HTML_RE.search(text):
            errs.append(f"{path}: HTML tag in the copy (plain text only)")
            break
        if EMAIL_RE.search(text):
            errs.append(f"{path}: plain-text email (contacts are JS-assembled on offer pages)")
            break
    allowed = _allowed_scripts(lang)
    _script_hits = 0
    for path, text in _walk_paths(B):
        for name, rx in SCRIPT_RANGES.items():
            if name in allowed:
                continue
            m = rx.search(text)
            if not m:
                continue
            snippet = " ".join(text[max(0, m.start() - 35):m.end() + 35].split())
            errs.append(f"{path}: {name} script inside a {lang} text — “{snippet}”")
            _script_hits += 1
            break
        if _script_hits >= 2:
            break
    glue = re.compile(rf"[a-zà-ÿ]{re.escape(brand)}", re.I)
    for path, text in _walk_paths(B):
        if glue.search(text):
            errs.append(f"{path}: brand glued to the previous word")
            break
    return errs


def _walk_paths(node, path=""):
    if isinstance(node, str):
        yield path or "pack", node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_paths(v, f"{path}.{k}".strip("."))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_paths(v, f"{path}.{i}")


# ------------------------------------------------------------------ rendering
def _cover_img(covers, slug: str, cls: str) -> str:
    c = (covers or {}).get(slug) or {}
    rel = c.get("rel")
    if not rel:
        return ""
    return (f'<img class="{cls}" src="{A.esc(rel)}" alt="" style="width:100%;height:auto" '
            f'width="1200" height="630" loading="lazy" decoding="async">')


def _teaser_inner(plan, B, covers=None, link_prefix="") -> str:
    hub = B.get("hub") or {}
    arts = B.get("articles") or []
    style = (plan.get("blog") or {}).get("style") or "a"
    lang = plan["params"].get("lang", "en")
    min_label = A.esc(hub.get("min_read_label") or "min")
    px = link_prefix

    def meta(a):
        return (f'<span class="blog-card-meta">{A.esc(fmt_blog_date(a["date"], lang))} · '
                f'{int(a.get("read_min") or 1)} {min_label}</span>')

    def card(a):
        return (f'<a class="blog-card" href="{px}{A.esc(a["slug"])}.php">'
                f'{_cover_img(covers, a["slug"], "blog-card-cover")}'
                f'<span class="blog-card-k">{A.esc(hub.get("eyebrow") or "Guide")}</span>'
                f'<h3>{A.esc(a["title"])}</h3>'
                f'<p>{A.esc(a["excerpt"])}</p>{meta(a)}</a>')

    if style == "b" and len(arts) > 1:
        feature = arts[0]
        rows = "".join(
            f'<a class="blog-row" href="{px}{A.esc(a["slug"])}.php"><time datetime="{A.esc(a["date"])}">'
            f'{A.esc(fmt_blog_date(a["date"], lang))}</time><span>{A.esc(a["title"])}</span>'
            f'<em>{int(a.get("read_min") or 1)} {min_label}</em></a>'
            for a in arts[1:])
        return (f'<div class="blog-teaser-split"><a class="blog-feature" href="{px}{A.esc(feature["slug"])}.php">'
                f'{_cover_img(covers, feature["slug"], "blog-card-cover")}'
                f'<span class="blog-card-k">{A.esc(hub.get("eyebrow") or "Guide")}</span>'
                f'<h3>{A.esc(feature["title"])}</h3><p>{A.esc(feature["excerpt"])}</p>{meta(feature)}'
                f'</a><div class="blog-rows">{rows}</div></div>')
    if style == "c":
        rows = "".join(
            f'<a class="blog-num-row" href="{px}{A.esc(a["slug"])}.php"><i>{i + 1:02d}</i>'
            f'<span><b>{A.esc(a["title"])}</b><small>{A.esc(a["excerpt"])}</small></span>'
            f'<em>{int(a.get("read_min") or 1)} {min_label}</em></a>'
            for i, a in enumerate(arts))
        return f'<div class="blog-num-list">{rows}</div>'
    return '<div class="blog-teaser-grid">' + "".join(card(a) for a in arts) + "</div>"


def teaser_html(plan, B, covers=None) -> str:
    """Home-page section that links the hub and every article (crawl path, no orphans)."""
    hub = B.get("hub") or {}
    arts = B.get("articles") or []
    if not arts:
        return ""
    style = (plan.get("blog") or {}).get("style") or "a"
    px = f"{A.BLOG_DIR}/"
    eyebrow = A.esc(hub.get("eyebrow") or "Guides")
    title = A.esc(hub.get("title") or "Guides")
    lead = A.esc(hub.get("lead") or "")
    all_label = A.esc(hub.get("all_label") or hub.get("eyebrow") or "Guides")
    return (f'<section class="section sec sec-blog-teaser" id="guides" data-blog-teaser="{style}">'
            f'<div class="wrap"><div class="blog-teaser-head"><div class="eyebrow">{eyebrow}</div>'
            f'<h2>{title}</h2><p>{lead}</p>'
            f'<a class="blog-all" href="{px}{A.BLOG_HUB}">{all_label} '
            f'<span aria-hidden="true">→</span></a></div>'
            f'{_teaser_inner(plan, B, covers, px)}</div></section>')


def hub_jsonld(plan, B, url: str) -> str:
    brand = plan["params"]["brand"]
    dom = plan["params"]["domain"]
    hub = B.get("hub") or {}
    home = (plan.get("layout", {}).get("menu") or ["Home"])[0]
    items = []
    for i, a in enumerate(B.get("articles") or [], start=1):
        u = f"https://{dom}/{A.BLOG_DIR}/{a['slug']}.php"
        items.append({"@type": "ListItem", "position": i, "name": a.get("title") or "",
                      "url": u})
    return json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "@id": f"{url}#page", "url": url,
         "name": str(hub.get("title") or "Guides"), "description": str(hub.get("lead") or ""),
         "inLanguage": plan["params"].get("locale", ""),
         "isPartOf": {"@id": f"https://{dom}/#site"},
         "mainEntity": {"@id": f"{url}#list"}},
        {"@type": "ItemList", "@id": f"{url}#list", "numberOfItems": len(items),
         "itemListElement": items},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": home, "item": f"https://{dom}/"},
            {"@type": "ListItem", "position": 2, "name": hub.get("eyebrow") or "Guides",
             "item": f"https://{dom}/{A.BLOG_DIR}/{A.BLOG_HUB}"}]}]},
        ensure_ascii=False, separators=(",", ":"))


def build_hub(plan, C, B, css_vars, fonts_import, theme, covers=None) -> str:
    """Real /blog/index.php hub: breadcrumb target, one crawl entry point for all articles."""
    brand = plan["params"]["brand"]
    dom = plan["params"]["domain"]
    hub = B.get("hub") or {}
    url = f"https://{dom}/{A.BLOG_DIR}/{A.BLOG_HUB}"
    home = (plan.get("layout", {}).get("menu") or ["Home"])[0]
    livebar, header, footer = A.build_header_footer(plan, C)
    body = (f'{livebar}{header}<main>'
            f'<nav class="blog-crumbs" aria-label="{A.esc(hub.get("eyebrow") or "Guides")}">'
            f'<a href="../index.php">{A.esc(home)}</a><span aria-hidden="true">›</span>'
            f'<span>{A.esc(hub.get("eyebrow") or "Guides")}</span></nav>'
            f'<section class="section sec sec-blog-hub" data-blog-hub="1"><div class="wrap">'
            f'<div class="blog-teaser-head"><div class="eyebrow">{A.esc(hub.get("eyebrow") or "Guides")}</div>'
            f'<h1>{A.h1_with_brand(hub.get("title"), brand)}</h1>'
            f'<p class="blog-lead">{A.esc(hub.get("lead") or "")}</p></div>'
            f'{_teaser_inner(plan, B, covers)}</div></section></main>{footer}')
    title = A.brand_first(hub.get("title") or "", brand)
    descr = A.clamp_meta(hub.get("lead") or "")
    keywords = str((C.get("meta") or {}).get("keywords") or "")
    page = A.page_shell(title, descr,
                        keywords.replace("{Brand}", brand).replace("{dom}", dom),
                        f"/{A.BLOG_DIR}/{A.BLOG_HUB}",
                        plan["params"].get("locale") or plan["params"].get("lang"),
                        css_vars, fonts_import, theme, body,
                        jsonld=hub_jsonld(plan, B, url), blog=True)
    page = page.replace('href="#claim"', 'href="../index.php#claim"')
    page = A.finish_page(page, plan, C)
    local = {A.BLOG_HUB} | {f"{a['slug']}.php" for a in (B.get("articles") or [])}
    return A.rebase_relative(page, local)


def _meta_line(plan, B, art) -> str:
    hub = B.get("hub") or {}
    return (f'<div class="blog-byline"><span class="blog-author">{A.esc(art.get("author"))}'
            f'<small>{A.esc(art.get("author_role"))}</small></span>'
            f'<time datetime="{A.esc(art.get("date"))}">'
            f'{A.esc(fmt_blog_date(art.get("date"), plan["params"].get("lang", "en")))}</time>'
            f'<span>{int(art.get("read_min") or 1)} {A.esc(hub.get("min_read_label") or "min")}</span></div>')


def _section_block(sec, idx):
    hid = f"part-{idx}"
    paras = "".join(f"<p>{A.esc(p)}</p>" for p in (sec.get("p") or []) if str(p).strip())
    pts = [str(p).strip() for p in (sec.get("points") or []) if str(p).strip()]
    bullets = f'<ul class="blog-points">{"".join(f"<li>{A.esc(p)}</li>" for p in pts)}</ul>' if pts else ""
    return f'<section class="blog-sec"><h2 id="{hid}">{A.esc(sec.get("h2"))}</h2>{paras}{bullets}</section>'


def _takeaways(B, art):
    hub = B.get("hub") or {}
    items = [str(x).strip() for x in (art.get("takeaways") or []) if str(x).strip()]
    if not items:
        return ""
    return (f'<aside class="blog-takeaways"><p class="blog-kicker">'
            f'{A.esc(hub.get("takeaways_label") or "Key points")}</p>'
            f'<ul>{"".join(f"<li>{A.esc(x)}</li>" for x in items)}</ul></aside>')


def _faq_block(B, art):
    hub = B.get("hub") or {}
    items = [x for x in (art.get("faq") or []) if isinstance(x, dict)]
    if not items:
        return ""
    rows = "".join(f'<details><summary>{A.esc(x.get("q"))}</summary>'
                   f'<p>{A.esc(x.get("a"))}</p></details>' for x in items)
    return (f'<section class="blog-faq"><h2>{A.esc(hub.get("faq_label") or "FAQ")}</h2>'
            f'<div class="faq-list">{rows}</div></section>')


def _related_block(plan, C, B, art):
    hub = B.get("hub") or {}
    arts = B.get("articles") or []
    by_slug = {a["slug"]: a for a in arts}
    rel = [by_slug[s] for s in (art.get("related") or []) if s in by_slug and s != art["slug"]]
    if not rel:
        rel = [a for a in arts if a["slug"] != art["slug"]][:2]
    if not rel:
        return ""
    cards = "".join(
        f'<a class="blog-rel" href="{A.esc(a["slug"])}.php">'
        f'<small>{A.esc(hub.get("eyebrow") or "Guide")}</small>'
        f'<h3>{A.esc(a["title"])}</h3><p>{A.esc(a["excerpt"])}</p></a>' for a in rel)
    return (f'<section class="blog-related"><h2>{A.esc(hub.get("related_title") or "Read next")}</h2>'
            f'<div class="blog-related-grid">{cards}</div></section>')


def _cta_block(plan, C, B, art):
    hub = B.get("hub") or {}
    cta = (C.get("sections") or {}).get("cta") or {}
    title = str(art.get("cta_title") or cta.get("h2") or hub.get("title") or "").strip()
    text = str(art.get("cta_text") or cta.get("lead") or "").strip()
    btn = str(art.get("cta_btn") or (C.get("bands") or {}).get("submit_nav") or "").strip()
    if not title:
        return ""
    btn_html = (f'<a class="blk-btn" href="index.php#claim">{A.esc(btn)} <span>↗</span></a>'
                if btn else "")
    return (f'<section class="blog-cta"><div class="eyebrow">{A.esc(hub.get("eyebrow") or "Guide")}</div>'
            f'<h2>{A.esc(title)}</h2><p>{A.esc(text)}</p>{btn_html}</section>')


def article_jsonld(plan, B, art, url: str, image_url: str = "") -> str:
    brand = plan["params"]["brand"]
    dom = plan["params"]["domain"]
    hub = B.get("hub") or {}
    home = (plan.get("layout", {}).get("menu") or ["Home"])[0]
    words = sum(_words(s.get("h2")) + sum(_words(p) for p in (s.get("p") or []))
                + sum(_words(x) for x in (s.get("points") or []))
                for s in (art.get("sections") or []) if isinstance(s, dict))
    post = {
        "@type": "BlogPosting", "@id": f"{url}#article",
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "headline": str(art.get("h1") or art.get("title") or ""),
        "description": str(art.get("excerpt") or ""),
        "image": {"@type": "ImageObject", "url": image_url or f"https://{dom}/og-image.png",
                  "width": 1200, "height": 630},
        "datePublished": art.get("date"), "dateModified": art.get("date"),
        "inLanguage": plan["params"].get("locale", ""),
        "author": {"@type": "Person", "name": str(art.get("author") or brand),
                   **({"jobTitle": str(art["author_role"])} if art.get("author_role") else {})},
        "publisher": {"@type": "Organization", "@id": f"https://{dom}/#org", "name": brand,
                      "url": f"https://{dom}/",
                      "logo": {"@type": "ImageObject", "url": f"https://{dom}/favicon.svg",
                               "width": 64, "height": 64}},
        "url": url,
        "isPartOf": {"@id": f"https://{dom}/#site"},
        "articleSection": str(hub.get("eyebrow") or ""),
        "wordCount": words,
    }
    graph = [post,
             {"@type": "BreadcrumbList", "itemListElement": [
                 {"@type": "ListItem", "position": 1, "name": home, "item": f"https://{dom}/"},
                 {"@type": "ListItem", "position": 2, "name": hub.get("eyebrow") or "Guides",
                  "item": f"https://{dom}/{A.BLOG_DIR}/{A.BLOG_HUB}"},
                 {"@type": "ListItem", "position": 3, "name": art.get("title") or "", "item": url}]}]
    faq = [x for x in (art.get("faq") or []) if isinstance(x, dict) and x.get("q") and x.get("a")]
    if faq:
        graph.append({"@type": "FAQPage", "@id": f"{url}#faq", "mainEntity": [
            {"@type": "Question", "name": x["q"],
             "acceptedAnswer": {"@type": "Answer", "text": x["a"]}} for x in faq]})
    return json.dumps({"@context": "https://schema.org", "@graph": graph},
                      ensure_ascii=False, separators=(",", ":"))


def build_article(plan, C, B, art, css_vars, fonts_import, theme, covers=None) -> str:
    brand = plan["params"]["brand"]
    dom = plan["params"]["domain"]
    style = (plan.get("blog") or {}).get("style") or "a"
    if style not in BLOG_STYLES:
        style = "a"
    slug = art["slug"]
    url = f"https://{dom}/{A.BLOG_DIR}/{slug}.php"
    hub = B.get("hub") or {}
    cover = (covers or {}).get(slug) or {}
    image_url = cover.get("url") if cover.get("png") else f"https://{dom}/og-image.png"
    livebar, header, footer = A.build_header_footer(plan, C)

    secs = [s for s in (art.get("sections") or []) if isinstance(s, dict)]
    blocks = "".join(_section_block(s, i + 1) for i, s in enumerate(secs))

    if style == "b":
        toc = "".join(f'<a href="#part-{i + 1}">{A.esc(s.get("h2"))}</a>'
                      for i, s in enumerate(secs))
        layout = (f'<div class="blog-layout"><aside class="blog-toc">'
                  f'<p class="blog-kicker">{A.esc(hub.get("toc_label") or "Contents")}</p>'
                  f'<nav>{toc}</nav></aside><div class="blog-body">{blocks}</div></div>')
    elif style == "c":
        words = sum(_words(s.get("h2")) + sum(_words(p) for p in (s.get("p") or []))
                    + sum(_words(x) for x in (s.get("points") or [])) for s in secs)
        layout = (f'<div class="blog-facts">'
                  f'<div><b>{len(secs)}</b><span>{A.esc(hub.get("facts_sections_label") or "sections")}</span></div>'
                  f'<div><b>{words}</b><span>{A.esc(hub.get("facts_words_label") or "words")}</span></div>'
                  f'<div><b>{int(art.get("read_min") or 1)}</b><span>{A.esc(hub.get("min_read_label") or "min")}</span></div>'
                  f'</div><div class="blog-body blog-numbered">{blocks}</div>')
    else:
        layout = (f'{_takeaways(B, art)}<div class="blog-body">{blocks}</div>')

    taken = _takeaways(B, art) if style != "a" else ""
    cover_html = (f'<figure class="blog-cover"><img src="{A.esc(cover["rel"])}" '
                  f'alt="{A.esc(art.get("title"))}" style="width:100%;height:auto" '
                  f'width="1200" height="630" '
                  f'loading="eager" fetchpriority="high" decoding="async"></figure>'
                  if cover.get("rel") else "")
    body = (f"{livebar}{header}<main>"
            f'<nav class="blog-crumbs" aria-label="{A.esc(hub.get("eyebrow") or "Guides")}">'
            f'<a href="../index.php">{A.esc((plan.get("layout", {}).get("menu") or ["Home"])[0])}</a>'
            f'<span aria-hidden="true">›</span>'
            f'<a href="{A.BLOG_HUB}">{A.esc(hub.get("eyebrow") or "Guides")}</a>'
            f'<span aria-hidden="true">›</span><span>{A.esc(art.get("title"))}</span></nav>'
            f'<article class="blk-blog blk-blog-{style}" data-blog-article="{style}">'
            f'<header class="blog-head"><div class="eyebrow">{A.esc(hub.get("eyebrow") or "Guide")}'
            f' · {int(art.get("read_min") or 1)} {A.esc(hub.get("min_read_label") or "min")}</div>'
            f'<h1>{A.h1_with_brand(art.get("h1"), brand)}</h1>'
            f'<p class="blog-lead">{A.esc(art.get("excerpt"))}</p>{_meta_line(plan, B, art)}</header>'
            f'{cover_html}{taken}{layout}{_faq_block(B, art)}{_cta_block(plan, C, B, art)}'
            f'{_related_block(plan, C, B, art)}</article></main>{footer}')

    title = A.brand_first(art.get("title") or art.get("h1") or "", brand)
    descr = A.clamp_meta(art.get("excerpt") or "")
    keywords = str((C.get("meta") or {}).get("keywords") or "")
    page = A.page_shell(title, descr,
                        keywords.replace("{Brand}", brand).replace("{dom}", dom),
                        f"/{A.BLOG_DIR}/{slug}.php",
                        plan["params"].get("locale") or plan["params"].get("lang"),
                        css_vars, fonts_import, theme, body,
                        jsonld=article_jsonld(plan, B, art, url, image_url),
                        og_type="article", og_image=image_url, blog=True)
    page = page.replace('href="#claim"', 'href="../index.php#claim"')
    page = A.finish_page(page, plan, C)
    local = {A.BLOG_HUB, f"{slug}.php"} | {
        f"{a['slug']}.php" for a in (B.get("articles") or [])}
    return A.rebase_relative(page, local)


def _palette(plan) -> dict:
    try:
        data = json.loads(A.PALETTES.read_text(encoding="utf-8"))
        p = next((x for x in data.get("palettes", []) if x.get("id") == plan["design"]["palette_id"]), None)
        return (p or {}).get("vars") or {}
    except Exception:
        return {}


def _wrap(text: str, max_chars: int, max_lines: int = 3) -> list[str]:
    words, lines, cur = str(text or "").split(), [], ""
    for w in words:
        if not cur or len(cur) + 1 + len(w) <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != " ".join(str(text or "").split()):
        lines[-1] = lines[-1].rstrip(" .,;:—-") + "…"
    return lines or [""]


def _cover_svg(plan, B, art) -> str:
    v = _palette(plan)
    bg = v.get("bg", "#111111")
    ink = v.get("ink", "#ffffff")
    acc = v.get("acc", "#c8a24a")
    acc2 = v.get("acc_2", acc)
    brand = plan["params"]["brand"]
    dom = plan["params"]["domain"]
    head = plan["design"]["fonts"]["head"]
    hub = B.get("hub") or {}
    eyebrow = str(hub.get("eyebrow") or "Guide")[:42]
    title = str(art.get("title") or art.get("h1") or "")
    title_len = len(title)
    if title_len <= 46:
        fs, maxc = 72, 30
    elif title_len <= 62:
        fs, maxc = 62, 36
    else:
        fs, maxc = 54, 42
    lines = _wrap(title, maxc, 3)
    seed = int(hashlib.sha1(str(art.get("slug") or "").encode()).hexdigest()[:6], 16) % 3
    if seed == 0:
        decor = (f'<circle cx="1040" cy="190" r="210" fill="{acc}" opacity=".09"/>'
                 f'<circle cx="1040" cy="190" r="120" fill="{acc2}" opacity=".08"/>')
    elif seed == 1:
        decor = (f'<path d="M760 630 L1200 170 V630 Z" fill="{acc}" opacity=".08"/>'
                 f'<path d="M900 630 L1200 340 V630 Z" fill="{acc2}" opacity=".07"/>')
    else:
        decor = "".join(
            f'<rect x="{880 + (i % 3) * 90}" y="{110 + (i // 3) * 90}" width="64" height="64" '
            f'rx="10" fill="{acc}" opacity=".07"/>' for i in range(9))
    title_svg = "".join(
        f'<text x="72" y="{300 + i * (fs + 10)}" font-family="{A.esc(head)}, Georgia, serif" '
        f'font-size="{fs}" font-weight="700" fill="{ink}">{A.esc(line)}</text>'
        for i, line in enumerate(lines))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630" role="img" aria-label="{A.esc(title)}">
<rect width="1200" height="630" fill="{bg}"/>
{decor}
<text x="72" y="112" font-family="{A.esc(head)}, Georgia, serif" font-size="28" font-weight="700" fill="{ink}" opacity=".62">{A.esc(brand)}</text>
<rect x="72" y="140" width="88" height="6" rx="3" fill="{acc}"/>
<text x="72" y="205" font-family="Helvetica, Arial, sans-serif" font-size="21" font-weight="700" letter-spacing="2.6" fill="{acc}">{A.esc(eyebrow.upper())}</text>
{title_svg}
<rect x="72" y="592" width="1056" height="1" fill="{ink}" opacity=".16"/>
<text x="72" y="566" font-family="Helvetica, Arial, sans-serif" font-size="23" fill="{ink}" opacity=".58">{A.esc(dom)}</text>
</svg>
'''


def write_covers(out, plan, B) -> dict:
    """Deterministic 1200×630 article covers from the offer palette.

    PNG is used for og:image / BlogPosting.image when rsvg-convert is available;
    the SVG stays in the site either way (and is the <img> fallback).
    """
    out = pathlib.Path(out)
    img = out / "img"
    img.mkdir(parents=True, exist_ok=True)
    dom = plan["params"]["domain"]
    covers = {}
    for art in B.get("articles") or []:
        slug = art.get("slug")
        if not slug:
            continue
        svg_path = img / f"blog-{slug}.svg"
        svg_path.write_text(_cover_svg(plan, B, art), encoding="utf-8")
        png_path = img / f"blog-{slug}.png"
        png = False
        if shutil.which("rsvg-convert"):
            rc = subprocess.run(["rsvg-convert", "-w", "1200", "-h", "630",
                                 str(svg_path), "-o", str(png_path)],
                                capture_output=True).returncode
            png = rc == 0 and png_path.exists()
        rel = f"img/blog-{slug}.png" if png else f"img/blog-{slug}.svg"
        covers[slug] = {"rel": rel, "png": png, "url": f"https://{dom}/{rel}"}
    return covers
