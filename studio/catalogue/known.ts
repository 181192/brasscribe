// Findings of the catalogue that are known, each with the issue that tracks it. An entry is removed when
// its issue is fixed. Nothing may be listed here without an issue.
import type { Finding } from "./checks";

/** Each entry names the one view and variant it is for, so an entry that no longer matches anything is noticed. */
export type Known = { check: Finding["check"]; view: string; variant: string; what: RegExp; issue: number };

export const KNOWN: Known[] = [];

export function isKnown(f: Finding, view: string, variant: string): boolean {
  return KNOWN.some((k) => matches(k, f, view, variant));
}

function matches(k: Known, f: Finding, view: string, variant: string): boolean {
  return k.check === f.check && k.view === view && k.variant === variant && k.what.test(f.what);
}

/** The entries for this view and variant that matched none of its findings: fixed, so they go. */
export function stale(findings: Finding[], view: string, variant: string, known: Known[] = KNOWN): Known[] {
  return known.filter((k) => k.view === view && k.variant === variant && !findings.some((f) => matches(k, f, view, variant)));
}
