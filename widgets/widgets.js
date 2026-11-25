/* ============================================================================
   widgets.js — widget library (shared file). No inline scripts.
   Each behavior finds itself via [data-widget="<id>"] and silently
   exits if that widget is not on the page.
   Include BEFORE the offer's app.js (app.js remains for menu/form).
   ========================================================================== */
(function () {
  'use strict';
  var LOCALE = (document.documentElement.lang || 'en').replace('_', '-');
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var fmt = function (n, d) { return Number(n).toLocaleString(LOCALE, d != null ? { minimumFractionDigits: d, maximumFractionDigits: d } : undefined); };
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- G1: livebar-counter (two live numbers) ------------------------------- */
  $$('[data-widget="livebar-counter"]').forEach(function (bar) {
    var lat = $('#live-latency', bar), ord = $('#live-orders', bar);
    if (!lat || !ord) return;
    setInterval(function () {
      lat.textContent = (32 + Math.round(Math.random() * 10)) + ' ms';
      ord.textContent = fmt(2900 + Math.round(Math.random() * 380));
    }, 1700);
  });

  /* ---- G1: tape-marquee (seamless tape — content duplicated) -------------- */
  $$('[data-widget="tape-marquee"] .wk-tape-track').forEach(function (track) {
    track.innerHTML += track.innerHTML;
  });

  /* ---- G1: [data-price] — subtle live price movements --------------------- */
  var prices = $$('[data-price]');
  if (prices.length) {
    var setPrices = function () {
      prices.forEach(function (el) {
        var base = Number(el.dataset.price);
        if (isNaN(base)) return;
        var v = base * (1 + (Math.random() - 0.5) * 0.024);
        var dec = el.dataset.dec ? Number(el.dataset.dec) : (base < 200 ? 2 : 0);
        el.textContent = (el.dataset.prefix || '') + fmt(v, dec);
      });
    };
    setPrices();
    if (!reduced) setInterval(setPrices, 1100);
  }

  /* ---- G1: heatmap ---------------------------------------------------------- */
  $$('[data-widget="heatmap"]').forEach(function (map) {
    var tiles = $$('[data-chg]', map);
    var paint = function () {
      tiles.forEach(function (t) {
        var c = Number(t.dataset.chg) || 0;
        t.classList.toggle('is-up', c >= 0);
        t.classList.toggle('is-down', c < 0);
        t.style.setProperty('--wk-i', Math.min(45, 14 + Math.abs(c) * 8) + '%');
        var label = $('small', t);
        if (label) label.textContent = (c >= 0 ? '+' : '') + fmt(c, 1) + '%';
      });
    };
    paint();
    if (!reduced) setInterval(function () {
      tiles.forEach(function (t) {
        t.dataset.chg = Math.max(-9, Math.min(9,
          (Number(t.dataset.chg) || 0) + (Math.random() - 0.48) * 2.0)).toFixed(1);
      });
      paint();
    }, 1500);
  });

  /* ---- G1: tile-flip -------------------------------------------------------- */
  $$('[data-widget="tile-flip"] [data-value]').forEach(function (el) {
    var base = Number(el.dataset.value) || 0;
    var step = function () {
      var v = base * (1 + (Math.random() - 0.5) * 0.04);
      el.textContent = fmt(v, el.dataset.dec != null ? +el.dataset.dec : (base < 200 ? 2 : 0));
      el.classList.remove('is-flip'); void el.offsetWidth; el.classList.add('is-flip');
    };
    if (!reduced) setInterval(step, 1400);
  });

  /* ---- G1: odometer --------------------------------------------------------- */
  $$('[data-widget="odometer"] [data-odometer]').forEach(function (el) {
    var value = Number(el.dataset.odometer) || 0;
    el.textContent = fmt(value);
    if (reduced) return;
    setInterval(function () {
      value += Math.round(Math.random() * 9) + 1;
      el.textContent = fmt(value);
    }, 1200);
  });

  /* ---- G2: countdown (shared for plates / bar / rings / flip-clock) --------- */
  $$('[data-widget="countdown"], #countdown').forEach(function (box) {
    if (!$$('[data-unit]', box).length) return;
    var KEY = 'wk-deadline-' + (box.dataset.key || 'default');
    var stored = Number(localStorage.getItem(KEY));
    var deadline = stored > Date.now() ? stored : Date.now() + 2 * 864e5 + 13 * 36e5 + 4 * 6e4 + 43e3;
    try { localStorage.setItem(KEY, String(deadline)); } catch (e) {}
    var pad = function (n) { return String(n).padStart(2, '0'); };
    var span = { days: 3, hours: 24, minutes: 60, seconds: 60 };
    var tick = function () {
      var left = Math.max(0, deadline - Date.now());
      if (!left) { deadline = Date.now() + 2 * 864e5; try { localStorage.setItem(KEY, String(deadline)); } catch (e) {} left = deadline - Date.now(); }
      var parts = {
        days: Math.floor(left / 864e5),
        hours: Math.floor(left % 864e5 / 36e5),
        minutes: Math.floor(left % 36e5 / 6e4),
        seconds: Math.floor(left % 6e4 / 1e3)
      };
      Object.keys(parts).forEach(function (unit) {
        var node = $('[data-unit="' + unit + '"]', box);
        if (!node) return;
        var txt = pad(parts[unit]);
        if (node.textContent !== txt && node.classList.contains('is-flap') === false && box.dataset.widget === 'countdown' && box.classList.contains('wk-flip')) {
          node.classList.add('is-flap');
        }
        node.textContent = txt;
        (node.parentElement || node).style.setProperty('--p', (parts[unit] / span[unit]).toFixed(3));
      });
    };
    tick();
    setInterval(tick, 1000);
  });

  /* ---- G2: progress-intake -------------------------------------------------- */
  $$('[data-widget="progress-intake"]').forEach(function (w) {
    var seats = $('[data-seats]', w), pct = $('[data-percent]', w);
    var bar = $('.wk-bar i', w), value = Number((seats && seats.textContent) || 11);
    var p = 100 - Math.round(value / 15 * 100);
    var apply = function () {
      if (seats) seats.textContent = value;
      if (pct) pct.textContent = p;
      if (bar) bar.style.setProperty('--fill', p + '%');
      var box = $('.wk-bar', w); if (box) box.setAttribute('aria-valuenow', String(p));
    };
    apply();
    if (reduced) return;
    setInterval(function () { if (value > 1) { value--; p = Math.min(96, p + 3); apply(); } }, 6000);
  });

  /* ---- G3: demo (line/bars combined) ---------------------------------------- */
  $$('[data-widget="demo-line"], [data-widget="demo-bars"]').forEach(function (sec) {
    var svg = $('#demo-svg', sec); if (!svg) return;
    var line = $('#demo-line', sec), area = $('#demo-area', sec), bars = $('#demo-bars', sec);
    var amount = $('#demo-amount', sec), amountOut = $('#demo-amount-out', sec), runsOut = $('#demo-runs', sec);
    var NS = 'http://www.w3.org/2000/svg';
    var W = 640, H = 280, N = 47, pts = [], runs = 0, dir = 1;
    var build = function () {
      pts = []; var v = H * 0.62;
      for (var i = 0; i <= N; i++) {
        v += (Math.random() - 0.46 + dir * 0.002) * 14 + dir * 0.6;
        v = Math.max(H * 0.14, Math.min(H * 0.9, v)); pts.push(v);
      }
      render();
    };
    var render = function () {
      var max = Math.max.apply(null, pts), min = Math.min.apply(null, pts);
      var range = Math.max(1, max - min);
      var x = function (i) { return 6 + i / N * (W - 12); };
      var y = function (v) { return 20 + (1 - (v - min) / range) * (H - 44); };
      var d = pts.map(function (v, i) { return (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); }).join(' ');
      if (line) line.setAttribute('d', d);
      if (area) area.setAttribute('d', d + ' L' + (W - 6).toFixed(1) + ' ' + H + ' L6 ' + H + ' Z');
      if (bars) {
        bars.innerHTML = '';
        var bw = Math.max(3, (W - 14) / (N + 1) - 5);
        pts.forEach(function (v, i) {
          var up = i === 0 || v >= pts[i - 1];
          var h = Math.max(2, H - y(v));
          var r = document.createElementNS(NS, 'rect');
          r.setAttribute('x', (x(i) - bw / 2).toFixed(1));
          r.setAttribute('y', (H - h).toFixed(1));
          r.setAttribute('width', bw.toFixed(1));
          r.setAttribute('height', h.toFixed(1));
          r.setAttribute('rx', '1.5');
          r.setAttribute('fill', up ? 'var(--wk-up)' : 'var(--wk-down)');
          r.setAttribute('opacity', '0.5');
          bars.appendChild(r);
        });
      }
    };
    var nudge = function (up) {
      dir = up ? 1 : -1;
      pts = pts.map(function (v) { return Math.max(H * 0.1, Math.min(H * 0.94, v + (up ? -24 : 24) + (Math.random() - 0.5) * 12)); });
      render();
    };
    build();
    if (amount && amountOut) { var sync = function () { amountOut.textContent = amount.value; }; amount.addEventListener('input', sync); sync(); }
    $$('.seg-btn', sec).forEach(function (btn) {
      btn.addEventListener('click', function () {
        $$('.seg-btn', sec).forEach(function (b) { b.classList.remove('is-on'); });
        btn.classList.add('is-on'); build();
      });
    });
    $$('[data-dir]', sec).forEach(function (btn) {
      btn.addEventListener('click', function () {
        runs++; if (runsOut) runsOut.textContent = runs; nudge(btn.dataset.dir === 'up');
      });
    });
    var reset = $('#demo-reset', sec);
    if (reset) reset.addEventListener('click', function () { runs = 0; if (runsOut) runsOut.textContent = '0'; build(); });
    /* idle drift: the demo keeps breathing without pretending to be a live quote */
    if (!reduced) setInterval(function () {
      var last = pts[pts.length - 1];
      var next = Math.max(H * 0.14, Math.min(H * 0.9,
        last + (Math.random() - 0.48) * 16 + dir * 0.4));
      pts.push(next); pts.shift(); render();
    }, 1000);
  });

  /* ---- G3: book-ladder (simulated depth, no real quotes) ------------------ */
  $$('[data-widget="book-ladder"]').forEach(function (box) {
    var rows = $$('.wk-book-row', box);
    if (!rows.length) return;
    var base = Number(box.dataset.base) || 90000;
    var dec = box.dataset.dec != null ? Number(box.dataset.dec) : (base < 200 ? 4 : 0);
    var step = Math.max(base * 0.00005, dec ? Math.pow(10, -dec) : 1);
    var mid = base;
    var paint = function () {
      mid = mid * (1 + (Math.random() - 0.5) * 0.0018);
      rows.forEach(function (row) {
        var lvl = Number(row.dataset.lvl) || 0;
        var price = mid + lvl * step * (1 + Math.random() * 0.4);
        var val = $('b', row), bar = $('i', row);
        if (val) val.textContent = fmt(price, dec);
        if (bar) bar.style.setProperty('--w', (26 + Math.random() * 64).toFixed(0) + '%');
      });
    };
    paint();
    if (!reduced) setInterval(paint, 900);
  });

  /* ---- G3: sentiment-gauge -------------------------------------------------- */
  $$('[data-widget="sentiment-gauge"]').forEach(function (g) {
    var needle = $('.wk-needle', g), out = $('[data-score]', g), fill = $('.wk-arc-fill', g);
    var set = function (score) {
      score = Math.max(0, Math.min(100, score));
      var angle = -90 + score / 100 * 180;
      if (needle) needle.style.transform = 'rotate(' + angle + 'deg)';
      if (fill) fill.setAttribute('stroke-dasharray', (score / 100 * 172) + ' 999');
      if (out) out.textContent = score;
    };
    set(Number((out && out.dataset.score) || 60));
    if (reduced) return;
    setInterval(function () {
      var cur = Number((out && out.dataset.score) || 60);
      var next = Math.max(15, Math.min(92, cur + Math.round((Math.random() - 0.5) * 18)));
      if (out) out.dataset.score = next;
      set(next);
    }, 1200);
  });

  /* ---- G4: faq-split -------------------------------------------------------- */
  $$('[data-widget="faq-split"]').forEach(function (faq) {
    var qs = $$('[data-q]', faq), ans = $$('[data-a]', faq);
    var show = function (id) {
      qs.forEach(function (q) { q.classList.toggle('is-on', q.dataset.q === id); q.setAttribute('aria-selected', String(q.dataset.q === id)); });
      ans.forEach(function (a) { a.hidden = a.dataset.a !== id; });
    };
    qs.forEach(function (q) { q.addEventListener('click', function () { show(q.dataset.q); }); });
    if (qs[0]) show(qs[0].dataset.q);
  });
})();
