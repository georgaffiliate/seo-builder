<?php
// Pixels in <head> are enabled with the header_pixels flag (they run on Keitaro macros)
$__cfg = is_file(__DIR__ . '/config.php') ? require __DIR__ . '/config.php' : [];
if (empty($__cfg['header_pixels'])) { return; }

// The Facebook pixel can be disabled separately with the facebook_pixel flag
$fbPixelEnabled = !empty($__cfg['facebook_pixel']);
?>
<script>
(function () {
  var tsId = '{ts_id}';
  var pixel = '{pixel}';
  var fbEnabled = <?= $fbPixelEnabled ? 'true' : 'false' ?>;

  if (!pixel || String(pixel).indexOf('{') !== -1) {
    return;
  }

  function loadFacebook(withCatalog) {
    !function (f, b, e, v, n, t, s) {
      if (f.fbq) return;
      n = f.fbq = function () {
        n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments);
      };
      if (!f._fbq) f._fbq = n;
      n.push = n;
      n.loaded = !0;
      n.version = '2.0';
      n.queue = [];
      t = b.createElement(e);
      t.async = !0;
      t.src = v;
      s = b.getElementsByTagName(e)[0];
      s.parentNode.insertBefore(t, s);
    }(window, document, 'script', 'https://connect.facebook.net/en_US/fbevents.js');

    fbq('init', pixel);
    fbq('track', 'PageView');

    if (!withCatalog) {
      return;
    }

    var catalogId = '{catalog_id}';
    var catalogName = '{catalog_name}';

    if (catalogId && catalogId.indexOf('{') === -1) {
      var viewContent = {
        content_ids: [catalogId],
        content_type: 'product'
      };

      if (catalogName && catalogName.indexOf('{') === -1) {
        viewContent.content_name = catalogName;
      }

      fbq('track', 'ViewContent', viewContent);
    }
  }

  function loadTikTok() {
    !function (w, d, t) {
      w.TiktokAnalyticsObject = t;
      var ttq = w[t] = w[t] || [];
      ttq.methods = [
        'page', 'track', 'identify', 'instances', 'debug', 'on', 'off',
        'once', 'ready', 'alias', 'group', 'enableCookie', 'disableCookie'
      ];
      ttq.setAndDefer = function (obj, method) {
        obj[method] = function () {
          obj.push([method].concat(Array.prototype.slice.call(arguments, 0)));
        };
      };
      for (var i = 0; i < ttq.methods.length; i++) {
        ttq.setAndDefer(ttq, ttq.methods[i]);
      }
      ttq.instance = function (id) {
        var inst = ttq._i[id] || [];
        for (var n = 0; n < ttq.methods.length; n++) {
          ttq.setAndDefer(inst, ttq.methods[n]);
        }
        return inst;
      };
      ttq.load = function (e, n) {
        var r = 'https://analytics.tiktok.com/i18n/pixel/events.js';
        ttq._i = ttq._i || {};
        ttq._i[e] = [];
        ttq._i[e]._u = r;
        ttq._t = ttq._t || {};
        ttq._t[e] = +new Date;
        ttq._o = ttq._o || {};
        ttq._o[e] = n || {};
        var s = d.createElement('script');
        s.type = 'text/javascript';
        s.async = true;
        s.src = r + '?sdkid=' + e + '&lib=' + t;
        var a = d.getElementsByTagName('script')[0];
        a.parentNode.insertBefore(s, a);
      };

      ttq.load(pixel);
      ttq.page();
    }(window, document, 'ttq');
  }

if (tsId === '3') {
  loadTikTok();
  return;
}

  if(tsId === '13'){
    
  window.bgdataLayer = window.bgdataLayer || [];
  function bge() { bgdataLayer.push(arguments); }
  window.bge = window.bge || bge;
  bge('init', "{pixel}");


  !function(e,t){try{if(!e)return;try{"undefined"!=typeof localStorage&&localStorage.setItem("pixel_storage_dm",e)}catch(e){}var n=document.createElement("script");n.src="https://"+e+"/ad/events.js?pixel_id="+t,n.async=!0,n.setAttribute("data-pixel-script-dm",e),(document.head||document.getElementsByTagName("head")[0]||document.body||document.documentElement).appendChild(n)}catch(e){}}(function(e){try{var t=new RegExp("(^|&)"+e+"=([^&]*)(&|$)"),n=window.location.search.substr(1).match(t);return null!=n?decodeURIComponent(n[2].replace(/\+/g," ")):""}catch(e){return""}}("dm")||"tk.mowell.tech","{pixel}");


  }

if (fbEnabled && (tsId === '2' || tsId.indexOf('{') !== -1)) {
  loadFacebook(true);
}

})();
</script>
