#!/usr/bin/env python3
"""Hero harness: the five production hero fragments, side by side.

Each variant renders blocks/blk-hero-<letter>.html through assemble.R with a
real content shape, so the preview shows what a build ships. Review code, not
ship code.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import build as B  # noqa: E402

LEAD = ("Grafici puliti, avvisi di prezzo ed esecuzione in tempo reale: tutto quello "
        "che serve per decidere, in un solo posto.")
CTA = '<a class="blk-btn" href="#claim">Apri il conto <span>↗</span></a>'
LINK = '<a class="text-link" href="#come">Guarda il pannello →</a>'

# The harness renders the PRODUCTION fragments (blocks/blk-hero-*.html) with a
# real pack shape, so what you look at is exactly what assemble ships.
sys.path.insert(0, str(ROOT))
import assemble as A  # noqa: E402

PLAN = {
    "params": {"brand": "Jandervoq", "domain": "jandervoq-it.xyz", "lang": "it",
               "geo_short": "IT", "geo": "Roma"},
    "numbers": {"rating": "4,5", "users": 21480, "latency_ms": 64, "reviews": 467, "orders": 3900},
    "layout": {"variants": {"hero": "e"}},
}

C = {"hero": {
    "eyebrow": "ITALIA · ACCESSO VERIFICATO",
    "h1_rest": "riunisce azioni, crypto e materie prime in un'unica dashboard",
    "h1_accent": "senza passaggi inutili",
    "lead": LEAD,
    "secondary": "Per chi vuole un'interfaccia sobria al posto di una sala comandi rumorosa.",
    "cta_primary": "Apri il conto",
    "cta_secondary": "Guarda il pannello",
    "trust_label": "recensioni verificate",
    "device_aria": "Anteprima del pannello portafoglio con saldo, andamento e due posizioni",
    "device_bal": "€9.640,22",
    "device_delta": "↗ €318,40 (3,4%) questo mese",
    "device_note": "Illustrazione dell'interfaccia: valori del portafoglio a scopo dimostrativo",
    "device_rows": [
        {"n": "Liquidità disponibile", "s": "EUR", "v": "€5.320,60", "vv": "5320.60", "d": "+0,4%"},
        {"n": "Portafoglio misto", "s": "MIX", "v": "€4.319,62", "vv": "4319.62", "d": "+2,9%"},
    ],
    "proof": {
        "claims": ["Prelievi entro 24 ore", "Nessun costo nascosto", "Demo gratuita prima di operare"],
        "quote": "Ordino dal telefono mentre sono in giro per clienti: gli avvisi di prezzo mi hanno tolto il bisogno di guardare i grafici ogni ora.",
        "quote_by": "Roberto F. · Bergamo",
        "steps": [
            {"t": "Apri il conto", "d": "Nome, email e telefono: bastano trenta secondi."},
            {"t": "Verifica l'identità", "d": "Un documento e una prova di residenza, poi il controllo parte da solo."},
            {"t": "Prova la demo", "d": "Ordini e grafici con denaro virtuale, senza alcun vincolo."},
        ],
    },
}}

VARIANTS = [
    ("statement", "d", "Заява — тип + три обіцянки"),
    ("proof", "e", "Доказ — мокап + відгук з іменем"),
    ("steps", "f", "Кроки 01/02/03 замість метрик"),
    ("band", "g", "Смуга — компактний рядок"),
    ("review", "h", "Відгук — картка праворуч"),
    ("legacy", "c", "БУЛО — легасі `c` з тріо цифр"),
]

ORDER = [(vid, name) for vid, _letter, name in VARIANTS]


def hero_html(letter: str) -> str:
    PLAN["layout"]["variants"]["hero"] = letter
    return A.R("hero", PLAN, C)


HEROES = {vid: hero_html(letter) for vid, letter, _ in VARIANTS}

HEADER = ('<header class="blk-header" data-var="a"><a class="blk-logo" data-var="f" href="#" '
          'aria-label="Jandervoq"><span class="caps">jandervoq</span></a>'
          '<nav class="blk-nav" aria-label="Navigazione principale">'
          '<a href="#" aria-current="page">Home</a><a href="#">Chi siamo</a>'
          '<a href="#">A chi si rivolge</a><a href="#">Contatti</a></nav>'
          '<a class="blk-btn" href="#claim">Iscriviti</a>'
          '<button class="menu-toggle" aria-label="Menu" aria-expanded="false">'
          '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" '
          'stroke-width="1.75" stroke-linecap="round" aria-hidden="true">'
          '<path class="i-burger" d="M4 7h16M4 12h16M4 17h16"/>'
          '<path class="i-close" d="M6 6l12 12M18 6L6 18"/></svg></button></header>')

PAGE = """<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #f3f2ef; color: #1b1c26;
         font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
  .top { padding: 28px 28px 0; max-width: 1240px; margin-inline: auto; }
  .top h1 { font-size: 24px; margin: 0 0 6px; letter-spacing: -0.01em; }
  .top p { margin: 0; color: #5c5e6c; max-width: 74ch; }
  .legend { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 12px; font-size: 13px; color: #5c5e6c; }
  .legend b { color: #1b1c26; }
  .picker { position: sticky; top: 0; z-index: 5; display: flex; gap: 10px; align-items: center;
    flex-wrap: wrap; margin: 16px 0 0; padding: 10px; border-radius: 14px;
    background: rgb(20 20 20 / 0.94); box-shadow: inset 0 0 0 1px rgb(255 255 255 / 0.1);
    color: #fff; font: 13px/1 system-ui, -apple-system, "Segoe UI", sans-serif; }
  .picker .label { color: rgb(255 255 255 / 0.45); font-size: 11px; }
  .picker select { appearance: none; max-width: 100%; padding: 9px 34px 9px 14px; border: 0;
    border-radius: 999px; background: rgb(255 255 255 / 0.12); color: #fff;
    font: 600 13px/1 system-ui, sans-serif; cursor: pointer; }
  .picker option, .picker optgroup { background: #141414; color: #fff; }
  .picker a { color: rgb(255 255 255 / 0.75); font-size: 12px; margin-left: auto; padding-right: 6px; }
  .card { max-width: 1240px; margin: 26px auto; padding: 0 28px; }
  .card > header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
  .card h2 { font-size: 15px; margin: 0; }
  .card .id { font: 600 11px/1 ui-monospace, monospace; background: #e7e3da; border-radius: 4px; padding: 4px 6px; }
  .card .h { font: 600 12px/1 ui-monospace, monospace; color: #8a4b00; background: #fbe9d2; padding: 4px 7px; border-radius: 4px; }
  .card .h.small { color: #0b6b3a; background: #dff3e6; }
  .card .h.big { color: #a41818; background: #fadcdc; }
  iframe { display: block; border: 0; width: 100%; max-width: 1180px; height: 820px; background: #fff;
    box-shadow: 0 1px 0 #d8d3c8, 0 12px 30px -22px #000; }
  .phones { display: flex; gap: 20px; overflow-x: auto; padding: 4px; }
  .phone { flex: none; }
  .phone iframe { width: 390px; height: 760px; }
  .hint { max-width: 1240px; margin: 20px auto 0; padding: 0 28px 48px; color: #8a8b96; font-size: 12px; }
</style></head><body>
<div class="top">
  <h1>__TITLE__</h1>
  <p>__LEAD__</p>
  <div class="legend">__LEGEND__</div>
  <div class="picker">
    <span class="label">Hero</span>
    <select id="pick" aria-label="Варіант">__OPTIONS__</select>
    <a href="__LINK_HREF__">__LINK_TEXT__</a>
  </div>
</div>
__SECTIONS__
<div class="hint">Харнес: <span class="mono">preview/tops/heroes_build.py</span> · CSS: <span class="mono">heroes.css</span> · згенеровані сторінки в git не йдуть.</div>
<script>
(function(){
  var pick = document.getElementById('pick');
  pick.addEventListener('change', function(){
    var el = document.getElementById('c-' + pick.value);
    if (el) el.scrollIntoView({ block: 'start' });
  });
  addEventListener('message', function(e){
    var d = e.data || {};
    if (d.src !== 'tops' || !d.hero) return;
    document.querySelectorAll('[data-h="' + d.id + '"]').forEach(function(el){
      el.textContent = 'hero ' + d.hero + 'px · до hero ' + d.top + 'px' +
        (d.overflow ? ' · ГОРИЗОНТАЛЬНИЙ СКРОЛ' : '');
      el.className = 'h' + (d.hero <= 420 ? ' small' : '');
    });
  });
  addEventListener('load', function(){
    document.querySelectorAll('iframe').forEach(function(f){
      try { f.contentWindow.postMessage({ src: 'tops-ping' }, '*'); } catch (e) {}
    });
  });
})();
</script>
</body></html>"""


def part(vid: str) -> str:
    return (B.PART.replace("__ID__", vid).replace("__NAME__", f"hero {vid}")
                  .replace("__PALETTE__", B.PALETTE)
                  .replace("__STRIP__", B.render("ad"))
                  .replace("__HEADER__", HEADER)
                  .replace("__HERO__", HEROES[vid])
                  .replace("__IDJSON__", '"%s"' % vid))


def main() -> None:
    for vid, _ in ORDER:
        (HERE / f"hero-{vid}.html").write_text(part(vid), encoding="utf-8")

    options = "\n".join(f'<option value="{vid}">{name}</option>' for vid, name in ORDER)
    cards = "\n".join(
        f'<article class="card" id="c-{vid}"><header><span class="id">{vid}</span>'
        f'<h2>{name}</h2><span class="h" data-h="{vid}">…</span></header>'
        f'<iframe src="hero-{vid}.html" title="{vid}"></iframe></article>'
        for vid, name in ORDER)

    (HERE / "heroes.html").write_text(
        PAGE.replace("__TITLE__", "Hero — п’ять композицій без тріо цифр")
            .replace("__LEAD__", "Одна палітра, один продукт. Змінена композиція і тип доказу: обіцянки, відгук, кроки — "
                                 "замість трьох маркетингових цифр, які стояли в кожному hero. "
                                 "Кожен варіант — у контексті стрічка → хедер → hero.")
            .replace("__LEGEND__",
                     "<span><b>вісь:</b> композиція (better-layout)</span>"
                     "<span><b>порядок DOM = візуальний порядок</b>, без CSS-перестановок</span>"
                     "<span><b>жодного разу</b> — тріо «4,5 / 21.480 / 64 ms»</span>")
            .replace("__OPTIONS__", options).replace("__SECTIONS__", cards)
            .replace("__LINK_HREF__", "heroes-mobile.html").replace("__LINK_TEXT__", "Телефон →"),
        encoding="utf-8")

    phones = "\n".join(
        f'<section class="phone"><header><span class="id">{vid}</span> <h2>{name}</h2>'
        f'<span class="h" data-h="{vid}">…</span></header>'
        f'<iframe src="hero-{vid}.html" title="{vid}" loading="lazy"></iframe></section>'
        for vid, name in ORDER)
    (HERE / "heroes-mobile.html").write_text(
        PAGE.replace("__TITLE__", "Hero — телефон 390px")
            .replace("__LEAD__", "Ті самі п’ять композицій на 390px: перевірка, що нічого не ріжеться, "
                                 "кнопка не висить над краєм і цифри не лопаються.")
            .replace("__LEGEND__", "<span><b>стало</b></span>")
            .replace("__OPTIONS__", options)
            .replace("__SECTIONS__", '<div class="phones">' + phones + "</div>")
            .replace("__LINK_HREF__", "heroes.html").replace("__LINK_TEXT__", "Десктоп →"),
        encoding="utf-8")
    print(f"built {len(ORDER)} heroes -> {HERE}")


if __name__ == "__main__":
    main()
