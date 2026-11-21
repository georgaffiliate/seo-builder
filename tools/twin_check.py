#!/usr/bin/env python3
"""twin_check.py (standalone) — anti-twin gate for static-create-sites.

Renders a built site through php -S and compares its STRUCTURE against every
history plan in plans/:

  section inventory (type Jaccard) · positional order · variant map ·
  inner-page skeletons · slug set · CSS class vocabulary · widget signatures.

Fail (exit 1) on any of:
  * type Jaccard ≥ 0.72 with any plan            (same block vocabulary)
  * positional ≥ 0.60 with two or more plans     (same running order)
  * identical section type set / variant map / slug set / inner-page set
  * class-set Jaccard ≥ 0.85                     (same markup, new paint)
  * widget sign set equal to, or a superset of, a plan's widget set

Usage: python3 tools/twin_check.py sites/<domain> [more…]
"""
from __future__ import annotations
import json, pathlib, re, socket, subprocess, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLANS = ROOT / "plans"
PROFILES = ROOT / "profiles"
sys.path.insert(0, str(ROOT / "tools"))
try:
    from profile_write import fingerprints, personas_of
except Exception:            # fingerprint gate degrades gracefully if tools move
    fingerprints = personas_of = None
PORT = 8797
SKIP = {"section", "wrap", "center", "alt", "sec", "blk", ""}
TYPE_OF = {"claim-band": "band", "access-band": "band", "enroll-band": "band",
           "trust-band": "cta", "cta-band": "cta", "intro-center": "intro", "stats-intro": "intro",
           "steps-live": "steps", "brand-note": "brandnote"}
CLASS2TYPE = {"calculator-wrap": "calculator", "faq-flex": "faq", "faq-list": "faq",
              "review-grid": "people", "ladder": "ladder", "timeline": "timeline",
              "cta-strip": "cta", "brand-note-grid": "brandnote", "office-grid": "office"}
def free_port(preferred):
    for p in (preferred, 0):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p)); return s.getsockname()[1]
        except OSError:
            continue
        finally:
            s.close()
    return preferred

SIGNS = ["id=\"countdown\"", "data-unit", "tape-track", "live-latency", "live-orders",
         "data-widget=", "id=\"calculator\"", "demo-svg", "demo-bars", "rating-bars",
         "qa-list", "progress-intake", "stats-band", "heatmap", "tile-flip",
         "odometer", "flip-clock", "sentiment", "book-row", "pi-bar"]


def fetch(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode("utf-8", "ignore")


def render(folder: pathlib.Path) -> dict[str, str]:
    port = free_port(PORT)
    srv = subprocess.Popen(["php", "-S", f"127.0.0.1:{port}", "-t", str(folder)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pages = {}
    try:
        time.sleep(1.3)
        idx = fetch(f"http://127.0.0.1:{port}/")
        pages["/"] = idx
        for href in set(re.findall(r'href="(?!https?:|#|mailto:|tel:)([a-z0-9\-_/]+\.php)"', idx)):
            try:
                pages[href] = fetch(f"http://127.0.0.1:{port}/{href}")
            except Exception:
                pass
    finally:
        srv.terminate()
        srv.wait(timeout=5)
    return pages


def tokenize(cls: str) -> str:
    """CSS class attribute -> structural TYPE token (sec-features-b -> features)."""
    for c in cls.split():
        if c.startswith("sec-") and c != "sec":
            head, _, tail = c[4:].rpartition("-")
            return head if tail in {"a", "b", "c"} and head else c[4:]
        if c.startswith("blk-"):
            return TYPE_OF.get(c[4:], c[4:])
    for c in cls.split():
        if c not in SKIP:
            return CLASS2TYPE.get(c, c)
    return ""


def skeleton(html: str) -> list[str]:
    out = []
    for m in re.finditer(r'<section[^>]*\bclass="([^"]+)"', html):
        t = tokenize(m.group(1))
        if t:
            out.append(t)
    return out


def variant_map(html: str) -> dict[str, str]:
    out = {}
    for m in re.finditer(r'<section[^>]*\bclass="([^"]+)"[^>]*\bdata-var="([a-z0-9]+)"', html):
        t = tokenize(m.group(1))
        if t:
            out[t] = m.group(2)
    return out


def widgets_of(pages) -> frozenset:
    s = set()
    for html in pages.values():
        for sg in SIGNS:
            if sg in html:
                s.add(sg.rstrip("="))
    return frozenset(s)


def classes_of(pages) -> set:
    s = set()
    for html in pages.values():
        s.update(re.findall(r'class="([^"]+)"', html))
    return s


def jac(a, b) -> float:
    A, B = set(a), set(b)
    return len(A & B) / max(1, len(A | B))


def pos(a, b) -> float:
    n = min(len(a), len(b))
    return sum(1 for x, y in zip(a[:n], b[:n]) if x == y) / max(n, 1)


def main():
    folders = [pathlib.Path(a).resolve() for a in sys.argv[1:]]
    if not folders:
        print("usage: twin_check.py sites/<domain> …")
        sys.exit(2)
    hist = []
    for f in sorted(PLANS.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        lay = d.get("layout", {})
        hist.append({"name": f.stem,
                     "types": {TYPE_OF.get(t.lower(), t.lower()) for t in lay.get("section_order", [])},
                     "order": [TYPE_OF.get(t.lower(), t.lower()) for t in lay.get("section_order", [])],
                     "variants": lay.get("variants", {}) or {},
                     "inner": {tuple(v) for v in (d.get("inner_pages") or {}).values()},
                     "slugs": set((lay.get("slugs") or {}).values()),
                     "widgets": set((d.get("widgets") or {}).values())})
    profs = []
    for f in sorted(PROFILES.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        profs.append({"name": f.stem,
                      "brand": (d.get("brand") or "").lower(),
                      "fp": set((d.get("content_fp") or {}).values()),
                      "personas": d.get("personas") or []})
    probs = []
    for folder in folders:
        pages = render(folder)
        mine = skeleton(pages.get("/", ""))
        myvar = variant_map(pages.get("/", ""))
        myc = classes_of(pages)
        myw = widgets_of(pages)
        my_fp, my_personas, my_brand = set(), [], ""
        if fingerprints and personas_of:
            cf = ROOT / "content" / f"{folder.name}-content.json"
            pf = PLANS / f"{folder.name}.json"
            brand0, dom0 = "", folder.name
            if pf.exists():
                try:
                    d0 = json.loads(pf.read_text(encoding="utf-8"))
                    brand0 = (d0.get("params", {}).get("brand", "") or "").lower()
                    dom0 = d0.get("params", {}).get("domain", "") or dom0
                except Exception:
                    pass
            my_brand = brand0
            if cf.exists():
                try:
                    pack = json.loads(cf.read_text(encoding="utf-8"))
                    # same normalization as profile_write: brand variants masked out
                    my_fp = set(fingerprints(pack, [brand0, dom0]).values())
                    my_personas = personas_of(pack)
                except Exception:
                    pass
        myslugs = {p.stem for p in folder.glob("*.php")
                   if p.name not in {"index.php", "thanks.php", "404.php", "_postback.php"}}
        myinner = set()
        for p in folder.glob("*.php"):
            if p.name in {"index.php", "thanks.php", "404.php", "_postback.php"}:
                continue
            tags = tuple(re.findall(r'class="([^"]+)"', p.read_text(encoding="utf-8"))[:40])
            myinner.add(tags)
        worstJ, worstN, worstC, hits = 0.0, "", 0.0, []
        for h in hist:
            if h["name"] == folder.name:
                continue
            j = jac(mine, h["types"])
            if j > worstJ:
                worstJ, worstN = j, h["name"]
            if h["order"] and min(len(mine), len(h["order"])) >= 6 and pos(mine, h["order"]) >= 0.60:
                hits.append(h["name"])
            if h["types"] and h["types"] == set(mine):
                probs.append(f"{folder.name}: identical section inventory to {h['name']}")
            hv = {TYPE_OF.get(k, k): v for k, v in h["variants"].items()}
            if hv and hv == myvar:
                probs.append(f"{folder.name}: identical variant map to {h['name']}")
            if h["slugs"] and h["slugs"] == (myslugs - {"privacy", "terms"}):
                probs.append(f"{folder.name}: slug set equals {h['name']}")
            if h["widgets"] and h["widgets"] <= myw:
                probs.append(f"{folder.name}: widgets superset of {h['name']}")
        for pr in profs:
            if pr["name"] == folder.name:
                continue
            if my_fp and pr["fp"] and jac(my_fp, pr["fp"]) >= 0.45:
                probs.append(f"{folder.name}: content fingerprint {jac(my_fp, pr['fp']):.0%} like "
                             f"{pr['name']} — rewrite the cloned sections")
            if my_personas and pr["personas"] and pr["brand"] == my_brand:
                phits = sum(1 for a, b in zip(my_personas, pr["personas"])
                            if (a.get("city") or "").strip().lower() == (b.get("city") or "").strip().lower()
                            or (a.get("tenure") or "") == (b.get("tenure") or ""))
                if phits >= 2:
                    probs.append(f"{folder.name}: review template repeats {pr['name']} "
                                 f"({phits}/3 same city/tenure)")
        if worstJ >= 0.72:
            probs.append(f"{folder.name}: section inventory {worstJ:.0%} like {worstN} — swap block types")
        if len(hits) >= 2:
            probs.append(f"{folder.name}: positional ≥60% vs {len(hits)} plans ({', '.join(hits[:3])})")
        print(f"  {folder.name}: inventory {worstJ:.0%} (vs {worstN or '—'}) · "
              f"{len(mine)} sections / {len(set(mine))} types · variants {len(myvar)} · "
              f"{len(myw)} widget signs · slugs {sorted(myslugs)}")
    if probs:
        print("\nTWIN PROBLEMS:")
        for p in probs:
            print("  ✗", p)
        sys.exit(1)
    print("  unique enough — gate passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
