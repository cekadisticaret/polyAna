(function () {
  "use strict";
  if (window.__BA_ANALYTICS__) return;
  window.__BA_ANALYTICS__ = 1;

  var ENDPOINT = "/api/analytics/beacon";
  var started = Date.now();
  var maxScroll = 0;
  var sentEngage = false;

  function pathNow() {
    return (location.pathname || "/").split("?")[0].split("#")[0] || "/";
  }

  function sessionStart() {
    try {
      var k = "ba_sess_start";
      var v = sessionStorage.getItem(k);
      if (!v) sessionStorage.setItem(k, String(Date.now()));
      return parseInt(sessionStorage.getItem(k) || String(Date.now()), 10);
    } catch (e) {
      return started;
    }
  }

  function scrollPct() {
    var doc = document.documentElement;
    var body = document.body;
    var h = Math.max(
      doc.scrollHeight,
      body ? body.scrollHeight : 0,
      doc.clientHeight
    );
    var y = window.scrollY || doc.scrollTop || 0;
    var win = window.innerHeight || doc.clientHeight || 0;
    if (h <= win) return 100;
    return Math.min(100, Math.round(((y + win) / h) * 100));
  }

  function onScroll() {
    var p = scrollPct();
    if (p > maxScroll) maxScroll = p;
  }

  function send(payload) {
    payload.path = payload.path || pathNow();
    var body = JSON.stringify(payload);
    try {
      if (navigator.sendBeacon) {
        var blob = new Blob([body], { type: "application/json" });
        if (navigator.sendBeacon(ENDPOINT, blob)) return;
      }
    } catch (e) {}
    try {
      fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body,
        keepalive: true,
        credentials: "same-origin",
      });
    } catch (e2) {}
  }

  function trackClick(kind, target) {
    send({ event: "click", kind: kind, target: target || pathNow() });
  }

  function trackEngage() {
    if (sentEngage) return;
    sentEngage = true;
    var sec = Math.round((Date.now() - started) / 1000);
    if (sec < 2 && maxScroll < 10) return;
    var sess = Math.round((Date.now() - sessionStart()) / 1000);
    send({
      event: "engage",
      seconds: sec,
      scroll: maxScroll,
      session_seconds: sess,
    });
  }

  function classifyClick(el, href) {
    if (!href) return null;
    if (href.indexOf("tel:") === 0) return { kind: "phone", target: href.slice(0, 80) };
    if (href.indexOf("mailto:") === 0) return { kind: "cta", target: "mailto" };
    if (/google\.com\/maps|maps\.app\.goo\.gl/i.test(href)) {
      return { kind: "maps", target: href.slice(0, 120) };
    }
    if (/^https?:\/\//i.test(href)) {
      try {
        var u = new URL(href, location.origin);
        if (u.origin !== location.origin) {
          return { kind: "web", target: u.hostname };
        }
      } catch (e) {}
    }
    if (href.charAt(0) === "/" || href.indexOf(location.origin) === 0) {
      var p = href.charAt(0) === "/" ? href.split("?")[0] : href.replace(location.origin, "").split("?")[0];
      return { kind: "nav", target: p || "/" };
    }
    return null;
  }

  document.addEventListener(
    "click",
    function (ev) {
      var el = ev.target;
      while (el && el !== document) {
        if (el.getAttribute && el.getAttribute("data-ba-track")) {
          trackClick(el.getAttribute("data-ba-track"), el.getAttribute("data-ba-target") || "");
          return;
        }
        if (el.tagName === "A") {
          var href = el.getAttribute("href") || "";
          var info = classifyClick(el, href);
          if (info) trackClick(info.kind, info.target);
          return;
        }
        el = el.parentElement;
      }
    },
    true
  );

  window.addEventListener("scroll", onScroll, { passive: true });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") trackEngage();
  });
  window.addEventListener("pagehide", trackEngage);
  window.addEventListener("beforeunload", trackEngage);
})();
