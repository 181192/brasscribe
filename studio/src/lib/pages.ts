// Pages: printed music a job reads instead of a recording (pictures or PDFs, in order). What the new-run
// form and the run view need to know of them, apart from the DOM.
import type { ProfileInfo } from "../api/types";

/** What a job reads: a recording, or pages of printed music. */
export type Input = ProfileInfo["input"];

/** The most pages one job takes, and the largest one file may be (engine: pages.py). */
export const MAX_PAGES = 40;
export const MAX_PAGE_BYTES = 50 * 1024 * 1024;
/** The two limits as the words say them: {max} pages, {mb} MB. */
export const PAGE_LIMITS = { max: MAX_PAGES, mb: MAX_PAGE_BYTES / 1024 / 1024 };

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

/** The pictures a job's input is shown as, by the media type the engine sends it with; anything else is a file to open. */
const PICTURES = ["image/png", "image/jpeg", "image/webp"] as const;

/**
 * What a job's input is, by the media type of the engine's answer: one of the three pictures (the blob's type is
 * taken from this fixed list, never from the header), a PDF, the archive several pages are kept as, or other.
 */
export function inputKind(contentType: string | null): { kind: "picture"; type: (typeof PICTURES)[number] } | { kind: "pdf" | "archive" | "other" } {
  const media = (contentType ?? "").split(";")[0].trim().toLowerCase();
  const picture = PICTURES.find((t) => t === media);
  if (picture) return { kind: "picture", type: picture };
  return { kind: media === "application/pdf" ? "pdf" : media === "application/zip" ? "archive" : "other" };
}

/** The words a job that could not read its pages ends its error with (engine: sheet.py), by the name Studio's own words have. */
const READ_FAILURES: [string, string][] = [
  ["no notes were found on the page", "no_music"],
  ["there are more than 40 pages", "too_many_pages"],
  ["a page is too large to read", "page_too_large"],
  ["the pages could not be read", "not_read"],
  ["the reader's files could not be fetched: check the network and try again", "weights_missing"],
  ["no staff of notes was found on the page: a tab staff is not read", "only_tab"],
  ["the computer's disk is full: free some space on it and try again", "no_space"],
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
