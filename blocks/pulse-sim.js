/* pulse-sim.js — market pulse simulator widget (illustrative data, no live quotes).
   Mounts on [data-widget="pulse-sim"]; silently exits when the widget is absent.
   Curve, price and delta are seeded/derived — nothing here is a real quote. */
(function () {
  'use strict';
  function onReady(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }
  onReady(function () {
    var box = document.querySelector('[data-widget="pulse-sim"]');
    if (!box || box.dataset.psBound) return;
    box.dataset.psBound = '1';
    var svg = document.getElementById('ps-svg');
    var line = document.getElementById('ps-line');
    var area = document.getElementById('ps-area');
    var cross = document.getElementById('ps-cross');
    var crossLine = document.getElementById('ps-cross-line');
    var crossDot = document.getElementById('ps-cross-dot');
    var tip = document.getElementById('ps-tip');
    var tipPrice = document.getElementById('ps-tip-price');
    var tipName = document.getElementById('ps-tip-name');
    var price = document.getElementById('ps-price');
    var qname = document.getElementById('ps-qname');
    var delta = document.getElementById('ps-delta');
    var plot = box.querySelector('.ps-plot');
    var axis = box.querySelectorAll('.ps-axis span');
    if (!svg || !line || !area || !price || !delta || !plot) return;

    var LOCALE = document.documentElement.getAttribute('lang') || 'en';
    var W = 720, H = 300, N = 26;
    var TOP = 26, BOTTOM = 34;            /* vertical padding inside the viewBox */
    var values = [], base = 0, dec = 2, range = 0, active = null, timer = null;
    var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function fmt(v) {
      try {
        return new Intl.NumberFormat(LOCALE, { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(v);
      } catch (e) { return Number(v).toFixed(dec); }
    }
    function seeded(s) { var x = Math.sin(s * 999) * 43758.5453; return x - Math.floor(x); }
    function makeValues(seed, span) {
      var out = [], drift = 0.3 + range * 0.22;
      for (var i = 0; i < N; i++) {
        var wave = Math.sin((i + seed) * 0.58) * 1.7 + Math.cos((i + seed) * 0.27) * 1.1;
        var noise = (seeded(seed + i * 0.71 + span) - 0.5) * 2.1;
        out.push(48 + i * drift + wave * 8 + noise * 8);
      }
      return out;
    }
    function pointAt(i) {
      var min = Math.min.apply(null, values), max = Math.max.apply(null, values);
      var sp = Math.max(1, max - min);
      return { x: i / (N - 1) * W, y: (H - BOTTOM) - ((values[i] - min) / sp) * (H - TOP - BOTTOM) };
    }
    function paths() {
      var d = '', p0 = pointAt(0);
      d = 'M' + p0.x.toFixed(1) + ' ' + p0.y.toFixed(1);
      for (var i = 1; i < values.length; i++) {
        var pr = pointAt(i - 1), nx = pointAt(i), mid = (pr.x + nx.x) / 2;
        d += ' C' + mid.toFixed(1) + ' ' + pr.y.toFixed(1) + ' ' + mid.toFixed(1) + ' ' + nx.y.toFixed(1) +
             ' ' + nx.x.toFixed(1) + ' ' + nx.y.toFixed(1);
      }
      line.setAttribute('d', d);
      area.setAttribute('d', d + ' L' + W + ' ' + H + ' L0 ' + H + ' Z');
    }
    var DEC_COMMA;
    try { DEC_COMMA = (1.1).toLocaleString(LOCALE).indexOf(',') >= 0; } catch (e) { DEC_COMMA = false; }
    function pct(v) {
      var s = v.toFixed(2);
      return DEC_COMMA ? s.replace('.', ',') : s;
    }
    function updateQuote() {
      var factor = (values[N - 1] - values[0]) / 100;
      price.textContent = fmt(base * (1 + factor / 100));
      var ch = factor * 2.4;
      delta.textContent = (ch >= 0 ? '+' : '') + pct(ch) + '%';
      delta.classList.toggle('is-down', ch < 0);
    }
    function hideCross() { cross.setAttribute('opacity', '0'); if (tip) tip.hidden = true; }
    function draw(seed) {
      values = makeValues(seed, range * 7);
      paths(); updateQuote(); hideCross();
      if (!reduced) {
        line.classList.remove('is-drawing');
        void line.getBoundingClientRect();
        line.classList.add('is-drawing');
      }
    }
    function axisLabels() {
      var labels = [];
      try {
        if (range === 0) {
          var f = new Intl.DateTimeFormat(LOCALE, { hour: '2-digit', minute: '2-digit' });
          var t = new Date(); t.setHours(9, 0, 0, 0);
          for (var i = 0; i < 5; i++) { labels.push(f.format(t)); t.setHours(t.getHours() + 2); }
        } else if (range === 1) {
          var fw = new Intl.DateTimeFormat(LOCALE, { weekday: 'short' });
          var d = new Date();
          for (var j = 0; j < 5; j++) { labels.push(fw.format(d)); d.setDate(d.getDate() - 1); }
          labels.reverse();
        } else {
          labels = ['W1', 'W2', 'W3', 'W4'];
        }
      } catch (e) { labels = []; }
      axis.forEach(function (sp, k) { sp.textContent = labels[k] || ''; });
    }
    function activate(btn) {
      assets.forEach(function (b) { b.classList.remove('is-active'); b.setAttribute('aria-selected', 'false'); });
      btn.classList.add('is-active'); btn.setAttribute('aria-selected', 'true');
      active = btn;
      base = parseFloat(btn.getAttribute('data-price')) || 100;
      dec = parseInt(btn.getAttribute('data-dec'), 10); if (isNaN(dec)) dec = 2;
      var nm = btn.getAttribute('data-name') || '';
      if (qname) qname.textContent = nm;
      if (tipName) tipName.textContent = nm;
      draw(parseInt(btn.getAttribute('data-seed'), 10) || 4);
      axisLabels();
    }
    var assets = Array.prototype.slice.call(box.querySelectorAll('[data-asset]'));
    var ranges = Array.prototype.slice.call(box.querySelectorAll('[data-range]'));
    assets.forEach(function (b) {
      b.addEventListener('click', function () { activate(b); });
    });
    ranges.forEach(function (b) {
      b.addEventListener('click', function () {
        ranges.forEach(function (x) { x.classList.remove('is-active'); x.setAttribute('aria-pressed', 'false'); });
        b.classList.add('is-active'); b.setAttribute('aria-pressed', 'true');
        range = parseInt(b.getAttribute('data-range'), 10) || 0;
        if (active) draw(parseInt(active.getAttribute('data-seed'), 10) || 4);
        axisLabels();
      });
    });
    if (plot.addEventListener) {
      plot.addEventListener('pointermove', function (ev) {
        if (!values.length) return;
        var rect = plot.getBoundingClientRect();
        var x = Math.max(0, Math.min(rect.width, ev.clientX - rect.left));
        var idx = Math.round(x / rect.width * (N - 1));
        var p = pointAt(idx);
        cross.setAttribute('opacity', '1');
        crossLine.setAttribute('d', 'M' + p.x.toFixed(1) + ' 0V' + H);
        crossDot.setAttribute('cx', p.x.toFixed(1));
        crossDot.setAttribute('cy', p.y.toFixed(1));
        if (tip) {
          tip.hidden = false;
          tip.style.left = Math.max(8, Math.min(rect.width - 130, x + 14)) + 'px';
          tip.style.top = Math.max(8, p.y / H * rect.height - 58) + 'px';
        }
        var ratio = 1 + ((values[idx] - values[0]) / 100) / 100;
        if (tipPrice) tipPrice.textContent = fmt(base * ratio);
      });
      plot.addEventListener('pointerleave', hideCross);
    }
    if (assets.length) activate(assets[0]);

    /* live pulse: shift + push a fresh point every few seconds (illustrative only) */
    if (!reduced) {
      timer = window.setInterval(function () {
        if (document.hidden || !active) return;
        var seed = parseInt(active.getAttribute('data-seed'), 10) || 4;
        var v = 48 + N * (0.3 + range * 0.22) + Math.sin(seed + Date.now() / 100000) * 16 + Math.cos(seed * 0.7) * 9;
        values.shift(); values.push(v);
        paths(); updateQuote();
      }, 4200);
      window.addEventListener('pagehide', function () { if (timer) window.clearInterval(timer); }, { once: true });
    }
  });
})();
