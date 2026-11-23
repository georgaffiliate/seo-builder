#!/usr/bin/env python3
"""Opener harness: how the strip opens (no label / label right / a widget).

Renders 3 bodies x 7 openers in the real page context (strip -> header -> hero)
and builds a desktop and a phone gallery. Review code, not ship code.
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import build as B  # noqa: E402

BODIES = [("ad", "Рядок-леджер"), ("a", "Тейп + стати"), ("q", "Енергія, тейп")]

OPENERS = [
    ("label-left", "Напис зліва — як зараз"),
    ("none", "Без напису — дані першими"),
    ("label-end", "Напис праворуч"),
    ("clock", "Віджет: годинник"),
    ("session", "Віджет: сесія + відлік"),
    ("headline", "Віджет: заголовок дня"),
    ("spark", "Віджет: спарклайн + індекс"),
]

WIDGETS = {
    "clock": ('<span class="lb-w lb-w-clock"><b>16:20</b>'
              '<small>CET · Roma</small></span>'),
    "session": ('<span class="lb-w lb-w-live"><span class="dot"></span><b>Sessione UE</b>'
                '<small>chiusa · apre fra 14h 40m</small></span>'),
    "headline": ('<span class="lb-w lb-w-head"><span class="tag">Notizie</span>'
                 '<b>BTP: asta coperta 2,4 volte</b></span>'),
    "spark": ('<span class="lb-w lb-w-spark"><svg viewBox="0 0 54 16" aria-hidden="true">'
              '<polyline points="0,11 9,8 18,12 27,6 36,9 45,4 54,6"/></svg>'
              '<small>FTSE MIB</small><b>32 537</b><small>+1,09%</small></span>'),
}


def span_end(html: str, i: int) -> int:
    """Index just past the </span> that closes the span starting at i."""
    depth, j = 0, i
    while True:
        o = html.find("<span", j)
        c = html.find("</span>", j)
        if c < 0:
            return -1
        if 0 <= o < c:
            depth += 1
            j = o + 5
        else:
            depth -= 1
            j = c + 7
            if depth == 0:
                return j


def strip_for(body: str, opener: str) -> str:
    html = B.render(body)
    html = html.replace('<div class="blk-livebar', f'<div data-open="{opener}" class="blk-livebar', 1)
    if opener == "label-left":
        return html
    i = html.find('<span class="live">')
    end = span_end(html, i) if i >= 0 else -1
    if end < 0:
        return html
    live = html[i:end]
    rest = html[:i] + html[end:]
    if opener == "none":
        return rest
    if opener == "label-end":
        geo = rest.find('<span class="geo">')
        return rest[:geo] + live + rest[geo:]
    return html[:i] + WIDGETS[opener] + html[end:]


def part(body: str, opener: str) -> str:
    sid = f"{body}-{opener}"
    return (B.PART.replace("__ID__", sid)
                  .replace("__NAME__", f"{body} · {opener}")
                  .replace("__PALETTE__", B.PALETTE)
                  .replace("__STRIP__", strip_for(body, opener))
                  .replace("__HEADER__", B.HEADER).replace("__HERO__", B.HERO)
                  .replace("__IDJSON__", json.dumps(sid)))


PAGE = """<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Відкриття стрічки — Jandervoq</title>
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
  .picker button { border: 0; padding: 9px 14px; border-radius: 999px; cursor: pointer;
    background: rgb(255 255 255 / 0.12); color: #fff; font-weight: 600; }
  .picker button[aria-pressed="true"] { background: rgb(255 255 255 / 0.22); }
  .picker:focus-within button:focus-visible, .picker select:focus-visible { outline: 2px solid #fff; outline-offset: 2px; }
  .body-sec { max-width: 1240px; margin: 34px auto 0; padding: 0 28px; }
  .body-sec > h2 { font-size: 17px; margin: 0 0 4px; }
  .body-sec > p { margin: 0 0 6px; color: #5c5e6c; font-size: 13px; }
  .card { margin: 18px 0 0; }
  .card > header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 7px; }
  .card h3 { font-size: 14px; margin: 0; }
  .card .id { font: 600 11px/1 ui-monospace, monospace; background: #e7e3da; border-radius: 4px; padding: 4px 6px; }
  .card .h { font: 600 12px/1 ui-monospace, monospace; color: #8a4b00; background: #fbe9d2; padding: 4px 7px; border-radius: 4px; }
  .card .h.small { color: #0b6b3a; background: #dff3e6; }
  iframe { display: block; border: 0; width: 100%; max-width: 1180px; height: 860px; background: #fff;
    box-shadow: 0 1px 0 #d8d3c8, 0 12px 30px -22px #000; }
  .phones { display: flex; gap: 20px; overflow-x: auto; padding: 4px; }
  .phone { flex: none; }
  .phone iframe { width: 390px; height: 780px; }
  .hint { max-width: 1240px; margin: 24px auto 0; padding: 0 28px 48px; color: #8a8b96; font-size: 12px; }
</style></head><body>
<div class="top">
  <h1>Відкриття стрічки — три способи × чотири віджети</h1>
  <p>Корпус стрічки той самий (дані, палітра, шрифти Jandervoq); змінюється лише те, з чого вона
     починається. Кожен варіант — у реальному оточенні: стрічка → хедер → початок hero.
     Плашка — висота стрічки. Кнопка «Примружити» блюрить стрічку: так видно силует, а не слова.</p>
  <div class="legend">
    <span><b>30%</b> без напису</span><span><b>30%</b> напис праворуч</span>
    <span><b>30%</b> віджет (годинник / сесія / заголовок / спарклайн)</span>
    <span><b>10%</b> напис зліва</span>
    <span><b>усі 32 стрічки:</b> <a href="index.html">index.html</a></span>
  </div>
  <div class="picker">
    <span class="label">Відкриття</span>
    <select id="pick" aria-label="Варіант">__OPTIONS__</select>
    <button type="button" id="squint" aria-pressed="false">Примружити</button>
  </div>
</div>
__SECTIONS__
<div class="hint">Харнес: <span class="mono">preview/tops/openers_build.py</span> · телефон: <span class="mono">openers-mobile.html</span> · кожен варіант також окремою сторінкою <span class="mono">o-&lt;body&gt;-&lt;opener&gt;.html</span>.</div>
<script>
(function(){
  var pick = document.getElementById('pick');
  pick.addEventListener('change', function(){
    var el = document.getElementById('c-' + pick.value);
    if (el) el.scrollIntoView({ block: 'start' });
  });
  var squint = document.getElementById('squint'), on = false;
  squint.addEventListener('click', function(){
    on = !on;
    squint.setAttribute('aria-pressed', String(on));
    document.querySelectorAll('iframe').forEach(function(f){
      try { f.contentWindow.postMessage({ src: 'tops-squint', on: on }, '*'); } catch (e) {}
    });
  });
  addEventListener('message', function(e){
    var d = e.data || {};
    if (d.src !== 'tops' || !d.strip) return;
    document.querySelectorAll('[data-h="' + d.id + '"]').forEach(function(el){
      el.textContent = 'стрічка ' + d.strip + 'px · до hero ' + d.top + 'px' +
        (d.overflow ? ' · ГОРИЗОНТАЛЬНИЙ СКРОЛ' : '');
      el.className = 'h' + (d.strip <= 34 ? ' small' : '');
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


def main() -> None:
    for body, _ in BODIES:
        for opener, _ in OPENERS:
            (HERE / f"o-{body}-{opener}.html").write_text(part(body, opener), encoding="utf-8")

    options = '<!-- groups -->'
    sections = []
    for body, body_name in BODIES:
        cards = []
        for opener, opener_name in OPENERS:
            sid = f"{body}-{opener}"
            cards.append(
                f'<article class="card" id="c-{sid}"><header><span class="id">{sid}</span>'
                f'<h3>{opener_name}</h3><span class="h" data-h="{sid}">…</span></header>'
                f'<iframe src="o-{sid}.html" title="{sid}"></iframe></article>')
        sections.append(f'<section class="body-sec"><h2>Корпус <code>{body}</code> — {body_name}</h2>'
                        f'<p>Усі сім відкриттів на одних і тих самих даних.</p>'
                        + "\n".join(cards) + '</section>')

    opts = []
    for body, body_name in BODIES:
        opts.append(f'<optgroup label="{body} — {body_name}">')
        for opener, opener_name in OPENERS:
            opts.append(f'<option value="{body}-{opener}">{opener_name}</option>')
        opts.append('</optgroup>')

    (HERE / "openers.html").write_text(
        PAGE.replace("__OPTIONS__", "\n".join(opts)).replace("__SECTIONS__", "\n".join(sections)),
        encoding="utf-8")

    phones = []
    for opener, opener_name in OPENERS:
        sid = f"ad-{opener}"
        phones.append(f'<section class="phone"><header><span class="id">{sid}</span> <h3>{opener_name}</h3>'
                      f'<span class="h" data-h="{sid}">…</span></header>'
                      f'<iframe src="o-{sid}.html" title="{sid}" loading="lazy"></iframe></section>')
    mobile = (PAGE.replace("__OPTIONS__", "\n".join(opts))
                  .replace("__SECTIONS__", '<div class="phones">' + "\n".join(phones) + '</div>')
                  .replace("Відкриття стрічки — три способи × чотири віджети",
                           "Відкриття стрічки — телефон 390px (корпус ad)"))
    (HERE / "openers-mobile.html").write_text(mobile, encoding="utf-8")
    print(f"built {len(BODIES) * len(OPENERS)} opener pages -> {HERE}")


if __name__ == "__main__":
    main()
