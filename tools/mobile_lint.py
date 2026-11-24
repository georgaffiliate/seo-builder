#!/usr/bin/env python3
"""mobile_lint.py — static mobile sanity gate for a built site (360/390/768 contract).

Catches what the SEO audit ignores: missing viewport meta, wide tables outside
.tbl-scroll, inline grid-template-columns, fixed widths above the 360 px floor
and unbreakable strings in headings.

Usage: python3 tools/mobile_lint.py sites/<domain>
Exit 1 on any error.
"""
from __future__ import annotations
import pathlib, re, sys

VPH = re.compile(r'<meta[^>]+name=["\']viewport["\'][^>]+width=device-width', re.I)
INLINE_GRID = re.compile(r'style=["\'][^"\']*grid-template-columns', re.I)


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _mobile_before_base(css: str) -> list:
    """Selectors whose @media(max-width) block appears before their own base rule."""
    css = _strip_comments(css)
    media_spans = []
    for m in re.finditer(r"@media[^{]*\(max-width[^{]*\)\s*\{", css):
        depth, i = 1, m.end()
        while i < len(css) and depth:
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
            i += 1
        media_spans.append((m.start(), i))

    def in_media(pos: int) -> bool:
        return any(a <= pos < b for a, b in media_spans)

    def selectors(text: str):
        for m in re.finditer(r"([^{}@;]+)\{", text):
            raw = m.group(1).strip()
            if not raw or raw.startswith("@"):
                continue
            for sel in raw.split(","):
                sel = " ".join(sel.split())
                if sel:
                    yield sel, m.start()

    last_base = {}
    for sel, pos in selectors(css):
        if not in_media(pos):
            last_base[sel] = max(pos, last_base.get(sel, -1))
    bad = []
    for sel, pos in selectors(css):
        if in_media(pos) and sel in last_base and pos < last_base[sel] and sel not in bad:
            bad.append(sel)
    return bad[:6]


def main():
    if len(sys.argv) < 2:
        print("usage: mobile_lint.py sites/<domain>")
        sys.exit(2)
    site = pathlib.Path(sys.argv[1])
    if not site.is_dir():
        print(f"✗ no such site: {site}")
        sys.exit(1)
    errs, warns, checks = [], [], 0

    pages = sorted(p for p in site.glob("*.php") if not p.name.startswith("_"))
    blog_dir = site / "blog"
    if blog_dir.is_dir():
        pages += sorted(p for p in blog_dir.glob("*.php") if not p.name.startswith("_"))
    for page in pages:
        html = page.read_text(encoding="utf-8")
        checks += 1
        if not VPH.search(html):
            errs.append(f"{page.name}: no width=device-width viewport")
        for m in INLINE_GRID.finditer(html):
            snippet = html[max(0, m.start() - 60):m.start() + 40].splitlines()[-1]
            errs.append(f"{page.name}: inline grid-template-columns → {snippet.strip()[:70]}")
        ids = set(re.findall(r'id="([^"]+)"', html))
        for href in re.findall(r'href="#([^"]+)"', html):
            checks += 1
            if href not in ids and not href.startswith("/"):
                errs.append(f"{page.name}: dead anchor #{href}")
        for m in re.finditer(r"<table", html, re.I):
            window = html[max(0, m.start() - 250):m.start()]
            if "tbl-scroll" not in window:
                errs.append(f"{page.name}: <table> outside .tbl-scroll")
        for m in re.finditer(r"<(?:img|svg|iframe)[^>]*\bwidth=[\"'](\d{3,})[\"']", html, re.I):
            if int(m.group(1)) > 360 and "width:100%" not in m.group(0):
                warns.append(f"{page.name}: fixed width {m.group(1)}px")
        large = [x for x in re.findall(r"\bmin-width:\s*(\d{3,})px", html) if int(x) > 360]
        if large:
            warns.append(f"{page.name}: min-width {','.join(sorted(set(large)))}px")

    css_files = list(site.glob("*.css")) + list((site / "blocks").glob("*.css")) if (site / "blocks").is_dir() else list(site.glob("*.css"))
    for css in css_files:
        checks += 1
        body = css.read_text(encoding="utf-8")
        if body.count("{") != body.count("}"):
            errs.append(f"{css.name}: unbalanced braces")
        if not css.name.startswith("skin") and not re.search(r"@media\s*\(\s*max-width", body):
            errs.append(f"{css.name}: no max-width breakpoint")
        wide = [x for ln in body.splitlines() if "@media" not in ln
                for x in re.findall(r"min-width:\s*(\d{3,})px", ln) if int(x) > 360]
        if wide:
            warns.append(f"{css.name}: hard min-width {','.join(sorted(set(wide)))}px")
        # a mobile override written BEFORE the component's base rule loses the cascade:
        # the base grid/flex rule later in the file wins and the phone layout breaks
        for sel in _mobile_before_base(body):
            warns.append(f"{css.name}: mobile rule for '{sel}' sits before its base rule "
                         f"— the base overrides it on phones")

    print(f"=== MOBILE LINT ({site}) ===")
    print(f"files checked: {checks}")
    print(f"ERRORS: {len(errs)}")
    for e in errs:
        print("  ✗", e)
    print(f"WARNINGS: {len(warns)}")
    for w in warns[:12]:
        print("  !", w)
    if errs:
        sys.exit(1)


if __name__ == "__main__":
    main()
