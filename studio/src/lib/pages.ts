// Pages: printed music a job reads instead of a recording (pictures or PDFs, in order). What the new-run
// form and the run view need to know of them, apart from the DOM.
import type { Job, ProfileInfo } from "../api/types";

/** What a job reads: a recording, or pages of printed music. */
export type Input = ProfileInfo["input"];

/** The most pages one job takes, and the largest one file may be (engine: pages.py). */
export const MAX_PAGES = 40;
export const MAX_PAGE_BYTES = 50 * 1024 * 1024;

/** What the file chooser offers for pages. A file is a page by what it holds, which the engine reads; this is by its name. */
export const PAGE_ACCEPT = "image/png,image/jpeg,image/webp,application/pdf,.png,.jpg,.jpeg,.webp,.pdf";

/** The profiles that read `input`. A profile that does not say what it reads listens to a recording. */
export function profilesFor(profiles: ProfileInfo[], input: Input): ProfileInfo[] {
  return profiles.filter((p) => (p.input === "pages") === (input === "pages"));
}

/** A picture or a PDF, by its type or its name: not a recording, whatever profile it was chosen for. */
export function looksLikePage(file: { name: string; type?: string }): boolean {
  return /^image\//.test(file.type ?? "") || file.type === "application/pdf" || /\.(png|jpe?g|webp|heic|heif|tiff?|bmp|gif|pdf)$/i.test(file.name);
}

/** `list` with the item at `i` moved one place up (-1) or down (+1); the same list when it is already at that end. */
export function moved<T>(list: readonly T[], i: number, by: -1 | 1): T[] {
  const j = i + by;
  const out = [...list];
  if (i < 0 || i >= out.length || j < 0 || j >= out.length) return out;
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}

/** Why these pages cannot be sent, before anything is: none, too many, or one too large. */
export function pagesProblem(files: readonly { size: number }[]): "none" | "too_many" | "too_large" | null {
  if (!files.length) return "none";
  if (files.length > MAX_PAGES) return "too_many";
  return files.some((f) => f.size > MAX_PAGE_BYTES) ? "too_large" : null;
}

/**
 * The job read pages. Its profile says so where the engine lists it; a run kept from before the reader was
 * taken off the computer is known by its first stage, which reads the pages.
 */
export function readsPages(job: Pick<Job, "profile" | "stages">, profiles: ProfileInfo[]): boolean {
  const profile = profiles.find((p) => p.name === job.profile);
  return profile ? profile.input === "pages" : job.stages[0]?.name === "read";
}

/**
 * The media type of a job's input, by its first bytes (as the engine tells pages apart): a picture, a PDF, or
 * the archive several pages are kept as. Null for anything else.
 */
export function pageFormat(head: Uint8Array): "image/png" | "image/jpeg" | "image/webp" | "application/pdf" | "application/zip" | null {
  const starts = (...bytes: number[]) => bytes.every((b, i) => head[i] === b);
  const text = (from: number, s: string) => [...s].every((c, i) => head[from + i] === c.charCodeAt(0));
  if (starts(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a)) return "image/png";
  if (starts(0xff, 0xd8, 0xff)) return "image/jpeg";
  if (text(0, "RIFF") && text(8, "WEBP")) return "image/webp";
  if (text(0, "%PDF-")) return "application/pdf";
  return text(0, "PK") ? "application/zip" : null;
}

/** The words a job that could not read its pages ends its error with (engine: sheet.py), by the name Studio's own words have. */
const READ_FAILURES: [string, string][] = [
  ["no notes were found on the page", "no_music"],
  ["there are more than 40 pages", "too_many_pages"],
  ["a page is too large to read", "page_too_large"],
  ["the pages could not be read", "not_read"],
  ["the reader's files could not be fetched: check the network and try again", "weights_missing"],
  ["no staff of notes was found on the page: a tab staff is not read", "only_tab"],
];

/** Which of the reader's failures `error` is, or null for any other error. */
export function readFailure(error: string): string | null {
  // The words end the error, or its first line when a traceback follows.
  const said = [error.trim(), error.trim().split("\n")[0].trim()];
  return READ_FAILURES.find(([words]) => said.some((line) => line.endsWith(words)))?.[1] ?? null;
}

/** What sheet.json says was read: counts, and the bars the reader is unsure of. */
export interface SheetSummary {
  staves: number;
  bars: number;
  notes: number;
  doubtful_bars: { staff: number; bar: number }[];
}
