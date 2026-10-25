// Picks English or Norwegian: a saved choice wins, then the browser's language order.
(function () {
  var KEY = "bc-lang";
  var here = document.documentElement.lang.slice(0, 2) === "nb" ? "nb" : "en";
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  var want = saved;
  if (!want) {
    var langs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || "en"];
    for (var i = 0; i < langs.length; i++) {
      var l = String(langs[i]).toLowerCase();
      if (/^(nb|nn|no)\b/.test(l)) { want = "nb"; break; }
      if (/^en\b/.test(l)) { want = "en"; break; }
    }
  }
  if (want && want !== here) {
    var alt = document.querySelector('link[rel="alternate"][hreflang="' + want + '"]');
    if (alt) { location.replace(alt.href + location.hash); return; }
  }
  document.addEventListener("DOMContentLoaded", function () {
    var toggle = document.querySelector("[data-lang-switch]");
    if (!toggle) return;
    toggle.addEventListener("click", function () {
      try { localStorage.setItem(KEY, toggle.getAttribute("hreflang")); } catch (e) {}
      toggle.href = toggle.href.split("#")[0] + location.hash;
    });
  });
})();
