// What a score's staves show (notation, tablature or both), read from the score as alphaTab loaded
// it, and the alphaTab stave profile that draws it.

/** The same three names the engine uses for what tab.musicxml shows (schemas.Tab `layout`). */
export type StaveLayout = "notation" | "tab" | "tab-and-notation";

/** The parts of alphaTab's Staff used here. */
export interface StaffLike {
  showTablature: boolean;
  showStandardNotation: boolean;
  isPercussion: boolean;
  /** The strings' open pitches; empty when the file gave no tuning. */
  tuning: number[];
}

export interface TrackLike {
  staves: StaffLike[];
}

/** alphaTab draws tablature for a staff only when it has the strings' tuning (MusicXML `staff-tuning`). */
export function showsTab(staff: StaffLike): boolean {
  return staff.showTablature && !staff.isPercussion && staff.tuning.length > 0;
}

/**
 * Makes every staff one alphaTab can draw: a staff left with neither notation nor tablature (a TAB
 * clef without a tuning) is drawn as notation. alphaTab's layout fails on a track with no staff to
 * draw ("Cannot read properties of undefined (reading 'staves')").
 */
export function makeDrawable(tracks: TrackLike[]): void {
  for (const track of tracks)
    for (const staff of track.staves)
      if (!showsTab(staff) && !staff.showStandardNotation) staff.showStandardNotation = true;
}

/** Tablature only, notation only, or both (in one part or across parts). Call after makeDrawable. */
export function staveLayout(tracks: TrackLike[]): StaveLayout {
  const staves = tracks.flatMap((t) => t.staves);
  const tab = staves.some(showsTab);
  const notation = staves.some((s) => s.showStandardNotation);
  return tab ? (notation ? "tab-and-notation" : "tab") : "notation";
}

/**
 * alphaTab's stave profile (the name in its `StaveProfile` enum) for a layout. `Score` draws only
 * notation and `Tab` only tablature, whatever the staff asks for: a tab-only part under `Score` has
 * no staff at all, which is how a tab used to fail to open. `ScoreTab` draws what each staff asks for.
 */
export const STAVE_PROFILE: Record<StaveLayout, "Score" | "Tab" | "ScoreTab"> = {
  notation: "Score",
  tab: "Tab",
  "tab-and-notation": "ScoreTab",
};

/** A part can be read aloud when it has no tablature: the talking score reads notation only. */
export function readable(track: TrackLike): boolean {
  return !track.staves.some(showsTab);
}

/**
 * Whether a score plays with the General MIDI set instead of the band's sounds: when none of its
 * pitched parts is a band instrument (a guitar tab, with or without a drum part: the band has a
 * kit for any drum part, so percussion does not decide). A score of percussion alone goes by that.
 */
export function playsGeneral(parts: { percussion: boolean; band: boolean }[]): boolean {
  const pitched = parts.filter((p) => !p.percussion);
  return !(pitched.length ? pitched : parts).some((p) => p.band);
}

/**
 * General MIDI program (0-based) for a fretted part: the file's own instrument when it names one,
 * else a fingered bass for a part called a bass or whose lowest string is a bass guitar's E or
 * lower, else a steel-string guitar. `named` is the part's <midi-program> (null when the file has
 * none, undefined when the file could not be read for it, as with compressed MusicXML: then a
 * loaded program other than alphaTab's default 0 counts as named).
 */
export function frettedProgram(name: string, tuning: number[], named?: number | null, loaded = 0): number {
  if (named != null) return named;
  if (named === undefined && loaded !== 0) return loaded;
  const BASS_LOW_E = 28;
  return /bass/i.test(name) || Math.min(...tuning) <= BASS_LOW_E ? 33 : 25;
}
