#!/usr/bin/env python3
"""Header harness: all ten header layouts, before and after the upgrade.

Renders each header in the real page context (strip -> header -> hero) with the
real palette, fonts and menu copy, and measures it in the browser.
Review code, not ship code.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import build as B  # noqa: E402

LOGO = ('<a class="blk-logo" data-var="f" href="#" aria-label="Jandervoq">'
        '<span class="caps">jandervoq</span></a>')
NAV = ('<nav class="blk-nav" aria-label="Navigazione principale">'
       '<a href="#" aria-current="page">Home</a><a href="#">Chi siamo</a>'
       '<a href="#">A chi si rivolge</a><a href="#">Contatti</a></nav>')
CTA = '<a class="blk-btn" href="#claim">Iscriviti</a>'
TOGGLE = ('<button class="menu-toggle" aria-label="Menu" aria-expanded="false">'
          '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" '
          'stroke-width="1.75" stroke-linecap="round" aria-hidden="true">'
          '<path class="i-burger" d="M4 7h16M4 12h16M4 17h16"/>'
          '<path class="i-close" d="M6 6l12 12M18 6L6 18"/></svg></button>')

PARTS = {"logo": LOGO, "nav": NAV, "cta": CTA, "toggle": TOGGLE}

HEADERS = [
    ("a", "Лого зліва · навігація · CTA", ("logo", "nav", "cta", "toggle")),
    ("c", "Лого по центру, навігація зліва", ("nav", "logo", "cta", "toggle")),
    ("d", "Без лого", ("nav", "cta", "toggle")),
    ("e", "Без CTA", ("logo", "nav", "toggle")),
    ("f", "Лого + CTA, навігація другим рядком", ("logo", "cta", "nav", "toggle")),
    ("g", "Навігація притиснута вправо", ("logo", "cta", "nav", "toggle")),
    ("h", "Лого по центру, навігація під ним", ("logo", "cta", "nav", "toggle")),
    ("i", "Лого + CTA, навігація під ними", ("logo", "cta", "nav", "toggle")),
    ("j", "Навігація зліва, лого справа", ("nav", "cta", "logo", "toggle")),
    ("k", "Бренд зверху, меню + CTA другим рядком", ("logo", "nav", "cta", "toggle")),
    ("l", "Правий кластер: меню → лінія → CTA", ("logo", "nav", "cta", "toggle")),
    ("m", "Док-навігація пігулкою", ("logo", "nav", "cta", "toggle")),
]

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
  iframe { display: block; border: 0; width: 100%; max-width: 1180px; height: 860px; background: #fff;
    box-shadow: 0 1px 0 #d8d3c8, 0 12px 30px -22px #000; }
  .phones { display: flex; gap: 20px; overflow-x: auto; padding: 4px; }
  .phone { flex: none; }
  .phone iframe { width: 390px; height: 700px; }
  .hint { max-width: 1240px; margin: 20px auto 0; padding: 0 28px 48px; color: #8a8b96; font-size: 12px; }
</style></head><body>
<div class="top">
  <h1>__TITLE__</h1>
  <p>__LEAD__</p>
  <div class="legend">__LEGEND__</div>
  <div class="picker">
    <span class="label">Хедер</span>
    <select id="pick" aria-label="Варіант">__OPTIONS__</select>
    <a href="__LINK_HREF__">__LINK_TEXT__</a>
  </div>
</div>
__SECTIONS__
<div class="hint">Харнес: <span class="mono">preview/tops/headers_build.py</span> · таблиця висот — у звіті. Згенеровані сторінки в git не йдуть.</div>
<script>
(function(){
  var pick = document.getElementById('pick');
  pick.addEventListener('change', function(){
    var el = document.getElementById('c-' + pick.value);
    if (el) el.scrollIntoView({ block: 'start' });
  });
  addEventListener('message', function(e){
    var d = e.data || {};
    if (d.src !== 'tops' || !d.header) return;
    document.querySelectorAll('[data-h="' + d.id + '"]').forEach(function(el){
      el.textContent = 'хедер ' + d.header + 'px · стрічка ' + d.strip + 'px · до hero ' + d.top + 'px';
      el.className = 'h' + (d.header <= 70 ? ' small' : (d.header >= 120 ? ' big' : ''));
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


def header_html(order) -> str:
    return ('<header class="blk-header" data-var="%s">' % order[0] +
            "\n".join(PARTS[k] for k in order[1]) + "</header>")


def part(vid: str, order, old: bool) -> str:
    sid = vid
    html = (B.PART.replace("__ID__", sid)
                  .replace("__NAME__", f"header {vid}")
                  .replace("__PALETTE__", B.PALETTE)
                  .replace("__STRIP__", B.render("ad"))
                  .replace("__HEADER__", ('<header class="blk-header" data-var="%s">' % vid) +
                           "\n".join(PARTS[k] for k in order) + "</header>")
                  .replace("__HERO__", B.HERO)
                  .replace("__IDJSON__", '\"%s\"' % sid))
    if old:
        html = html.replace('href="blocks.css"', 'href="blocks-old.css"')
    return html


def build_page(title, lead, legend, cards, options, link_href, link_text) -> str:
    return (PAGE.replace("__TITLE__", title).replace("__LEAD__", lead)
                .replace("__LEGEND__", legend).replace("__OPTIONS__", options)
                .replace("__SECTIONS__", cards)
                .replace("__LINK_HREF__", link_href).replace("__LINK_TEXT__", link_text))


def main() -> None:
    # the bar as it shipped before this change, for an honest side-by-side
    old_css = subprocess.run(["git", "show", "HEAD:blocks/blocks.css"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
    (HERE / "blocks-old.css").write_text(old_css, encoding="utf-8")

    for vid, _, order in HEADERS:
        (HERE / f"h-{vid}.html").write_text(part(vid, order, old=False), encoding="utf-8")
        (HERE / f"h-old-{vid}.html").write_text(part(vid, order, old=True), encoding="utf-8")

    options = "\n".join(f'<option value="{vid}">{name}</option>' for vid, name, _ in HEADERS)

    def cards_for(prefix: str) -> str:
        return "\n".join(
            f'<article class="card" id="c-{vid}"><header><span class="id">{vid}</span>'
            f'<h2>{name}</h2><span class="h" data-h="{vid}">…</span></header>'
            f'<iframe src="{prefix}{vid}.html" title="{vid}"></iframe></article>'
            for vid, name, _ in HEADERS)

    (HERE / "headers.html").write_text(build_page(
        "Хедер — після апскейлу (усі 12 варіантів)",
        "Той самий каркас і та сама палітра, що були; змінені масштаб логотипа, вага навігації, "
        "висота рядка, поверхня бара (просвічує + блюр замість жорсткої тіні), стан бургера. "
        "Кожен хедер показаний у реальному оточенні: стрічка → хедер → початок hero.",
        "<span><b>стало:</b> один рядок ≈ 62–70px, дворівневі ≈ 96–104px (було 135)</span>"
        "<span><b>до:</b> <a href=\"headers-before.html\">headers-before.html</a></span>"
        "<span><b>телефон:</b> <a href=\"headers-mobile.html\">headers-mobile.html</a></span>",
        cards_for("h-"), options, "headers-before.html", "Було →"), encoding="utf-8")

    (HERE / "headers-before.html").write_text(build_page(
        "Хедер — як було (10 варіантів, до апскейлу)",
        "Стан до апскейлу: логотип 30px/800, пігулки в навігації, CTA 12×20, бар 20px по вертикалі, "
        "глиф ☰ замість іконки. Той самий контекст, що й у «стало», — різниця тільки в header-CSS.",
        "<span><b>до:</b> рядок ≈ 70px, дворівневі = 135px</span>"
        "<span><b>стало:</b> <a href=\"headers.html\">headers.html</a></span>",
        cards_for("h-old-"), options, "headers.html", "Стало →"), encoding="utf-8")

    phones = "\n".join(
        f'<section class="phone"><header><span class="id">{vid}</span> <h2>{name}</h2>'
        f'<span class="h" data-h="{vid}">…</span></header>'
        f'<iframe src="h-{vid}.html" title="{vid}" loading="lazy"></iframe></section>'
        for vid, name, _ in HEADERS)
    (HERE / "headers-mobile.html").write_text(build_page(
        "Хедер — телефон 390px",
        "Усі дванадцять варіантів на 390px: бургер 42px, панель меню під баром, посилання 15px "
        "з волосяними роздільниками.",
        "<span><b>стало</b></span>",
        '<div class="phones">' + phones + '</div>', options,
        "headers.html", "Десктоп →"), encoding="utf-8")
    print(f"built {len(HEADERS)} headers (new + old) -> {HERE}")


if __name__ == "__main__":
    main()
