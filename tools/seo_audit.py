#!/usr/bin/env python3
"""SEO/runtime auditor for landing offers. Zero external deps (stdlib only).

Usage:
  python3 seo_audit.py sites/<offer-folder> [--deploy]

Spins up a local php -S server (if php available), crawls every linked page,
and runs all checks an LLM builder tends to miss. Exit code 0 = ship, 1 = fix first.

Add to BUILD.sh before deploy step:
  python3 ../../seo_audit.py . || exit 1
"""
import json, os, re, socket, subprocess, sys, time, urllib.request, urllib.error
from html.parser import HTMLParser
from collections import defaultdict

PORT = 8794

def _free_port(preferred):
    """Pick an unused TCP port on localhost (parallel audits collide otherwise)."""
    for p in (preferred, 0):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p))
            port = s.getsockname()[1]
            return port
        except OSError:
            continue
        finally:
            s.close()
    return preferred

class PageParser(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.links, self.imgs, self.headings = [], [], defaultdict(list)
        self.title, self.canonical, self.h1 = "", [], []
        self.metas, self.jsonlds = {}, []
        self._in_title = False
        self._in_jsonld = 0
        self._json_buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        t = tag.lower()
        if t == "title": self._in_title = True
        elif t == "meta" and a.get("name"): self.metas[a["name"].lower()] = a.get("content", "")
        elif t == "link" and a.get("rel") == "canonical": self.canonical = a.get("href", "")
        elif t in ("h1","h2","h3"):
            depth_placeholder = None
            self.headings[t.upper()].append({"pending": True})
        elif t == "a" and a.get("href"): self.links.append(a["href"])
        elif t == "img": self.imgs.append(a)
        elif t == "script" and a.get("type") == "application/ld+json":
            self._in_jsonld += 1
            self._json_buf.append([])

    def handle_endtag(self, tag):
        t = tag.lower()
        if t == "title": self._in_title = False
        elif t == "script" and self._in_jsonld:
            self._in_jsonld -= 1

    def handle_data(self, data):
        if self._in_title: self.title += data.strip()
        elif self._in_jsonld: self._json_buf[-1].append(data)

def fetch(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "seo-audit/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")

# --------- lighter regex fallback parser (robust enough for our own output) ---------
def extract(page_html, base_url):
    out = {}
    out["title"] = (re.search(r"<title[^>]*>(.*?)</title>", page_html, re.S|re.I) or [None,""])[1].strip()
    out["metas"] = {m[0].lower(): m[1] for m in re.findall(
        r'<meta[^>]+name=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']', page_html, re.I)}
    out["metas"].update({m[0].lower(): m[1] for m in re.findall(
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']([^"\']+)["\']', page_html, re.I)})
    out["h1s"] = [re.sub(r"<[^>]+>", "", m).strip() for m in re.findall(r"<h1[^>]*>(.*?)</h1>", page_html, re.S|re.I)]
    out["h2s"] = [re.sub(r"<[^>]+>", "", m).strip() for m in re.findall(r"<h2[^>]*>(.*?)</h2>", page_html, re.S|re.I)]
    out["canonical"] = (re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', page_html, re.I) or [None,""])[1]
    if not out["canonical"]:
        out["canonical"] = (re.search(r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']canonical["\']', page_html, re.I) or [None,""])[1]
    out["hreflangs"] = re.findall(r'hreflang=["\']([^"\']+)["\']', page_html, re.I)
    out["imgs_noalt"] = len(re.findall(r"<img(?![^>]*\balt=)[^>]*>", page_html, re.I))
    out["forms"] = {
        "lead_forms": len(re.findall(r'<form[^>]+class=["\'][^"\']*lead-form', page_html, re.I)),
        "phone_inputs": len(re.findall(r'<input[^>]+js-lead-phone', page_html)),
        "submit_btns": len(re.findall(r'class=["\'][^"\']*form-submit', page_html)),
        "server_hidden": len(re.findall(r'name=["\'](country|lang|funnel|domain|buyer)["\']', page_html)),
        "inline_scripts": len([m for m in re.findall(r"<script([^>]*)>", page_html, re.I)
                               if "src=" not in m and "ld+json" not in m]),
        "data_demo_on_lead": len(re.findall(r'<form[^>]+data-demo[^>]+lead-form|<form[^>]+lead-form[^>]+data-demo', page_html, re.I)),
    }
    out["links"] = re.findall(r'href=["\']([^"\']+)["\']', page_html)
    jd = re.findall(r'<script[^>]+ld\+json[^>]*>(.*?)</script>', page_html, re.S|re.I)
    parsed = []
    for raw in jd:
        try: parsed.append(json.loads(raw))
        except Exception as e: parsed.append({"__invalid__": str(e)[:100]})
    out["jsonld"] = parsed
    out["brand_in_h1_line"] = bool(re.search(r'<h1[^>]*>.*?<span[^>]+class=["\'][^"\']*brand-line', page_html, re.S|re.I))
    bl = re.search(r'<span[^>]+class=["\'][^"\']*brand-line[^>]*>(.*?)</span>', page_html, re.S|re.I)
    out["brand_line"] = re.sub(r"<[^>]+>", "", bl[1]).strip() if bl else ""
    return out

CHECKS = []          # (level, msg)
def chk(cond_ok, lvl, ok_msg=None, fail_msg=None):
    CHECKS.append(("ok" if cond_ok else lvl, ok_msg if cond_ok else fail_msg))

def norm_url(href, page):
    """Return normalized ABSOLUTE http URL when origin known, else path-like."""
    if href.startswith(("mailto:", "tel:", "javascript:", "#")): return None
    if href.startswith("//"): return "https:" + href
    if href.startswith("http"): return href
    if href.startswith("/"):
        return "PATH:" + href
    base = page if page.startswith("PATH:") else "PATH:/"
    cur = base[5:].rsplit("/", 1)[0]
    while href.startswith("../"):
        href = href[3:]
        cur = cur.rsplit("/", 1)[0] if "/" in cur else ""
    return "PATH:" + (cur + "/" + href.lstrip("/"))

CHK_EXTENSIONS = (".php", "/", "")

# ------------------------- comment-language gate -------------------------
# Rule: shipped files must contain NO Cyrillic comments (bug: site scripts
# surfaced Ukrainian comments in browser DevTools). Any Cyrillic text that
# is not inside quotes/strings must live only in comments, so we flag it.
CYR_RE = re.compile(r"[А-Яа-яЁёЇїІіЄєҐґ]")
SHIP_EXTS = (".js", ".css", ".php", ".html", ".htm", ".svg", ".xml", ".txt")
SHIP_SKIP_DIRS = {"storage", "jobs", "node_modules", ".git", "img", "fonts", "icons"}

CODE, STR, LINE, BLOCK, HTML = range(5)

def _iter_comment_spans(src):
    """Single-pass lexer over RAW source: yields (start,end) spans of
    <!-- -->, // EOL and /* */ comments. Tracks string literals so
    apostrophes inside comments ("buyer's chat") do not swallow comment
    terminators, and '//' inside strings ("https://...") stays untreated."""
    i, n = 0, len(src)
    st, q, start = CODE, "", 0
    while i < n:
        c = src[i]
        if st == CODE:
            if src[i:i + 4] == "<!--":
                st, start, i = HTML, i, i + 4; continue
            if src[i:i + 2] == "/*":
                st, start, i = BLOCK, i, i + 2; continue
            if src[i:i + 2] == "//":
                st, start, i = LINE, i, i + 2; continue
            if c in ("'", '"'):
                st, q = STR, c
            i += 1
        elif st == STR:
            if c == "\\":
                i += 2; continue
            if c == q:
                st = CODE
            i += 1
        elif st == LINE:
            if c == "\n":
                yield start, i; st = CODE
            i += 1
        elif st == BLOCK:
            if src[i:i + 2] == "*/":
                i += 2; yield start, i; st = CODE; continue
            i += 1
        else:  # HTML
            j = src.find("-->", i)
            j = n if j == -1 else j + 3
            yield start, j; i = j; st = CODE
    if st in (LINE, BLOCK, HTML) and start < n:
        yield start, n

def audit_cyrillic_comments(folder):
    """Return [(relpath, line, snippet)] for Cyrillic found inside comment
    regions of every shipped text file (browser- or dev-facing code)."""
    out = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SHIP_SKIP_DIRS and not d.startswith(".")]
        for fn in files:
            if not fn.lower().endswith(SHIP_EXTS):
                continue
            p = os.path.join(root, fn)
            try:
                src = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for a, b in _iter_comment_spans(src):
                frag = src[a:b]
                if CYR_RE.search(frag):
                    line = src.count("\n", 0, a) + 1
                    out.append((os.path.relpath(p, folder), line, " ".join(frag.split())[:70]))
    return out

def _page_text_nodes(html):
    """Strip script/style/comments/tags; return visible text only."""
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)

def audit_visible_cyrillic(pages):
    """Cyrillic in RENDERED page text (spot offer-language leaks)."""
    out = []
    for path, (_, html) in pages.items():
        hit = CYR_RE.search(_page_text_nodes(html))
        if hit:
            frag = " ".join(_page_text_nodes(html).split())
            pos = CYR_RE.search(frag).start()
            out.append((path, frag[max(0, pos - 30):pos + 40]))
    return out

def main():
    folder = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "."
    want_deploy = "--deploy" in sys.argv
    domain_hint = ""
    robots_p = os.path.join(folder, "robots.txt")
    if os.path.exists(robots_p):
        mm = re.search(r"https://([^/]+)/", open(robots_p).read()); domain_hint = mm.group(1) if mm else ""

    port = _free_port(PORT)
    srv = None
    try:
        srv = subprocess.Popen(["php", "-S", f"127.0.0.1:{port}", "-t", folder],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               env={**os.environ, "PHP_CLI_SERVER_WORKERS": "4"})
        time.sleep(2.5)
        origin = f"http://127.0.0.1:{port}"
    except FileNotFoundError:
        origin = "file://" + os.path.abspath(folder)

    index_url = origin + "/"
    try:
        _, idx_html = fetch(index_url)
    except urllib.error.HTTPError as e:
        print(f"FATAL: index returns {e.code}"); sys.exit(1)

    queue = ["/"]
    seen_pages, titles, descs, h1_texts = {}, {}, {}, {}
    site_brand = {"v": ""}
    # canonicalize: "/" and "/index.php" are the same page
    def canon(p):
        return "/" if p in ("/", "/index.php") else p
    internal_links = set()
    CSSISH = (".css", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".woff", ".woff2", ".gif", ".webp")

    while queue:
        path = queue.pop(0)
        if path in seen_pages: continue
        try: code, html = fetch(origin + path)
        except urllib.error.HTTPError as e:
            code, html = e.code, ""
        seen_pages[path] = (code, html)
        d = extract(html, path)
        titles[path], descs[path] = d["title"], d["metas"].get("description","")
        h1_texts[path] = d["h1s"]
        for href in d["links"]:
            nu = norm_url(href, path)
            if nu and nu.startswith("PATH:"):
                il = canon(nu[5:].split("?")[0].split("#")[0])   # drop qs/fragment + unify home
                if il.endswith(CHK_EXTENSIONS) and not il.endswith(CSSISH):
                    internal_links.add(il)
        queue.extend(sorted(internal_links - set(seen_pages)))
        # page-level checks
        brand_hint = (domain_hint.split("-")[0] or domain_hint)[:12]
        brands = {brand_hint.lower()} if brand_hint else set()
        if d.get("brand_line"): brands.add(d["brand_line"].lower())
        page_brand = ""
        for node in d["jsonld"]:
            for org in (node.get("@graph") if isinstance(node, dict) else None) or ([node] if isinstance(node, dict) else []):
                if not isinstance(org, dict) or not org.get("name"):
                    continue
                if str(org.get("@id", "")).endswith("#org") or org.get("@type") in (
                        "Organization", "FinancialService", "LocalBusiness", "Store"):
                    brands.add(str(org["name"]).lower())
                    page_brand = page_brand or str(org["name"])
        if path == "/":
            site_brand["v"] = page_brand or d.get("brand_line") or ""
        if site_brand["v"]: brands.add(site_brand["v"].lower())
        brand_ok = bool(d["title"]) and any(d["title"].lower().startswith(b) for b in brands if b)
        chk(brand_ok, "ERR", f"brand-first title /{path}", f"title does not start with brand /{path}: '{d['title'][:50]}'")
        chk(bool(d["title"]), "ERR", f"title /{path}", f"EMPTY <title> /{path}")
        chk(len(d["title"]) <= 75, "WARN", None, f"title >75ch /{path}: '{d['title'][:60]}…'")
        chk(len(d["h1s"]) == 1, "ERR", f"one h1 /{path}", f"{len(d['h1s'])} h1 on /{path}")
        chk(d["brand_in_h1_line"], "ERR", f"h1.brand-line /{path}", f"h1 lacks span.brand-line /{path}")
        chk(bool(d["metas"].get("description")), "ERR", f"desc /{path}", f"no meta description /{path}")
        chk(bool(d["metas"].get("keywords")), "WARN", None, f"no meta keywords /{path}")
        chk(bool(d["canonical"]), "ERR", f"canonical /{path}", f"no canonical /{path}")
        if d["canonical"] and domain_hint:
            chk(d["canonical"].startswith(f"https://{domain_hint}"), "ERR",
                f"canonical host /{path}", f"canonical wrong host /{path}: {d['canonical']}")
            cpath = d["canonical"].split(domain_hint, 1)[1]
            chk(cpath == "/" or cpath.endswith(".php"), "ERR",
                f"canonical .php /{path}", f"canonical lacks .php suffix /{path}: {d['canonical']}")
        f = d["forms"]
        chk(f["lead_forms"] <= 1 or path != "/", "INFO")
        if f["lead_forms"]:
            chk(f["phone_inputs"] >= 1, "ERR", f"phone jq /{path}",
                f"lead-form lacks js-lead-phone /{path}")
            chk(f["submit_btns"] >= 1, "ERR", f"submit /{path}", f"no .form-submit /{path}")
        # first crawl pass keeps note; final tally after loop
        dup_check_placeholder = None
    # aggregate duplicates
    inv_titles = [p for p,t in titles.items() if not t]
    tlist = list(titles.values()); dlist = list(descs.values())
    dup_t = {t for t in tlist if t and tlist.count(t) > 1}
    dup_d = {t for t in dlist if t and dlist.count(t) > 1}
    chk(not dup_t, "ERR", "titles unique", f"DUPLICATE titles: {[p for p,t in titles.items() if t in dup_t]}")
    chk(not dup_d, "WARN", None, f"DUPLICATE descriptions: {[p for p,d in descs.items() if d in dup_d]}")
    flat_h1 = [x for v in h1_texts.values() for x in v]
    # deposit rule: 250-like amounts banned from meta/head text but ok in <small> / legal
    dep_pat = re.compile(r"(€\s?250\b|250\s?€|min(?:imum)?\s?deposit|min(?:imální|minimāl)|100\s?000\s?Ft|100000\s?Ft)")
    idx_src = seen_pages["/"][1]
    for tagname, pat in [("keywords", r'<meta[^>]+keywords[^>]+content=["\']([^"\']+)'),
                         ("og/twitter/JSONLD", r'<script[^>]+ld\+json[^>]*>(.*?)</script>')]:
        blob = " ".join(re.findall(pat, idx_src, re.S|re.I))
        hits = dep_pat.findall(blob)
        chk(not hits, "ERR", "deposit not in meta",
            f"deposit amount FOUND inside {tagname}: {hits[:2]}")
    # json validity
    for path,(code,html) in seen_pages.items():
        d = extract(html, path)
        for obj in d["jsonld"]:
            if "__invalid__" in obj:
                chk(False, "ERR", None, f"INVALID JSON-LD /{path}: {obj['__invalid__']}")
    # broken internal links (skip assets with ?v=, they're static not pages)
    ASSETS = (".css", ".png", ".jpg", ".svg", ".ico", ".woff", ".webp", ".js")
    for il in sorted(internal_links):
        bare = il.split("?")[0]
        if bare.endswith(ASSETS):
            continue
        code = seen_pages.get(il, (None,))[0]
        if code is None:
            try: code,_ = fetch(origin + il)
            except urllib.error.HTTPError as e: code = e.code
        chk(code == 200, "ERR", f"200 {il}", f"BROKEN internal link {il} → {code}")

    # ---- canonical-url gate: sitemap must list the .php canonicals
    # (hosting-panel consoles regenerate sitemap.xml without .php - legacy bug) ----
    sm_path = os.path.join(folder, "sitemap.xml")
    if os.path.exists(sm_path):
        locs = re.findall(r"<loc>([^<]+)</loc>", open(sm_path, encoding="utf-8").read())
        root_url = f"https://{domain_hint}/" if domain_hint else ""
        prefix = f"https://{domain_hint}"
        bad = [u for u in locs if not (u.endswith(".php") or u == root_url)]
        chk(not bad, "ERR", "sitemap .php urls",
            f"sitemap lists non-canonical (non-.php) URLs: {bad[:4]}")
        sm_paths = {u[len(prefix):] if u.startswith(prefix) else u for u in locs}
        can_paths = set()
        for p, (code, html) in seen_pages.items():
            c = extract(html, p)["canonical"]
            if c:
                can_paths.add(c[len(prefix):] if c.startswith(prefix) else c)
        missing = can_paths - sm_paths
        chk(not missing, "ERR", "sitemap covers canonicals",
            f"canonical URLs missing from sitemap: {sorted(missing)[:4]}")
        # every <url> needs a valid, non-future lastmod (fuller crawl signals)
        blocks = re.findall(r"<url>(.*?)</url>", open(sm_path, encoding="utf-8").read(), re.S)
        bad_lm = []
        today = time.strftime("%Y-%m-%d")
        for blk in blocks:
            m = re.search(r"<lastmod>([^<]+)</lastmod>", blk)
            if not m or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", m.group(1)) or m.group(1) > today:
                bad_lm.append(m.group(1) if m else "(missing)")
        chk(not bad_lm, "ERR", "sitemap lastmod",
            f"sitemap <url> entries with missing/invalid/future lastmod: {bad_lm[:4]}")

    # ---- language gate: Cyrillic comments in shipped files (= DevTools leak) ----
    cyr_hits = audit_cyrillic_comments(folder)
    chk(not cyr_hits, "ERR", "no Cyrillic comments in shipped files",
        f"CYRILLIC comments in shipped files ({len(cyr_hits)} spots) — rewrite in English, e.g. "
        + "; ".join(f"{p}:{ln}" for p, ln, _ in cyr_hits[:6]))
    vis_cyr = audit_visible_cyrillic(seen_pages)
    chk(not vis_cyr, "WARN", "no Cyrillic in rendered page text",
        f"Cyrillic visible on pages: " + "; ".join(f"{p}: …{s}…" for p, s in vis_cyr[:4]))

    srv.terminate()

    errs = [m for lv, m in CHECKS if lv == "ERR" and m]
    warns = [m for lv, m in CHECKS if lv == "WARN" and m]
    print(f"\n=== SEO AUDIT ({folder}) ===")
    print(f"pages crawled : {len(seen_pages)}")
    print(f"ERRORS: {len(errs)}"); [print("  ✗", m) for m in errs]
    print(f"WARNINGS: {len(warns)}"); [print("  ! ", m) for m in warns]
    if cyr_hits:
        print("Cyrillic comment details:")
        for p, ln, snip in cyr_hits[:20]:
            print(f"  {p}:{ln}  {snip}")
    ok_count = sum(1 for lv,_ in CHECKS if lv=="ok")
    print(f"passed checks : {ok_count}")
    if errs: sys.exit(1)
    if want_deploy: print("\nGate passed — safe to deploy.")
    else: print("\nLocal audit passed.")

if __name__ == "__main__":
    main()
