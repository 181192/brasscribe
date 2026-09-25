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

## How the instruments are built

- **Samples:** mono, 44.1 kHz, 24-bit. Trimmed; with the EQ baked in (so no player needs an EQ); with a crossfade loop in the first ~3 s of the sustain. They are level-normalised per dynamic layer: the loudest 300 ms RMS is −30/−26/−21/−18.5/−16 dBFS for pp/p/mf/f/ff.
- **Layers:** from the library's own labels. Iowa has pp/mf/ff. VSCO has v1 < v2 < …, and 2 layers are treated as p/f. Velocity splits sit halfway between the nominal velocities pp 30, p 48, mf 80, f 100, ff 116. The MuseScore export plays everything at velocity 80, which is the mf layer, or f for 2-layer sources.
- **Missing notes in a layer:** a sample is transposed up to 3 semitones. Beyond that, the nearest sample from a neighbouring layer is used at that layer's level (`volume` in SFZ, `initialAttenuation` in SF2).
- **Velocity curve:** dB-linear, 6 dB from velocity 127 down to 0. SFZ declares it with `amp_velcurve_N`. In SF2, the default velocity modulators are overridden and replaced by one linear velocity→attenuation modulator.
- **Round robin:** SFZ only (`seq_length`/`seq_position`). SF2 has no round robin and uses the first variant.
- **Articulation at render time:** a note is staccato only if it is at most 0.3 s long and lasts under 60% of the time to the next onset in its part. Everything else plays the sustain with a 0.2 s release.
- **Staccato samples:** VSCO has real staccato samples, with 2–4 round robins. Iowa has none, so Iowa targets use the sustain sample cut to 0.6 s with a 0.1 s release.

## Measured

Mikkel golden score, `render.py` defaults (sfizz, central-hall, audience, humanized):

- Render time: 25 s for 227 s of audio with 25 player voices (M5 Pro).
- **Pitch check:** pYIN on every stem against the score. For both tiers, 100% of checked notes are within 50 cents, except the B♭ bass in the realistic tier at 97%.
- **SFZ via sfizz vs SF2 via FluidSynth, dry stems (`parity.py`):**
  - Centroid ratio is 0.996–1.004 on every part.
  - Median envelope correlation is 0.997. The lowest are Solo Cornet at 0.90 and E♭ bass at 0.92: these use round robin, which is SFZ only.
  - Level has a constant engine offset of +5.9 dB, with a 0.15 dB spread across parts. The flugelhorn is +8.9 dB: FluidSynth scales `initialAttenuation` by 0.4 (its EMU-compatibility behaviour), and most of that instrument's mf zones borrow ff samples at −5 dB.
- **Spectral centroid per part** (`descriptors.py`) is compared in harmonics against held-out ChoraleBricks songs and URMP, in each part's pitch window. The realistic tier is closer to the reference than the baseline on 14 of 16 parts. The exceptions are the euphonium and B♭ bass: both are Iowa-sourced and still too bright. The baseline is 1.5–3× too bright on the cornets, horns, baritones and trombones.
  - Treat this as weak evidence: the harmonic centroid barely moves under EQ, so it does not measure brightness above ~2 kHz well.
- **Loop seams** (`checks.py loops`): 652 loops. The jump step is at most 1.55× the largest natural sample step in the 40 ms before it, with a median of 0.12×. No gross clicks.
- **Articulation:** the score has no articulation marks. A length-only staccato rule would have played 546 of the 689 Solo Cornet notes as staccato. The gate-ratio rule plays 19.
- **Room:** with a critical distance of 5 m and the audience listener 8–15 m from the players, the reverberant level is 4–10 dB above the direct sound.

## Open questions

- Timbre EQ is hand-set, and there is no cornet, tenor horn or euphonium reference recording to fit it to. The descriptors show the Iowa-sourced low brass (bass trombone, euphonium, B♭ bass) brighter than the ChoraleBricks/URMP references in harmonic-centroid terms. A single-shelf fit was tried and moved the centroid very little (±6 dB gave ±0.1–0.4 harmonics), so it was dropped. The next steps are our own recordings or a multi-band spectral-envelope match.
- Is the ChoraleBricks "Baritone" a German *Bariton* (close to a euphonium) or a British baritone horn? It is used as the reference for both.
- The Usina del Arte IR page links both CC BY-SA 3.0 and CC BY 4.0. It is not the default room until that is confirmed.
- The flugelhorn is built from Iowa horn, whose pp/mf runs have gaps (C2–B3). Most flugel mf keys borrow ff samples.
- Does AVAudioUnitSampler apply SF2 `initialAttenuation` per spec, or scale it like FluidSynth does? Check with a parity render on macOS.
- Samples loop after at most ~3 s. Notes longer than that sustain on a 1.2 s loop.
