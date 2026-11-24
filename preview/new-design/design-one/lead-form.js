/* lead-form.js — canonical lead intake for assembled landings.
   Logic ported from the reference landing (altvecto-hu.site footer script):
   intl-tel-input with isValidNumber() validation, red .input-error highlight on
   the input, localized field errors (<html lang> dictionary, EN fallback),
   selected-country sync into the hidden country input, and thanks-redirect with
   pixel / autologin / subid / ts_id. Network failure still forwards to thanks.
   Form contract (do not change): form.lead-form, phone input .js-lead-phone
   WITHOUT name attribute — intl-tel-input hiddenInput carries name="phone". */
(function () {
  'use strict';

  var SCRIPT = document.currentScript;
  function attr(el, name) { return el ? el.getAttribute(name) || "" : ""; }
  function qs(root, sel) { return root ? root.querySelector(sel) : null; }
  function qsa(root, sel) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  /* ---------- localized field errors (keyed by <html lang>) ---------- */
  var ERR = {
    cs: { name: "Zadejte platnou hodnotu", email: "Neplatný e-mail",
          phoneNotLoaded: "Telefon se nepodařilo načíst", phoneInvalid: "Neplatné telefonní číslo" },
    sk: { name: "Zadajte platnú hodnotu", email: "Neplatný e-mail",
          phoneNotLoaded: "Telefón sa nepodarilo načítať", phoneInvalid: "Neplatné telefónne číslo" },
    hu: { name: "Adj meg érvényes értéket", email: "Érvénytelen e-mail",
          phoneNotLoaded: "A telefon nem töltődött be", phoneInvalid: "Érvénytelen telefonszám" },
    pl: { name: "Wprowadź poprawną wartość", email: "Nieprawidłowy email",
          phoneNotLoaded: "Telefon nie został załadowany", phoneInvalid: "Nieprawidłowy numer telefonu" },
    de: { name: "Bitte geben Sie einen gültigen Wert ein", email: "Ungültige E-Mail",
          phoneNotLoaded: "Telefon nicht geladen", phoneInvalid: "Ungültige Telefonnummer" },
    nl: { name: "Voer een geldige waarde in", email: "Ongeldig e-mailadres",
          phoneNotLoaded: "Telefoon niet geladen", phoneInvalid: "Ongeldig telefoonnummer" },
    it: { name: "Inserisci un valore valido", email: "Email non valida",
          phoneNotLoaded: "Telefono non caricato", phoneInvalid: "Numero di telefono non valido" },
    es: { name: "Ingrese un valor válido", email: "Correo electrónico no válido",
          phoneNotLoaded: "Teléfono no cargado", phoneInvalid: "Número de teléfono no válido" },
    fr: { name: "Veuillez entrer une valeur valide", email: "Email invalide",
          phoneNotLoaded: "Téléphone non chargé", phoneInvalid: "Numéro de téléphone invalide" },
    pt: { name: "Digite um valor válido", email: "Email inválido",
          phoneNotLoaded: "Telefone não carregado", phoneInvalid: "Número de telefone inválido" },
    ro: { name: "Introduceți o valoare validă", email: "Email invalid",
          phoneNotLoaded: "Telefonul nu a fost încărcat", phoneInvalid: "Număr de telefon invalid" },
    en: { name: "Please enter a valid value", email: "Invalid email",
          phoneNotLoaded: "Phone not loaded", phoneInvalid: "Invalid phone number" }
  };
  var LANG = (document.documentElement.lang || "cs").split("-")[0].toLowerCase();
  function errMsg(type) { return (ERR[LANG] && ERR[LANG][type]) || ERR.en[type]; }

  /* ---------- error highlight: red border on input + message under it ---------- */
  function showError(input, type) {
    var group = input.closest ? input.closest(".form-group") : null;
    var box = group ? qs(group, ".form-error") : null;
    input.classList.add("input-error");
    if (box) box.textContent = errMsg(type);
  }
  function clearError(input) {
    var group = input.closest ? input.closest(".form-group") : null;
    var box = group ? qs(group, ".form-error") : null;
    input.classList.remove("input-error");
    if (box) box.textContent = "";
  }

  /* ---------- validators (reference logic) ---------- */
  function validateName(input) {
    if (input.value.trim().length < 2) { showError(input, "name"); return false; }
    clearError(input); return true;
  }
  function validateEmail(input) {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(input.value.trim())) { showError(input, "email"); return false; }
    clearError(input); return true;
  }
  function validatePhone(phoneEl, iti) {
    if (!phoneEl.value.trim()) { showError(phoneEl, "name"); return false; }
    if (!iti) { showError(phoneEl, "phoneNotLoaded"); return false; }
    if (!iti.isValidNumber()) { showError(phoneEl, "phoneInvalid"); return false; }
    clearError(phoneEl); return true;
  }

  function getPhoneInput(form) {
    return qs(form, "input.js-lead-phone") ||
      qs(form, "#phone") ||
      qs(form, '[name="phone"]') ||
      qs(form, 'input[type="tel"]:not([type="hidden"])');
  }
  function getLeadForms() {
    var list = qsa(document, "form.lead-form");
    if (!list.length) {
      var legacy = document.getElementById("lead-form");
      if (legacy) list = [legacy];
    }
    return list;
  }

  /* ---------- intl-tel-input per form ---------- */
  function initPhoneForForm(form, codes) {
    var phoneEl = getPhoneInput(form);
    if (!phoneEl || phoneEl.getAttribute("data-lead-iti-init")) return;

    var list = Array.isArray(codes)
      ? codes.map(function (c) { return String(c).toLowerCase(); })
      : [String(codes || "us").toLowerCase()];
    var countryInput = qs(form, '.js-lead-country, #country, input[name="country"]');

    var iti = window.intlTelInput(phoneEl, {
      initialCountry: list[0],
      onlyCountries: list,
      separateDialCode: true,
      nationalMode: true,
      autoPlaceholder: "polite",
      formatOnDisplay: true,
      hiddenInput: "phone",
      utilsScript: "https://cdnjs.cloudflare.com/ajax/libs/intl-tel-input/17.0.15/js/utils.js"
    });

    form._leadTelIti = iti;
    phoneEl.setAttribute("data-lead-iti-init", "1");

    var syncCountry = function () {
      if (!countryInput || !iti) return;
      var sel = iti.getSelectedCountryData();
      if (sel && sel.iso2) countryInput.value = sel.iso2.toUpperCase();
    };
    syncCountry();
    phoneEl.addEventListener("countrychange", syncCountry);
  }
  function initAllLeadPhones(code) {
    getLeadForms().forEach(function (form) {
      /* intl-tel-input may fail to load (CDN) — the form must still submit */
      try { initPhoneForForm(form, code); } catch (err) { /* noop */ }
    });
  }

  /* ---------- tracking helpers ---------- */
  function cleanMacro(v) {
    v = String(v == null ? "" : v).trim();
    return v.indexOf("{") === -1 ? v : "";
  }
  function searchParams() {
    var out = {}, q = location.search.replace(/^\?/, ""), parts = q ? q.split("&") : [];
    parts.forEach(function (kv) {
      var i = kv.indexOf("=");
      if (i < 0) { out[kv] = ""; return; }
      out[decodeURIComponent(kv.slice(0, i))] =
        decodeURIComponent(kv.slice(i + 1).replace(/\+/g, "%20"));
    });
    return out;
  }
  function sessionDump() {
    var out = { href: location.href, referrer: document.referrer || "",
                screen: screen.width + "x" + screen.height };
    try { out.tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch (e) {}
    ["localStorage", "sessionStorage"].forEach(function (store) {
      try {
        var s = window[store];
        for (var i = 0; i < s.length; i++) {
          var k = s.key(i);
          if (/(_subid|kt_|keitaro|clickid|tsid)/i.test(k) &&
              String(s.getItem(k)).length < 200) out[store + "." + k] = s.getItem(k);
        }
      } catch (e) {}
    });
    return out;
  }
  function collect(form) {
    /* mirror reference: sync the full E.164 number into every phone-named input */
    var iti = form._leadTelIti, phoneEl = getPhoneInput(form);
    if (iti && phoneEl) phoneEl.value = iti.getNumber();
    qsa(form, 'input[name="phone"]').forEach(function (h) { if (iti) h.value = iti.getNumber(); });
    var post = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      var n = el.name;
      if (!n || el.disabled || el.type === "submit") return;
      if (el.type === "checkbox") { post[n] = el.checked ? 1 : 0; return; }
      if (el.type === "radio") { if (el.checked) post[n] = el.value; return; }
      post[n] = el.value;
    });
    return post;
  }
  function goThanks(scriptEl, extra) {
    extra = extra || {};
    var base = attr(scriptEl, "data-thanks") || "./thanks.php";
    var q = new URLSearchParams();
    var params = searchParams();
    var pixel = cleanMacro(params.pixel != null ? params.pixel : extra.pixel);
    var subid = cleanMacro(extra.subid);
    var tsid = cleanMacro(attr(scriptEl, "data-tsid"));
    if (pixel) q.append("pixel", pixel);
    if (extra.autologin) q.append("autologin", extra.autologin);
    if (subid) q.append("subid", subid);
    if (tsid) q.append("ts_id", tsid);
    if (extra.jobId) q.append("job_id", extra.jobId);
    window.location.href = base + (q.toString() ? "?" + q.toString() : "");
  }

  /* ---------- submit wiring ---------- */
  function wire(form, scriptEl) {
    var status = qs(form, ".form-status");
    var firstName = qs(form, '[name="first_name"]');
    var lastName = qs(form, '[name="last_name"]');
    var emailInput = qs(form, '[name="email"]');
    var submitBtn = qs(form, ".form-submit");
    var phoneEl = getPhoneInput(form);
    if (!firstName || !lastName || !emailInput || !submitBtn || !phoneEl) return;

    /* clear the error as soon as the user starts fixing the field */
    [firstName, lastName, emailInput, phoneEl].forEach(function (el) {
      el.addEventListener("input", function () { clearError(el); });
    });

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var iti = form._leadTelIti;
      var okName = validateName(firstName);
      var okLast = validateName(lastName);
      var okMail = validateEmail(emailInput);
      var okPhone = validatePhone(phoneEl, iti);
      if (!(okName && okLast && okMail && okPhone)) {
        if (status) status.textContent = attr(status, "data-msg-fix") || "";
        return;
      }

      submitBtn.disabled = true;
      if (status) status.textContent = attr(status, "data-msg-sending") || "";

      var payload = { post: collect(form), session: sessionDump(),
                      server: { ua: navigator.userAgent, lang: navigator.language || "" },
                      rawclick: searchParams() };

      fetch(form.getAttribute("action"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      })
        .then(function (res) { return res.text(); })
        .then(function (text) {
          /* display_errors may prepend warnings — slice out the first JSON object */
          var data = null;
          try { data = JSON.parse(text); }
          catch (e) {
            var first = text.indexOf("{"), last = text.lastIndexOf("}");
            if (first !== -1 && last > first) {
              try { data = JSON.parse(text.slice(first, last + 1)); } catch (e2) {}
            }
          }
          data = data || {};

          var auto = "", jobId = "", subid = "";
          var cr = data.crm_response;
          if (cr && typeof cr === "object") { auto = cr.auto_login_url || cr.autologin || ""; }
          else if (cr && typeof cr === "string") {
            try {
              var p = JSON.parse(cr);
              auto = (p && (p.auto_login_url || p.autologin)) || "";
            } catch (e) {}
          }
          if (data.job_id) jobId = data.job_id;
          subid = (payload.post && payload.post.subid) || "";

          if (status) status.textContent = attr(status, "data-msg-ok") || "";
          var poll = attr(scriptEl, "data-poll") === "true";
          if (jobId && poll) goThanks(scriptEl, { autologin: auto, subid: subid, jobId: jobId });
          else goThanks(scriptEl, { autologin: auto, subid: subid });
        })
        .catch(function () {
          /* reference behaviour: network hiccup still forwards to the thank-you page */
          goThanks(scriptEl, { subid: (payload.post && payload.post.subid) || "" });
        });
    });
  }

  function wireAll(scriptEl) {
    getLeadForms().forEach(function (f) {
      if (!f.getAttribute("data-lead-wired")) {
        f.setAttribute("data-lead-wired", "1");
        wire(f, scriptEl);
      }
    });
  }

  /* ---------- boot: country from config or IP-geolocation ---------- */
  function boot() {
    var cfgCountry = attr(SCRIPT, "data-country") || "auto";
    if (cfgCountry === "auto") {
      var done = false;
      var finish = function (cc) {
        if (done) return;
        done = true;
        initAllLeadPhones(cc || "us");
        wireAll(SCRIPT);
      };
      try {
        fetch("https://ipapi.co/json/")
          .then(function (r) { return r.json(); })
          .then(function (d) { finish(d && d.country); })
          .catch(function () { finish(""); });
        setTimeout(function () { finish(""); }, 2500);
      } catch (e) { finish(""); }
    } else {
      initAllLeadPhones(cfgCountry);
      wireAll(SCRIPT);
    }
  }
  if (document.readyState !== "loading") boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();
