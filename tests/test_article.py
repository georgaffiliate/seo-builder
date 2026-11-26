"""POST /blog/article: контент-JSON, форматні виправлення і один repair-пас.

Запуск без залежностей (stdlib):
    python3 tests/test_article.py
або pytest, якщо він є.
"""
from __future__ import annotations

import json
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

import article  # noqa: E402


def valid_article() -> dict:
    para = ("Sąskaitos išrašas parodo, kiek pinigų išėjo ir kokia tvarka. Patikrinkite datas, "
            "sumas ir tarpininko komisinius prieš darydami išvadas apie realią kainą. ")
    para2 = ("Fiksuotas mokestis dažnai slepiamas sąlygose, o valiutos keitimo marža kinta kartu "
             "su rinkos kursu, todėl dvi sąskaitos už tą pačią sumą gali skirtis. Palyginkite "
             "abu mokesčius vienoje operacijoje, o ne po vieną. ")
    body = para + para2
    return {
        "slug": "kaip-patikrinti-mokescius",
        "title": "Kaip patikrinti mokesčius už išėmimą",
        "h1": "Kaip patikrinti, kiek kainuoja išimti pinigus",
        "excerpt": ("Išėmimo mokestis slepiasi trijose vietose: fiksuota suma, valiutos keitimas "
                    "ir tarpininko komisiniai. Šis vadovas parodo, kaip juos palyginti."),
        "read_min": 6,
        "link_label": "Naudingos nuorodos",
        "takeaways": ["Patikrinkite fiksuotą mokestį", "Atskirai skaičiuokite valiutos keitimą",
                      "Palyginkite su alternatyvomis"],
        "sections": [
            {"h2": "Kur slepiasi išėmimo mokestis", "p": [body, body]},
            {"h2": "Kaip palyginti du pasiūlymus", "p": [body],
             "points": ["Fiksuota suma už pavedimą", "Valiutos keitimo marža"]},
            {"h2": "Kokius dokumentus pasitikrinti", "p": [body, body]},
            {"h2": "Ką daryti prieš išimant", "p": [body]},
            {"h2": "Kada mokestis tampa per didelis", "p": [body, body]},
        ],
        "faq": [{"q": "Kiek kainuoja išimti pinigus?", "a": body + body},
                {"q": "Kodėl suma skiriasi nuo balanso?", "a": body + body}],
        "related": [],
        "cta": {"title": "Peržiūrėkite sąlygas dar kartą",
                "text": "Palyginkite mokesčius su savo išrašu.", "btn": "Skaityti toliau"},
    }


def with_stub(answers: list[str]):
    """Підміняє провайдера чергою відповідей; повертає список надісланих messages."""
    stub = types.ModuleType("llm_content")
    calls: list[list] = []

    stub.load_cfg = lambda: {"model": "stub"}
    stub.resolve_key = lambda cfg: "key"
    stub.extract_json = json.loads

    def http_chat(cfg, key, messages, *a, **k):
        calls.append(messages)
        return answers[min(len(calls) - 1, len(answers) - 1)], "stop"

    stub.http_chat = http_chat
    sys.modules["llm_content"] = stub
    return calls


def generate(answers: list[str], req: dict | None = None) -> dict:
    calls = with_stub(answers)
    body = {"lang": "lt", "brand": "Brento"} | (req or {})
    try:
        return {"article": article.generate(body), "calls": calls}
    finally:
        sys.modules.pop("llm_content", None)


def check(cond: bool, msg: str, failures: list[str]) -> None:
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond:
        failures.append(msg)


def main() -> int:
    failures: list[str] = []

    # 1. Валідний JSON — один виклик моделі
    out = generate([json.dumps(valid_article())])
    check(len(out["calls"]) == 1 and out["article"]["slug"], "valid article needs one model call", failures)

    # 2. `p` рядком замість масиву — лікуємо без повторного виклику
    broken = valid_article()
    broken["sections"][3]["p"] = broken["sections"][3]["p"][0]
    out = generate([json.dumps(broken)])
    check(out["article"]["sections"][3]["p"] == [broken["sections"][3]["p"].strip()],
          "string p is coerced", failures)
    check(len(out["calls"]) == 1, "format slips do not cost a second call", failures)

    # 3. Змістова помилка (замало слів) — один repair-пас із переліком претензій
    thin = valid_article()
    for sec in thin["sections"]:
        sec["p"] = sec["p"][:1]
    out = generate([json.dumps(thin), json.dumps(valid_article())])
    check(len(out["calls"]) == 2, "rejected article triggers exactly one repair call", failures)
    repair_msg = out["calls"][1][-1]["content"]
    check("failed validation" in repair_msg and "body is" in repair_msg,
          "repair prompt lists the validator errors", failures)
    check(out["article"]["slug"] == "kaip-patikrinti-mokescius", "repaired article is returned", failures)

    # 4. Repair не допоміг — зрозуміла відмова, а не порожня стаття
    try:
        generate([json.dumps(thin), json.dumps(thin)])
        check(False, "second rejection raises ArticleError", failures)
    except article.ArticleError as e:
        check("article rejected" in str(e), f"second rejection raises ArticleError ({e})", failures)

    # 5. Беклінк-блок: URL з'являється в системному промпті
    sys.modules.pop("llm_content", None)
    msgs = article.build_messages({"lang": "pt", "brand": "pnaf",
                                   "links": [{"url": "https://other.site/page"}]})
    check("https://other.site/page" in msgs[0]["content"], "links reach the system prompt", failures)
    check("LINKS (mandatory" not in article.build_messages({"lang": "pt", "brand": "pnaf"})[0]["content"],
          "no links → prompt unchanged", failures)

    print()
    if failures:
        print(f"ARTICLE TESTS FAILED: {len(failures)}")
        return 1
    print("ARTICLE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
