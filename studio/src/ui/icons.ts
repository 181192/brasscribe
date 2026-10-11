// Icons and the Studio lockup from the design system. icons.js (generated from
// design/tokens/icons.json) defines globalThis.BrasscribeIcons: path data on the
// Material Symbols 960 grid, keyed by action.
import "../../../design/dist/web/icons.js";
import lockupSvg from "../../../design/brand/logo/lockup-studio.svg";

declare global {
  // eslint-disable-next-line no-var
  var BrasscribeIcons: Record<string, string>;
}

const NS = "http://www.w3.org/2000/svg";

/** A decorative icon (aria-hidden); the button or link next to it carries the name. */
export function icon(name: string, cls = "i"): SVGSVGElement {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 -960 960 960");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("class", cls);
  const d = globalThis.BrasscribeIcons?.[name];
  if (d) {
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d);
    svg.append(p);
  }
  return svg;
}

export function hasIcon(name: string): boolean {
  return !!globalThis.BrasscribeIcons?.[name];
}

/**
 * The "Brasscribe Studio" lockup, recoloured from the tokens so it follows the
 * theme (brass mark, ink wordmark, brass italic "Studio").
 */
export function lockup(): SVGSVGElement {
  const themed = lockupSvg
    .replace(/fill="#A57A2C"/g, 'style="fill:var(--scribe-brand)"')
    .replace(/fill="#1B1A17"/g, 'style="fill:var(--scribe-text)"')
    .replace(/fill="#7A5719"/g, 'style="fill:var(--scribe-brand-text)"');
  const doc = new DOMParser().parseFromString(themed, "image/svg+xml");
  const svg = document.importNode(doc.documentElement, true) as unknown as SVGSVGElement;
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  return svg;
}
