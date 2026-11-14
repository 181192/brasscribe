// The variant rail: where an app runs. Without this script each chip is a link to its panel, and every panel is on
// the page. With it the chips are tabs: one panel shows, the arrow keys move between chips, and the choice follows
// the address (#mac), so a link to a place on the page opens that place. The page's language script may swap the
// rail's words; the choice stays.

const roots = () => document.querySelectorAll("[data-rail-root]");
let chosen = null;

function set(root, id, focus) {
  const chips = [...root.querySelectorAll(".rail a[data-variant]")];
  const panels = [...root.querySelectorAll(".variant-panel")];
  if (!chips.some((c) => c.dataset.variant === id)) id = chips[0]?.dataset.variant;
  for (const chip of chips) {
    const on = chip.dataset.variant === id;
    chip.setAttribute("aria-selected", String(on));
    chip.tabIndex = on ? 0 : -1;
    if (on && focus) chip.focus();
  }
  for (const panel of panels) {
    panel.classList.toggle("chosen", panel.dataset.variant === id);
    panel.hidden = panel.dataset.variant !== id;
  }
  chosen = id;
}

let started = false;
function make(root) {
  const list = root.querySelector(".rail");
  if (!list) return;
  list.setAttribute("role", "tablist");
  for (const li of list.children) li.setAttribute("role", "presentation");
  for (const chip of list.querySelectorAll("a[data-variant]")) {
    const panel = root.querySelector(`.variant-panel[data-variant="${chip.dataset.variant}"]`);
    if (!panel) continue;
    chip.setAttribute("role", "tab");
    chip.id = `tab-${chip.dataset.variant}`;
    chip.setAttribute("aria-controls", panel.id);
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", chip.id);
    panel.tabIndex = -1;
  }
  const wanted = location.hash.slice(1);
  const asked = root.querySelector(`.variant-panel[data-variant="${wanted}"]`);
  set(root, chosen ?? wanted, false);
  if (asked && !started) asked.scrollIntoView();
}

document.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-rail-root] .rail a[data-variant]");
  if (!chip) return;
  e.preventDefault();
  set(chip.closest("[data-rail-root]"), chip.dataset.variant, true);
  history.replaceState(null, "", `#${chip.dataset.variant}`);
});

document.addEventListener("keydown", (e) => {
  const chip = e.target.closest?.("[data-rail-root] .rail a[data-variant]");
  if (!chip) return;
  const chips = [...chip.closest(".rail").querySelectorAll("a[data-variant]")];
  const i = chips.indexOf(chip);
  const to = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: chips.length - 1 }[e.key];
  if (to === undefined) return;
  e.preventDefault();
  set(chip.closest("[data-rail-root]"), chips[(to + chips.length) % chips.length].dataset.variant, true);
});

addEventListener("hashchange", () => {
  const id = location.hash.slice(1);
  for (const root of roots()) {
    if (root.querySelector(`.variant-panel[data-variant="${id}"]`)) {
      set(root, id, false);
      root.querySelector(`.variant-panel[data-variant="${id}"]`)?.scrollIntoView();
    }
  }
});

document.addEventListener("scribe:lang", () => roots().forEach(make));
roots().forEach(make);
started = true;

// On a download page the rail leads to every panel, all of them shown; the visitor's own device is marked, when the
// browser says which it is, and its download becomes the filled button of its panel. [place, download]
const device = () => {
  const ua = navigator.userAgent;
  if (/iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return ["tablet", "ios"];
  if (/Android/.test(ua)) return [/Mobile/.test(ua) ? "phone" : "tablet", "android"];
  if (/iPhone/.test(ua)) return ["phone", "ios"];
  if (/Macintosh/.test(ua)) return ["mac", "mac"];
  if (/Windows/.test(ua)) return ["windows", "windows"];
  return [];
};
const markMine = () => {
  const rail = document.querySelector("main.downloads .rail"), [mine, group] = device();
  const chip = mine && rail?.querySelector(`a[data-variant="${mine}"]`);
  if (!chip) return;
  chip.classList.add("mine");
  // The tag is part of the link's words, so a screen reader says it too.
  if (!chip.querySelector(".mine-tag")) chip.insertAdjacentHTML("beforeend", ` <span class="mine-tag">${rail.dataset.mine}</span>`);
  // A panel with two downloads (Android and iPhone) fills the visitor's; the other stays outlined.
  const own = document.querySelector(`main.downloads .dl-device[data-group="${group}"] .button`);
  const filled = own?.closest("section").querySelector(".button.primary");
  if (own && filled && filled !== own) {
    filled.classList.replace("primary", "outline");
    own.classList.replace("outline", "primary");
  }
};
document.addEventListener("scribe:lang", markMine);
markMine();

// The family's pen draws under a heading once, when it first comes into view.
const pen = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) { e.target.classList.add("drawn"); pen.unobserve(e.target); }
}, { threshold: 0.6 });
const drawPens = () => document.querySelectorAll(".pen-heading:not(.drawn), .line-hero:not(.drawn)").forEach((el) => pen.observe(el));
document.addEventListener("scribe:lang", drawPens);
drawPens();
