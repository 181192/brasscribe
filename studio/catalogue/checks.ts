// The catalogue's checks, each a function of the page as it stands that returns its findings (empty when
// the view passes). checks.spec.ts shows each one failing on a view broken on purpose.
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

export type Finding = { check: "axe" | "clipped" | "reach" | "order" | "hidden-focus" | "obscured" | "reflow" | "spacing"; what: string };

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

/** axe-core with the WCAG 2.2 AA rules: every serious or critical violation, one finding per element. */
export async function axe(page: Page): Promise<Finding[]> {
  const res = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  return res.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .flatMap((v) => v.nodes.map((n) => ({ check: "axe" as const, what: `${v.id}: ${n.target.join(" ")}` })));
}

/**
 * Text that is cut off: by its own box or by a box it is in that hides what overflows it (overflow hidden or
 * clip, so also an ellipsis), on either axis. A part that scrolls hides nothing: text out of its view can be
 * scrolled to. Visually hidden text (the screen-reader-only pattern) and the engraved score are left out.
 */
export async function clipped(page: Page, check: "clipped" | "spacing" = "clipped"): Promise<Finding[]> {
  const cut = await page.evaluate(() => {
    const describe = (el: Element) => {
      const parts: string[] = [];
      for (let e: Element | null = el; e && e !== document.body && parts.length < 3; e = e.parentElement) {
        parts.unshift(e.id ? `${e.localName}#${e.id}` : `${e.localName}${[...e.classList].slice(0, 2).map((c) => `.${c}`).join("")}`);
        if (e.id) break;
      }
      return parts.join(" > ");
    };
    const srOnly = (el: Element) => {
      for (let e: Element | null = el; e; e = e.parentElement) {
        const r = e.getBoundingClientRect();
        const s = getComputedStyle(e);
        if (r.width <= 1 && r.height <= 1 && (s.overflow === "hidden" || s.clip !== "auto" || s.clipPath !== "none")) return true;
      }
      return false;
    };
    const out = new Map<Element, string>();
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode as Text;
      const text = node.textContent?.trim();
      const el = node.parentElement;
      if (!text || !el || out.has(el) || el.closest("svg, script, style, template, .score-surface, .at-surface")) continue;
      if (getComputedStyle(el).visibility !== "visible") continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      const rects = [...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0);
      if (!rects.length || srOnly(el)) continue;
      for (let a: Element | null = el; a && a !== document.documentElement; a = a.parentElement) {
        const s = getComputedStyle(a);
        if (s.display === "contents") continue;
        const hidesX = s.overflowX === "hidden" || s.overflowX === "clip";
        const hidesY = s.overflowY === "hidden" || s.overflowY === "clip";
        const scrolls = /auto|scroll/.test(`${s.overflowX} ${s.overflowY}`);
        if (!hidesX && !hidesY && !scrolls) continue;
        const ellipsis = a === el && s.textOverflow === "ellipsis" && a.scrollWidth > a.clientWidth + 1;
        const b = a.getBoundingClientRect();
        const left = b.left + a.clientLeft;
        const top = b.top + a.clientTop;
        const outside = rects.some((r) =>
          (hidesX && (r.left < left - 1 || r.right > left + a!.clientWidth + 1)) || (hidesY && (r.top < top - 1 || r.bottom > top + a!.clientHeight + 1)));
        if (ellipsis || (outside && (hidesX || hidesY))) {
          out.set(el, `${describe(el)} "${text.slice(0, 40)}"${a === el ? "" : ` (cut by ${describe(a)})`}`);
          break;
        }
        if (scrolls) break;
      }
    }
    return [...out.values()];
  });
  return cut.map((what) => ({ check, what }));
}

/** The page scrolls sideways (WCAG 1.4.10): the elements that stick out, outside any part that scrolls. */
export async function reflow(page: Page, check: "reflow" | "spacing" = "reflow"): Promise<Finding[]> {
  const wide = await page.evaluate(() => {
    const root = document.documentElement;
    if (root.scrollWidth - root.clientWidth <= 1) return [];
    const out: string[] = [];
    for (const el of Array.from(document.body.querySelectorAll("*"))) {
      const r = el.getBoundingClientRect();
      if (r.right <= root.clientWidth + 1 || r.width === 0) continue;
      let inScroller = false;
      for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
        if (/auto|scroll|hidden|clip/.test(getComputedStyle(a).overflowX)) inScroller = true;
      }
      // Only the outermost element that sticks out: its children stick out with it.
      const parent = el.parentElement?.getBoundingClientRect();
      if (!inScroller && !(parent && parent.right > root.clientWidth + 1 && el.parentElement !== document.body)) {
        out.push(`${el.localName}${el.id ? `#${el.id}` : ""}${[...el.classList].slice(0, 2).map((c) => `.${c}`).join("")} reaches ${Math.round(r.right)} px`);
      }
    }
    return [`the page is ${root.scrollWidth} px wide in a ${root.clientWidth} px window`, ...out.slice(0, 3)];
  });
  return wide.map((what) => ({ check, what }));
}

/**
 * The keyboard: Tab from the top of the page until focus comes round again. Every element a pointer can act
 * on must be reached (an inactive tab of a tab list, reached with the arrow keys, is not one of them), focus
 * must not stop on something that cannot be seen, and it must go through the page in reading order: the order
 * of the document, and never back up the page within one column.
 */
export async function keyboard(page: Page): Promise<Finding[]> {
  const targets = await page.evaluate(() => {
    const ACTION = "a[href], button, input:not([type=hidden]), select, textarea, summary, [tabindex], [contenteditable=''], [contenteditable=true], " +
      "[role=button], [role=link], [role=checkbox], [role=switch], [role=tab], [role=menuitem], [role=option], [role=radio], [role=slider], [role=spinbutton], [role=textbox], [role=combobox]";
    const COMPOSITE = "[role=tablist], [role=menu], [role=menubar], [role=listbox], [role=radiogroup], [role=grid], [role=tree], [role=toolbar]";
    const shown = (el: Element) => {
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) return false;
      return el.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true }) && !el.closest("[inert]");
    };
    // A modal dialog makes the rest of the page inert: only the dialog is walked.
    const scope: Element = document.querySelector("dialog:modal") ?? document.body;
    const all = Array.from(scope.querySelectorAll<HTMLElement>(ACTION));
    // On a layer of its own (a header that stays, a menu or tip over the page): its place says nothing of the reading order.
    const floating = (el: Element) => {
      for (let e: Element | null = el; e; e = e.parentElement) if (/fixed|sticky|absolute/.test(getComputedStyle(e).position)) return true;
      return false;
    };
    let k = 0;
    const out: { k: number; name: string; top: number; bottom: number; left: number; right: number; expected: boolean; floating: boolean }[] = [];
    for (const el of all) {
      if (!shown(el) || (el as HTMLButtonElement).disabled || (el.getAttribute("aria-disabled") === "true" && el.localName !== "button")) continue;
      const ti = el.getAttribute("tabindex");
      // A focus target (a heading, the main region) is not an action; neither is a roving item of a composite.
      let notAction = ti === "-1" && (!!el.closest(COMPOSITE) || !el.matches(ACTION.replace(", [tabindex]", "")) || ["h1", "h2", "h3", "main", "li"].includes(el.localName));
      // Of a group of radio buttons Tab stops on the one chosen (or the first); the arrows move between them.
      if (el instanceof HTMLInputElement && el.type === "radio" && el.name) {
        const group = Array.from(document.querySelectorAll<HTMLInputElement>(`input[type=radio][name="${CSS.escape(el.name)}"]`)).filter((r) => r.form === el.form);
        notAction ||= el !== (group.find((r) => r.checked) ?? group[0]);
      }
      const r = el.getBoundingClientRect();
      el.dataset.catK = String(k);
      const label = (el.getAttribute("aria-label") ?? el.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 40);
      const kind = el instanceof HTMLInputElement ? `[type=${el.type}]` : "";
      out.push({ k: k++, name: `${el.localName}${kind}${el.id ? `#${el.id}` : ""}${label ? ` "${label}"` : ""}`, top: r.top + scrollY, bottom: r.bottom + scrollY,
        left: r.left + scrollX, right: r.right + scrollX, expected: !notAction, floating: floating(el) });
    }
    // Tab starts from the top of the page.
    const start = document.createElement("span");
    start.tabIndex = -1;
    start.id = "catalogue-start";
    scope.prepend(start);
    start.focus();
    return out;
  });
  const findings: Finding[] = [];
  const seen: number[] = [];
  const max = targets.length * 2 + 20;
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    const at = await page.evaluate(async () => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body || el.id === "catalogue-start") return null;
      // Let what focus starts settle first: a transition (the skip link sliding in) and a smooth scroll.
      await Promise.all(el.getAnimations().map((a) => a.finished.catch(() => undefined)));
      const where = () => {
        const b = el.getBoundingClientRect();
        return `${scrollX},${scrollY},${b.left},${b.top}`;
      };
      for (let n = 0, last = where(); n < 60; n++) {
        await new Promise((res) => requestAnimationFrame(res));
        const now = where();
        if (now === last) break;
        last = now;
      }
      const r = el.getBoundingClientRect();
      const visible = r.width > 0 && r.height > 0 && el.checkVisibility();
      // WCAG 2.4.11: focus is not hidden. What is on top at the focused element's centre must be the element
      // itself, something inside it, or its label (a file input hidden behind the button that is its label).
      const label = (e: Element) => `${e.localName}${e.id ? `#${e.id}` : ""}${[...e.classList].slice(0, 2).map((c) => `.${c}`).join("")}`;
      // The part of it that can be seen: inside the window and inside every box around it that clips.
      let [x0, y0, x1, y1] = [Math.max(r.left, 0), Math.max(r.top, 0), Math.min(r.right, innerWidth), Math.min(r.bottom, innerHeight)];
      let clipper = "the edge of the window";
      for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
        if (getComputedStyle(a).overflow === "visible") continue;
        const b = a.getBoundingClientRect();
        [x0, y0, x1, y1] = [Math.max(x0, b.left), Math.max(y0, b.top), Math.min(x1, b.right), Math.min(y1, b.bottom)];
        if (x1 - x0 < 1 || y1 - y0 < 1) {
          clipper = label(a);
          break;
        }
      }
      const cx = (x0 + x1) / 2;
      const cy = (y0 + y1) / 2;
      let covered: string | null = null;
      if (visible && (x1 - x0 < 1 || y1 - y0 < 1)) covered = clipper;
      else if (visible) {
        const top = document.elementFromPoint(cx, cy);
        if (top && top !== el && !el.contains(top) && top.closest("label")?.control !== el) covered = label(top);
      }
      return { k: el.dataset.catK ? Number(el.dataset.catK) : -1, name: label(el), visible, covered };
    });
    if (!at) break;
    if (at.k >= 0 && seen.includes(at.k)) break;
    if (!at.visible) findings.push({ check: "hidden-focus", what: `Tab stops on ${at.name}, which cannot be seen` });
    else if (at.covered) findings.push({ check: "obscured", what: `${at.name} has focus under ${at.covered}` });
    if (at.k >= 0) seen.push(at.k);
  }
  await page.evaluate(() => document.getElementById("catalogue-start")?.remove());
  for (const t of targets) {
    if (t.expected && !seen.includes(t.k)) findings.push({ check: "reach", what: `Tab never reaches ${t.name}` });
  }
  // A positive tabindex takes an element out of the page's order (put first, from the address bar on).
  for (const name of await page.evaluate(() => Array.from(document.querySelectorAll<HTMLElement>("[tabindex]"))
    .filter((el) => el.tabIndex > 0).map((el) => `${el.localName}${el.id ? `#${el.id}` : ""} (tabindex ${el.tabIndex})`))) {
    findings.push({ check: "order", what: `${name} is taken out of the order of the page` });
  }
  const byK = new Map(targets.map((t) => [t.k, t]));
  for (let i = 1; i < seen.length; i++) {
    const a = byK.get(seen[i - 1])!;
    const b = byK.get(seen[i])!;
    if (b.k < a.k) findings.push({ check: "order", what: `Tab goes from ${a.name} back to ${b.name}, earlier in the page` });
    else if (!a.floating && !b.floating && b.bottom <= a.top + 1 && Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0) {
      findings.push({ check: "order", what: `Tab goes from ${a.name} up to ${b.name}, above it` });
    }
  }
  return findings;
}

/** WCAG 1.4.12 text spacing: with the user's spacing, the page still fits and no text is cut. */
export async function textSpacing(page: Page): Promise<Finding[]> {
  await page.addStyleTag({ content: "* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; } p { margin-bottom: 2em !important; }" });
  await page.waitForTimeout(100);
  return [...await reflow(page, "spacing"), ...await clipped(page, "spacing")];
}
