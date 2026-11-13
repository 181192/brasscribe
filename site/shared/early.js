/* Put in every page's head by the build. It runs before anything is drawn: when the page is going to be
   read in Norwegian, <html> says so at once and the words stay hidden until scribe.js has put them in. */
(function () {
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
    document.documentElement.setAttribute("data-lang-wanted", "nb");
    setTimeout(function () { document.documentElement.removeAttribute("data-lang-wanted"); }, 2500);
  }
})();
