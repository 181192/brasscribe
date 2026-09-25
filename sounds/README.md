# sounds: realistic playback tier

Sample fetching, brass-band instrument building, seating and room placement, and the offline reference renderer the native players are expected to match (docs/plan/apps-plan.md §5.4).

## Run it

```sh
uv run sounds/fetch.py                                   # ~700 MB into data/sounds/raw, sha256-verified
sounds/tools/build-sfizz.sh                              # sfizz_render 1.2.3 (no Homebrew formula)
uv run --project sounds python sounds/analyse.py         # catalogue notes -> data/sounds/analysis.json
uv run --project sounds python sounds/build.py           # SFZ + SF2 per target -> data/sounds/built/
uv run --project sounds python sounds/render.py data/golden/mikkel-arranged-band/brass-band.musicxml \
    -o data/runs/sound/realistic                         # WAV + MP3 + dry stems
uv run --project sounds python sounds/render.py SCORE -o OUT --engine fluidsynth   # same, via the SF2s
uv run --project sounds python sounds/parity.py RUN_A RUN_B                        # stem-by-stem engine comparison
uv run --project sounds python sounds/descriptors.py RUN... --midi SCORE.mid -o report.json
uv run --project sounds python sounds/checks.py loops | balance RUN...              # loop seams, section loudness
uv run --project sounds python sounds/timbre_probe.py                              # source/EQ candidates vs real references
uv run --project sounds python sounds/ab-test/room_baseline.py --baseline B.mp3 --realistic-info R.json -o OUT.mp3
```

The blind A/B test is described in [ab-test/protocol.md](ab-test/protocol.md). The plan for recording our own brass-band samples is in [recording-plan.md](recording-plan.md).

## Files

| File | What |
|---|---|
| `manifest.json` | Every downloaded file: URL (pinned to a commit on GitHub), size, sha256, plus licence and attribution text per source. `fetch.py --pin` regenerates it. |
| `mapping.json` | Built instruments (`targets`: source library and instrument, RBJ biquad EQ chain, why) and score parts: players per part and which target each player uses, seat and mix gain. |
| `seating.json` | Contest horseshoe positions (x/y in metres from the conductor), bell direction, listener positions, precomputed azimuth and distance per listener. |
| `dsp.py` | The biquads (RBJ cookbook) and level/centroid helpers; the single definition of the timbre EQ. |
| `analyse.py` | Pitch of every raw sample: from the file name, with the octave convention voted per library against pYIN f0; the fine tuning comes from f0. Iowa chromatic runs are cut on silence. |
| `build.py`, `sf2.py` | Region table → `<target>-sus.sfz`, `<target>-stac.sfz`, `<target>.sf2` (program 0 sus, 1 stac), `regions.json`. |
| `render.py` | MusicXML/MIDI → humanised per-player renders → placement, early reflections, IR convolution → −16 LUFS WAV/MP3. |
| `humanize.py` | Deterministic humanization (specified below). |

## How the instruments are built

- **Samples:** mono, 44.1 kHz, 24-bit. Trimmed; with the EQ baked in (so no player needs an EQ); with a crossfade loop in the first ~3 s of the sustain. They are level-normalised per dynamic layer: the loudest 300 ms RMS is −30/−26/−21/−18.5/−16 dBFS for pp/p/mf/f/ff.
- **Layers:** from the library's own labels. Iowa has pp/mf/ff. VSCO has v1 < v2 < …, and 2 layers are treated as p/f. Velocity splits sit halfway between the nominal velocities pp 30, p 48, mf 80, f 100, ff 116. The MuseScore export plays everything at velocity 80, which is the mf layer, or f for 2-layer sources.
- **Missing notes in a layer:** a sample is transposed up to 3 semitones. Beyond that, the nearest sample from a neighbouring layer is used at that layer's level (`volume` in SFZ, `initialAttenuation` in SF2).
- **Velocity curve:** dB-linear, 6 dB from velocity 127 down to 0. SFZ declares it with `amp_velcurve_N`. In SF2, the default velocity modulators are overridden and replaced by one linear velocity→attenuation modulator.
- **Round robin:** SFZ only (`seq_length`/`seq_position`). SF2 has no round robin and uses the first variant.
- **Articulation at render time:** a note is staccato only if it is at most 0.3 s long and lasts under 60% of the time to the next onset in its part. Everything else plays the sustain with a 0.2 s release.
- **Staccato samples:** VSCO has real staccato samples, with 2–4 round robins. Iowa has none, so Iowa targets use the sustain sample cut to 0.6 s with a 0.1 s release.

## Humanization

`humanize.py` implements this algorithm, and `render.py --seed S --composition C --timing score|performed` drives it. It runs only in the realistic tier, and never on percussion, which stays identical in both tiers. `--no-humanize` turns it off. Every random number comes from a keyed hash, so results do not depend on evaluation order.

**Inputs.**
- A part's notes, each with:
  - its score position `s` and length `d` in Composition ticks (`TPB = 24` per beat; MIDI ticks × 24 / MIDI ticks-per-beat, rounded);
  - its score-tempo times `t0`, `t1` in seconds from the MIDI tempo map;
  - its pitch and MIDI velocity.
- The part name `P`, player index `k` (0-based desk position in `mapping.json`) and seed `S` (default `brasscribe`).
- Optionally a Composition `C`: `composition.json` next to the score, or `--composition`.

**PRNG.**
- `fnv1a64(bytes)`: offset basis `0xcbf29ce484222325`, prime `0x100000001b3`, xor then multiply per byte, mod 2^64.
- `splitmix64(x)`:
  - `x += 0x9e3779b97f4a7c15`
  - `x = (x ^ x>>30) * 0xbf58476d1ce4e5b9`
  - `x = (x ^ x>>27) * 0x94d049bb133111eb`
  - return `x ^ x>>31` (all mod 2^64)
- `U(key) = (splitmix64(fnv1a64(utf8(key))) >> 11) × 2^-53`, which lies in [0, 1).
- `T(key) = U(key + "#a") + U(key + "#b") − 1`, triangular on (−1, 1).
- Note keys are `"{S}|{P}|{k}|{i}|{field}"`, where `i` is the note's index after sorting the part by `(s, pitch)`. Per-player keys use `-` for `i`.
- Test vectors:
  - `fnv1a64("") = 0xcbf29ce484222325`, `U("") = 0.7636945250957473`, `U("a") = 0.3717309634354091`.
  - `fnv1a64("brasscribe|Solo Cornet|0|-|lag") = 0xee216da0d3be2b6a`, and its `splitmix64` is `0xc0c340d7787c06ac`.
  - `T("brasscribe|Solo Cornet|0|-|lag") = -0.7633896560002583`.

**Performed beat map (from C).**
- `beat(s) = s / 24 + C.first_downbeat`.
- `B(b)` interpolates `C.beat_times` linearly. Below index 0 and above the last index, it extrapolates with the first and last beat interval.
- Deviation of a Composition note `n`: `dev(n) = n.onset_s − B(beat(n.start))`. It is only defined when `onset_s` is present and `confidence ≥ 0.5`.
- Ensemble deviation `D(s)`: the median of `dev` over all Composition notes (all voices) starting at tick `s`, clipped to ±40 ms. The median of an even count is the mean of the two middle values.

**Voice matching.**
- A part note matches a Composition note with the same start tick and the same pitch class. Within a voice, the first note in file order wins for each `(start, pitch class)`.
- The part's voice is the one with the highest share of matched part notes, and only if that share is ≥ 0.5. Ties go to the first voice in file order.
- The part keeps its own per-note deviations only if that voice's role is `melody`. The soloist leads. Every other part uses `D(s)`, so the band stays together.

**Per player (constants).**
- `lag = 0.002 + 0.008 × T(S|P|k|-|lag)` seconds.
- `detune = [0, +4, −5, +3][k mod 4] + 1.5 × T(S|P|k|-|detune)` cents, sent as one pitch bend (±2 semitone range) at the start of the player's MIDI.

**Per note `i`.**

1. Timing offset `e`, together with a jitter width `σ`:
   - `e = clip(dev(m), ±40 ms)` if the part keeps its own timing and the matched note `m` has a deviation;
   - else `e = D(s)` if defined;
   - else `e = 0`.
   - `σ = 4 ms` when `e` came from C, otherwise `10 ms`.
2. Base time and span:
   - `score` timing (the default; it keeps MuseScore's tempo, so the A/B excerpts line up): `base = t0`, `span = t1 − t0`;
   - `performed` timing (follows the recording's rubato): `base = B(beat(s))`, `span = B(beat(s + d)) − base`.
3. Length factor: `f = clamp(m.performed_dur / m.dur, 0.3, 1.0)` if `m` has `performed_dur`, else 1.
4. Onset and end:
   - `onset = max(0, base + e + lag + σ × T(key|onset))`;
   - `end = onset + max(0.03 s, span × f)`.
5. Velocity:
   - `v0 = m.velocity` if present, else the MIDI velocity;
   - `v = clamp(round_half_even(v0 + 5 × T(key|vel)), 1, 127)`.
6. Articulation: staccato is forced when `m.articulations` contains `staccato`. Otherwise the render-time gate rule applies (at most 0.3 s long and under 60% of the time to the next onset).

The current Composition has `onset_s` and `offset_s` but no `performed_dur`, `articulations` or `velocity`. Those three are used as soon as the transcription writes them. Until then, velocity is the score velocity plus jitter.

## Measured

Mikkel golden score, `render.py` defaults (sfizz, central-hall, audience, `--composition data/golden/mikkel-arranged-band/composition.json`, score timing, seed `brasscribe`):

- **Render time:** about 25 s for 227 s of audio with 25 player voices (M5 Pro).
- **Humanization:**
  - Coverage: Solo Cornet takes its own deviations from the `solo` voice on all 689 notes. The other parts take `D(s)` on 87–100% of their notes, with the rest jitter only. `D(s)` exists for 1188 ticks, and its median magnitude is 19.8 ms.
  - Mean absolute onset shift from the score is 20–27 ms per part (p95 42–47 ms). With jitter only (no Composition) it is 3–6 ms (p95 8–12 ms).
  - Onsets that share a tick across all parts and players are spread by a median of 12.1 ms (p95 60.6 ms, which is the soloist against the band).
  - The velocity standard deviation is about 2.1.
  - Two runs gave an identical note hash.
- **Pitch check:** pYIN on every stem against the score. With humanization off, 100% of checked notes are within 50 cents on every part. With humanization on, the lowest are E♭ bass at 0.91 and 1st Horn at 0.98. The check reads at score time, so it partly lands on shifted attacks; this is not a tuning error.
- **SFZ via sfizz vs SF2 via FluidSynth, dry stems (`parity.py`):**
  - Centroid ratio is 0.996–1.011 on every part.
  - Median envelope correlation is 0.996. Solo Cornet is lowest at 0.90, because of round robin, which is SFZ only.
  - Level has a constant engine offset of +5.9 dB, with a 0.20 dB spread across parts. The flugelhorn is +8.9 dB: FluidSynth scales `initialAttenuation` by 0.4.
- **Spectral centroid in harmonics** against held-out ChoraleBricks songs, in each part's pitch window:
  - The realistic tier is closer than the baseline on all 16 parts.
  - Euphonium, now from VSCO trombone with 2 × 1.2 kHz low-pass: 2.67 (it was 3.61 from Iowa), against 2.00 for real baritones; the baseline is 1.23.
  - B♭ bass, now from VSCO tuba: 4.03 (it was 6.24), against 4.15 in ChoraleBricks and 1.81 in URMP; the baseline is 3.26.
  - Measured on samples alone, `timbre_probe.py` gives Iowa trombone 3.01 even with a 900 Hz 24 dB/oct low-pass, and Iowa tuba 4.31 with a 400 Hz one. The Iowa sources were therefore replaced rather than filtered harder.
- **Loop seams** (`checks.py loops`): 507 loops. The jump step is at most 1.55× the largest natural step in the 40 ms before it (median 0.14×), and the seam correlation is at least 0.948.
- **Articulation:** the score has no articulation marks. A length-only staccato rule would have played 546 of the 689 Solo Cornet notes as staccato. The gate-ratio rule plays 19.
- **Room:**
  - The reverb is calibrated so its energy equals the band's direct energy at 5 m, with players summed as incoherent sources.
  - The measured wet-to-(direct + early reflections) ratio is +4.5 dB at the audience seat.
  - The earlier fixed gain of 1/5 gave +17.6 dB: the unison desks summed coherently in the send, and the two IR channels doubled the energy.

## Open questions

- Timbre EQ is hand-set, and there is no cornet, tenor horn or euphonium reference recording to fit it to. The bass trombone (Iowa) is still brighter than the references: 6.47 against 3.59 harmonics. The cornets and trombones are also brighter than the references. The two tuba references disagree by a factor of 2.3 (ChoraleBricks 4.15, URMP 1.81).
- Baritone and euphonium now share the VSCO tenor trombone samples, differing only in EQ.
- The ensemble deviation `D(s)` comes from transcribed onsets. The ~20 ms it adds is partly transcription error, not performance. Once there is a measure of onset accuracy, weight or shrink it accordingly.
- Is the ChoraleBricks "Baritone" a German *Bariton* (close to a euphonium) or a British baritone horn? It is used as the reference for both.
- The Usina del Arte IR page links both CC BY-SA 3.0 and CC BY 4.0. It is not the default room until that is confirmed.
- The flugelhorn is built from Iowa horn, whose pp/mf runs have gaps (C2–B3). Most flugel mf keys borrow ff samples.
- Does AVAudioUnitSampler apply SF2 `initialAttenuation` per spec, or scale it like FluidSynth does? Check with a parity render on macOS.
- Samples loop after at most ~3 s. Notes longer than that sustain on a 1.2 s loop.
