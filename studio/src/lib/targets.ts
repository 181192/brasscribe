// Targets: what the engine makes (a brass-band score, a tab for a fretted instrument). Every profile
// belongs to one (ProfileInfo.target), and a target names its own files. Studio serves every target.
import type { ProfileInfo } from "../api/types";

export type Target = ProfileInfo["target"];

/** The targets, in the order Studio lists them. */
export const TARGETS: readonly Target[] = ["brass", "fretted"];

/** The name of a target's score file without its suffix, as the engine writes it (engine: targets.py). */
const STEM: Record<Target, string> = { brass: "brass-band", fretted: "tab" };

/** A target's score in one format: scoreFile("brass", "pdf") is brass-band.pdf. */
export function scoreFile(target: Target, ext: string): string {
  return `${STEM[target]}.${ext}`;
}

/** Whether any target's score in this format is among `outputs`. */
export function hasScore(outputs: readonly string[] | undefined | null, ext: string): boolean {
  return TARGETS.some((target) => !!outputs?.includes(scoreFile(target, ext)));
}
