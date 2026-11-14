/* Put in every page's head by the build. It runs before anything is drawn: when the page is going to be
   read in Norwegian, <html> says so at once and the words stay hidden until scribe.js has put them in. */
(function () {
  var root = document.documentElement;
  root.classList.add("js");  /* what a script will work can take its place at once */
  /* What moves by itself on a page moves once a visit: after that the page opens as it ends (showcase.js, rail.js). */
  try { if (sessionStorage.getItem("scribe-played:" + location.pathname)) root.classList.add("played"); } catch (e) {}
  var want = null;
  try { want = localStorage.getItem("scribe-lang"); } catch (e) {}
  var asked = /[?&]lang=(en|nb)\b/.exec(location.search);
  if (asked) want = asked[1];
  if (!want) {
    var langs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || "en"];
    for (var i = 0; i < langs.length && !want; i++) {
      if (/^(nb|nn|no)\b/i.test(langs[i])) want = "nb";
      else if (/^en\b/i.test(langs[i])) want = "en";
    }
  }
  if (want === "nb") {
    /* The page stays hidden until its Norwegian words are in, so no English is seen first. The words are fetched from
       here, at once, beside the styles; scribe.js takes them from this fetch. If they never come, the page is shown
       in English a moment after the fetch has ended (or after five seconds at the most). */
    root.setAttribute("data-lang-wanted", "nb");
    var show = function () { root.removeAttribute("data-lang-wanted"); };
    var words = document.createElement("link");
    words.rel = "preload"; words.as = "fetch"; words.crossOrigin = "anonymous";
    words.href = new URL("nb.json", location.href.split(/[?#]/)[0]).href;
    words.onload = words.onerror = function () { setTimeout(show, 300); };
    document.head.appendChild(words);
    setTimeout(show, 5000);
  }
})();
