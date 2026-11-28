#!/usr/bin/env python3
"""Build the prize-image bank for blocks/blk-prizes*.html from Wikimedia Commons.

Usage:
    python3 scripts/fetch_prizes.py            # download missing files
    python3 scripts/fetch_prizes.py --force    # re-download everything
    python3 scripts/fetch_prizes.py --check    # verify files + print the manifest

Why Commons: the product photos are freely licensed (CC0 / public domain /
CC BY / CC BY-SA), the API needs no key, and every entry keeps its author and
source page in prizes/manifest.json so a site can print a credits line when the
licence asks for attribution (CC BY / CC BY-SA do).

The bank is a *placeholder* set for demo offers. Before a production launch
either keep the credits line (`sections.prizes.credit`) or swap the files for
licensed product renders — the block only reads `prizes/manifest.json`.

The picks below are search heuristics: the shipped manifest was reviewed by hand
(some search hits are hands-on snapshots or teardowns). Re-running with --force
re-picks them, so replace a bad file manually and keep its manifest entry.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "prizes"
API = "https://commons.wikimedia.org/w/api.php"
UA = "seo-builder-prize-bank/1.0 (template asset fetch)"
OK_LICENCES = ("cc0", "public domain", "cc by 4.0", "cc by-sa 4.0", "cc by 3.0",
               "cc by-sa 3.0", "cc by 2.0")

# id, Commons search query, words that must appear in the file title, alt (it/en)
PRODUCTS = [
    ("iphone-18-pro", "iPhone 18 Pro Vector.svg", ("iphone 18",),
     "iPhone 18 Pro", "iPhone 18 Pro"),
    ("ps5", "PlayStation 5 console", ("playstation 5", "ps5"),
     "Console PlayStation 5 con controller", "PlayStation 5 console with controller"),
    ("ps5-slim", "PlayStation 5 Slim", ("playstation 5", "ps5"),
     "PlayStation 5 Slim", "PlayStation 5 Slim"),
    ("macbook-air", "MacBook Air M2", ("macbook air",),
     "MacBook Air aperto", "MacBook Air, open"),
    ("macbook-pro", "MacBook Pro 16 M2", ("macbook pro",),
     "MacBook Pro 16 pollici", "MacBook Pro 16-inch"),
    ("ipad-pro", "iPad Pro", ("ipad pro", "ipad"),
     "iPad Pro con Apple Pencil", "iPad Pro with Apple Pencil"),
    ("apple-watch", "Apple Watch Ultra", ("apple watch",),
     "Apple Watch Ultra", "Apple Watch Ultra"),
    ("airpods-pro", "AirPods Pro", ("airpods",),
     "AirPods Pro nella custodia", "AirPods Pro in the case"),
    ("sony-headphones", "Sony WH-1000XM4", ("wh-1000", "sony"),
     "Cuffie Sony WH-1000XM4", "Sony WH-1000XM4 headphones"),
    ("nintendo-switch", "Nintendo Switch", ("nintendo switch",),
     "Nintendo Switch con Joy-Con", "Nintendo Switch with Joy-Con"),
    ("drone", "DJI Mavic 3", ("dji", "mavic"),
     "Drone DJI Mavic", "DJI Mavic drone"),
    ("gopro", "GoPro Hero 10", ("gopro",),
     "Action camera GoPro", "GoPro action camera"),
    ("galaxy-s24", "Samsung Galaxy S24 Ultra", ("galaxy s24", "samsung galaxy"),
     "Samsung Galaxy S24 Ultra", "Samsung Galaxy S24 Ultra"),
    ("dyson", "Dyson vacuum cleaner", ("dyson",),
     "Aspirapolvere Dyson", "Dyson vacuum cleaner"),
    ("keyboard", "Mechanical keyboard", ("keyboard",),
     "Tastiera meccanica", "Mechanical keyboard"),
    ("monitor", "Computer monitor", ("monitor", "display"),
     "Monitor da scrivania", "Desktop monitor"),
    ("camera", "Sony Alpha 7", ("sony", "alpha", "camera"),
     "Fotocamera mirrorless", "Mirrorless camera"),
    ("scooter", "Electric kick scooter", ("scooter",),
     "Monopattino elettrico", "Electric kick scooter"),
]


def api(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def candidates(query: str) -> list[dict]:
    data = api({
        "action": "query", "format": "json", "generator": "search",
        "gsrnamespace": 6, "gsrlimit": 15, "gsrsearch": f"{query} filetype:bitmap",
        "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 760,
    })
    pages = (data.get("query") or {}).get("pages") or {}
    out = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        title = page["title"].replace("File:", "")
        lic = (meta.get("LicenseShortName") or {}).get("value", "")
        out.append({
            "title": title,
            "width": info.get("width") or 0,
            "height": info.get("height") or 0,
            "thumb": info.get("thumburl") or "",
            "license": lic,
            "author": re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip(),
        })
    return out


def pick(query: str, words: tuple[str, ...]) -> dict | None:
    best, best_score = None, -1
    for c in candidates(query):
        if not c["thumb"] or c["width"] < 900 or c["height"] < 600:
            continue
        if not any(w in c["title"].lower() for w in words):
            continue
        if not any(k in c["license"].lower() for k in OK_LICENCES):
            continue
        ratio = c["width"] / max(1, c["height"])
        score = 40 if 0.65 <= ratio <= 1.7 else 0
        score += 15 if "pro" in c["title"].lower() else 0
        score += 10 if c["width"] >= 1800 else 0
        score -= 20 if "logo" in c["title"].lower() or "vector" in c["title"].lower() else 0
        if score > best_score:
            best, best_score = c, score
    return best


def download(url: str, dest: pathlib.Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        dest.write_bytes(r.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    manifest_path = OUT / "manifest.json"
    manifest = {"note": ("Placeholder product photos from Wikimedia Commons. CC0/PD need no "
                         "attribution; CC BY / CC BY-SA keep author + source below. "
                         "Replace with licensed renders before a paid launch or print "
                         "sections.prizes.credit."),
                "license_url": "https://commons.wikimedia.org/wiki/Commons:Licensing",
                "items": []}
    if manifest_path.exists() and not args.force:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    known = {i["id"]: i for i in manifest.get("items", [])}
    for pid, query, words, alt_it, alt_en in PRODUCTS:
        dest = OUT / f"{pid}.jpg"
        if dest.exists() and pid in known and not args.force:
            continue
        if args.check:
            continue
        try:
            best = pick(query, words)
            time.sleep(1.5)          # Commons throttles parallel searches (HTTP 429)
        except Exception as exc:                       # network hiccup: keep going
            print(f"! {pid}: search failed ({exc})", file=sys.stderr)
            continue
        if not best:
            print(f"! {pid}: no licensed landscape photo for {query!r}", file=sys.stderr)
            continue
        download(best["thumb"], dest)
        known[pid] = {
            "id": pid, "file": f"{pid}.jpg", "alt_it": alt_it, "alt_en": alt_en,
            "commons_title": best["title"], "license": best["license"],
            "author": best["author"] or "Wikimedia Commons contributor",
            "source": "https://commons.wikimedia.org/wiki/File:" +
                      urllib.parse.quote(best["title"].replace(" ", "_")),
        }
        print(f"· {pid}: {best['width']}x{best['height']} [{best['license']}] {best['title']}")

    manifest["items"] = [known[p[0]] for p in PRODUCTS if p[0] in known]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                             encoding="utf-8")
    if args.check:
        missing = [p[0] for p in PRODUCTS if not (OUT / f"{p[0]}.jpg").exists()]
        print(f"{len(manifest['items'])} items in manifest, "
              f"{len(missing)} missing files" + (f": {missing}" if missing else ""))
        return 1 if missing else 0
    print(f"manifest: {manifest_path.relative_to(ROOT)} ({len(manifest['items'])} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
