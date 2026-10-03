// Findings of the catalogue that are known, each with the issue that tracks it. An entry is removed when
// its issue is fixed. Nothing may be listed here without an issue.
import type { Finding } from "./checks";

export type Known = { check: Finding["check"]; view?: string; variant?: string; what: RegExp; issue: number };

export const KNOWN: Known[] = [
  // The suite table scrolls sideways at 320 px and does not scroll a row's info button back into view.
  { check: "obscured", view: "bench", variant: "reflow320", what: /^button\.tip-btn has focus under div\.table-wrap$/, issue: 178 },
];

export function isKnown(f: Finding, view: string, variant: string): boolean {
  return KNOWN.some((k) => k.check === f.check && (!k.view || k.view === view) && (!k.variant || k.variant === variant) && k.what.test(f.what));
}
