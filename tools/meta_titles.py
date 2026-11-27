#!/usr/bin/env python3
"""meta_titles.py — title/description factory: funnel name first (SEO) + a hook that earns the click.

Why a separate step: the content pack's `title_home`/`description` carry two different jobs.
Search needs the funnel name at the start and one category phrase right after it; the click
needs a number, a concrete benefit or a removed fear in the tail. One string can do both only
when the slots are explicit:

    <brand> — <category>, <hook>          <- what people see in the SERP
    <brand> — <category>: <hook>

Everything here is deterministic and offline-capable (no key, no network): candidates come from
the pack's own strings (claims, side stats, hero lead, CTA), so nothing is invented. `--llm`
adds model-authored candidates on top; they still pass the same scoring and lint, and anything
with a compliance risk or a cliché is dropped instead of ranked.

Canonical copy lives here; seo-copyring keeps an identical `copyring/engine/meta_titles.py`
(core verbatim + lxml helpers at the bottom). Change both together.

Usage:
  python3 tools/meta_titles.py --content content/<domain>-content.json --n 6
  python3 tools/meta_titles.py --content ... --apply 1          # write the winner into the pack
  python3 tools/meta_titles.py --content ... --check            # lint only, exit 1 on ERR
  python3 tools/meta_titles.py --brand "Aurevia Capital" --lang en --hook "free demo first"
  python3 tools/meta_titles.py --content ... --llm --n 8         # + model candidates
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import unicodedata
from dataclasses import dataclass, field

# --- limits -----------------------------------------------------------------
TITLE_MAX = 60          # visible part in the SERP
TITLE_HARD = 70         # build gate (tools/llm_content.py, seo_audit.py)
DESC_MIN = 110
DESC_MAX = 155

# --- pattern banks ----------------------------------------------------------
# Only the category slot needs a per-language bank: hooks and sentences come from
# the pack itself, so they are already in the site language.
CATEGORY_BANK: dict[str, list[str]] = {
    "en": ["AI investment platform", "investing platform", "trading platform",
           "market data platform"],
    "it": ["piattaforma di investimento con AI", "piattaforma di trading",
           "piattaforma per investire", "dati di mercato"],
    "de": ["KI-Investmentplattform", "Trading-Plattform", "Investmentplattform",
           "Marktdaten-Plattform"],
    "es": ["plataforma de inversión con IA", "plataforma de trading",
           "plataforma de inversión", "datos de mercado"],
    "fr": ["plateforme d'investissement IA", "plateforme de trading",
           "plateforme d'investissement", "données de marché"],
    "nl": ["AI-beleggingsplatform", "handelsplatform", "beleggingsplatform",
           "marktdata-platform"],
    "pl": ["platforma inwestycyjna AI", "platforma tradingowa",
           "platforma inwestycyjna", "dane rynkowe"],
    "pt": ["plataforma de investimento com IA", "plataforma de trading",
           "plataforma de investimento", "dados de mercado"],
    "tr": ["yapay zekâ yatırım platformu", "işlem platformu", "yatırım platformu",
           "piyasa verileri"],
    "cs": ["investiční platforma s AI", "obchodní platforma", "investiční platforma"],
    "sk": ["investičná platforma s AI", "obchodná platforma", "investičná platforma"],
    "hu": ["AI befektetési platform", "kereskedési platform", "befektetési platform"],
    "ro": ["platformă de investiții cu AI", "platformă de tranzacționare",
           "platformă de investiții"],
}

# --- vocabulary that moves the score ---------------------------------------
CLICHE = (
    "best ", "world-class", "world class", "revolutionary", "cutting-edge", "cutting edge",
    "seamless", "empower", "unlock", "ultimate", "leading provider", "welcomes you",
    "next-level", "game-changer", "state-of-the-art", "інноваційн", "провідн", "найкращ",
)
RISK = (
    "guaranteed", "guarantee", "risk-free", "risk free", "no risk", "riskless", "fixed return",
    "passive income", "double your", "% per month", "% a month", "100% safe", "no loss",
    "guadagno garantito", "rendimento garantito", "senza rischio", "rendimiento garantizado",
    "sin riesgo", "rendement garanti", "sans risque", "garantierter", "risikofrei",
    "gegarandeerd", "zonder risico", "gwarantowany", "bez ryzyka", "garantido", "risco zero",
    "garanti", "risksiz", "гарантован", "без ризику",
)
TRANSPARENCY = (
    "no hidden", "commits you to nothing", "no return promises", "without promises",
    "nessun costo nascosto", "senza impegno", "keine versteckten", "unverbindlich",
    "sin costes ocultos", "sans frais cachés", "geen verborgen", "bez ukrytych",
    "sem custos escondidos", "gizli ücret", "nihai maliyet",
)
PLACEHOLDER = (
    "lorem", "ipsum", "build real headline", "{brand}", "{", "TODO", "TBD", "xxx",
    "sample text", "your headline", "placeholder", "заголовок",
)
PLACEHOLDER_RX = re.compile(
    r"\{[^{}]{0,80}\}|\{\{|\}\}|"
    r"(?i:lorem|ipsum|build real headline|sample text|your headline|placeholder|заголовок)|"
    r"\bTODO\b|\bTBD\b|\bXXX\b")
# "todo"/"todos" is an ordinary word in Portuguese/Spanish ("all"); only the
# uppercase code marker is a placeholder. Substring matching used to fail a pt
# blog page on "para todos" (live: pnaf.info).
PLACEHOLDER = (
    "lorem", "ipsum", "build real headline", "{brand}", "{", "TODO", "TBD", "xxx",
    "sample text", "your headline", "placeholder", "заголовок",
)


def _placeholder_hit(text) -> bool:
    return bool(PLACEHOLDER_RX.search(str(text or "")))


def clean_meta(text) -> str:
    """Strip schema/placeholder tokens from a title or description."""
    s = PLACEHOLDER_RX.sub(" ", str(text or ""))
    s = re.sub(r"[{}]", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" .,;:—-")



DEPOSIT_RE = re.compile(
    r"(€\s?\d|£\s?\d|\$\s?\d|\d\s?€|\d\s?£|deposit|depozyt|einzahlung|deposito|versement|"
    r"storting|wpłata|yatırım tutarı)", re.I)


@dataclass
class Variant:
    title: str
    description: str
    seo: int = 0
    ctr: int = 0
    notes: list[str] = field(default_factory=list)
    category: str = ""          # which category phrase this title actually used
    h1_rest: str = ""           # hero line after the brand
    h1_accent: str = ""         # 2-4 word closing accent
    h1_score: int = 0
    source: str = "template"    # "model" when the copy came from the LLM

    @property
    def score(self) -> int:
        return round(self.seo * 0.6 + self.ctr * 0.4)

    @property
    def rank(self) -> int:
        """Title 60% + hero headline 40%. A variant without an H1 counts as neutral (60),
        so a model-written headline with real substance outranks a template title."""
        return round(self.score * 0.6 + (self.h1_score or 60) * 0.4)

    def as_dict(self) -> dict:
        return {"title": self.title, "description": self.description,
                "category": self.category, "seo": self.seo, "ctr": self.ctr,
                "score": self.score, "rank": self.rank,
                "h1_rest": self.h1_rest, "h1_accent": self.h1_accent,
                "h1_score": self.h1_score, "source": self.source, "notes": self.notes}


# --- helpers ----------------------------------------------------------------
def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _lower_first(text: str) -> str:
    t = _clean(text)
    if not t:
        return t
    first = t.split()[0]
    if (first.isupper() and len(first) > 1) or re.match(r"^[A-Z]{2,}", t):
        return t                                # acronym / brand-like: "SSL-secured"
    return t[0].lower() + t[1:]


def _upper_first(text: str) -> str:
    t = _clean(text)
    return t[:1].upper() + t[1:] if t else t


def _key(text: str) -> str:
    return re.sub(r"[^0-9a-zà-ÿа-я]+", "", text.lower())


def _width(text: str) -> int:
    """SERP width in Latin-character units: a CJK glyph takes roughly two.

    Without this a 60-character Japanese title is twice as long on screen as a
    60-character English one and gets cut mid-phrase.
    """
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _has(text: str, words) -> str:
    low = text.lower()
    return next((w for w in words if w in low), "")


def category_bank(lang: str) -> list[str]:
    return CATEGORY_BANK.get((lang or "en").lower()[:2], [])


def detect_category(text: str, brand: str = "") -> str:
    """Pull the category phrase out of an existing title ('Brand — AI platform | UK')."""
    t = _clean(text)
    if brand:
        t = re.sub(re.escape(brand), " ", t, flags=re.I)
    for chunk in re.split(r"[|•·—–:]| - ", t):
        chunk = _clean(chunk.strip(" ,.-"))
        words = chunk.split()
        if 2 <= len(words) <= 6 and not re.search(r"\d", chunk):
            return chunk
    return ""


def _ok_category(cat: str, brand: str = "") -> bool:
    """A category phrase is a search phrase, not a slogan: 1-4 words, no digits."""
    c = _clean(cat).strip(" .,;:—-")
    if not (4 <= len(c) <= 44) or len(c.split()) > 4:
        return False
    if re.search(r"\d", c):
        return False
    if brand and brand.lower() in c.lower():
        return False
    return not (_has(c, CLICHE) or _has(c, RISK) or _placeholder_hit(c))


def pack_category(pack: dict, brand: str = "") -> str:
    """The category phrase the model wrote for this site (in its own language)."""
    cat = _clean(str((pack.get("meta") or {}).get("category") or ""))
    return cat if _ok_category(cat, brand) else ""


def _ok_hook(hook: str, allow_deposit: bool) -> bool:
    h = _clean(hook).strip(" .,;:—-")
    if not (4 <= len(h) <= 44):
        return False
    if len(re.findall(r"[^\W\d_]", h)) < 4:      # "24/5" is a stat, not a hook
        return False
    if h[0] in "≤≥~<>≈±+":                       # "≤ 1 hour" reads badly after a comma
        return False
    if _has(h, CLICHE) or _has(h, RISK) or _placeholder_hit(h):
        return False
    if not allow_deposit and DEPOSIT_RE.search(h):
        return False
    return True


def _hook(text: str) -> str:
    """Title-sized hook: first clause, no trailing period, lowercase unless an acronym."""
    t = _clean(text).rstrip(".")
    t = re.split(r"[;:]| — ", t)[0].strip(" ✓✔•→·—–-,")
    if len(t) > 44:
        t = t[:44].rsplit(" ", 1)[0]
    return _lower_first(t)


STOP_TAIL = {"for", "with", "in", "on", "and", "to", "of", "a", "the", "at", "from",
             "by", "that", "your", "our", "is", "are", "as"}


WEAK_HOOK = ("begin", "start ", "discover", "get ", "stay ", "ways to", "click",
             "here", "learn more", "read more", "open an account", "sign up", "contact us")


def _hook_score(fact: str) -> int:
    """Which of the page's own strings deserves the tail of a title."""
    low = fact.lower()
    score = 0
    if re.search(r"\d", fact):
        score += 3
    if any(w in low for w in ("free", "no hidden", "no monthly", "no fee", "no cost",
                              "clear", "plain", "without", "instant", "same day", "step")):
        score += 2
    if 10 <= len(fact) <= 38:
        score += 1
    if any(w in low for w in WEAK_HOOK):
        score -= 3
    if any(ch in fact for ch in "✓✔•→·"):
        score -= 4
    return score


def _short_hook(text: str, limit: int = 30) -> str:
    """A long claim cut to title size: 'clearer instruments for today's markets' -> 'clearer instruments'."""
    words: list[str] = []
    for w in _clean(text).split():
        if len(" ".join(words + [w])) > limit:
            break
        words.append(w)
    while words and words[-1].lower().strip(".,;:") in STOP_TAIL:
        words.pop()
    out = " ".join(words).strip(" ,.;:—-")
    return out if len(out) >= 8 else ""


def _rank_facts(facts) -> list[str]:
    """Numbered and fear-removing facts first — they do the clicking."""
    def key(f: str) -> tuple:
        low = f.lower()
        return (0 if re.search(r"\d", f) else 1,
                0 if any(t in low for t in ("free", "demo", "no hidden", "no monthly",
                                            "commits", "no charge", "no fee")) else 1,
                len(f))
    return sorted({_clean(f) for f in facts if _clean(f)}, key=key)


def _facts_phrase(facts, limit: int = 56) -> str:
    out = ""
    for f in facts:
        f = _clean(f).rstrip(".")
        if not f:
            continue
        cand = f"{out}, {_lower_first(f)}" if out else _lower_first(f)
        if len(cand) > limit:
            continue
        out = cand
    return out


def _sentence(text: str) -> str:
    t = _clean(text)
    if not t:
        return ""
    if not t.endswith((".", "!", "?", "。", "！", "？", "…")):
        t += "."
    return _upper_first(t)


def _fit_desc(parts: list[str], limit: int = DESC_MAX) -> str:
    parts = [p for p in parts if p]
    while parts:
        text = " ".join(parts)
        text = re.sub(r"\s+([.,;:])", r"\1", text)
        text = re.sub(r"\.\s*\.", ".", text)
        if _width(text) <= limit:
            return text
        parts.pop()
    return ""


def _pad_desc(text: str, extra: list[str], minimum: int = DESC_MIN) -> str:
    for addon in extra:
        if _width(text) >= minimum:
            break
        addon = _sentence(addon)
        if not addon or addon.lower() in text.lower():
            continue
        cand = f"{text} {addon}"
        if _width(cand) <= DESC_MAX:
            text = cand
    return text


# --- scoring ----------------------------------------------------------------
def score_title(title: str, brand: str, category: str = "", geo: str = "") -> tuple[int, int, list[str]]:
    t = _clean(title)
    low = t.lower()
    b = _clean(brand).lower()
    seo, ctr, notes = 40, 45, []
    if b and low.startswith(b):
        seo += 25
    else:
        seo -= 35
        notes.append("title не починається з назви воронки")
    if category and category.lower() in low:
        seo += 20
        pos = low.find(category.lower())
        if pos <= len(b) + 4:
            seo += 5
            notes.append("категорія одразу після бренду")
    elif category:
        seo -= 12
        notes.append("немає категорії-ключа")
    if re.search(r"\d", t):
        ctr += 12
        notes.append("+ цифра")
    if geo and geo.lower() in low:
        seo += 4
    if category:
        tail = t.lower().split(category.lower(), 1)[-1].strip(" ,:—–-")
        if len(tail) >= 6:                      # brand + category + something to click
            ctr += 8
            notes.append("+ гачок у хвості")
    n = _width(t)
    if n < 25:
        seo -= 6
        notes.append(f"title короткий ({n}) — SERP-простір не використано")
    elif n <= TITLE_MAX:
        seo += 8
    elif n <= TITLE_HARD:
        seo += 3
    else:
        seo -= 18
        notes.append(f"title задовгий ({n} > {TITLE_HARD})")
    if re.search(r"[—–:|,]", t):
        ctr += 6
    if _has(t, CLICHE):
        seo -= 12
        ctr -= 22
        notes.append(f"кліше: «{_has(t, CLICHE).strip()}»")
    if _has(t, RISK):
        seo -= 20
        ctr -= 20
        notes.append(f"комплаєнс-ризик: «{_has(t, RISK)}»")
    if b and low.count(b) > 1:
        seo -= 8
        notes.append("бренд двічі")
    if _placeholder_hit(t):
        seo -= 40
        notes.append("плейсхолдер")
    return max(0, min(100, seo)), max(0, min(100, ctr)), notes


def score_desc(desc: str, title: str, brand: str, category: str = "") -> tuple[int, int, list[str]]:
    d = _clean(desc)
    low = d.lower()
    seo, ctr, notes = 45, 45, []
    n = _width(d)
    if DESC_MIN <= n <= DESC_MAX:
        seo += 18
        ctr += 8
    elif 100 <= n < DESC_MIN:
        seo += 6
        notes.append(f"description короткий ({n})")
    elif DESC_MAX < n <= 175:
        seo += 2
        notes.append(f"description довгий ({n})")
    else:
        seo -= 15
        notes.append(f"description поза межами ({n})")
    if re.search(r"\d", d):
        ctr += 10
        notes.append("+ цифра")
    if brand and brand.lower() in low:
        seo += 6
    if category and category.lower() in low:
        seo += 8
    if _has(d, TRANSPARENCY):
        ctr += 8
        notes.append("+ прозорість")
    if _has(d, CLICHE):
        seo -= 10
        ctr -= 18
        notes.append(f"кліше: «{_has(d, CLICHE).strip()}»")
    if _has(d, RISK):
        seo -= 20
        ctr -= 20
        notes.append(f"комплаєнс-ризик: «{_has(d, RISK)}»")
    if _placeholder_hit(d):
        seo -= 40
        notes.append("плейсхолдер")
    if title and _key(d).startswith(_key(title)[:40]):
        ctr -= 10
        notes.append("description повторює title")
    elif title and len(d) > 24 and d[:24].lower() in title.lower():
        ctr -= 6
        notes.append("description починається тим самим, що й title")
    if d and not d.endswith((".", "!", "?", "。", "！", "？")):
        notes.append("немає фінальної крапки")
        seo -= 3
    return max(0, min(100, seo)), max(0, min(100, ctr)), notes


# --- hero headline (H1) ------------------------------------------------------
# The model writes it; these words are what makes it read like a claim instead of a slogan.
WEAK_H1 = ("access", "solution", "solutions", "platform", "method", "tools", "noise",
           "experience", "ecosystem", "journey", "welcome", "market access", "guided",
           "платформ", "рішен", "метод", "інструмент", "доступ")
ACTION = ("see", "check", "open", "start", "compare", "track", "keep", "get", "choose",
          "build", "place", "watch", "read", "look", "find", "set", "побач", "відкрий",
          "почни", "порівняй", "перевір", "дивись", "тримай", "обери")
# Words that keep a punchy H1 on-topic. Without at least one of them the headline is
# pure emotion ("Start today / right now") and stops helping relevance.
TOPIC_SYNONYMS = {
    "market", "markets", "price", "prices", "quote", "quotes", "spread", "fee", "fees",
    "cost", "costs", "trade", "trades", "trading", "chart", "charts", "order", "orders",
    "account", "accounts", "data", "instrument", "instruments", "alert", "alerts",
    "deposit", "withdrawal", "portfolio", "invest", "investing", "risk",
    "ринок", "ціна", "ціни", "спред", "комісія", "угода", "графік", "рахунок",
    "дані", "інструмент", "депозит", "виведення", "портфель", "ризик",
}


def _topic_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[^\W\d_]{4,}", (text or "").lower())}


def _on_topic(both: str, topic: str) -> bool:
    words = _topic_words(both)
    return bool(words & (_topic_words(topic) | TOPIC_SYNONYMS))


def score_h1(rest: str, accent: str, brand: str = "",
             topic: str = "") -> tuple[int, list[str]]:
    r, a = _clean(rest), _clean(accent)
    both = f"{r} {a}"
    score, notes = 50, []
    if brand and brand.lower() in both.lower():
        score -= 40
        notes.append("бренд у H1 повторюється (він уже в .brand-line)")
    wr, wa = len(r.split()), len(a.split())
    if 3 <= wr <= 7:
        score += 10
    elif wr > 9:
        score -= 10
        notes.append(f"перший рядок задовгий ({wr} слів)")
    if 2 <= wa <= 4:
        score += 10
    elif wa > 5:
        score -= 10
        notes.append(f"акцент задовгий ({wa} слів)")
    if _width(r) > 52:
        score -= 8
        notes.append("перший рядок не влізе в мобільний hero")
    if _width(a) > 26:
        score -= 8
        notes.append("акцент довший за 26 одиниць")
    if re.search(r"\d", both):
        score += 8
        notes.append("+ цифра")
    if _has(both.lower(), WEAK_H1):
        score -= 12
        notes.append(f"абстракція «{_has(both.lower(), WEAK_H1)}»")
    if _has(both.lower(), ACTION):
        score += 8
        notes.append("+ дієслово")
    if topic:
        if _on_topic(both, topic):
            score += 6
            notes.append("+ тематичне слово (релевантність збережена)")
        else:
            score -= 10
            notes.append("H1 без тематичного слова — лише емоція, SEO-сигнал слабшає")
    if _has(both, CLICHE):
        score -= 15
        notes.append("кліше")
    if _has(both, RISK):
        score -= 30
        notes.append("комплаєнс-ризик")
    return max(0, min(100, score)), notes


def lint_h1(rest: str, accent: str, brand: str = "",
            topic: str = "") -> list[tuple[str, str]]:
    r, a = _clean(rest), _clean(accent)
    both = f"{r} {a}"
    out: list[tuple[str, str]] = []
    if not r or not a:
        out.append(("ERR", "H1 без другої або акцентної лінії"))
    if brand and brand.lower() in both.lower():
        out.append(("ERR", "H1 повторює бренд — він уже в .brand-line"))
    if len(a.split()) > 5:
        out.append(("WARN", f"акцент {len(a.split())} слів (краще 2–4)"))
    if _has(both, CLICHE) or _has(both, RISK):
        out.append(("WARN", "H1 з кліше або комплаєнс-словом"))
    if _placeholder_hit(both):
        out.append(("ERR", "плейсхолдер у H1"))
    if topic and r and a and not _on_topic(both, topic):
        out.append(("WARN", "H1 без тематичного слова — емоція без релевантності"))
    return out


# --- generation -------------------------------------------------------------
def variants(brand: str, lang: str = "en", *, categories=None, facts=(), sentences=(),
             cta: str = "", geo: str = "", allow_deposit: bool = False,
             extra_hooks=(), n: int = 6) -> list[Variant]:
    """Ranked title/description pairs. Same inputs -> same output (no randomness)."""
    brand = _clean(brand)
    lang = (lang or "en").lower()[:2]
    if not brand:
        return []
    cats = [_clean(c) for c in (categories or category_bank(lang)) if _clean(c)]
    facts = _rank_facts([_clean(f).strip(" ✓✔•→·—–-") for f in facts])
    # UI labels ("begin here", checkmark items) score below a real claim and stay out of
    # the description unless the page has nothing better to offer.
    strong = ([f for f in facts if _hook_score(f) >= 2]
              or [f for f in facts if _hook_score(f) >= 1] or facts)
    hooks = []
    for h in list(extra_hooks) + list(strong):
        if _ok_hook(h, allow_deposit):
            hk = _hook(h)
            if hk and hk not in hooks:
                hooks.append(hk)
    hooks.sort(key=lambda h: -_hook_score(h))
    hooks = hooks[:5]
    # a claim that does not fit a 60-char title still yields a usable short hook
    mixed: list[str] = []
    for hk in hooks:
        mixed.append(hk)
        short = _short_hook(hk)
        if short and short not in mixed:
            mixed.append(short)
    hooks = mixed[:6]
    sents = [_clean(s) for s in sentences if 45 <= len(_clean(s)) <= 230
             and not _has(s, RISK) and not _placeholder_hit(s)]
    cta = _clean(cta).rstrip(".")
    facts_phrase = _facts_phrase([f for f in strong if _ok_hook(f, allow_deposit)])

    # (title, category it uses): each candidate is scored against ITS OWN category,
    # otherwise only the first phrase in the bank can ever earn the category bonus.
    pairs: list[tuple[str, str]] = []
    for cat in cats[:3]:
        for hk in hooks[:4]:
            pairs.append((f"{brand} — {cat}, {hk}", cat))
            pairs.append((f"{brand} — {cat}: {hk}", cat))
        pairs.append((f"{brand} — {cat}", cat))
    for hk in hooks[:3]:
        pairs.append((f"{brand} — {hk}", cats[0] if cats else ""))
    if geo and cats:
        pairs.append((f"{brand} — {cats[0]} {geo}", cats[0]))

    # A lead that is already 140 characters leaves no room for facts, so both the full
    # sentence and its first clause are offered to the description assembler.
    leads: list[str] = []
    for s in sents[:2]:
        for piece in (s, re.split(r"(?<=[.!?])\s+", s)[0]):
            cand = _sentence(piece)
            if cand and cand not in leads:
                leads.append(cand)
    tail = _sentence(facts_phrase) if facts_phrase else ""
    cta_s = _sentence(cta)
    s1 = _sentence(sents[1]) if len(sents) > 1 else ""
    descs: list[str] = []
    for lead in leads:
        for combo in ([lead, tail, cta_s], [lead, tail], [tail, lead],
                      [lead, cta_s], [lead]):
            text = _fit_desc(combo)
            if text and text not in descs:
                descs.append(text)
    if tail and cta_s:
        extra = _fit_desc([tail, cta_s])
        if extra and extra not in descs:
            descs.append(extra)
    reserve = [s1, facts_phrase, cta]
    descs = [_pad_desc(d, reserve) for d in descs if d]
    descs = list(dict.fromkeys(descs))

    out: list[Variant] = []
    seen: set[str] = set()
    for raw, cat in pairs:
        title = _clean(raw).rstrip(",:").strip()
        if not title.lower().startswith(brand.lower()):
            continue
        if _width(title) > TITLE_HARD or _key(title) in seen:
            continue
        if _has(title, RISK) or _placeholder_hit(title):
            continue
        cat0 = cat
        seo_t, ctr_t, notes_t = score_title(title, brand, cat0, geo)
        desc, seo_d, ctr_d, notes_d = "", -1, -1, []
        for cand in descs:
            s_, c_, n_ = score_desc(cand, title, brand, cat0)
            if s_ * 0.6 + c_ * 0.4 > seo_d * 0.6 + ctr_d * 0.4:
                desc, seo_d, ctr_d, notes_d = cand, s_, c_, n_
        seen.add(_key(title))
        if desc:
            seo = round((seo_t + seo_d) / 2)
            ctr = round((ctr_t + ctr_d) / 2)
        else:
            seo, ctr = seo_t, ctr_t
        out.append(Variant(title=title, description=desc, seo=seo, ctr=ctr,
                           notes=list(dict.fromkeys(notes_t + notes_d)),
                           category=cat0))
    # ties fall back to the bank order, i.e. the operator's preference: the first
    # category in CATEGORY_BANK is the default for the funnel, not a hardcoded word.
    out.sort(key=lambda v: (-v.score,
                            cats.index(v.category) if v.category in cats else len(cats),
                            len(v.title)))
    return out[:max(1, n)]


def best(brand: str, lang: str = "en", **kw) -> Variant | None:
    got = variants(brand, lang, n=1, **kw)
    return got[0] if got else None


# --- lint (shared by both audits) -------------------------------------------
def lint(title: str, description: str, brand: str, *, lang: str = "en",
         category: str = "", others: tuple[str, ...] = (),
         home: bool = True) -> list[tuple[str, str]]:
    """Return [('ERR'|'WARN', message)]. ERR blocks a build, WARN is a nudge.

    `home=False` for inner/legal pages: their title names the page topic, so the
    category phrase and a digit are not required there.
    """
    t = _clean(title)
    d = _clean(description)
    out: list[tuple[str, str]] = []
    if _placeholder_hit(t) or _placeholder_hit(d):
        out.append(("ERR", "плейсхолдер у meta"))
    if t and brand and not t.lower().startswith(_clean(brand).lower()):
        out.append(("ERR", "title не починається з назви воронки"))
    tn, dn = _width(t), _width(d)
    if t and tn < 25:
        out.append(("WARN", f"title короткий ({tn}) — SERP-простір не використано"))
    if tn > TITLE_HARD:
        out.append(("WARN", f"title {tn} > {TITLE_HARD}"))
    elif tn > TITLE_MAX:
        out.append(("WARN", f"title {tn} > {TITLE_MAX} (обріжеться у видачі)"))
    if d and dn > DESC_MAX + 10:
        out.append(("WARN", f"description {dn} > {DESC_MAX}"))
    elif d and dn < 95:
        out.append(("WARN", f"description короткий ({dn})"))
    for name, text in (("title", t), ("description", d)):
        if _has(text, RISK):
            out.append(("ERR", f"{name}: комплаєнс-ризик «{_has(text, RISK)}»"))
        if _has(text, CLICHE):
            out.append(("WARN", f"{name}: кліше «{_has(text, CLICHE).strip()}»"))
    if home:
        cats = [category] if category else category_bank(lang)
        if t and not cats:
            out.append(("WARN", "немає категорії-ключа: мова без банку — задайте meta.category"))
        elif cats and t and not any(c.lower() in t.lower() for c in cats):
            out.append(("WARN", "title без категорії-ключа"))
        if t and not re.search(r"\d", t) and not re.search(r"\d", d):
            out.append(("WARN", "ні цифри в title, ні в description"))
    if t and t.lower() in {o.lower() for o in others if o}:
        out.append(("ERR", "дубль title з іншою сторінкою"))
    return out


# --- content-pack adapter ---------------------------------------------------
def sentences_from_pack(pack: dict) -> list[str]:
    hero = pack.get("hero") or {}
    bands = pack.get("bands") or {}
    intros = (pack.get("sections") or {}).get("intro") or {}
    out = []
    for val in (hero.get("lead"), intros.get("lead"), bands.get("mid_lead")):
        val = _clean(val)
        if 45 <= len(val) <= 230:
            out.append(val)
    return out


def facts_from_pack(pack: dict, *, allow_deposit: bool = False) -> list[str]:
    hero = pack.get("hero") or {}
    bands = pack.get("bands") or {}
    facts: list[str] = []
    for c in ((hero.get("proof") or {}).get("claims") or []):
        facts.append(_clean(c))
    # side_stats are already the hook-sized facts ("3 steps", "≤ 1 hour", "24/5");
    # side_labels are captions ("how long registration takes") and would read as noise.
    for v in bands.get("side_stats") or []:
        facts.append(_clean(v))
    tl = _clean(hero.get("trust_label"))
    if tl and not re.search(r"\d", tl):
        facts.append(tl)
    if not allow_deposit:
        facts = [f for f in facts if not DEPOSIT_RE.search(f) and not re.search(r"[€£$]\s?\d", f)]
    return facts


def pack_variants(pack: dict, brand: str, lang: str = "en", *, n: int = 6,
                  categories=None, extra_hooks=()) -> list[Variant]:
    meta = pack.get("meta") or {}
    hint = detect_category(str(meta.get("title_home") or ""), brand)
    spec = pack_category(pack, brand)
    # 1) the phrase the model wrote for THIS language (works for any of the 37),
    # 2) the tested bank for the 13 covered languages, 3) the existing title's wording
    cats = list(categories or ([spec] if spec else []) or category_bank(lang)
                or ([hint] if hint else []))
    return variants(
        brand, lang,
        categories=cats,
        facts=facts_from_pack(pack),
        sentences=sentences_from_pack(pack),
        cta=str((pack.get("hero") or {}).get("cta_primary") or ""),
        extra_hooks=extra_hooks, n=n,
    )


def apply_to_pack(pack: dict, variant: Variant) -> dict:
    meta = pack.setdefault("meta", {})
    old = {k: meta.get(k, "") for k in ("title_home", "description", "og_description",
                                        "category")}
    meta["title_home"] = variant.title
    meta["description"] = variant.description
    if variant.description:
        meta["og_description"] = variant.description
    if variant.category:
        meta["category"] = variant.category
    hero = pack.setdefault("hero", {})
    if variant.h1_rest and variant.h1_accent and variant.h1_score:
        old["h1_rest"] = hero.get("h1_rest", "")
        old["h1_accent"] = hero.get("h1_accent", "")
        hero["h1_rest"] = variant.h1_rest
        hero["h1_accent"] = variant.h1_accent
    return old


# --- optional LLM pass ------------------------------------------------------
def llm_prompt(brand: str, lang: str, categories, facts, sentences, cta: str, n: int) -> list[dict]:
    rules = (
        "You write the hero headline (H1), the SEO title and the meta description for a "
        "lead-gen landing page. Nothing may be invented that the payload does not support.\n"
        "H1 rules:\n"
        "- The brand is already printed on its own line above the H1: h1_rest and h1_accent "
        "MUST NOT contain the brand.\n"
        "- h1_rest: 3-7 words, a claim with a verb (see, open, compare, keep) and, when true, "
        "a number. No abstractions: access, platform, solution, method, tools, noise.\n"
        "- h1_accent: 2-4 words that close the sentence concretely (a place, a time, a condition).\n"
        "- Useful shapes: <verb> <object> <condition>; <number> <noun> <benefit>; "
        "<object> <where it lives>.\n"
        "- Keep at least one concrete market word in the H1 (price, fee, spread, order, "
        "chart, account, market): a headline made only of emotion loses the page's relevance.\n"
        "Title rules:\n"
        "- MUST start with the funnel name exactly as given.\n"
        "- Right after the name put ONE category phrase from the allowed list.\n"
        "- Then a concrete hook: a number, a removed fear or a practical benefit.\n"
        f"- Title <= {TITLE_MAX} characters (hard stop {TITLE_HARD}).\n"
        f"- Description {DESC_MIN}-{DESC_MAX} characters, starts with a fact, ends with a call to action.\n"
        "Compliance:\n"
        "- Never promise returns, profit or safety; never use 'guaranteed', 'risk-free', 'best', "
        "'seamless', 'world-class'.\n"
        f"- Language: {lang}. No emojis, no markdown, no placeholders.\n"
        f"- Return JSON only: {{\"variants\":[{{\"title\":\"…\",\"description\":\"…\","
        f"\"h1_rest\":\"…\",\"h1_accent\":\"…\"}}]}} with {n} items."
    )
    payload = {
        "brand": brand, "lang": lang,
        "allowed_categories": categories or category_bank(lang),
        "facts_from_site": [f for f in facts][:12],
        "sentences_from_site": [s for s in sentences][:4],
        "cta": cta,
    }
    return [{"role": "system", "content": rules},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


def parse_llm(text: str) -> list[dict]:
    raw = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", str(text or ""), flags=re.S)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return []
    items = data.get("variants") if isinstance(data, dict) else data
    out = []
    for it in items or []:
        if isinstance(it, dict) and it.get("title") and it.get("description"):
            out.append({
                "title": _clean(it["title"]),
                "description": _clean(it["description"]),
                "h1_rest": _clean(it.get("h1_rest") or ""),
                "h1_accent": _clean(it.get("h1_accent") or ""),
            })
    return out


def with_llm(chat, brand: str, lang: str, **kw) -> list[Variant]:
    """Merge model candidates into the deterministic ranking. `chat(messages) -> str`."""
    base = variants(brand, lang, **kw)
    cats = kw.get("categories") or category_bank(lang)
    try:
        text = chat(llm_prompt(brand, lang, cats, kw.get("facts") or [],
                               kw.get("sentences") or [], kw.get("cta") or "", kw.get("n", 6)))
    except Exception:                                       # noqa: BLE001 — model is optional
        return base
    cat0 = cats[0] if cats else ""
    extra: list[Variant] = []
    for item in parse_llm(text):
        title, desc = item["title"], item["description"]
        probs = [lvl for lvl, _ in lint(title, desc, brand, lang=lang, category=cat0)
                 if lvl == "ERR"]
        if probs:
            continue
        seo_t, ctr_t, notes = score_title(title, brand, cat0)
        seo_d, ctr_d, notes_d = score_desc(desc, title, brand, cat0)
        h1r, h1a = item["h1_rest"], item["h1_accent"]
        h1s, notes_h1 = 0, []
        if h1r and h1a and not [lvl for lvl, _ in lint_h1(h1r, h1a, brand, cat0)
                                if lvl == "ERR"]:
            h1s, notes_h1 = score_h1(h1r, h1a, brand, cat0)
        extra.append(Variant(
            title=title, description=desc, seo=seo_t,
            ctr=round((ctr_t + ctr_d) / 2) if desc else ctr_t,
            notes=["модель"] + notes + notes_d + notes_h1, category=cat0,
            h1_rest=h1r if h1s else "", h1_accent=h1a if h1s else "", h1_score=h1s,
            source="model"))
    merged: dict[str, Variant] = {}
    for v in base + extra:
        k = _key(v.title)
        if k not in merged or v.rank > merged[k].rank:
            merged[k] = v
    ranked = sorted(merged.values(), key=lambda v: (-v.rank, len(v.title)))
    return ranked[:max(1, kw.get("n", 6))]


# --- CLI --------------------------------------------------------------------
def _load_pack(path: str) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _print_table(got: list[Variant]) -> None:
    for i, v in enumerate(got, 1):
        print(f"\n[{i}] {v.source:<8} rank {v.rank}  (title {v.score}: seo {v.seo}/ctr {v.ctr}"
              f"{f'; h1 {v.h1_score}' if v.h1_score else ''})  {len(v.title)}ch")
        print(f"    {v.title}")
        print(f"    {v.description}  ({len(v.description)}ch)")
        if v.h1_rest or v.h1_accent:
            print(f"    H1: {v.h1_rest}  /  {v.h1_accent}")
        if v.notes:
            print(f"    · {' · '.join(dict.fromkeys(v.notes))}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="generate brand-first, clickable titles/descriptions")
    ap.add_argument("--content", help="content pack JSON (meta/hero/bands)")
    ap.add_argument("--plan", help="plan JSON (brand, lang, geo)")
    ap.add_argument("--brand")
    ap.add_argument("--lang", default="")
    ap.add_argument("--geo", default="")
    ap.add_argument("--category", action="append", default=[],
                    help="category phrase; repeatable, replaces the language bank")
    ap.add_argument("--hook", action="append", default=[], help="extra hook phrase")
    ap.add_argument("--fact", action="append", default=[], help="extra fact for descriptions")
    ap.add_argument("--cta", default="")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--apply", type=int, default=0, metavar="N",
                    help="write variant N into the content pack")
    ap.add_argument("--check", action="store_true", help="lint the pack's current meta only")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--llm", action="store_true", help="add model candidates (needs a key)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    if not a.category and os.environ.get("META_CATEGORY", "").strip():
        a.category = [os.environ["META_CATEGORY"].strip()]

    pack = _load_pack(a.content) if a.content else {}
    plan = _load_pack(a.plan) if a.plan else {}
    params = plan.get("params") or {}
    brand = a.brand or params.get("brand") or ""
    lang = (a.lang or params.get("lang") or "en").lower()
    geo = a.geo or str(params.get("cc") or params.get("geo_short") or "")

    if not brand:
        print("✗ потрібен --brand або --plan з params.brand", file=sys.stderr)
        return 2

    meta = pack.get("meta") or {}
    if a.check:
        problems = lint(str(meta.get("title_home") or ""), str(meta.get("description") or ""),
                        brand, lang=lang, category=detect_category(str(meta.get("title_home") or ""), brand))
        for level, msg in problems:
            print(f"{level}: {msg}")
        print("ok" if not [p for p in problems if p[0] == "ERR"] else "FAIL")
        return 1 if [p for p in problems if p[0] == "ERR"] else 0

    if pack:
        got = pack_variants(pack, brand, lang, n=a.n,
                            categories=a.category or None, extra_hooks=a.hook)
    else:
        got = variants(brand, lang, categories=a.category or None,
                       facts=a.fact, sentences=[f for f in a.fact if len(f) > 60],
                       cta=a.cta, geo=geo, extra_hooks=a.hook + a.fact, n=a.n)
    if a.llm:
        def _chat(messages):
            # any transport problem must degrade to the deterministic ranking, never
            # break the build: the generator is the floor, the model is the ceiling
            try:
                sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
                import llm_content
                cfg = llm_content.load_cfg()
                key = llm_content.resolve_key(cfg)
                transport = os.environ.get("LLM_PROVIDER", "auto")
                if key and transport in ("auto", "http"):
                    return llm_content.http_chat(cfg, key, messages)[0]
                return llm_content.cli_chat(llm_content.find_cli(), cfg.get("model", ""),
                                            json.dumps(messages, ensure_ascii=False))
            except (Exception, SystemExit):     # noqa: BLE001 — model is optional
                return ""
        _spec = pack_category(pack, brand) if pack else ""
        got = with_llm(lambda m: _chat(m), brand, lang,
                       categories=(a.category or ([_spec] if _spec else None)),
                       facts=facts_from_pack(pack) if pack else a.fact,
                       sentences=sentences_from_pack(pack) if pack else [],
                       cta=a.cta or str((pack.get("hero") or {}).get("cta_primary") or ""),
                       n=a.n, extra_hooks=a.hook)

    if a.json:
        print(json.dumps([v.as_dict() for v in got], ensure_ascii=False, indent=1))
    elif not a.quiet:
        _print_table(got)

    if a.apply:
        if not pack:
            print("✗ --apply потребує --content", file=sys.stderr)
            return 2
        if not 1 <= a.apply <= len(got):
            print(f"✗ немає варіанта {a.apply} (є 1..{len(got)})", file=sys.stderr)
            return 2
        chosen = got[a.apply - 1]
        old = apply_to_pack(pack, chosen)
        pathlib.Path(a.content).write_text(json.dumps(pack, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
        print(f"· meta.title_home [{chosen.source}]: {old['title_home']!r} → {chosen.title!r}")
        print(f"· meta.description: {len(str(old['description']))}ch → {len(chosen.description)}ch")
        print(f"· meta.category: {old.get('category')!r} → {chosen.category!r}")
        if "h1_rest" in old:
            print(f"· hero.h1: {old['h1_rest']!r} / {old['h1_accent']!r} → "
                  f"{chosen.h1_rest!r} / {chosen.h1_accent!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
