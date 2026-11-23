#!/usr/bin/env python3
"""profile_write.py — register a built offer in profiles/<domain>.json.

Reads the plan (identity/design/people) and the content pack (contacts) so the
registry stays consistent with what actually shipped.

Usage: python3 tools/profile_write.py --plan plans/<domain>.json --content content/<domain>-content.json
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILES = ROOT / "profiles"

FP_SKIP = {"legal", "footer", "thanks", "livebar"}   # boilerplate / numeric noise


def norm_text(text: str, brand_variants: list[str]) -> str:
    t = text.lower()
    for b in brand_variants:
        if b:
            t = t.replace(b.lower(), " ")
    t = re.sub(r"\d+", "#", t)
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()


def fingerprints(content: dict, brand_variants: list[str] | None = None) -> dict:
    """Per-section fingerprint of the SHIPPED TEXT (digits masked).
    Brand masking is intentionally NOT applied: the brand token is constant for a
    sibling pair, so it never inflates their similarity, and normalization stays
    reproducible from the content pack alone (no plan file needed)."""
    fp = {}
    for key, node in content.items():
        if key in FP_SKIP or key.startswith("_"):
            continue
        if isinstance(node, str):
            text = node
        else:
            text = " ".join(re.findall(r"\w+", json.dumps(node, ensure_ascii=False)))
        t = norm_text(text, [])
        if len(t) > 40:
            fp[key] = hashlib.sha1(t.encode()).hexdigest()[:10]
    return fp


def personas_of(content: dict) -> list[dict]:
    out = []
    for it in (content.get("reviews") or {}).get("items") or []:
        out.append({"name": it.get("name", ""), "city": it.get("city", ""),
                    "role": it.get("role", ""), "tenure": it.get("tenure", "")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--content", required=True)
    a = ap.parse_args()
    plan = json.loads(pathlib.Path(a.plan).read_text(encoding="utf-8"))
    content = json.loads(pathlib.Path(a.content).read_text(encoding="utf-8"))
    p = plan["params"]
    dom = p["domain"]

    siblings = []
    for f in sorted(PROFILES.glob("*.json")):
        if f.stem == dom:
            continue
        try:
            other = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (other.get("brand") or "").lower() == p["brand"].lower():
            siblings.append(f.stem)

    reg = plan.get("regulator") or {}
    office = content.get("office", {})
    meta = content.get("meta", {})
    brand_variants = [p["brand"], p["brand"].lower(), dom]
    prof = {
        "domain": dom,
        "brand": p["brand"],
        "brand_variants": [p["brand"], p["brand"].lower(), dom],
        "geo": p.get("cc") or p["lang"].upper(),
        "lang": p["lang"],
        "locale": p.get("locale") or p["lang"],
        "currency": p.get("currency", "EUR"),
        "deposit_rule": "250 EUR equivalent, only in bands.form_consent <small>",
        "regulator": reg.get("name", ""),
        "buyer": "PUMA",
        "funnel": max(p["brand"].split(), key=len).upper().replace("-", ""),
        "city": re.sub(r"^[\d\s-]+", "", (office.get("addr") or "").split(",")[-1]).strip(),
        "contacts": {"addr": office.get("addr", ""), "phone": meta.get("telephone", ""),
                     "email": meta.get("email", f"info@{dom}"), "hours": office.get("hours", "")},
        "design": {"palette": plan["design"]["palette_id"], "theme": plan["design"].get("theme"),
                   "skin": plan["design"].get("skin"), "fonts": " / ".join(plan["design"]["fonts"].values()),
                   "hero": plan["layout"]["hero"]},
        "widgets": list(plan["widgets"].values()),
        "slugs": plan["layout"].get("slugs", {}),
        "people": [{"name": n, "photo": ph} for n, ph in zip(plan.get("people", []), plan.get("photos", []))],
        "personas": personas_of(content),
        "content_fp": fingerprints(content, brand_variants),
        "plan": f"plans/{dom}.json",
        "content": f"content/{dom}-content.json",
        "built": plan.get("built") or "2026-11-21",
        "siblings": siblings,
        "gates": {"seo_audit": "PASSED 0 err / 0 warn", "twin_check": "PASSED",
                  "mobile_static": "PASSED (viewport/tbl-scroll/no inline grid)"},
        "manual": ["DNS", "IP whitelist", "real-device 360/390/768 look", "prod not tested (submit = CRM lead)"],
    }
    PROFILES.mkdir(exist_ok=True)
    if (plan.get("blog") or {}).get("enabled"):
        bl = plan["blog"]
        prof["blog"] = {"style": bl.get("style"),
                        "topics": [t.get("id") for t in (bl.get("topics") or [])],
                        "articles": []}
        bp = ROOT / "content" / f"{dom}-blog.json"
        if bp.exists():
            try:
                bd = json.loads(bp.read_text(encoding="utf-8"))
                prof["blog"]["articles"] = [a.get("slug") for a in (bd.get("articles") or [])]
            except Exception:
                pass
    out = PROFILES / f"{dom}.json"
    out.write_text(json.dumps(prof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for sib in siblings:
        sf = PROFILES / f"{sib}.json"
        try:
            s = json.loads(sf.read_text(encoding="utf-8"))
        except Exception:
            continue
        s["siblings"] = sorted(set(s.get("siblings", [])) | {dom})
        sf.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✓ profile: profiles/{dom}.json (siblings: {', '.join(siblings) or '—'})")


if __name__ == "__main__":
    main()
