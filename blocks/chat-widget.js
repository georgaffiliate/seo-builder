/* ============================================================================
   chat-widget.js — floating "live chat" shell around the site lead form.

   There is no operator and no socket. The first step is a scripted greeting and
   a message box; after the visitor sends anything, the widget reveals the real
   lead form. That form keeps the canonical contract (`form.lead-form`,
   `.js-lead-phone`, `.form-submit`, `.form-status`), so blocks/lead-form.js
   validates it, locks the phone to the offer's single country and posts it to
   api_local/integration/api.php exactly like the form in the page body.

   The typed text is copied into the form's hidden `message` field before the
   form is shown, so it is submitted with the lead instead of being thrown away.
   ============================================================================ */
(function () {
  'use strict';

  var root = document.getElementById('cw');
  if (!root) return;

  var bubble = root.querySelector('.cw-bubble');
  var panel = root.querySelector('.cw-panel');
  var closeBtn = root.querySelector('.cw-close');
  var log = root.querySelector('.cw-log');
  var say = root.querySelector('.cw-say');
  var sayInput = say ? say.querySelector('input') : null;
  var sayBtn = say ? say.querySelector('button') : null;
  var lead = root.querySelector('.cw-form');
  var msgField = lead ? lead.querySelector('input[name="message"]') : null;
  var firstField = lead ? lead.querySelector('input[name="first_name"]') : null;
  var afterText = root.getAttribute('data-after') || '';
  var isOpen = false;
  var nudgeTimer = null;
  var reduceMotion = false;
  try {
    reduceMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  } catch (e) {}

  function lang() {
    var l = document.documentElement.getAttribute('lang') || 'en';
    return l;
  }

  function clock() {
    try {
      return new Date().toLocaleTimeString(lang(), { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
      var d = new Date();
      var h = d.getHours(), m = d.getMinutes();
      return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
    }
  }

  function scrollDown() {
    if (log) log.scrollTop = log.scrollHeight;
  }

  function addMessage(text, mine) {
    if (!log) return null;
    var wrap = document.createElement('div');
    wrap.className = 'cw-msg ' + (mine ? 'cw-out' : 'cw-in');
    var p = document.createElement('p');
    p.textContent = text;
    var t = document.createElement('span');
    t.className = 'cw-time';
    t.textContent = clock();
    wrap.appendChild(p);
    wrap.appendChild(t);
    log.appendChild(wrap);
    scrollDown();
    return wrap;
  }

  function setTyping(on) {
    var old = log ? log.querySelector('.cw-typing') : null;
    if (old) {
      log.removeChild(old);
    }
    if (!on || !log) return;
    var box = document.createElement('div');
    box.className = 'cw-typing';
    box.setAttribute('aria-label', '…');
    for (var i = 0; i < 3; i++) box.appendChild(document.createElement('i'));
    log.appendChild(box);
    scrollDown();
  }

  function focusStart() {
    if (!isOpen) return;
    var el = (!lead || lead.hasAttribute('hidden')) ? sayInput : firstField;
    if (el) {
      try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); }
    }
  }

  function open() {
    if (isOpen) return;
    isOpen = true;
    if (nudgeTimer) { clearTimeout(nudgeTimer); nudgeTimer = null; }
    root.classList.remove('is-nudge');
    panel.removeAttribute('hidden');
    root.classList.add('is-open');
    bubble.setAttribute('aria-expanded', 'true');
    setTimeout(focusStart, 30);
    scrollDown();
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;
    panel.setAttribute('hidden', '');
    root.classList.remove('is-open');
    bubble.setAttribute('aria-expanded', 'false');
    try { bubble.focus({ preventScroll: true }); } catch (e) { bubble.focus(); }
  }

  bubble.setAttribute('aria-expanded', 'false');
  bubble.addEventListener('click', function () {
    if (isOpen) close(); else open();
  });
  if (closeBtn) closeBtn.addEventListener('click', close);

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && isOpen) close();
  });

  document.addEventListener('click', function (e) {
    if (isOpen && !root.contains(e.target)) close();
  });

  /* first step: scripted "typing" then the real lead form */
  function revealForm() {
    var text = (msgField && msgField.value) || '';
    if (say && sayInput && sayInput.value.trim()) text = sayInput.value.trim();
    if (msgField && text) msgField.value = text;
    if (say) say.setAttribute('hidden', '');
    if (lead) {
      lead.removeAttribute('hidden');
      var total = lead.querySelectorAll('input').length;
      if (total) setTimeout(focusStart, 20);
    }
    scrollDown();
  }

  function send() {
    if (!sayInput) return;
    var value = sayInput.value.trim();
    if (!value) return;
    if (msgField) msgField.value = value;
    addMessage(value, true);
    sayInput.value = '';
    if (sayBtn) sayBtn.disabled = true;
    setTyping(true);
    var wait = reduceMotion ? 250 : 1100;
    setTimeout(function () {
      setTyping(false);
      if (afterText) addMessage(afterText, false);
      if (sayBtn) sayBtn.disabled = false;
      revealForm();
    }, wait);
  }

  if (say) {
    say.addEventListener('submit', function (e) {
      e.preventDefault();
      send();
    });
  }
  if (sayInput) {
    sayInput.addEventListener('input', function () {
      if (sayBtn) sayBtn.disabled = !sayInput.value.trim();
    });
    sayBtn.disabled = true;
  }

  /* fill the timestamp of the server-rendered greeting bubble */
  if (log) {
    var times = log.querySelectorAll('.cw-time');
    for (var ti = 0; ti < times.length; ti++) {
      if (!times[ti].textContent) times[ti].textContent = clock();
    }
  }

  /* soft nudge: the reference shows a preview bubble; we only pulse the
     launcher, and only once, so it never reads as a fake unread message */
  if (!reduceMotion) {
    nudgeTimer = setTimeout(function () {
      nudgeTimer = null;
      if (!isOpen) root.classList.add('is-nudge');
    }, 12000);
  }
})();
