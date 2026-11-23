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
import json
import re

import assemble as A

BLOG_STYLES = ("a", "b", "c")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RESERVED_SLUGS = {"index", "thanks", "404", "_postback", "privacy", "terms"}
DEPOSIT_RE = re.compile(r"(€\s?250\b|250\s?€|min(?:imum)?\s?deposit|100\s?000\s?Ft)", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I)
TOKEN_RE = re.compile(r"\{\{|\}\}|\{(?:brand|domain|city|deposit)\}|TODO|PLACEHOLDER", re.I)
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF]")
HTML_RE = re.compile(r"</?[a-z][^>]*>", re.I)


def _words(text: str) -> int:
    return len(re.findall(r"\w+", str(text or ""), re.UNICODE))


def _cjk(lang: str) -> bool:
    return (lang or "").lower() in ("ja", "zh", "ko")


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
    if TOKEN_RE.search(blob):
        errs.append("unresolved token in the blog pack")
    if EMOJI_RE.search(blob):
        errs.append("emoji in the blog pack (copy uses monochrome glyphs only)")
    for path, text in _walk_paths(B):
        if HTML_RE.search(text):
            errs.append(f"{path}: HTML tag in the copy (plain text only)")
            break
        if EMAIL_RE.search(text):
            errs.append(f"{path}: plain-text email (contacts are JS-assembled on offer pages)")
            break
    brand = plan["params"]["brand"]
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
def teaser_html(plan, B) -> str:
    """Home-page section that links every article (crawl path + no orphan pages)."""
    hub = B.get("hub") or {}
    arts = B.get("articles") or []
    if not arts:
        return ""
    style = (plan.get("blog") or {}).get("style") or "a"
    eyebrow = A.esc(hub.get("eyebrow") or "Guides")
    title = A.esc(hub.get("title") or "Guides")
    lead = A.esc(hub.get("lead") or "")

    def card(a, extra=""):
        return (f'<a class="blog-card{extra}" href="{A.esc(a["slug"])}.php">'
                f'<span class="blog-card-k">{A.esc(hub.get("eyebrow") or "Guide")}</span>'
                f'<h3>{A.esc(a["title"])}</h3>'
                f'<p>{A.esc(a["excerpt"])}</p>'
                f'<span class="blog-card-meta">{A.esc(a["date"])} · {int(a.get("read_min") or 1)} '
                f'{A.esc(hub.get("min_read_label") or "min")}</span></a>')

    if style == "b" and len(arts) > 1:
        feature = arts[0]
        rows = "".join(
            f'<a class="blog-row" href="{A.esc(a["slug"])}.php"><time datetime="{A.esc(a["date"])}">'
            f'{A.esc(a["date"])}</time><span>{A.esc(a["title"])}</span>'
            f'<em>{int(a.get("read_min") or 1)} {A.esc(hub.get("min_read_label") or "min")}</em></a>'
            for a in arts[1:])
        inner = (f'<div class="blog-teaser-split"><a class="blog-feature" href="{A.esc(feature["slug"])}.php">'
                 f'<span class="blog-card-k">{A.esc(hub.get("eyebrow") or "Guide")}</span>'
                 f'<h3>{A.esc(feature["title"])}</h3><p>{A.esc(feature["excerpt"])}</p>'
                 f'<span class="blog-card-meta">{A.esc(feature["date"])} · '
                 f'{int(feature.get("read_min") or 1)} {A.esc(hub.get("min_read_label") or "min")}</span>'
                 f'</a><div class="blog-rows">{rows}</div></div>')
    elif style == "c":
        rows = "".join(
            f'<a class="blog-num-row" href="{A.esc(a["slug"])}.php"><i>{i + 1:02d}</i>'
            f'<span><b>{A.esc(a["title"])}</b><small>{A.esc(a["excerpt"])}</small></span>'
            f'<em>{int(a.get("read_min") or 1)} {A.esc(hub.get("min_read_label") or "min")}</em></a>'
            for i, a in enumerate(arts))
        inner = f'<div class="blog-num-list">{rows}</div>'
    else:
        inner = '<div class="blog-teaser-grid">' + "".join(card(a) for a in arts) + "</div>"

    return (f'<section class="section sec sec-blog-teaser" id="guides" data-blog-teaser="{style}">'
            f'<div class="wrap"><div class="blog-teaser-head"><div class="eyebrow">{eyebrow}</div>'
            f'<h2>{title}</h2><p>{lead}</p></div>{inner}</div></section>')


def _meta_line(plan, B, art) -> str:
    hub = B.get("hub") or {}
    return (f'<div class="blog-byline"><span class="blog-author">{A.esc(art.get("author"))}'
            f'<small>{A.esc(art.get("author_role"))}</small></span>'
            f'<time datetime="{A.esc(art.get("date"))}">{A.esc(art.get("date"))}</time>'
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


def article_jsonld(plan, B, art, url: str) -> str:
    brand = plan["params"]["brand"]
    dom = plan["params"]["domain"]
    hub = B.get("hub") or {}
    home = (plan.get("layout", {}).get("menu") or ["Home"])[0]
    graph = [
        {"@type": "BlogPosting", "@id": f"{url}#article", "mainEntityOfPage": {"@id": url},
         "headline": str(art.get("h1") or art.get("title") or ""),
         "description": str(art.get("excerpt") or ""),
         "datePublished": art.get("date"), "dateModified": art.get("date"),
         "inLanguage": plan["params"].get("locale", ""),
         "author": {"@type": "Person", "name": str(art.get("author") or brand)},
         "publisher": {"@id": f"https://{dom}/#org"},
         "url": url},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": home, "item": f"https://{dom}/"},
            {"@type": "ListItem", "position": 2, "name": hub.get("eyebrow") or "Guides",
             "item": f"https://{dom}/#guides"},
            {"@type": "ListItem", "position": 3, "name": art.get("title") or "", "item": url}]},
    ]
    faq = [x for x in (art.get("faq") or []) if isinstance(x, dict) and x.get("q") and x.get("a")]
    if faq:
        graph.append({"@type": "FAQPage", "@id": f"{url}#faq", "mainEntity": [
            {"@type": "Question", "name": x["q"],
             "acceptedAnswer": {"@type": "Answer", "text": x["a"]}} for x in faq]})
    return json.dumps({"@context": "https://schema.org", "@graph": graph},
                      ensure_ascii=False, separators=(",", ":"))


def build_article(plan, C, B, art, css_vars, fonts_import, theme) -> str:
    brand = plan["params"]["brand"]
    dom = plan["params"]["domain"]
    style = (plan.get("blog") or {}).get("style") or "a"
    if style not in BLOG_STYLES:
        style = "a"
    slug = art["slug"]
    url = f"https://{dom}/{slug}.php"
    hub = B.get("hub") or {}
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
    body = (f"{livebar}{header}<main>"
            f'<nav class="blog-crumbs" aria-label="{A.esc(hub.get("eyebrow") or "Guides")}">'
            f'<a href="index.php">{A.esc((plan.get("layout", {}).get("menu") or ["Home"])[0])}</a>'
            f'<span aria-hidden="true">›</span><a href="index.php#guides">{A.esc(hub.get("eyebrow") or "Guides")}</a>'
            f'<span aria-hidden="true">›</span><span>{A.esc(art.get("title"))}</span></nav>'
            f'<article class="blk-blog blk-blog-{style}" data-blog-article="{style}">'
            f'<header class="blog-head"><div class="eyebrow">{A.esc(hub.get("eyebrow") or "Guide")}'
            f' · {int(art.get("read_min") or 1)} {A.esc(hub.get("min_read_label") or "min")}</div>'
            f'<h1>{A.h1_with_brand(art.get("h1"), brand)}</h1>'
            f'<p class="blog-lead">{A.esc(art.get("excerpt"))}</p>{_meta_line(plan, B, art)}</header>'
            f'{taken}{layout}{_faq_block(B, art)}{_cta_block(plan, C, B, art)}'
            f'{_related_block(plan, C, B, art)}</article></main>{footer}')

    title = A.brand_first(art.get("title") or art.get("h1") or "", brand)
    descr = A.clamp_meta(art.get("excerpt") or "")
    keywords = str((C.get("meta") or {}).get("keywords") or "")
    page = A.page_shell(title, descr,
                        keywords.replace("{Brand}", brand).replace("{dom}", dom),
                        f"/{slug}.php",
                        plan["params"].get("locale") or plan["params"].get("lang"),
                        css_vars, fonts_import, theme, body,
                        jsonld=article_jsonld(plan, B, art, url), og_type="article")
    page = page.replace('href="#claim"', 'href="index.php#claim"')
    page = A.finish_page(page, plan, C)
    return page
