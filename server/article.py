"""Generation of one blog article as content JSON (POST /blog/article).

The model writes text, never markup: the caller renders the page into the site's own
shell, so CSS/header/footer/guard can never drift and a bad answer cannot ship a broken
PHP file. Kept in its own module so /build stays untouched.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

log = logging.getLogger("article")

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I)
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF]")
HTML_RE = re.compile(r"</?[a-z][^>]*>", re.I)
DEPOSIT_RE = re.compile(r"(€\s?250\b|250\s?€|min(?:imum)?\s?deposit|100\s?000\s?Ft)", re.I)

INTENTS = [
    "platform fees and the real cost of a trade",
    "how to verify a platform licence and legal entity",
    "withdrawal process, limits and typical delays",
    "KYC and account verification",
    "risk per position and stop placement",
    "position sizing from account size",
    "volatility and its effect on stops and slippage",
    "trader psychology and decision journaling",
    "taxes for a retail trader",
    "beginner mistakes that cost money",
    "how to read an account statement and trade history",
]


class ArticleError(Exception):
    pass


SYSTEM = """You write one blog article for a review-style website. Output ONLY a JSON object.

LANGUAGE: write in {lang}. Brand: {brand}. Do NOT mix languages.

GOOGLE SEO
- The first paragraph answers the query directly in 2-3 sentences. No warm-up intro.
- One main query and 2-3 sub-queries that people actually type. Each H2 closes one sub-query.
- Headings are phrased as the query, not "Part 1" or "Conclusion".
- At least 3 concrete facts, steps or examples that are specific to this topic. No generic filler.
- 700-1100 words total. 4-6 sections. Paragraphs of 300-600 characters.
- 3-4 FAQ entries; each answer starts with the direct answer (150+ characters).
- Never invent numbers, dates, regulators, company names, studies or quotes. If a number is
  not known, describe the mechanism without a number.

HUMAN TONE
- Vary sentence length: a short sentence after two long ones.
- Concrete nouns instead of abstractions; name who does what (active voice).
- Admit trade-offs ("this does not work when ...").
- Banned: "not X but Y", "it is not just X, it is Y", one-line closers restating the paragraph
  ("That is the real difference."), forced triads of abstract nouns, "in today's world",
  "it is important to note", "in conclusion", "plays a key role", "is a testament to",
  "dynamic landscape", "comprehensive approach", em dashes as the universal connector,
  bold labels on every list item, emoji, exclamation marks, chatbot phrases.
- Do not restate the heading in the first sentence of a section.
- The last paragraph gives a concrete action or conclusion, not a summary.

OUTPUT JSON (no markdown fences, no commentary):
{{
  "slug": "lowercase-latin-hyphen-slug",
  "title": "{tmin}-{tmax} chars, no brand, plain query",
  "h1": "headline, 12-90 chars, brand only if it reads naturally",
  "excerpt": "140-160 chars summary for cards and meta description",
  "read_min": 6,
  "link_label": "short heading for a useful-links block, in {lang}",
  "takeaways": ["...", "...", "..."],
  "sections": [
    {{"h2": "...", "p": ["...", "..."], "points": ["optional", "optional"]}}
  ],
  "faq": [{{"q": "...", "a": "..."}}],
  "related": ["existing-slug-1", "existing-slug-2"],
  "cta": {{"title": "...", "text": "...", "btn": "..."}}
}}

Rules for the fields: takeaways 3-5 items; sections 4-6; points optional 2-6; faq 3-4;
related only from the provided existing slugs (1-2); cta is one soft next step.
No HTML tags, no e-mail addresses, no deposit amounts anywhere.
"""


def _existing(req: dict) -> list[dict]:
    out = []
    for a in req.get("existing") or []:
        if isinstance(a, dict) and a.get("slug"):
            out.append({"slug": str(a["slug"]), "title": str(a.get("title") or "")[:120],
                        "h1": str(a.get("h1") or "")[:140]})
    return out[:40]


def title_limit(req: dict) -> int:
    """Скільки знаків лишає панель на title без бренду (`title_max` у запиті).

    Панель дописує `Brand — ` у <title>, тому бюджет залежить від довжини бренду.
    Старий запит без поля — 65, як було в промпті.
    """
    try:
        return max(30, min(72, int(req.get("title_max") or 65)))
    except (TypeError, ValueError):
        return 65


def _fit(text: str, limit: int) -> str:
    """Обрізає по межі слова, не лишаючи висячих коми/тире. Коротше за 18 не робить."""
    text = _text(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip(" ,.;:—–-")
    head = cut.rsplit(" ", 1)[0].rstrip(" ,.;:—–-") if " " in cut else ""
    return head if len(head) >= 18 else cut


def requested_links(req: dict) -> list[str]:
    """Беклінки від панелі: список http(s)-URL, без дублів, максимум 3."""
    out: list[str] = []
    for item in req.get("links") or []:
        url = str((item.get("url") if isinstance(item, dict) else item) or "").strip()[:300]
        if url.startswith(("http://", "https://")) and url not in out:
            out.append(url)
    return out[:3]


def links_brief(urls: list[str], lang: str) -> str:
    """Інструкція моделі про беклінки. Порожній рядок — запит без посилань, промпт не змінюється."""
    if not urls:
        return ""
    items = "\n".join(f"- {u}" for u in urls)
    return (
        "LINKS (mandatory, each URL exactly once):\n"
        f"{items}\n"
        "Put each URL inside a normal body paragraph as [anchor](URL). Anchor: 2-6 words in "
        f"{lang}, describes what is behind the link; never \"read more\", \"click here\" or the "
        "brand of this site. One link per sentence, not in the first paragraph. Never invent "
        "URLs and never add links outside this list. link_label: a short heading for a links "
        f"block, in {lang}."
    )


def build_messages(req: dict) -> list[dict]:
    lang = str(req.get("lang") or "en")[:12]
    brand = str(req.get("brand") or "")[:80]
    existing = _existing(req)
    topic = req.get("topic")
    if isinstance(topic, dict):
        topic_line = (f"TOPIC (fixed): {topic.get('intent') or ''}. Angle: {topic.get('angle') or ''}. "
                      f"Keywords: {', '.join(str(k) for k in (topic.get('keywords') or [])[:8])}")
    else:
        topic_line = ("TOPIC: choose one that is NOT covered by the existing articles. "
                      f"Good directions: {'; '.join(INTENTS)}")
    known = "\n".join(f'- {a["slug"]} — {a["title"]}' for a in existing) or "- (none yet)"
    user = (f"{topic_line}\n\nExisting articles (do not repeat them):\n{known}\n\n"
            "Write the article now. JSON only.")
    tmax = title_limit(req)
    tmin = max(18, min(50, tmax - 15))
    system = SYSTEM.format(lang=lang, brand=brand, tmin=tmin, tmax=tmax)
    brief = links_brief(requested_links(req), lang)
    if brief:
        system += "\n\n" + brief
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def _text(x) -> str:
    return str(x or "").strip()


def validate(payload: dict, lang: str = "en", existing_slugs: set[str] | None = None,
             title_max: int = 72) -> list[str]:
    """Hard gate before the panel renders anything. Mirrors the blog gates of the factory."""
    errs: list[str] = []
    if not isinstance(payload, dict):
        return ["answer is not a JSON object"]
    slug = _text(payload.get("slug"))
    if not SLUG_RE.fullmatch(slug):
        errs.append(f"slug is not lowercase-hyphenated: {slug!r}")
    if existing_slugs and slug in existing_slugs:
        errs.append(f"slug already exists: {slug}")
    title, h1 = _text(payload.get("title")), _text(payload.get("h1"))
    excerpt = _text(payload.get("excerpt"))
    if not 18 <= len(title) <= title_max:
        errs.append(f"title length {len(title)} (18..{title_max})")
    if not 12 <= len(h1) <= 90:
        errs.append(f"h1 length {len(h1)} (12..90)")
    if not 60 <= len(excerpt) <= 190:
        errs.append(f"excerpt length {len(excerpt)} (60..190)")
    try:
        if int(payload.get("read_min") or 0) < 2:
            errs.append("read_min must be >= 2")
    except (TypeError, ValueError):
        errs.append("read_min is not a number")
    take = [x for x in (payload.get("takeaways") or []) if _text(x)]
    if len(take) < 3:
        errs.append("takeaways needs >= 3 items")
    secs = payload.get("sections")
    if not isinstance(secs, list) or not 3 <= len(secs) <= 7:
        errs.append("sections needs 3..7 blocks")
        secs = []
    words, heads = 0, set()
    for i, sec in enumerate(secs):
        if not isinstance(sec, dict):
            errs.append(f"sections[{i}] is not an object")
            continue
        h2 = _text(sec.get("h2"))
        if not 8 <= len(h2) <= 90:
            errs.append(f"sections[{i}].h2 length {len(h2)} (8..90)")
        if h2.casefold() in heads:
            errs.append(f"sections[{i}].h2 repeats")
        heads.add(h2.casefold())
        paras = sec.get("p")
        if not isinstance(paras, list) or not 1 <= len(paras) <= 5:
            errs.append(f"sections[{i}].p needs 1..5 paragraphs")
            paras = []
        for j, p in enumerate(paras):
            if len(_text(p)) < 40:
                errs.append(f"sections[{i}].p[{j}] is too short")
            words += len(re.findall(r"\w+", _text(p), re.UNICODE))
        pts = sec.get("points") or []
        if pts and (not isinstance(pts, list) or not 2 <= len(pts) <= 6):
            errs.append(f"sections[{i}].points needs 2..6 items")
        for p in (pts if isinstance(pts, list) else []):
            if len(_text(p)) < 12:
                errs.append(f"sections[{i}].points has a too-short item")
            words += len(re.findall(r"\w+", _text(p), re.UNICODE))
        words += len(re.findall(r"\w+", h2, re.UNICODE))
    min_words = 220 if (lang or "").lower() in ("ja", "zh", "ko") else 380
    if words < min_words:
        errs.append(f"body is {words} words, needs >= {min_words}")
    faq = payload.get("faq")
    if not isinstance(faq, list) or not 2 <= len(faq) <= 5:
        errs.append("faq needs 2..5 entries")
        faq = []
    for k, item in enumerate(faq):
        if not isinstance(item, dict):
            errs.append(f"faq[{k}] is not an object")
            continue
        if len(_text(item.get("q"))) < 10:
            errs.append(f"faq[{k}].q is too short")
        if len(_text(item.get("a"))) < 90:
            errs.append(f"faq[{k}].a is too short")
    related = payload.get("related") or []
    if not isinstance(related, list):
        errs.append("related must be an array")
    elif existing_slugs is not None:
        for r in related:
            if r not in existing_slugs:
                errs.append(f"related points to an unknown slug: {r}")
    blob = json.dumps(payload, ensure_ascii=False)
    if DEPOSIT_RE.search(blob):
        errs.append("article mentions a deposit amount")
    if EMAIL_RE.search(blob):
        errs.append("plain-text e-mail in the article")
    if EMOJI_RE.search(blob):
        errs.append("emoji in the article")
    for key, val in _strings(payload):
        if HTML_RE.search(val):
            errs.append(f"{key}: HTML tag in the copy")
            break
    return errs


def _strings(node, path=""):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, f"{path}[{i}]")


def _texts(value) -> list[str]:
    """Список непорожніх рядків: рядок → [рядок], None → []."""
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    return [x.strip() for x in items if isinstance(x, str) and x.strip()]


def _coerce(payload: dict) -> dict:
    """Лагодить типові форматні відхилення моделі, які не варті цілої повторної генерації.

    Найчастіше: `p` прийшов рядком замість масиву, порожні/зайві пункти, faq одним
    об'єктом, read_min рядком. Зміст не переписуємо — лише приводимо форму.
    """
    if not isinstance(payload, dict):
        return payload
    sections = payload.get("sections")
    if sections is not None and not isinstance(sections, list):
        payload["sections"] = [sections]
    for sec in payload.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        sec["p"] = _texts(sec.get("p"))[:5]
        if sec.get("points") is not None:
            sec["points"] = _texts(sec.get("points"))[:6]
    if payload.get("takeaways") is not None:
        payload["takeaways"] = _texts(payload.get("takeaways"))
    if isinstance(payload.get("faq"), dict):
        payload["faq"] = [payload["faq"]]
    for item in payload.get("faq") or []:
        if isinstance(item, dict):
            item["q"] = str(item.get("q") or "").strip()
            item["a"] = str(item.get("a") or "").strip()
    if isinstance(payload.get("cta"), str):
        payload["cta"] = {"title": payload["cta"]}
    if isinstance(payload.get("related"), str):
        payload["related"] = [payload["related"]]
    try:
        payload["read_min"] = int(payload.get("read_min") or 0)
    except (TypeError, ValueError):
        payload["read_min"] = 0
    return payload


def _repair_messages(messages: list[dict], raw: str, errs: list[str]) -> list[dict]:
    """Один повторний запит: віддаємо моделі її ж JSON і список претензій."""
    return messages + [
        {"role": "assistant", "content": raw[:14000]},
        {"role": "user", "content": "That JSON failed validation:\n- " + "\n- ".join(errs[:6]) +
                                     "\nReturn the FULL corrected JSON object only: same topic, same "
                                     "language, same links. No commentary, no fences."},
    ]


def generate(req: dict) -> dict:
    """Ask the provider for the content JSON. Raises ArticleError with a readable reason."""
    import llm_content as L  # noqa: E402  (tools/llm_content.py, same repo)
    try:
        cfg = L.load_cfg()
        key = L.resolve_key(cfg)
    except SystemExit as e:  # provider config missing
        raise ArticleError(f"LLM config error: {e}") from e
    if not key:
        raise ArticleError("LLM key is not configured on the builder (VENICE_API_KEY / .llm_env)")
    messages = build_messages(req)
    try:
        raw, _finish = L.http_chat(cfg, key, messages)
    except SystemExit as e:  # http_chat() reports failures via die()
        raise ArticleError(f"provider call failed: {e}") from e
    try:
        payload = L.extract_json(raw)
    except (ValueError, json.JSONDecodeError) as e:
        raise ArticleError(f"model did not return JSON: {e}") from e
    tmax = title_limit(req)
    lang = str(req.get("lang") or "en")

    def clean(p: dict) -> dict:
        if isinstance(p, dict):
            p = _coerce(p)
            # перебір на кілька знаків — не привід палити запуск: підрізаємо по межі слова
            p["title"] = _fit(_text(p.get("title")), tmax)
        return p

    payload = clean(payload)
    errs = validate(payload, lang, title_max=tmax)
    if errs:
        # форматні відхилення (p рядком, faq об'єктом) лікує _coerce; змістові — один repair
        log.warning("article: rejected (%s) — one repair pass", "; ".join(errs[:3]))
        try:
            fixed_raw, _finish = L.http_chat(cfg, key, _repair_messages(messages, raw, errs))
            payload = clean(L.extract_json(fixed_raw))
            errs = validate(payload, lang, title_max=tmax)
        except (ValueError, json.JSONDecodeError) as e:
            log.warning("article: repair returned non-JSON: %s", e)
        except Exception as e:  # noqa: BLE001 — repair не має ховати початкову причину
            log.warning("article: repair pass failed: %s", e)
    if errs:
        raise ArticleError("article rejected: " + "; ".join(errs[:6]))
    payload["slug"] = _text(payload["slug"]).lower()
    payload["title"] = _text(payload["title"])
    payload["h1"] = _text(payload["h1"])
    payload["excerpt"] = _text(payload["excerpt"])
    return payload
