#!/usr/bin/env python3
"""Top-strip variant harness.

Renders every blk-livebar-* fragment into a standalone part page (real header and
hero head below it) and builds two galleries: desktop (1180) and phone (390).

Not ship code: this folder is a review harness only.
"""
import json
import random
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import gen_plan as g  # noqa: E402

ORDER = ["n", "t", "m", "w", "u", "x", "a", "b", "c", "d", "e", "f", "g", "h",
         "i", "j", "k", "l", "o", "p", "q", "r", "s", "v", "y", "z", "aa", "ab",
         "ac", "ad", "ae", "af"]

NAMES = {
    "a": "Тейп + три стати", "b": "FX тейп", "c": "Крипто тейп", "d": "Індекси",
    "e": "Сировина", "f": "Новини", "g": "Сесії", "h": "Сентимент",
    "i": "Система", "j": "Центрований тейп", "k": "Леджер BTC/DAX",
    "l": "FX EUR", "m": "Облігації (рядки)", "n": "Метри з барами — ПОТОЧНА",
    "o": "Календар", "p": "Movers", "q": "Енергія", "r": "Метали",
    "s": "Альткоїни", "t": "Борд 3×2", "u": "Годинники", "v": "Звіти",
    "w": "Історія", "x": "Волатильність", "y": "Відгуки", "z": "Спарклайни",
    "aa": "Флеш-тейп", "ab": "Volume + стрілки", "ac": "Статичні чіпи",
    "ad": "Рядок-леджер (новий)", "ae": "Лінійка 4 цифр (новий)",
    "af": "Акорд-край (новий)",
}

# exact numbers the live jandervoq site shows, so before/after is honest
LIVE_N = {
    "LB_LIVE": "MACRO", "GEO_SHORT": "IT",
    "LB1S": "Tasso BCE", "LB1V": "3,70%", "LB1C": "", "LB1D": "",
    "LB2S": "Infl. eurozona", "LB2V": "2,4%", "LB2C": "", "LB2D": "",
    "LB3S": "PMI", "LB3V": "51,1", "LB3C": "", "LB3D": "",
    "LB4S": "Disoccupazione", "LB4V": "6,5%", "LB4C": "", "LB4D": "",
    "LB5S": "GDP", "LB5V": "+0,8%", "LB5C": "up", "LB5D": "up",
    "LB6S": "Spread", "LB6V": "94 bp", "LB6C": "", "LB6D": "",
    "LB_S1K": "Aggiornato", "LB_S1V": "16:20", "LB_S2K": "API", "LB_S2V": "99,98%",
    "LB_S3K": "", "LB_S3V": "",
    "LB_NEWS1": "BTP, asta coperta 2,4 volte", "LB_NEWS2": "BCE: tono prudente sui tassi",
    "LB_NEWS3": "Borse europee in rialzo a metà seduta", "LB_NEWS4": "Oro ai massimi da cinque mesi",
}

PALETTE = ("--bg:#f7f6f2;--bg-soft:#efece5;--panel:#ffffff;--ink:#1b1c26;"
           "--muted:#5c5e6c;--line:#e7e3da;--acc:#5b34d1;--acc-deep:#4a2bb0;"
           "--acc-2:#e2622a;--up:#e2622a;--down:#d64545;"
           "--grad:linear-gradient(120deg,#5b34d1,#e2622a);--acc-text:#4a2bb0;"
           "--btn-ink:#ffffff;--up-text:#a34c2a;--down-text:#ac3c3e;"
           "--acc-ondark:#7f61db;--up-ondark:#ea8f66;--down-ondark:#da5858;"
           "--font-head:'Outfit';--font-body:'Public Sans'")

HEADER = """<header class="blk-header" data-var="i"><a class="blk-logo" data-var="f" href="#" aria-label="Jandervoq"><span class="caps">jandervoq</span></a>
<a class="blk-btn" href="#claim">Iscriviti</a>
<nav class="blk-nav" aria-label="Navigazione principale"><a href="#" aria-current="page">Home</a><a href="#">Chi siamo</a><a href="#">A chi si rivolge</a><a href="#">Contatti</a></nav>
<button class="menu-toggle" aria-label="Menu" aria-expanded="false">☰</button></header>"""

HERO = """<section class="blk-hero hero-ledger sec sec-hero" id="top" data-var="c">
  <div>
    <div class="eyebrow">JVQ · IT</div>
    <h1><span class="brand-line">Jandervoq</span>Azioni, crypto e materie prime in un'unica dashboard<br><span>senza passaggi inutili</span></h1>
    <p class="blk-hero-lead">Jandervoq riunisce mercati, grafici e ordini in un'unica area di lavoro, con esecuzione media di 64 millisecondi e un'interfaccia che si impara in una sera.</p>
    <div class="hero-cta">
      <a class="blk-btn" href="#claim">Apri il conto <span>↗</span></a>
      <a class="text-link" href="#claim">Vedi la demo →</a>
    </div>
    <div class="hero-stats">
      <div><b>4,5</b><span>valutazione media degli utenti</span></div>
      <div><b>21.400+</b><span>conti attivi in Europa</span></div>
      <div><b>64 ms</b><span>latenza media degli ordini</span></div>
    </div>
  </div>
  <div class="ledger" role="img" aria-label="Anteprima del pannello portafoglio">
    <div class="ledger-head"><span>€9.640,22</span><em class="up">↗ €318,40 (3,4%) questo mese</em></div>
    <div class="ledger-row"><b>Liquidità disponibile</b><small>EUR</small><span>€5.320,60</span><em class="up">+0,4%</em></div>
    <div class="ledger-row"><b>Portafoglio misto</b><small>MIX</small><span>€4.319,62</span><em class="up">+2,9%</em></div>
  </div>
</section>"""

PART = """<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__ID__ · __NAME__</title>
<link rel="stylesheet" href="blocks.css">
<link rel="stylesheet" href="skin.css">
<link rel="stylesheet" href="openers.css">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700;800&family=Public+Sans:wght@400;500;600;700&display=swap">
<style>:root{__PALETTE__}body{margin:0}
/* harness only: the fold line where a 800px laptop screen ends */
.fold{position:absolute;left:0;right:0;top:800px;border-top:1px dashed #d64545;pointer-events:none;z-index:60}
.fold b{position:absolute;right:8px;top:-9px;font:600 10px/1.4 system-ui,sans-serif;color:#d64545;background:#fff;padding:1px 6px}
/* harness only: squint test — keeps the rhythm, drops the letterforms */
body.squint .blk-livebar{filter:blur(2.6px)}
</style></head><body>
__STRIP__
<div class="fold" aria-hidden="true"><b>згин 800px</b></div>
__HEADER__
<main>__HERO__</main>
<script>
(function(){
  function send(){
    var s=document.querySelector('.blk-livebar'), h=document.querySelector('.blk-header');
    var hr=document.querySelector('.hv-hero, .blk-hero');
    var sb=s?s.getBoundingClientRect():null, hb=h?h.getBoundingClientRect():null;
    parent.postMessage({src:'tops', id:__IDJSON__,
      strip:sb?Math.round(sb.height):null,
      header:hb?Math.round(hb.height):null,
      hero:hr?Math.round(hr.getBoundingClientRect().height):null,
      top:sb&&hb?Math.round(hb.bottom):null,
      overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth}, '*');
  }
  send(); addEventListener('load', send); addEventListener('resize', send);
  addEventListener('message', function(e){ if (e.data && e.data.src === 'tops-ping') send();
    if (e.data && e.data.src === 'tops-squint') document.body.classList.toggle('squint', !!e.data.on); });
})();
</script>
</body></html>"""

GALLERY = """<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Верхні блоки — Jandervoq</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #f3f2ef; color: #1b1c26;
         font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
  .top { padding: 28px 28px 0; max-width: 1240px; margin-inline: auto; }
  .top h1 { font-size: 24px; margin: 0 0 6px; letter-spacing: -0.01em; }
  .top p { margin: 0; color: #5c5e6c; max-width: 74ch; }
  .legend { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 14px; font-size: 13px; color: #5c5e6c; }
  .legend b { color: #1b1c26; }
  /* picker: deliberately outside the design system — one dark neutral surface,
     system font, never the project's tokens (see skills/variant/picker.md) */
  .picker { position: sticky; top: 0; z-index: 5; display: flex; gap: 10px; align-items: center;
    flex-wrap: wrap; margin: 18px 0 0; padding: 10px; border-radius: 14px;
    background: rgb(20 20 20 / 0.94); box-shadow: inset 0 0 0 1px rgb(255 255 255 / 0.1);
    backdrop-filter: blur(6px); color: #fff; font: 13px/1 system-ui, -apple-system, "Segoe UI", sans-serif; }
  .picker .label { color: rgb(255 255 255 / 0.45); font-size: 11px; font-weight: 500;
    display: inline-flex; align-items: center; gap: 6px; padding: 0 4px; }
  .picker select { appearance: none; max-width: min(100%, 520px); padding: 9px 34px 9px 14px;
    border: 0; border-radius: 999px; background: rgb(255 255 255 / 0.12); color: #fff;
    font: 600 13px/1 system-ui, -apple-system, "Segoe UI", sans-serif; cursor: pointer; }
  .picker select:focus-visible, .picker button:focus-visible { outline: 2px solid rgb(255 255 255 / 0.75); outline-offset: 2px; }
  .picker option, .picker optgroup { background: #141414; color: #fff; }
  .picker button { border: 0; padding: 9px 14px; border-radius: 999px; cursor: pointer;
    background: rgb(255 255 255 / 0.12); color: #fff; font-weight: 600; }
  .picker button[aria-pressed="true"] { background: rgb(255 255 255 / 0.16); }
  .picker .stat { color: rgb(255 255 255 / 0.55); font-size: 11px; margin-left: auto; padding-right: 4px; }
  .card { max-width: 1240px; margin: 26px auto; padding: 0 28px; }
  .card > header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
  .card h2 { font-size: 15px; margin: 0; }
  .card .id { font: 600 11px/1 ui-monospace, monospace; background: #e7e3da; border-radius: 4px; padding: 4px 6px; }
  .card .h { font: 600 12px/1 ui-monospace, monospace; color: #8a4b00; background: #fbe9d2; padding: 4px 7px; border-radius: 4px; }
  .card .h.small { color: #0b6b3a; background: #dff3e6; }
  .card .h.big { color: #a41818; background: #fadcdc; }
  iframe { display: block; border: 0; background: #fff; box-shadow: 0 1px 0 #d8d3c8, 0 12px 30px -22px #000; }
  .desk iframe { width: 100%; max-width: 1180px; height: 860px; }
  .phone iframe { width: 390px; height: 780px; }
  .phones { display: flex; gap: 22px; overflow-x: auto; padding: 4px 4px 18px; }
  .phone { flex: none; }
  .hidden { display: none !important; }
  .card:target > header h2 { color: #4a2bb0; }
  .hint { max-width: 1240px; margin: 0 auto; padding: 0 28px 40px; color: #8a8b96; font-size: 12px; }
</style></head>
<body class="all">
<div class="top">
  <h1>Верхні блоки — стрічка над хедером · Jandervoq IT</h1>
  <p>Один варіант на екран. Кожен показаний у справжньому оточенні: стрічка → хедер <b>data-var="i"</b> → початок hero,
     у справжній палітрі та шрифтах сайту. Плашка над екраном — фактична висота стрічки, хедера й те, скільки пікселів
     вони зʼїдають до hero. Червона пунктирна лінія — згин ноутбука 800px.</p>
  <div class="legend">
    <span><b>на проді зараз:</b> стрічка 157px + хедер 135px = 292px до hero</span>
    <span><b>ціль:</b> стрічка ≤ 34px</span>
    <span><b>телефон:</b> <a href="mobile.html">mobile.html</a> · 390px</span>
    <span><b>відкриття стрічки:</b> <a href="openers.html">openers.html</a></span>
  </div>
  <div class="picker" aria-label="Варіанти">
    <span class="label">
      <svg aria-hidden="true" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v4a3 3 0 0 0 3 3h7"/><path d="m10 7 3 3-3 3"/></svg>
      Висота стрічки
    </span>
    <select id="pick" aria-label="Варіант"></select>
    <button type="button" id="v-all" aria-pressed="true">Показати всі</button>
    <span class="stat" id="stat">32 варіанти · клавіша H ховає панель</span>
  </div>
</div>
<div class="all">
  __CARDS__
</div>
<div class="hint">Харнес: <span class="mono">preview/tops/index.html</span> · клавіша <b>H</b> ховає панель · кожен варіант також окремою сторінкою <span class="mono">v-&lt;id&gt;.html</span>.</div>
<script>
(function(){
  var DATA = __DATA__;
  var NAMES = {}; DATA.forEach(function(d){ NAMES[d.id] = d.name; });
  var body = document.body, sel = document.getElementById('pick');
  var heights = {};
  var BUCKETS = [['Тонкі · до 29 px', 0, 29], ['Стандарт · 30–34 px', 30, 34], ['Високі · понад 34 px', 35, 9999]];

  function show(id){
    document.getElementById('v-all').setAttribute('aria-pressed', String(!id));
    sel.value = id || '';
    if (id) history.replaceState(null, '', '?__variant=' + id);
    else history.replaceState(null, '', location.pathname);
    if (id) { var el = document.getElementById('c-' + id); if (el) el.scrollIntoView({ block: 'start' }); }
    else window.scrollTo(0, 0);
  }
  function fillSelect(){
    var keep = sel.value;
    sel.innerHTML = '';
    var all = document.createElement('option');
    all.value = ''; all.textContent = 'Усі варіанти — показати все';
    sel.appendChild(all);
    BUCKETS.forEach(function(b){
      var g = document.createElement('optgroup'); g.label = b[0];
      DATA.forEach(function(d){
        var h = heights[d.id];
        if (h == null || h < b[1] || h > b[2]) return;
        var o = document.createElement('option');
        o.value = d.id; o.textContent = d.id + ' · ' + d.name + ' — ' + h + 'px';
        g.appendChild(o);
      });
      if (g.children.length) sel.appendChild(g);
    });
    sel.value = keep;
  }
  sel.addEventListener('change', function(){ show(sel.value || null); });
  document.getElementById('v-all').addEventListener('click', function(){ show(null); });
  addEventListener('message', function(e){
    var d = e.data || {};
    if (d.src !== 'tops' || !d.strip) return;
    heights[d.id] = d.strip;
    document.querySelectorAll('[data-h="' + d.id + '"]').forEach(function(el){
      el.textContent = 'стрічка ' + d.strip + 'px · хедер ' + d.header + 'px · до hero ' + d.top + 'px' +
        (d.overflow ? ' · ГОРИЗОНТАЛЬНИЙ СКРОЛ' : '');
      el.className = 'h' + (d.strip <= 34 ? ' small' : (d.strip >= 60 ? ' big' : ''));
    });
    fillSelect();
    var known = Object.keys(heights).length;
    var thin = Object.keys(heights).filter(function(k){ return heights[k] <= 34; }).length;
    document.getElementById('stat').textContent = known + ' з ' + DATA.length +
      ' заміряно · ' + thin + ' ≤ 34px · клавіша H ховає панель';
  });
  addEventListener('keydown', function(e){
    if (e.target.matches('input,textarea,select,[contenteditable]') || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 'h' || e.key === 'H') document.querySelector('.picker').classList.toggle('hidden');
  });
  addEventListener('load', function(){
    document.querySelectorAll('iframe').forEach(function(f){
      try { f.contentWindow.postMessage({ src: 'tops-ping' }, '*'); } catch (err) {}
    });
  });
  fillSelect();
  var m = location.search.match(/__variant=([a-z]+)/);
  if (m) show(m[1]);
})();
</script>
</body></html>"""

def fragment(vid: str) -> str:
    path = ROOT / "blocks" / ("blk-livebar.html" if vid == "a" else f"blk-livebar-{vid}.html")
    return path.read_text(encoding="utf-8")


def subs_for(vid: str) -> dict:
    if vid == "n":
        return dict(LIVE_N)
    data = g.build_livebar(random.Random(20261123 + ORDER.index(vid)), vid, "it", "IT")
    subs = dict(data["subs"])
    for k, v in LIVE_N.items():
        if k.startswith("LB_NEWS"):
            subs.setdefault(k, v)
    return subs


def render(vid: str) -> str:
    html = fragment(vid)
    subs = subs_for(vid)
    html = re.sub(r"\{\{(\w+)\}\}", lambda m: str(subs.get(m.group(1), "")), html)
    return html


def part_page(vid: str) -> str:
    return (PART.replace("__ID__", vid).replace("__NAME__", NAMES[vid])
                .replace("__PALETTE__", PALETTE).replace("__STRIP__", render(vid))
                .replace("__HEADER__", HEADER).replace("__HERO__", HERO)
                .replace("__IDJSON__", json.dumps(vid)))


def main() -> None:
    HERE.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "blocks" / "blocks.css", HERE / "blocks.css")
    shutil.copyfile(ROOT / "skins" / "skin-sharp-flat.css", HERE / "skin.css")
    for vid in ORDER:
        (HERE / f"v-{vid}.html").write_text(part_page(vid), encoding="utf-8")

    data_js = json.dumps([{"id": v, "name": NAMES[v]} for v in ORDER], ensure_ascii=False)
    cards = "\n".join(
        f'<section class="card desk" id="c-{vid}"><header><span class="id">{vid}</span>'
        f'<h2>{NAMES[vid]}</h2><span class="h" data-h="{vid}">…</span></header>'
        f'<iframe src="v-{vid}.html" title="{vid}"></iframe></section>'
        for vid in ORDER)
    (HERE / "index.html").write_text(
        GALLERY.replace("__DATA__", data_js).replace("__CARDS__", cards),
        encoding="utf-8")

    phones = "\n".join(
        f'<section class="phone"><header><span class="id">{vid}</span> <h2>{NAMES[vid]}</h2>'
        f'<span class="h" data-h="{vid}">…</span></header>'
        f'<iframe src="v-{vid}.html" title="{vid}" loading="lazy"></iframe></section>'
        for vid in ORDER)
    (HERE / "mobile.html").write_text(
        GALLERY.replace("__DATA__", data_js)
               .replace("__CARDS__", '<div class="phones">' + phones + '</div>')
               .replace("Верхні блоки (стрічка над хедером) — Jandervoq IT",
                        "Верхні блоки — телефон 390px"),
        encoding="utf-8")
    print(f"built {len(ORDER)} variants -> {HERE}")


if __name__ == "__main__":
    main()
