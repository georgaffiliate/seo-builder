#!/usr/bin/env python3
"""blog_content.py — writes content/<domain>-blog.json for `gen_plan.py --blog`.

The plan already carries 3–5 topic briefs (resources/blog-topics.json) and the date
for each article. This tool sends that compact brief to the model ONCE and gets the
whole pack back as JSON, so a blog build stays fast: one request, no per-article
round-trips.

Usage:
  python3 tools/blog_content.py --plan plans/<domain>.json
  python3 tools/blog_content.py --plan plans/<domain>.json --offline   # tests / no key
  python3 tools/blog_content.py --plan plans/<domain>.json --strict    # fail instead of bank fallback

Transport is the same as tools/llm_content.py (HTTP key from resources/llm.json /
.llm_env, opencode CLI as the fallback). Invalid output gets one repair pass; if it
still fails the deterministic offline pack is written so the site can still build.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import llm_content as L
from blog_assemble import A, body_word_target, validate_blog

MAX_TOKENS = 16000


def die(msg: str, code: int = 1):
    print(f"✗ {msg}")
    sys.exit(code)


def rel(path: pathlib.Path) -> str:
    """Path relative to ROOT when possible — --out may live elsewhere."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def brief(plan: dict) -> dict:
    blog = plan["blog"]
    topics = blog.get("topics") or []
    lang = plan["params"].get("lang", "en")
    brand = plan["params"]["brand"]
    title_max = max(18, 70 - len(brand) - 3)
    return {
        "task": "Write ONE JSON object: the guides/blog pack for the offer below. "
                "No HTML, no markdown, no commentary — only the JSON object.",
        "language": lang,
        "locale": plan["params"].get("locale"),
        "brand": plan["params"]["brand"],
        "domain": plan["params"]["domain"],
        "geo": plan["params"].get("geo") or "",
        "topic_rule": "Each topic below is a brief, not final copy. Write the article in the "
                      "site language, with a title/h1/excerpt that a local reader would search for. "
                      "Keep the topic id and the date exactly as given.",
        "article_count": len(topics),
        "title_max_chars": title_max,
        "topics": topics,
        "shape": {
            "hub": {"eyebrow": "section label, e.g. Guides",
                    "title": "hub page heading on the home page",
                    "lead": "one sentence, 80..160 chars",
                    "all_label": "short link label, e.g. All guides",
                    "toc_label": "contents",
                    "takeaways_label": "key points",
                    "related_title": "read next",
                    "min_read_label": "min",
                    "faq_label": "FAQ",
                    "facts_sections_label": "sections",
                    "facts_words_label": "words"},
            "articles": [{
                "topic": "topic id from the brief",
                "slug": "lowercase-latin-words-with-hyphens",
                "title": f"page title phrase without the brand, up to {title_max} chars",
                "h1": "on-page headline, 12..90 chars, may differ from title",
                "excerpt": "90..180 chars, used as meta description and card text",
                "date": "YYYY-MM-DD, exactly as in the brief",
                "read_min": 5,
                "author": "a plausible local name",
                "author_role": "short role, e.g. editorial team / market analyst",
                "takeaways": ["3..4 short key points"],
                "sections": [{"h2": "section heading, 8..90 chars",
                              "p": ["2..4 paragraphs, 40..90 words each"],
                              "points": ["optional 2..6 bullets, one line each"]}],
                "faq": [{"q": "question", "a": "answer, at least two sentences"}],
                "related": ["slug of another article in this pack"],
                "cta_title": "closing call to action heading",
                "cta_text": "one sentence",
                "cta_btn": "button label"
            }],
        },
        "rules": [
            "Exactly one article per topic, same order; do not invent extra topics.",
            "Slugs are Latin lowercase with hyphens, 2-5 words, unique, not the brand and not "
            "index/privacy/terms/thanks/404.",
            "Titles and descriptions must be unique across the pack and must not repeat the "
            "brand at the start (the assembler adds it).",
            f"Title budget: the assembler prepends '{brand} — ', so the title field itself must be "
            f"<= {title_max} characters; the final <title> must stay <= 70 characters.",
            "Each article: 3..7 sections, 2..4 paragraphs per section, 380+ words of body copy; "
            "at least one section carries 2..6 bullets.",
            "Vary openings, examples and section angles between articles. Never reuse a paragraph.",
            "FAQ answers are 2+ full sentences; they will be emitted as visible <details> cards and "
            "FAQPage JSON-LD.",
            "Related must point to other slugs in this same pack.",
            "Write in the site language, not English. No English boilerplate.",
            "Use only the script of the site language: no Chinese, Cyrillic, Greek, Arabic or other "
            "foreign characters inside Latin-script copy (a stray 允许 shipped on a live Italian site).",
            "Proofread grammar and spelling before answering: agreement, double letters, accents.",
            "No HTML tags, no markdown, no emoji, no e-mail addresses, no deposit amounts, "
            "no promises of profit or guaranteed returns.",
            "Dates are ISO YYYY-MM-DD and must equal the brief.",
            "The brand name must never be glued to the previous word (write 'the X platform', "
            "not 'theX platform').",
        ],
    }


def offline_pack(plan: dict) -> dict:
    """Deterministic, structure-valid pack for --offline and as a build fallback.

    It is intentionally generic: offline mode is for tests and keyless runs, not for
    shipping thin copy. Every paragraph is unique so the duplicate-copy gate holds.
    """
    lang = plan["params"].get("lang", "en")
    brand = plan["params"]["brand"]
    geo = plan["params"].get("geo") or plan["params"].get("cc") or ""
    T = _OFFLINE.get(lang) or _OFFLINE["en"]
    blog = plan["blog"]
    topics = blog.get("topics") or []
    rng = random.Random(f"{plan.get('seed', 0)}:{plan['params']['domain']}:blog")
    suffixes = ["guide", "explained", "checklist", "notes", "basics"]
    slugs = []
    for i, t in enumerate(topics):
        slugs.append(f"{t['id']}-{suffixes[(i + rng.randrange(len(suffixes))) % len(suffixes)]}")
    arts = []
    for i, t in enumerate(topics):
        topic = str(t.get("id") or "").replace("-", " ")
        secs = []
        for j, head in enumerate(T["heads"]):
            paras = []
            for k in range(4):
                idx = j * 4 + k
                frame = T["frames"][idx % len(T["frames"])]
                paras.append(frame.format(topic=topic, brand=brand, geo=geo)
                             + T["outro"].format(topic=topic, brand=brand))
            points = [T["points"][(idx + n) % len(T["points"])].format(topic=topic, brand=brand)
                      for n in range(2 if j % 2 == 0 else 0)]
            secs.append({"h2": head.format(topic=topic, brand=brand), "p": paras,
                         **({"points": points} if points else {})})
        words = sum(len(re.findall(r"\w+", x)) for s in secs
                    for x in [s["h2"], *s["p"], *s.get("points", [])])
        faq = [{"q": q.format(topic=topic, brand=brand), "a": a.format(topic=topic, brand=brand, geo=geo)}
               for q, a in T["faq"]]
        title = T["title"].format(topic=topic, brand=brand)
        if len(brand) + 3 + len(title) > 70:
            title = T.get("short_title", "Guide: {topic}").format(topic=topic)
        arts.append({
            "topic": t["id"],
            "slug": slugs[i],
            "title": title,
            "h1": T["h1"].format(topic=topic, brand=brand),
            "excerpt": T["excerpt"].format(topic=topic, brand=brand, geo=geo),
            "date": t.get("date") or "2026-01-01",
            "read_min": max(3, round(words / 200)),
            "author": (plan.get("people") or [brand])[0],
            "author_role": T["role"],
            "takeaways": [T["takeaways"][n].format(topic=topic, brand=brand) for n in range(3)],
            "sections": secs,
            "faq": faq,
            "related": [s for s in slugs if s != slugs[i]][:2],
            "cta_title": T["cta_title"].format(brand=brand),
            "cta_text": T["cta_text"].format(brand=brand),
            "cta_btn": T["cta_btn"],
        })
    return {"hub": {k: v.format(brand=brand, geo=geo) for k, v in T["hub"].items()},
            "articles": arts}


# ------------------------------------------------------------ partial answers
# A pack for 4-5 articles is a long single-shot JSON answer and providers cut them
# (live: a Dutch pack died at char 18 830 while finish_reason still said "stop").
# Two layers keep that from becoming an offline placeholder:
#   1. close_truncated() keeps everything the cut answer still held,
#   2. topics it did not deliver are asked for one article at a time.


def _balance(fragment: str) -> str:
    """Close an unfinished JSON fragment: the string, then every open array/object."""
    depth, in_str, esc = [], False, False
    for ch in fragment:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            depth.append(ch)
        elif ch in "]}":
            if depth:
                depth.pop()
    out = fragment + ('"' if in_str else "")
    out = re.sub(r"[,\s]+$", "", out)
    out = re.sub(r',?\s*"[^"\n]*"\s*:\s*$', "", out)      # dangling "key":
    out = re.sub(r"[,\s]+$", "", out)
    return out + "".join("}" if d == "{" else "]" for d in reversed(depth))


def close_truncated(raw: str) -> dict | None:
    """Parse a JSON object the model cut mid-answer (drops the incomplete last member)."""
    text = L.FENCE_RE.sub("", (raw or "").strip())
    start = text.find("{")
    if start < 0:
        return None
    text = text[start:]
    for _ in range(10):
        try:
            obj = json.loads(_balance(text), strict=False)
            return obj if isinstance(obj, dict) else None
        except Exception:
            cut = text.rfind(",")
            if cut < 0:
                return None
            text = text[:cut]
    return None


def parse_pack(raw: str) -> dict | None:
    try:
        obj = L.extract_json(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return close_truncated(raw)


def missing_topics(plan: dict, pack: dict) -> list:
    got = {str((a or {}).get("topic") or "")
           for a in (pack.get("articles") or []) if isinstance(a, dict)}
    return [t for t in (plan["blog"].get("topics") or []) if str(t.get("id") or "") not in got]


def article_error_map(errs: list) -> tuple[dict, list]:
    """Split validator errors into per-article buckets and pack-level ones.

    "articles[3] body is 358 words" is a problem of article 3 alone. Re-sending the
    whole ~5k-word pack for it costs two model round-trips and usually returns the
    same answer; rewriting just that article does not.
    """
    by_idx, pack_level = {}, []
    for e in errs:
        m = re.match(r"articles[\[.](\d+)[\].]", str(e))
        if m:
            by_idx.setdefault(int(m.group(1)), []).append(str(e))
        else:
            pack_level.append(str(e))
    return by_idx, pack_level


def article_words(art: dict) -> int:
    """Same count the gate uses: headings + paragraphs + bullets."""
    return sum(len(re.findall(r"\w+", str(x or ""), re.UNICODE))
               for s in (art.get("sections") or []) if isinstance(s, dict)
               for x in [s.get("h2"), *(s.get("p") or []), *(s.get("points") or [])])


def _trim(text, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" .,;:—-")


def _first_body(art: dict) -> str:
    for sec in art.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        for para in sec.get("p") or []:
            if str(para or "").strip():
                return str(para)
    return ""


def polish_article(plan: dict, art: dict) -> None:
    """Mechanical length fixes: titles/h1/excerpt/read_min never need a model call.

    The gate still rejects a broken value, but the generator repairs its own small
    misses before validating, so a 74-char title no longer costs a repair round-trip.
    """
    brand = plan["params"]["brand"]
    title = str(art.get("title") or "").strip()
    h1 = str(art.get("h1") or "").strip()
    excerpt = str(art.get("excerpt") or "").strip()
    if len(title) < 18 and h1:
        title = h1
    for _ in range(10):
        if not title or len(A.brand_first(title, brand)) <= 70:
            break
        shorter = _trim(title, max(18, len(title) - 4))
        if shorter == title:
            break
        title = shorter
    if len(title) < 18 and h1 and h1.casefold() != title.casefold():
        title = _trim(f"{title} — {h1}".strip(" —"), 72)
    art["title"] = title
    if len(h1) > 90:
        h1 = _trim(h1, 90)
    if len(h1) < 12:
        h1 = _trim(title if len(title) >= 12 else _first_body(art), 90)
    art["h1"] = h1
    if len(excerpt) > 190:
        excerpt = _trim(excerpt, 190)
    if len(excerpt) < 60:
        body = _first_body(art)
        cand = body or (f"{h1}. {excerpt}" if h1 else excerpt)
        if len(cand) < 60 and h1 and h1.casefold() not in cand.casefold():
            cand = f"{cand} — {h1}".strip(" —")
        excerpt = _trim(cand, 190)
    art["excerpt"] = excerpt
    art["read_min"] = max(2, round(article_words(art) / 200))


def polish_pack(plan: dict, pack: dict) -> None:
    for art in (pack.get("articles") or []):
        if isinstance(art, dict):
            polish_article(plan, art)


def gate(plan: dict, pack: dict) -> list[str]:
    """Polish the mechanical misses, then run the same gate assembly will run."""
    polish_pack(plan, pack)
    return validate_blog(plan, pack)


def _repoint_related(pack: dict) -> None:
    arts = [a for a in (pack.get("articles") or []) if isinstance(a, dict)]
    slugs = [str(a.get("slug") or "").strip() for a in arts]
    for a in arts:
        others = [s for s in slugs if s and s != str(a.get("slug") or "")]
        rel = [r for r in (a.get("related") or []) if r in others]
        if len(rel) < min(2, len(others)):
            rel = (rel + [s for s in others if s not in rel])[:2]
        a["related"] = rel


def replace_article(pack: dict, idx: int, art: dict) -> bool:
    arts = pack.get("articles") or []
    if not 0 <= idx < len(arts) or not isinstance(art, dict):
        return False
    arts[idx] = art
    _repoint_related(pack)
    return True


def ask_article(plan: dict, data: dict, topic: dict, known_slugs: list, titles: list,
                cfg: dict, key: str, errs: list | None = None,
                target_words: int = 0) -> dict | None:
    """One article in one small answer — the follow-up for a pack the provider cut
    or for an article the gate rejected (the rest of the pack stays untouched)."""
    shape = json.dumps(data["shape"]["articles"][0], ensure_ascii=False)
    rules = " ".join(r for r in data["rules"] if not r.startswith("Exactly one article"))
    extra = ""
    if target_words:
        extra += (f"\nLENGTH: write at least {target_words} words of body copy across 4..6 "
                  f"sections (h2 + 2..4 paragraphs of 40..90 words each, plus 2..6 bullets "
                  f"in at least one section).")
    if errs:
        extra += "\nFIX THESE PROBLEMS from the previous attempt: " + "; ".join(errs[:10])
    messages = [
        {"role": "system", "content": "You write one article object for a guides section. Answer "
                                      "with that JSON object only — no fences, no commentary."},
        {"role": "user", "content":
            "SITE: " + json.dumps({k: data.get(k) for k in ("language", "locale", "brand", "domain",
                                                             "geo", "title_max_chars")},
                                   ensure_ascii=False) +
            "\nTOPIC BRIEF: " + json.dumps(topic, ensure_ascii=False) +
            "\nARTICLE SHAPE (same keys and nesting, one object): " + shape +
            "\nSlugs already used (pick a different one): " + json.dumps(known_slugs, ensure_ascii=False) +
            "\nTitles already used (do not repeat): " + json.dumps(titles, ensure_ascii=False) +
            "\nRules: " + rules + extra +
            "\nReturn ONLY the article object."},
    ]
    c2 = dict(cfg)
    c2["max_tokens"] = min(int(cfg.get("max_tokens") or MAX_TOKENS), 6000)
    raw, _ = L.http_pack(c2, key, messages)
    art = parse_pack(raw)
    if isinstance(art, dict):
        if isinstance(art.get("articles"), list) and art["articles"]:
            art = art["articles"][0]
        elif isinstance(art.get("article"), dict):
            art = art["article"]
    if not isinstance(art, dict):
        return None
    art["topic"] = str(topic.get("id") or art.get("topic") or "")
    if topic.get("date"):
        art["date"] = str(topic["date"])
    return art


def prune_incomplete(pack: dict) -> int:
    """Drop articles the cut answer left half-written, so they get asked for again.

    A salvaged pack can end inside article 3: the topic would look "delivered" while
    the card is empty. Removing it puts the topic back on the follow-up list."""
    keep, dropped = [], 0
    for a in (pack.get("articles") or []):
        if not isinstance(a, dict):
            continue
        ok = (str(a.get("topic") or "").strip() and str(a.get("slug") or "").strip()
              and isinstance(a.get("sections"), list) and a["sections"]
              and isinstance(a.get("faq"), list) and a["faq"])
        if ok:
            keep.append(a)
        else:
            dropped += 1
            print(f"· dropping a half-written article ({a.get('topic') or a.get('slug') or '?'})")
    pack["articles"] = keep
    return dropped


def add_articles(plan: dict, pack: dict, arts: list) -> int:
    """Merge extra articles in plan order and re-point `related` at real slugs."""
    order = {str((t or {}).get("id") or ""): i
             for i, t in enumerate(plan["blog"].get("topics") or [])}
    cur = [a for a in (pack.get("articles") or []) if isinstance(a, dict)]
    cur += [a for a in arts if isinstance(a, dict)]
    cur.sort(key=lambda a: order.get(str(a.get("topic") or ""), 99))
    pack["articles"] = cur
    _repoint_related(pack)
    return len(cur)


def repair_articles(plan: dict, pack: dict, data: dict, cfg: dict, where: str,
                    by_idx: dict, target_words: int) -> int:
    """Rewrite only the articles the gate rejected, one small answer each.

    The whole-pack repair used to be the only path: ~5k words out, ~5k words back,
    twice — and on a flash model the short article often came back just as short.
    """
    fixed = 0
    arts = pack.get("articles") or []
    for idx in sorted(by_idx):
        if not 0 <= idx < len(arts):
            continue
        cur = arts[idx] if isinstance(arts[idx], dict) else {}
        topic = next((t for t in (plan["blog"].get("topics") or [])
                      if str((t or {}).get("id") or "") == str(cur.get("topic") or "")), None)
        if not topic:
            continue
        known = [str((a or {}).get("slug") or "").strip() for i, a in enumerate(arts) if i != idx]
        titles = [str((a or {}).get("title") or "").strip() for i, a in enumerate(arts) if i != idx]
        art = ask_article(plan, data, topic, [s for s in known if s], [t for t in titles if t],
                          cfg, where, errs=by_idx[idx], target_words=target_words)
        if not art:
            print(f"  ✗ articles[{idx}]: no usable rewrite")
            continue
        before = article_words(cur)
        replace_article(pack, idx, art)
        fixed += 1
        print(f"  ↻ articles[{idx}] rewritten ({before} → {article_words(art)} words)")
    return fixed


def pick_transport(cfg: dict, provider: str):
    key = L.resolve_key(cfg)
    use_http = provider == "http" or (provider == "auto" and bool(key))
    if provider == "http" and not key:
        return None, ""
    if provider == "cli" or (provider == "auto" and not use_http):
        try:
            return ("cli", L.find_cli())
        except SystemExit:
            return None, ""
    return ("http", key) if use_http else (None, "")


def ask_hub(plan: dict, data: dict, cfg: dict, key: str) -> dict:
    """Just the hub labels — the last-resort seed when the pack itself never parsed."""
    messages = [
        {"role": "system", "content": "You write the labels of a guides (blog) hub page for a "
                                      "landing site. Answer with that JSON object only."},
        {"role": "user", "content":
            "SITE: " + json.dumps({k: data.get(k) for k in ("language", "locale", "brand",
                                                             "domain", "geo")}, ensure_ascii=False) +
            "\nHUB SHAPE (same keys, short labels): " + json.dumps(data["shape"]["hub"], ensure_ascii=False) +
            "\nReturn ONLY the hub object."},
    ]
    c2 = dict(cfg)
    c2["max_tokens"] = min(int(cfg.get("max_tokens") or MAX_TOKENS), 2000)
    raw, _ = L.http_pack(c2, key, messages)
    hub = parse_pack(raw)
    if isinstance(hub, dict) and isinstance(hub.get("hub"), dict):
        hub = hub["hub"]
    return hub if isinstance(hub, dict) else {}


def _usable(pack) -> bool:
    """A pack worth building on: hub strings plus at least one real article."""
    return isinstance(pack, dict) and isinstance(pack.get("hub"), dict) and bool(pack.get("articles"))


def ask_model(plan: dict, data: dict, cfg: dict, transport: str, where: str):
    pack = None
    if transport == "http":
        key = where
        messages = [
            {"role": "system", "content": "You are a precise editor for a professional guides "
                                          "section. Return only the finished JSON object: no fences, "
                                          "no commentary, no {\"error\":...} wrapper."},
            {"role": "user", "content": "BRIEF:\n" + json.dumps(data, ensure_ascii=False) +
                                        "\n\nWrite the pack now. Return ONLY the JSON object."},
        ]
        c2 = dict(cfg)
        c2["max_tokens"] = min(int(cfg.get("max_tokens") or MAX_TOKENS), MAX_TOKENS)
        raw, finish = L.http_pack(c2, key, messages)
        pack = parse_pack(raw)
        if not _usable(pack):
            # a long single-shot answer gets cut by the provider (live: a 4-article Dutch
            # pack died at char 18 830 with finish_reason "stop"): one compact retry, and
            # whatever either answer still held is kept for the per-article follow-up
            hint = " (finish=length)" if finish == "length" else ""
            print(f"! blog JSON incomplete{hint} at char {len(raw)} — retrying with a compact answer")
            retry = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "That answer was not valid JSON — it was cut off or "
                                            "malformed. Return the SAME pack again as compact JSON "
                                            "(no indentation, no line breaks inside strings) and make "
                                            "sure every string, array and object is closed. Only the "
                                            "JSON object."},
            ]
            raw2, finish2 = L.http_pack(c2, key, retry)
            pack2 = parse_pack(raw2)
            pack = next((p for p in (pack2, pack) if _usable(p)), None) \
                or (pack2 if isinstance(pack2, dict) else pack)
            if isinstance(pack, dict):
                print(f"· recovered {len(pack.get('articles') or [])} article(s) "
                      f"({len(raw2)} chars, finish={finish2 or 'stop'})")
            elif finish2 == "length":
                print("! provider keeps cutting the answer — raise max_tokens in resources/llm.json")
        return pack, messages
    # CLI transport: the model writes the file itself
    brief_f = ROOT / "content" / f"{plan['params']['domain']}-blog-brief.json"
    brief_f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    out = ROOT / "content" / f"{plan['params']['domain']}-blog.json"
    out.unlink(missing_ok=True)
    L.cli_chat(where, cfg["model"],
               f"Read content/{plan['params']['domain']}-blog-brief.json. Write exactly one file: "
               f"content/{plan['params']['domain']}-blog.json. Return only the JSON object, no fences.")
    if not out.exists():
        return None, []
    try:
        return json.loads(out.read_text(encoding="utf-8")), []
    except Exception as e:
        print(f"! CLI wrote invalid JSON: {e}")
        return None, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--offline", action="store_true",
                    help="write the deterministic offline pack (tests / no key)")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 instead of falling back to the offline pack")
    ap.add_argument("--provider", choices=("auto", "http", "cli"), default="auto")
    ap.add_argument("--model", default="")
    a = ap.parse_args()

    plan_f = pathlib.Path(a.plan)
    plan = json.loads(plan_f.read_text(encoding="utf-8"))
    if not (plan.get("blog") or {}).get("enabled"):
        die("plan has no blog block — create it with: gen_plan.py ... --blog")
    dom = plan["params"]["domain"]
    out = pathlib.Path(a.out) if a.out else ROOT / "content" / f"{dom}-blog.json"
    data = brief(plan)

    pack = None
    if not a.offline:
        cfg = L.load_cfg()
        if a.model:
            cfg["model"] = a.model
        transport, where = pick_transport(cfg, a.provider)
        if not transport:
            print("! no LLM transport (no key, no CLI) — writing the offline pack")
        else:
            print(f"· blog transport: {'http ' + cfg['base_url'] if transport == 'http' else 'opencode CLI'}"
                  f" · model: {cfg['model']} · {len(plan['blog']['topics'])} articles")
            pack, messages = ask_model(plan, data, cfg, transport, where)
            if transport == "http" and not isinstance(pack, dict):
                # not one usable JSON object came back: seed the pack from the hub and let
                # the per-article follow-up write the articles (6 small answers instead of
                # one long one that this provider keeps breaking)
                print("· no usable pack — rebuilding it from the hub and single articles")
                pack = {"hub": ask_hub(plan, data, cfg, where), "articles": []}
                messages = messages or []
            lang = plan["params"].get("lang", "en")
            target = body_word_target(lang)
            if isinstance(pack, dict) and transport == "http":
                prune_incomplete(pack)
                miss = missing_topics(plan, pack)
                if miss:
                    print(f"· pack came back partial — asking for {len(miss)} article(s) separately")
                    extra = []
                    for topic in miss:
                        known = [str((a or {}).get("slug") or "") for a in (pack.get("articles") or [])]
                        known += [str(a.get("slug") or "") for a in extra]
                        titles = [str((a or {}).get("title") or "") for a in (pack.get("articles") or [])]
                        titles += [str(a.get("title") or "") for a in extra]
                        art = ask_article(plan, data, topic, [s for s in known if s],
                                          [t for t in titles if t], cfg, where,
                                          target_words=target)
                        if art:
                            extra.append(art)
                            print(f"  ✓ {topic.get('id')}: “{str(art.get('title'))[:54]}”")
                        else:
                            print(f"  ✗ {topic.get('id')}: no usable article object")
                    add_articles(plan, pack, extra)
                else:
                    add_articles(plan, pack, [])
            if isinstance(pack, dict):
                # Per-article problems are repaired per article: a small focused answer
                # beats re-sending the whole 5k-word pack (which is what used to happen,
                # and a short article often came back identical after it).
                full_done = 0
                for attempt in (1, 2, 3):
                    errs = gate(plan, pack)
                    if not errs:
                        break
                    by_idx, pack_level = article_error_map(errs)
                    if transport == "http" and by_idx:
                        print(f"· repair pass {attempt}: {len(by_idx)} article(s) failed the gate"
                              + (f" (+{len(pack_level)} pack issue(s))" if pack_level else ""))
                        if repair_articles(plan, pack, data, cfg, where, by_idx, target):
                            continue
                    if full_done:
                        break
                    full_done += 1
                    print(f"· repair pass {attempt} ({len(errs)} issues, whole pack)")
                    if transport == "http":
                        messages += [
                            {"role": "assistant", "content": json.dumps(pack, ensure_ascii=False)},
                            {"role": "user", "content": "Fix these errors, keep all other values, return "
                                                        "ONLY the corrected JSON object: " + "; ".join(errs[:14])},
                        ]
                        raw, _ = L.http_pack(dict(cfg, max_tokens=min(int(cfg.get("max_tokens") or MAX_TOKENS),
                                                                     MAX_TOKENS)), where, messages)
                        try:
                            pack = parse_pack(raw)
                            if pack is None:
                                raise ValueError("no JSON object in the repair answer")
                        except Exception as e:
                            print(f"! repair unparsable: {e}")
                            pack = None
                    else:
                        L.cli_chat(where, cfg["model"],
                                   f"Fix content/{dom}-blog.json. Errors: " + "; ".join(errs[:14]) +
                                   ". Keep the schema and language. Rewrite the whole file.")
                        try:
                            pack = json.loads(out.read_text(encoding="utf-8"))
                        except Exception:
                            pack = None
                    if not isinstance(pack, dict):
                        break
                if isinstance(pack, dict):
                    errs = gate(plan, pack)
                    if errs:
                        print("! blog pack still invalid: " + "; ".join(errs[:6]))
            elif pack is not None:
                print("! model did not return a JSON object")

    fell_back = False
    invalid_pack = None
    if not isinstance(pack, dict) or gate(plan, pack):
        if isinstance(pack, dict):
            invalid_pack = pack
        if a.strict and not a.offline:
            die("blog pack invalid (strict mode)")
        if not a.offline:
            print("! falling back to the deterministic offline pack (replace it before shipping)")
            fell_back = True
        pack = offline_pack(plan)
        if fell_back:
            # this is a placeholder, not copy: mark it so a later --build never
            # mistakes it for a valid blog pack and reuses English filler on a local site
            pack["_offline_fallback"] = True
        errs = gate(plan, pack)
        if errs:
            die("offline blog pack failed its own gate: " + "; ".join(errs[:8]))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    if invalid_pack is not None:
        bad = out.with_suffix(".invalid.json")
        bad.write_text(json.dumps(invalid_pack, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"· rejected model pack saved for review: {rel(bad)}")
    words = sum(len(re.findall(r"\w+", json.dumps(ar, ensure_ascii=False)))
                for ar in pack["articles"])
    print(f"BLOG CONTENT OK -> {rel(out)} "
          f"({len(pack['articles'])} articles, {words} words, style {plan['blog'].get('style')})")
    if fell_back:
        print("✗ the model did not produce a valid blog pack — the offline placeholder is on disk; "
              "fix the provider or rerun with --offline if this is a test build")
        sys.exit(2)


# ------------------------------------------------------------------ offline bank
_OFFLINE = {
    "en": {
        "hub": {"eyebrow": "Guides", "title": "Practical guides", "lead": "Short, factual notes on costs, risk and the everyday mechanics of the platform.",
                "all_label": "All guides",
                "toc_label": "Contents", "takeaways_label": "Key points", "related_title": "Read next",
                "min_read_label": "min", "faq_label": "Frequently asked questions",
                "facts_sections_label": "sections", "facts_words_label": "words"},
        "title": "A practical guide to {topic}",
        "short_title": "Guide: {topic}",
        "h1": "How to think about {topic}",
        "excerpt": "A plain-language look at {topic}: what to check, what it costs and which details are easy to miss.",
        "role": "Editorial team",
        "heads": ["What {topic} means in practice", "How to check {topic} yourself", "Where people go wrong with {topic}", "A short {topic} checklist"],
        "outro": " In practice, {topic} is worth one written comparison before any money moves.",
        "frames": [
            "{topic} is easier to judge when you separate the decision from the marketing. Start with what the platform actually charges, what it asks you to sign, and what happens when you want your money back.",
            "A useful test is to write the answer in one sentence. If you cannot explain {topic} to a friend without opening a brochure, the details still need checking.",
            "Numbers help only when they come from the same source. Compare the same instrument, the same amount and the same day; otherwise the difference is noise, not evidence.",
            "Keep a short record of what you checked and when. A dated note is more useful than a memory of a convincing sales call.",
            "Nothing on this page promises a result. The point is to make the cost, the risk and the next step visible before you commit.",
            "If a claim sounds unusually generous, ask which document supports it and who is responsible if it turns out to be wrong.",
            "Read the fee table next to the product description, not on its own. A low headline fee often hides a wider spread or a conversion charge.",
            "Test the process with a small amount first. A fast withdrawal of a small sum tells you more than a long list of testimonials.",
            "Ask which entity holds the account, which regulator supervises it and which language the contract uses.",
            "Compare the same moment in time. Prices move, so a screenshot from yesterday is not a fair comparison with a quote from today.",
            "Write down the conditions that would make you stop. A rule written in advance is easier to follow than a decision made in the middle of a bad day.",
            "Finally, check how support answers a simple question. Clear, specific replies are a better signal than a large help centre.",
            "Separate the product from the payment. A platform can be technically solid and still expensive if the deposit, conversion or withdrawal route is poorly explained.",
            "Ask for a worked example in your own currency. A percentage is easy to quote and hard to feel; an amount on a statement is not.",
            "Check what happens when something goes wrong: a rejected payment, a forgotten password, a closed market. Recovery paths matter more than the happy path.",
            "Give the decision a deadline. Comparing forever is its own kind of cost, and a dated review keeps the process finite.",
        ],
        "points": ["Check {topic} against the official fee schedule.",
                   "Keep a dated screenshot of every important term.",
                   "Ask support to confirm the point in writing."],
        "takeaways": ["Understand the cost before the product.", "Check the entity and the rules that apply.",
                      "Write down your stop conditions in advance."],
        "faq": [("What should I check first about {topic}?",
                 "Start with the official fee schedule and the legal entity behind the platform. Then confirm the withdrawal rules and the documents you will need, because those details decide how quickly you can get your money back."),
                ("Does this page give financial advice?",
                 "No. The page explains how to evaluate the topic and which questions to ask. Any decision about money should follow your own circumstances and, where relevant, advice from a qualified local professional."),
                ("How can I compare two platforms fairly?",
                 "Use the same instrument, the same amount and the same day, and include spreads, commissions and conversion costs. A comparison built on different conditions is only a comparison of marketing.")],
        "cta_title": "Put the checklist to work",
        "cta_text": "Open the platform, compare the terms and keep your notes in one place.",
        "cta_btn": "Open account",
    },
    "it": {
        "hub": {"eyebrow": "Guide", "title": "Guide pratiche", "lead": "Note brevi e concrete su costi, rischio e funzionamento quotidiano della piattaforma.",
                "all_label": "Tutte le guide",
                "toc_label": "Indice", "takeaways_label": "Punti chiave", "related_title": "Leggi anche",
                "min_read_label": "min", "faq_label": "Domande frequenti",
                "facts_sections_label": "sezioni", "facts_words_label": "parole"},
        "title": "Guida pratica a {topic}",
        "short_title": "Guida: {topic}",
        "h1": "Come valutare {topic}",
        "excerpt": "Uno sguardo concreto a {topic}: cosa verificare, quanto costa e quali dettagli sfuggono più spesso.",
        "role": "Redazione",
        "heads": ["Che cosa significa {topic} in pratica", "Come verificare {topic} da soli", "Dove si sbaglia con {topic}", "Una checklist breve su {topic}"],
        "outro": " In pratica, {topic} merita un confronto scritto prima di muovere denaro.",
        "frames": [
            "{topic} si valuta meglio separando la decisione dalla comunicazione. Parti da quanto costa davvero la piattaforma, da cosa firmi e da cosa succede quando chiedi indietro il denaro.",
            "Un test utile è riassumere la risposta in una frase. Se non riesci a spiegare {topic} a un amico senza aprire una brochure, i dettagli vanno ancora controllati.",
            "I numeri aiutano solo se vengono dalla stessa fonte. Confronta lo stesso strumento, lo stesso importo e lo stesso giorno; altrimenti la differenza è rumore, non prova.",
            "Tieni un breve registro di cosa hai controllato e quando. Una nota datata vale più del ricordo di una telefonata convincente.",
            "Questa pagina non promette risultati. Serve a rendere visibili costo, rischio e passo successivo prima di impegnarsi.",
            "Se un'affermazione sembra troppo generosa, chiedi quale documento la sostiene e chi risponde se si rivela sbagliata.",
            "Leggi la tabella delle commissioni accanto alla descrizione del prodotto, non da sola. Un costo di ingresso basso nasconde spesso uno spread più ampio o un cambio valuta.",
            "Prova il processo con una somma piccola. Un prelievo rapido di un importo ridotto dice più di un lungo elenco di testimonianze.",
            "Chiedi quale società gestisce il conto, quale autorità la vigila e in quale lingua è scritto il contratto.",
            "Confronta lo stesso momento. I prezzi si muovono: uno screenshot di ieri non è un confronto leale con una quotazione di oggi.",
            "Scrivi in anticipo le condizioni che ti farebbero fermare. Una regola decisa prima è più facile da seguire di una scelta fatta in una giornata storta.",
            "Infine guarda come il supporto risponde a una domanda semplice. Risposte chiare e specifiche sono un segnale migliore di un centro assistenza enorme.",
            "Tieni separati prodotto e pagamento. Una piattaforma può essere tecnicamente solida e comunque costosa se la via del deposito, della conversione o del prelievo è spiegata male.",
            "Chiedi un esempio concreto nella tua valuta. Una percentuale è facile da citare e difficile da percepire; un importo sull'estratto conto no.",
            "Controlla cosa succede quando qualcosa va storto: un pagamento rifiutato, una password dimenticata, un mercato chiuso. Le vie di recupero contano più del caso normale.",
            "Dai una scadenza alla decisione. Confrontare all'infinito è a sua volta un costo, e una verifica con una data mantiene il processo finito.",
        ],
        "points": ["Verifica {topic} sul listino ufficiale delle commissioni.",
                   "Conserva uno screenshot datato di ogni condizione importante.",
                   "Chiedi al supporto di confermare il punto per iscritto."],
        "takeaways": ["Capisci il costo prima del prodotto.", "Controlla la società e le regole applicabili.",
                      "Scrivi in anticipo le condizioni per fermarti."],
        "faq": [("Che cosa devo verificare per primo su {topic}?",
                 "Parti dal listino ufficiale delle commissioni e dalla società che gestisce la piattaforma. Poi controlla le regole di prelievo e i documenti richiesti, perché sono questi dettagli a decidere quanto rapidamente puoi riottenere il denaro."),
                ("Questa pagina offre consulenza finanziaria?",
                 "No. La pagina spiega come valutare l'argomento e quali domande porre. Ogni decisione sul denaro dipende dalla tua situazione e, quando serve, dal parere di un professionista locale qualificato."),
                ("Come posso confrontare due piattaforme in modo corretto?",
                 "Usa lo stesso strumento, lo stesso importo e lo stesso giorno, includendo spread, commissioni e costi di conversione. Un confronto costruito su condizioni diverse è solo un confronto di comunicazione.")],
        "cta_title": "Metti in pratica la checklist",
        "cta_text": "Apri la piattaforma, confronta le condizioni e tieni le note in un unico posto.",
        "cta_btn": "Apri un conto",
    },
}
_OFFLINE["cs"] = _OFFLINE["en"]
_OFFLINE["es"] = _OFFLINE["en"]


if __name__ == "__main__":
    main()
