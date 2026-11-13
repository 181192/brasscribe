// The language of the page. Every page has one address and is written in English; its Norwegian words are in
// nb.json beside it. The choice is, in this order: ?lang= in the address (which is then remembered, so an old
// Norwegian address stays Norwegian on the next page), what was chosen before, the browser's language.
// Changing it swaps the words where they stand, and says so to the scripts that draw things
// (the "scribe:lang" event on document, with the parts that were replaced).

const KEY = "scribe-lang";
const root = document.documentElement;
const NAMES = { en: "English", nb: "Norsk" };
let english = null, norwegian = null, now = "en";

const wanted = () => {
  const asked = new URLSearchParams(location.search).get("lang");
  if (asked === "en" || asked === "nb") return asked;
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "en" || saved === "nb") return saved;
  } catch {}
  for (const lang of navigator.languages?.length ? navigator.languages : [navigator.language || "en"]) {
    if (/^(nb|nn|no)\b/i.test(lang)) return "nb";
    if (/^en\b/i.test(lang)) return "en";
  }
  return "en";
};

// The page's words as it stands, to put back when English is chosen again.
const read = () => {
  const words = { t: {}, a: {}, slots: {}, title: document.title, description: document.querySelector('meta[name="description"]')?.content };
  for (const el of document.querySelectorAll("[data-t]")) words.t[el.dataset.t] ??= el.innerHTML;
  for (const el of document.querySelectorAll("*")) {
    for (const { name, value } of el.attributes) if (name.startsWith("data-t-")) words.a[value] ??= el.getAttribute(name.slice(7));
  }
  for (const el of document.querySelectorAll("[data-slot]")) words.slots[el.dataset.slot] = el.innerHTML;
  const main = document.querySelector("main");
  if (main && !main.querySelector("[data-t], [data-slot]")) words.main = main.innerHTML;
  return words;
};

// Where the reader is: the heading, figure or table nearest the top of the window, and how far from it. The words
// of another language take another amount of room; the reader stays at the same thing. Both languages have the
// same headings, figures and tables in the same order, so it is found again by its number.
const MARKS = "main :is(h1, h2, h3, h4, figure, table)";
const marks = () => [...document.querySelectorAll(MARKS)].filter((el) => el.getClientRects().length);
const place = () => {
  if (scrollY < 1) return null;
  const all = marks();
  let nth = -1, near = Infinity;
  all.forEach((el, i) => {
    const far = Math.abs(el.getBoundingClientRect().top - 80);
    if (far < near) [nth, near] = [i, far];
  });
  return nth < 0 ? null : { nth, top: all[nth].getBoundingClientRect().top };
};
const back = (was) => {
  const at = was && marks()[was.nth];
  if (at) scrollBy({ top: at.getBoundingClientRect().top - was.top, behavior: "instant" });
};

const write = (words, lang) => {
  const replaced = [], was = place();
  root.lang = lang;
  document.title = words.title;
  const description = document.querySelector('meta[name="description"]');
  if (description && words.description) description.content = words.description;
  if (words.main !== undefined) {
    const main = document.querySelector("main");
    main.innerHTML = words.main;
    replaced.push(main);
  }
  for (const el of document.querySelectorAll("[data-slot]")) {
    if (words.slots[el.dataset.slot] === undefined) continue;
    el.innerHTML = words.slots[el.dataset.slot];
    replaced.push(el);
  }
  for (const el of document.querySelectorAll("[data-t]")) if (words.t[el.dataset.t] !== undefined) el.innerHTML = words.t[el.dataset.t];
  for (const el of document.querySelectorAll("*")) {
    for (const { name, value } of [...el.attributes]) {
      if (name.startsWith("data-t-") && words.a[value] !== undefined) el.setAttribute(name.slice(7), words.a[value]);
    }
  }
  for (const button of document.querySelectorAll("[data-lang-switch]")) {
    const other = lang === "nb" ? "en" : "nb";
    // On the narrowest phones the bar has room for two letters; the name stays for those who hear it.
    button.innerHTML = `<span class="lang-long">${NAMES[other]}</span><span class="lang-short" aria-hidden="true">${other === "nb" ? "NO" : "EN"}</span>`;
    button.lang = other;
    button.hidden = false;
  }
  now = lang;
  root.removeAttribute("data-lang-wanted");
  document.dispatchEvent(new CustomEvent("scribe:lang", { detail: { lang, replaced } }));
  // Once now, and once more when the figures that draw themselves have taken their room.
  back(was);
  if (was) requestAnimationFrame(() => back(was));
  if (was) setTimeout(() => back(was), 300);  // and when the charts have drawn
};

export const language = () => now;

// An address that names a place on the page (#…): the browser went there while the page was English; the
// Norwegian words take another amount of room, so go there again once they are in.
const named = () => {
  const at = location.hash.length > 1 && document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if (!at) return;
  at.scrollIntoView({ behavior: "instant" });
  requestAnimationFrame(() => at.scrollIntoView({ behavior: "instant" }));
  // Once more when pictures and faces have arrived, unless the reader has moved on.
  const y = scrollY;
  setTimeout(() => Math.abs(scrollY - y) < 400 && at.scrollIntoView({ behavior: "instant" }), 600);
};

async function choose(lang, remember) {
  if (remember) try { localStorage.setItem(KEY, lang); } catch {}
  if (lang === now) return write(english ?? read(), lang);
  english ??= read();
  if (lang === "nb") {
    try {
      norwegian ??= await (await fetch(new URL("nb.json", location.href.split(/[?#]/)[0]))).json();
    } catch {
      return write(english, "en");  // the words did not arrive: the page stays as it is
    }
  }
  write(lang === "nb" ? norwegian : english, lang);
}

document.addEventListener("click", (e) => {
  const button = e.target.closest("[data-lang-switch]");
  if (button) choose(now === "nb" ? "en" : "nb", true);
});
const first = wanted();
choose(first, new URLSearchParams(location.search).has("lang")).then(() => first !== "en" && named());
