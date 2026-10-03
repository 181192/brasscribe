// Findings of the catalogue that are known, each with the issue that tracks it. An entry is removed when
// its issue is fixed. Nothing may be listed here without an issue.
import type { Finding } from "./checks";

/** Each entry names the one view and variant it is for, so an entry that no longer matches anything is noticed. */
export type Known = { check: Finding["check"]; view: string; variant: string; what: RegExp; issue: number };

export const KNOWN: Known[] = [
  // The suite table scrolls sideways at 320 px and does not scroll a row's info button back into view.
  { check: "obscured", view: "bench", variant: "reflow320", what: /^button\.tip-btn has focus under div\.table-wrap$/, issue: 178 },
];

export function isKnown(f: Finding, view: string, variant: string): boolean {
  return KNOWN.some((k) => matches(k, f, view, variant));
}

function matches(k: Known, f: Finding, view: string, variant: string): boolean {
  return k.check === f.check && k.view === view && k.variant === variant && k.what.test(f.what);
}

/** The entries for this view and variant that matched none of its findings: fixed, so they go. */
export function stale(findings: Finding[], view: string, variant: string): Known[] {
  return KNOWN.filter((k) => k.view === view && k.variant === variant && !findings.some((f) => matches(k, f, view, variant)));
}
