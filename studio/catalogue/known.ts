// Findings of the catalogue that are known, each with the issue that tracks it. An entry is removed when
// its issue is fixed. Nothing may be listed here without an issue.
import type { Finding } from "./checks";

export type Known = { check: Finding["check"]; view?: string; variant?: string; what: RegExp; issue: number };

export const KNOWN: Known[] = [
  // The suite table scrolls sideways at 320 px and does not scroll a row's info button back into view.
  { check: "obscured", view: "bench", variant: "reflow320", what: /^button\.tip-btn has focus under div\.table-wrap$/, issue: 178 },
  // Narrowed after it opened wide, the player's part list keeps its width and the page scrolls sideways.
  { check: "reflow", view: "run-score", variant: "reflow320", what: /^(the page is \d+ px wide in a 320 px window|div\.group reaches \d+ px)$/, issue: 192 },
  // Tab past the end of the open narrow menu moves focus into the page under it.
  { check: "obscured", view: "menu", variant: "reflow320", what: /^input has focus under div\.theme-switch$/, issue: 192 },
];

export function isKnown(f: Finding, view: string, variant: string): boolean {
  return KNOWN.some((k) => k.check === f.check && (!k.view || k.view === view) && (!k.variant || k.variant === variant) && k.what.test(f.what));
}
