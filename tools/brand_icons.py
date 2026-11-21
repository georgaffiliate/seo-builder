#!/usr/bin/env python3
"""brand_icons.py — brand favicon + og-image from the plan palette (no external design step).

Writes favicon.svg, favicon-32.png, apple-touch-icon.png, favicon.ico and og-image.png
into the built site. Uses only palette tokens, so icons follow the site identity.

Usage:
  python3 tools/brand_icons.py --plan plans/<domain>.json --site sites/<domain>
"""
from __future__ import annotations
import argparse, json, pathlib, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PALETTES = ROOT / "content" / "palettes-blk.json"


def die(m):
    print(f"✗ {m}")
    sys.exit(1)


def palette(plan: dict) -> dict:
    data = json.loads(PALETTES.read_text(encoding="utf-8"))
    pal = next((p for p in data["palettes"] if p["id"] == plan["design"]["palette_id"]), None)
    if not pal:
        die(f"palette {plan['design']['palette_id']} not found")
    return pal["vars"]


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--site", required=True)
    a = ap.parse_args()
    plan = json.loads(pathlib.Path(a.plan).read_text(encoding="utf-8"))
    site = pathlib.Path(a.site)
    if not site.is_dir():
        die(f"site not built: {site}")
    brand = plan["params"]["brand"]
    dom = plan["params"]["domain"]
    v = palette(plan)
    bg, ink, acc, acc2 = v.get("bg", "#111"), v.get("ink", "#fff"), v.get("acc", "#c8a24a"), v.get("acc_2", "#fff")
    letter = esc(brand.split()[0][0].upper())
    head = plan["design"]["fonts"]["head"]
    variant = (plan.get("layout", {}).get("variants") or {}).get("logo", "") or "a"
    glyph = {"e": "↗", "g": "/"}.get(variant, letter)

    fg_letter = acc2 if bg.lower() in ("#111111", "#000000") else acc
    shape = "circle" if variant in ("e", "h") else "rect"
    rx = "" if shape == "circle" else ' rx="14"'
    bg_rect = (f'<circle cx="32" cy="32" r="32" fill="{bg}"/>' if shape == "circle"
               else f'<rect width="64" height="64"{rx} fill="{bg}"/>')
    extra = ""
    if variant == "b":
        extra = f'<rect x="8" y="47" width="26" height="3" rx="1.5" fill="{acc}"/>'
        size, ty, tx = 34, 43, 8
    elif variant == "c":
        extra = f'<rect x="6" y="6" width="52" height="52" rx="9" fill="{acc}" opacity=".16"/>'
        size, ty, tx = 36, 46, 18
    elif variant == "d":
        extra = f'<circle cx="50" cy="46" r="4" fill="{acc}"/>'
        size, ty, tx = 34, 43, 8
    elif variant == "e":
        size, ty, tx = 30, 42, 20
    elif variant == "f":
        extra = f'<rect x="8" y="52" width="48" height="2" fill="{acc}" opacity=".5"/>'
        size, ty, tx = 32, 42, 8
    elif variant == "g":
        size, ty, tx = 34, 43, 12
    elif variant == "h":
        extra = f'<circle cx="48" cy="16" r="4" fill="{acc}"/>'
        size, ty, tx = 30, 40, 16
    else:
        extra = f'<rect x="8" y="47" width="26" height="3" rx="1.5" fill="{acc}"/>'
        size, ty, tx = 34, 43, 8
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" role="img" aria-label="{esc(brand)}">
{bg_rect}
<path d="M0 64 L64 0 V30 L30 64 Z" fill="{acc}" opacity=".16"/>
{extra}
<text x="{tx}" y="{ty}" font-family="{esc(head)}, Georgia, serif" font-size="{size}" font-weight="700" fill="{fg_letter}">{glyph}</text>
</svg>
'''
    (site / "favicon.svg").write_text(svg, encoding="utf-8")

    og = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
<rect width="1200" height="630" fill="{bg}"/>
<path d="M0 630 L1200 0 V630 Z" fill="{acc}" opacity=".10"/>
<rect x="72" y="72" width="56" height="56" rx="12" fill="{acc}"/>
<text x="84" y="116" font-family="{esc(head)}, Georgia, serif" font-size="34" font-weight="700" fill="{bg}">{glyph}</text>
<text x="72" y="196" font-family="{esc(head)}, Georgia, serif" font-size="76" font-weight="700" fill="{ink}">{esc(brand)}</text>
<text x="72" y="258" font-family="{esc(head)}, Georgia, serif" font-size="34" fill="{acc}">{esc(dom)}</text>
<g font-family="Helvetica, Arial, sans-serif" font-size="24" fill="{ink}" opacity=".82">
<rect x="72" y="330" width="250" height="54" rx="27" fill="{acc}" opacity=".16"/>
<text x="98" y="365">{esc(plan["params"].get("geo_short") or plan["params"]["lang"].upper())}</text>
<rect x="338" y="330" width="330" height="54" rx="27" fill="{acc}" opacity=".16"/>
<text x="364" y="365">{esc(plan["design"]["skin"])}</text>
</g>
<rect x="72" y="470" width="120" height="4" rx="2" fill="{acc}"/>
</svg>
'''
    (site / "og-image.svg").write_text(og, encoding="utf-8")

    jobs = [(180, 180, "apple-touch-icon.png"), (32, 32, "favicon-32.png"), (48, 48, None),
            (1200, 630, "og-image.png")]
    with tempfile.TemporaryDirectory() as tmp:
        for w, h, out in jobs:
            src = site / ("og-image.svg" if out == "og-image.png" else "favicon.svg")
            dst = site / out if out else pathlib.Path(tmp) / "f48.png"
            rc = subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h), str(src), "-o", str(dst)]).returncode
            if rc != 0:
                die(f"rsvg-convert failed for {w}x{h}")
        from PIL import Image
        img = Image.open(pathlib.Path(tmp) / "f48.png")
        img.save(site / "favicon.ico", sizes=[(48, 48), (32, 32), (16, 16)])
    print(f"✓ icons: favicon.svg/.ico/.png + apple-touch-icon + og-image.png ({plan['design']['palette_id']})")


if __name__ == "__main__":
    main()
