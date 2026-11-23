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
from blog_assemble import validate_blog

MAX_TOKENS = 16000


def die(msg: str, code: int = 1):
    print(f"✗ {msg}")
    sys.exit(code)


def brief(plan: dict) -> dict:
    blog = plan["blog"]
    topics = blog.get("topics") or []
    lang = plan["params"].get("lang", "en")
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
        "topics": topics,
        "shape": {
            "hub": {"eyebrow": "section label, e.g. Guides",
                    "title": "section heading on the home page",
                    "lead": "one sentence, 80..160 chars",
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
                "title": "page title phrase without the brand, 18..72 chars",
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
            "Each article: 3..7 sections, 2..4 paragraphs per section, 380+ words of body copy; "
            "at least one section carries 2..6 bullets.",
            "Vary openings, examples and section angles between articles. Never reuse a paragraph.",
            "FAQ answers are 2+ full sentences; they will be emitted as visible <details> cards and "
            "FAQPage JSON-LD.",
            "Related must point to other slugs in this same pack.",
            "Write in the site language, not English. No English boilerplate.",
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
        arts.append({
            "topic": t["id"],
            "slug": slugs[i],
            "title": T["title"].format(topic=topic, brand=brand),
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
        try:
            pack = L.extract_json(raw)
        except Exception as e:
            hint = " (output truncated — raise max_tokens)" if finish == "length" else ""
            print(f"! blog JSON invalid{hint}: {e}; head: {raw[:140]}")
            return None, messages
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
            if isinstance(pack, dict):
                errs = validate_blog(plan, pack)
                if errs:
                    print(f"· repair pass ({len(errs)} issues)")
                    if transport == "http":
                        messages += [
                            {"role": "assistant", "content": json.dumps(pack, ensure_ascii=False)},
                            {"role": "user", "content": "Fix these errors, keep all other values, return "
                                                        "ONLY the corrected JSON object: " + "; ".join(errs[:14])},
                        ]
                        raw, _ = L.http_pack(dict(cfg, max_tokens=min(int(cfg.get("max_tokens") or MAX_TOKENS),
                                                                     MAX_TOKENS)), where, messages)
                        try:
                            pack = L.extract_json(raw)
                        except Exception as e:
                            print(f"! repair unparsable: {e}")
                    else:
                        L.cli_chat(where, cfg["model"],
                                   f"Fix content/{dom}-blog.json. Errors: " + "; ".join(errs[:14]) +
                                   ". Keep the schema and language. Rewrite the whole file.")
                        try:
                            pack = json.loads(out.read_text(encoding="utf-8"))
                        except Exception:
                            pack = None
                    if isinstance(pack, dict):
                        errs = validate_blog(plan, pack)
                        if errs:
                            print("! blog pack still invalid: " + "; ".join(errs[:6]))
            elif pack is not None:
                print("! model did not return a JSON object")

    fell_back = False
    invalid_pack = None
    if not isinstance(pack, dict) or validate_blog(plan, pack):
        if isinstance(pack, dict):
            invalid_pack = pack
        if a.strict and not a.offline:
            die("blog pack invalid (strict mode)")
        if not a.offline:
            print("! falling back to the deterministic offline pack (replace it before shipping)")
            fell_back = True
        pack = offline_pack(plan)
        errs = validate_blog(plan, pack)
        if errs:
            die("offline blog pack failed its own gate: " + "; ".join(errs[:8]))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    if invalid_pack is not None:
        bad = out.with_suffix(".invalid.json")
        bad.write_text(json.dumps(invalid_pack, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"· rejected model pack saved for review: {bad.relative_to(ROOT)}")
    words = sum(len(re.findall(r"\w+", json.dumps(ar, ensure_ascii=False)))
                for ar in pack["articles"])
    print(f"BLOG CONTENT OK -> {out.relative_to(ROOT)} "
          f"({len(pack['articles'])} articles, {words} words, style {plan['blog'].get('style')})")
    if fell_back:
        print("✗ the model did not produce a valid blog pack — the offline placeholder is on disk; "
              "fix the provider or rerun with --offline if this is a test build")
        sys.exit(2)


# ------------------------------------------------------------------ offline bank
_OFFLINE = {
    "en": {
        "hub": {"eyebrow": "Guides", "title": "Practical guides", "lead": "Short, factual notes on costs, risk and the everyday mechanics of the platform.",
                "toc_label": "Contents", "takeaways_label": "Key points", "related_title": "Read next",
                "min_read_label": "min", "faq_label": "Frequently asked questions",
                "facts_sections_label": "sections", "facts_words_label": "words"},
        "title": "A practical guide to {topic}",
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
                "toc_label": "Indice", "takeaways_label": "Punti chiave", "related_title": "Leggi anche",
                "min_read_label": "min", "faq_label": "Domande frequenti",
                "facts_sections_label": "sezioni", "facts_words_label": "parole"},
        "title": "Guida pratica a {topic}",
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
