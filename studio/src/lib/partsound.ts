// Score part -> band SoundFont preset, following sounds/mapping.json `resolve` exactly (the
// reference is sounds/partsound.py; sounds/partsound-vectors.json are the shared test vectors):
// normalize, then exact part name, alias, first keyword contained in the name, instrument id or
// MusicXML instrument-sound, 0-based GM program. A brass part never falls back to General MIDI.

export interface TrackSound {
  program: number;
  bank: number;
  gainDb: number;
  percussion: boolean;
}

export interface ResolvedPart {
  part: string;
  step: "exact" | "alias" | "keyword" | "instrument" | "program";
  sound: TrackSound;
}

interface BandSoundfont {
  program: number;
  bank: number;
  channel_gain_db?: number;
  /** Balance when a layered preset plays only its first layer (the phone-sized SoundFont). */
  single_voice_gain_db?: number;
}

export interface Mapping {
  parts: Record<string, { band_soundfont?: BandSoundfont }>;
  resolve?: {
    aliases: Record<string, string>;
    keywords: [string, string][];
    instruments: Record<string, string>;
    programs: Record<string, string>;
  };
}

/** lowercase; ♭ -> b, ♯ -> #; every whitespace run (U+00A0 too) -> one space; trim. */
export function normalize(name: string): string {
  return name.toLowerCase().replaceAll("♭", "b").replaceAll("♯", "#").replace(/\s+/g, " ").trim();
}

export class PartSoundResolver {
  private readonly parts = new Map<string, { part: string; sound: TrackSound }>();

  /** singleVoice: the loaded SoundFont is the phone-sized build, whose layered presets keep one layer. */
  constructor(private readonly mapping: Mapping, singleVoice = false) {
    for (const [name, p] of Object.entries(mapping.parts)) {
      const b = p.band_soundfont;
      if (!b) continue;
      const gainDb = (singleVoice ? b.single_voice_gain_db : undefined) ?? b.channel_gain_db ?? 0;
      this.parts.set(normalize(name), {
        part: name,
        sound: { program: b.program, bank: b.bank, gainDb, percussion: b.bank === 128 },
      });
    }
  }

  resolve(name: string, instrument: string | null = null, program: number | null = null): ResolvedPart | null {
    const r = this.mapping.resolve;
    const n = normalize(name);
    let hit: string | undefined;
    let step: ResolvedPart["step"] | undefined;
    if (this.parts.has(n)) [hit, step] = [this.parts.get(n)!.part, "exact"];
    else if (r && n in r.aliases) [hit, step] = [r.aliases[n], "alias"];
    else if (r) {
      const kw = r.keywords.find(([text]) => n.includes(text));
      if (kw) [hit, step] = [kw[1], "keyword"];
    }
    if (hit === undefined && r && instrument !== null && instrument in r.instruments) [hit, step] = [r.instruments[instrument], "instrument"];
    if (hit === undefined && r && program !== null && String(program) in r.programs) [hit, step] = [r.programs[String(program)], "program"];
    if (hit === undefined) return null;
    const found = this.parts.get(normalize(hit));
    return found ? { part: found.part, step: step!, sound: found.sound } : null;
  }
}

export const DRUM_CHANNEL = 9;
export const METRONOME_CHANNEL = 16;

/**
 * One MIDI channel per part, percussion on channel 10 (index 9). alphaTab's synth has no
 * 16-channel limit (only 9 and its metronome's 16 are reserved); its own default of two channels
 * per track wraps past 16, so band parts would share channels and one would land on the drums.
 */
export function playbackChannels(percussion: boolean[]): number[] {
  let next = 0;
  return percussion.map((p) => {
    if (p) return DRUM_CHANNEL;
    while (next === DRUM_CHANNEL || next === METRONOME_CHANNEL) next++;
    return next++;
  });
}

/** Seconds of silence after the last note so alphaSynth does not cut the final release. */
export const RELEASE_TAIL_S = 1.5;

/** Synth master gain (-6 dB): headroom for the full band's tutti. */
export const MASTER_VOLUME = 0.5;
