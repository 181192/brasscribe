/* Put in every page's head by the build. It runs before anything is drawn: when the page is going to be
   read in Norwegian, <html> says so at once and the words stay hidden until scribe.js has put them in. */
(function () {
  var root = document.documentElement;
  root.classList.add("js");  /* what a script will work can take its place at once */
  /* What moves by itself on a page moves once in half an hour, in any tab: after that the page opens at rest
     (showcase.js keeps the time). Until then it is drawn where its motion starts ("starting"); if the scripts that move
     it never come, it is put at rest a second after the page has loaded. */
  var played = false;
  try { played = Date.now() - Number(localStorage.getItem("scribe-played:" + location.pathname) || 0) < 30 * 60 * 1000; } catch (e) {}
  root.classList.add(played ? "played" : "starting");
  addEventListener("load", function () {
    setTimeout(function () { if (!root.classList.contains("moving")) root.classList.remove("starting"); }, 1000);
  });
  var want = null;
  try { want = localStorage.getItem("scribe-lang"); } catch (e) {}
  if (want !== "en" && want !== "nb") want = null;
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
    /* The page stays hidden until scribe.js has put its Norwegian words in, so no English is seen first. The words
       are fetched from here, at once, beside the styles; scribe.js takes them from this fetch. If they cannot be
       had, the page is shown in English a moment later, and after three seconds at the most. */
    root.setAttribute("data-lang-wanted", "nb");
    var show = function () { root.removeAttribute("data-lang-wanted"); };
    var words = document.createElement("link");
    words.rel = "preload"; words.as = "fetch"; words.crossOrigin = "anonymous";
    words.href = new URL("nb.json", location.href.split(/[?#]/)[0]).href;
    words.onerror = function () { setTimeout(show, 300); };
    document.head.appendChild(words);
    setTimeout(show, 3000);
  }
})();
