// The instruments a tab is written for and the tunings each has, as the engine takes them (engine: tab.py,
// TUNINGS, with the basses of bass_tab.py). The first tuning of each is its usual one and the engine's default.
import { t } from "../i18n";

/** In the order Studio lists them: the engine's default (a six-string guitar) first. */
export const TUNINGS: Readonly<Record<string, readonly string[]>> = {
  "guitar-6": ["standard", "eb-standard", "d-standard", "c-standard", "drop-d", "drop-c", "drop-b", "dadgad", "open-g", "open-d", "open-e"],
  "guitar-7": ["standard", "eb-standard"],
  "guitar-8": ["standard"],
  "bass-4": ["standard", "eb-standard", "d-standard", "drop-d", "bead"],
  "bass-5": ["standard", "drop-a"],
  "bass-6": ["standard"],
  ukulele: ["high-g", "low-g"],
  "ukulele-baritone": ["standard"],
  mandolin: ["standard"],
};

export const DEFAULT_INSTRUMENT = "guitar-6";

/** The profiles that write a tab from pages and take an instrument and its tuning. */
export const TAB_FROM_PAGES = "sheet-tab";

/** An instrument as a player names it: "6-string guitar", "Baritone ukulele". */
export function instrumentName(instrument: string): string {
  return t(`tab.instrument.${instrument}`);
}

/** The instruments whose one tuning is named by its strings, not "Standard" (engine: tab.py, SINGLE_PRESET). */
const NAMED_BY_STRINGS = ["ukulele-baritone", "mandolin"];

/**
 * A tuning's name. The one tuning of a baritone ukulele and of a mandolin is named by its strings ("D G B E"),
 * the others by their usual names ("Drop D", "High G").
 */
export function tuningName(instrument: string, tuning: string): string {
  return NAMED_BY_STRINGS.includes(instrument) ? t(`tab.tuning.of.${instrument}`) : t(`tab.tuning.${tuning}`);
}
