# 12 — Band sound: every part, every lineup, no GM fallback, no chopping

**Owner feedback:** "The real-life sounds aren't as convincing as we thought and often just fall back to MIDI instruments. We need support for each instrument in each band lineup. It must sound natural and balanced. The worst thing that can happen is that the sound breaks up or chops."

**Short answer.**
- **Fallback.** The samples were never the reason parts fell back to MIDI instruments. The apps were. Apple never loaded the band sounds outside a developer checkout. Android and Studio played General MIDI (Sonivox) by default. On every platform, any part name missing from an exact-match table got General MIDI, a borrowed preset, a sine tone or silence.
- **Chopping.** There were seven separate causes. Each one is measured below, and each is now fixed.
- **Now.** Every part of every lineup resolves, by the same rules on every platform, to its own real-sample preset. The presets are level-matched and balanced by channel gain. They have ~250 ms releases and real samples across the range. Every rendered test phrase passes the click, chop, dropout and clipping checks on all five engines.

Everything below was measured with `sounds/phrases.py` (test phrases), `sounds/soundcheck.py` (render and analyse) and `sounds/checks.py coverage|phrases` (gates). Renders live in `data/sounds/check/{before,after}/<engine>` and are not in git.

## 1. Lineups and parts

| Lineup | Parts (score `<part-name>`) |
|---|---|
| Brass band | Soprano Cornet, Solo Cornet, Repiano Cornet, 2nd Cornet, 3rd Cornet, Flugelhorn, Solo Horn, 1st Horn, 2nd Horn, 1st Baritone, 2nd Baritone, 1st Trombone, 2nd Trombone, Bass Trombone, Euphonium, E♭ Bass, B♭ Bass, Percussion |
| Minimal brass | Solo Cornet, 2nd Cornet, Flugelhorn, Solo Horn, 1st Trombone, Euphonium, E♭ Bass, B♭ Bass |
| Brass quartet (being planned) | 1st Cornet, 2nd Cornet, Tenor Horn, Euphonium. A possible later variant has E♭ Bass instead of the Euphonium. |

These now live in `sounds/mapping.json` under `lineups`. The quartet's two new names, `1st Cornet` and `Tenor Horn`, are part entries that play the Solo Cornet and Solo Horn presets (`preset_of`).

## 2. Coverage before

What each part actually played. "Real" means our built instrument from VSCO 2 CE / Iowa MIS samples.

| Platform, default install | Band parts with exact names | Quartet / other names ("Tenor Horn", "1st Cornet", "Tuba", "Bass", …) | Band sounds missing |
|---|---|---|---|
| Offline reference (`render.py`, sfizz) | real | **skipped** (warning: not in mapping.json) | n/a |
| Apple (PlaybackKit) | **GM**: MuseScore_General if installed, else macOS `gs_instruments.dls`. Band sounds only with the `BRASSCRIBE_SOUNDS` env var, i.e. dev scripts. | GM on a sampler **shared per section**. The first part's program wins for the rest. | GM or a sine |
| Android | **GM (Sonivox)**. The band SF2 was a manual sideload only. The realistic tier (sfizz) needed sideloaded SFZ files. | GM at 0 dB, louder than mapped parts. Realistic tier: a **sine test tone** ("Tuba", "Bass"). | GM |
| Windows | real (band SF2 bundled) | the **borrowed** bank-0 principal (Solo Cornet, Solo Horn, 1st Trombone, E♭ Bass), or **silence** for other programs | silence (no SoundFont at all) |
| Studio (web) | **GM (Sonivox)**. Parts with `<midi-bank>` 2–6 may be silent, since Sonivox has only bank 0. | GM | n/a |

Within the real instruments, `data/sounds/before/built`:

| Target (parts) | Samples | Worst stretch in the pro range | Problems |
|---|---|---|---|
| cornet-a / cornet-b (cornets, soprano) | Iowa trumpet chromatic / VSCO trumpet every 3rd | 0 / 2–3 | none |
| flugelhorn | Iowa horn | 5 | 50 of 93 key×layer slots borrow a louder layer's sample through zone attenuation; the top (F5–B♭5) is stretched |
| tenor-horn (horns) | VSCO horn every 3–5 semitones | **10** | layer holes C4–F4 |
| trombone, baritone, euphonium | VSCO tenor trombone, only up to F4 | **9** (euphonium solos above F4) | |
| bass-trombone | Iowa bass trombone | 12 (A0–B♭0 only) | |
| eb-bass, bb-bass | VSCO tuba from F1 | **14** | the mf/ff layers stop at B♭1 |

Other properties of the old instruments:
- Every target was levelled on its own, so presets differed by up to 8 dB at the same velocity.
- The release was SFZ 0.2 s / SF2 0.2 s. That is **70–105 ms to −40 dB**.

## 3. Why it chopped: measured causes

Each cause, with the run where it was measured (`data/sounds/check/before/*`):

| # | Cause | Where | Measured |
|---|---|---|---|
| 1 | **AVAudioUnitSampler streams samples from disk.** When the file is not cached, held notes go silent about 0.5 s in. | Apple | Cold cache (`check/cold1`): 1st Horn 10 dropouts and 31 clicks, 1st Baritone 6/21, Bass Trombone 6/32. Gaps are 20–110 dB deep. Loading samples into memory (`cold2`): 0. |
| 2 | **Short release.** An SF2 release of 0.2 s is the time to fall 100 dB, so a note fell 40 dB in 70–100 ms. None of the app tiers has reverb, so every note-off sounded clipped. | all | Median release to −40 dB: sfizz 105 ms, FluidSynth 90, AVAudioUnitSampler 85, alphaTab 100 ms |
| 3 | **alphaTab stops every voice dead at the last MIDI event.** The last note of every playback, and any part played solo, lost its release. | Windows, Android, Studio | −32 → −140 dB within 10 ms (chop on every part). With a 0.2 s release, alphaTab also left a click where it killed staccato voices. |
| 4 | **Parts sharing a voice path.** One part's note-off ended another part's same-pitch note. Band scores are full of unisons. | Apple: section samplers. Android: humanized note-off landing on the next note of the same pitch. Windows: merged MIDI-export channels. Studio: alphaTab's two channels per track wrapped past 16. | Apple unison test: level 0.0 with a shared sampler, full level with one sampler per part |
| 5 | **Hard cuts and real-time risks in Android's sfizz tier.** `sfizz_all_sound_off` on stop and seek. Sample streaming after a 0.19 s preload. LowLatency Oboe. Channel gains 16–31 initialised to **0**, so parts on those channels were silent. | Android | code audit. A real phone was not available; see §9. |
| 6 | **Phone SoundFont loop points rounded after resampling to 22.05 kHz.** | Android (mobile SF2) | FluidSynth: 3 clicks per horn, 9 on E♭ Bass, 1 on B♭ Bass. Only in the mobile file. |
| 7 | **No headroom.** | Windows, Studio | Full-band chord at unity gain peaked at 1.227, so it clipped |

Three more problems made the sound unconvincing, though they are not chops:
- **Stretched samples.** Up to 14 semitones in the basses, 9–10 in the horn and the trombone family.
- **Level jumps across the range.** Up to 8.8 dB on E♭ Bass, 5.4 dB on the trombones.
- **Presets 7–8 LU apart.** Engines disagree on SF2 zone attenuation. alphaTab applies all of it, FluidSynth 0.4 of it, and AVAudioUnitSampler almost none.

## 4. What changed

### Sounds (`sounds/`)

**`mapping.json`**
- `lineups`.
- The quartet parts.
- `resolve`: the part → preset rules.
  1. Normalize the name.
  2. Look for an exact part name.
  3. Then an alias: "Tuba", "Bass", "Tenor Horn", "Horn in E♭" and so on.
  4. Then a keyword.
  5. Then the instrument id or MusicXML `<instrument-sound>`.
  6. Then the GM program family.
- A brass part never ends on General MIDI. `partsound.py` is the reference implementation. `partsound-vectors.json` holds 45 input → preset rows that the Apple, Android, Windows and Studio tests all assert.
- `balance_lu` per part and the `balance` rationale (§6).
- `extend` per target (below).
- `kit_offset_db` for the drum kit.

**`build.py`**
- **Equal-loudness presets.** Every target is scaled so that velocity 80 over its comfortable range has a K-weighted body level of −24 dB. The body level is the RMS from 80 ms to 1.0 s; slow-speaking samples were 4–5 dB quiet under the old loudest-300 ms rule. Part balance is then only the channel gain.
- **Releases.**
  - SFZ `ampeg_release`: 0.45 s sustain, 0.28 s staccato.
  - SF2: 0.60 s / 0.38 s.
  - Both give about 250 ms to −40 dB.
- **Range extensions with timbre adaptation.** Keys more than 2 semitones from any primary sample play a second real library instead of a stretched sample. The extension is spectrally matched to the primary: the long-term spectrum is measured on the pitches both libraries have, smoothed to 1/3 octave and clipped to ±9 dB, then applied as a 2049-tap linear-phase FIR. The fitted curves are recorded per target in `regions.json`.

  | Target | Extension | Keys |
  |---|---|---|
  | trombone, baritone, euphonium | Iowa tenor trombone | G♯3, A3, G♯4–C5 |
  | eb-bass, bb-bass | Iowa tuba | C1–D1, plus the mf/ff layers down to C1 |
  | tenor-horn | Iowa horn | E♭4–B4 and the layer holes |
  | flugelhorn | Iowa trumpet, matched to Iowa horn | A♭5–C6 |

- **Borrowed layers.** A sample borrowed from another layer is brought to that layer's level in a copy of the sample, not through zone attenuation, which the engines disagree on.
- **Region choice.** It prefers any layer within 3 semitones over a longer stretch.
- **Loops.** Loops fall back to a wider window for swelling pp notes. Every sustain zone now loops.

**`band.py`**
- `channel_gain_db = balance_lu − max − 3 dB` when the preset layers two targets.
- New fields: `single_voice_gain_db` (for one-target voices, e.g. the sfizz tier) and `layered`.
- Quartet parts get their own gain.
- `render.py` resolves score names through the same rules, so it no longer skips unknown parts.

**Checks**
- `checks.py coverage` reads the band SF2 and fails when a lineup part:
  - does not resolve by name to its own preset built from our targets;
  - is missing a zone for any key of its professional range at any velocity;
  - has a comfortable-range key more than 3 semitones from its sample;
  - plays an unlooped sustain;
  - has a release under 0.4 s.
- `checks.py phrases RUN…` fails on:
  - any click, chop, dropout or 1 ms gap;
  - a clipped sample;
  - a median release under 150 ms;
  - a non-monotonic velocity response;
  - a part more than 2 LU off its `balance_lu` (SoundFont runs).
- `partsound.py --check` (stdlib only) runs in CI, in `.github/workflows/ci.yml`.
- The detectors were checked by injection: 4 synthetic clicks and two 2–4 ms gaps planted in clean renders are all found, with 0 false positives on clean renders.

### Apple (`PlaybackKit`)
- **Band sounds with no setup.** The band SoundFont is found in the app bundle, then Application Support, then the repo. `scripts/stage-band-sounds.sh`, run by `make project` / `make bandsound`, copies the 16-bit SF2 and `mapping.json` into the bundle.
- **Resolver.** `PartSoundResolver.swift` implements the shared rules. Each part gets its own sampler with `channel_gain_db`.
- **Samples in memory.** Band samples are loaded into memory; this fixes cause 1.
- **Stop.** It releases through the preset, then fades out over 80 ms.
- **Basic tier.** It is explicit, with the missing-sounds message and the paths that were searched.
- **Program changes.** Measured: a MIDI program change does not override the loaded preset. 64 voices per part sampler.

### Android
- **Default sounds.** The phone band SoundFont (77 MB, 22.05 kHz, 16-bit, both cornet layers) is bundled uncompressed in the APK and used by default. A sideload still overrides it.
- **Resolver.** `BandSoundMap.resolve` implements the shared rules for the alphaTab channel plan and the sfizz tier. The sine test tone is gone.
- **Chop fixes.**
  - The same-pitch overlap is trimmed 5 ms before the next onset.
  - Stop fades out over 80 ms.
  - Seek and loop release held notes.
  - Oboe runs without LowLatency, with 4 bursts of buffer, and logs xruns.
  - Idle synths are skipped.
  - Channels 16–31 are at unity.
  - The sfizz preload is 32768 frames.
- **`mobile_soundfont.py`** rebuilds every loop at the new rate: it resamples an unrolled copy, searches for the best loop end and crossfades. This fixes cause 6.

### Windows
- **Resolver.** `PartSoundResolver.cs` implements the shared rules. `SoundMap(name, gmProgram)` means an unknown name still gets a brass preset.
- **Release tail.** A no-op event is scheduled 1.5 s after the last note, so alphaTab plays out the last release. This fixes cause 3.
- **Headroom.** Master volume 0.5, with a tanh soft limiter above 0.8. The full band peaks at 0.49.
- **Stop and pause** fade out over 80 ms.
- **MIDI export** keeps shared unisons: it drops a note-off while another note-on of the same key is still open.
- **Missing sounds.** `Player_SoundsMissing` and `…_Details` in en and nb.

### Studio
- `build.mjs` copies the phone band SF2 and `mapping.json` into `assets/band`, which is gitignored.
- `score.ts` loads it by default:
  - one channel per part, drums on 9;
  - the resolved preset;
  - channel gains;
  - the score's own program and bank changes removed.
- Stop and pause fade out over 80 ms.
- It falls back to Sonivox only when the band file is absent, and says so.

## 5. Coverage after

`checks.py coverage` gives 30 lineup parts and **0 problems**. Every part plays its own preset in `brasscribe-band.sf2`, built only from real samples, on every platform:

| Part (lineups) | Preset (bank, program) | Samples (primary + extension) | Layers | Worst stretch, comfortable/pro range |
|---|---|---|---|---|
| Solo / 1st Cornet (all) | 0, 56 | Iowa trumpet + VSCO trumpet, layered ±3 ct | 3 + 2 | 2 / 2 |
| Soprano, Repiano, 2nd, 3rd Cornet | 1–4, 56 | VSCO trumpet (2nd/3rd layered with Iowa) | 2–3 | 2–3 / 3 |
| Flugelhorn | 5, 56 | Iowa horn + Iowa trumpet (matched) | 3 | 3 / 3 |
| Solo Horn / Tenor Horn, 1st, 2nd Horn | 0–2, 60 | VSCO horn + Iowa horn (matched) | 4 | 3 / 3 |
| 1st, 2nd Baritone | 3–4, 58 | VSCO tenor trombone + Iowa tenor trombone (matched) | 3 | 2 / 2 |
| 1st, 2nd Trombone | 0–1, 57 | the same | 3 | 2 / 3 |
| Bass Trombone | 2, 57 | Iowa bass trombone | 3 | 0 / 12 (A0–B♭0 only) |
| Euphonium | 2, 58 | VSCO + Iowa tenor trombone (matched), darker EQ | 3 | 2 / 3 |
| E♭ Bass, B♭ Bass | 0–1, 58 | VSCO tuba + Iowa tuba (matched) | 3 | 3 / 3 |
| Percussion | 128, 0 | MS Basic GM Standard kit (MIT) | — | — |

The drum kit is the only General MIDI sound. It is a real sampled kit, and it is the same in both tiers on purpose, so the A/B test isolates the brass.

**Test phrases after.** `checks.py phrases` reports 0 clicks, chops, dropouts, gaps and clipped samples on every part in sfizz, the band SF2 (FluidSynth), the phone SF2 (FluidSynth), AVAudioUnitSampler and alphaTab. There is one exception, listed in §9. Median release to −40 dB, all measured on the "after" runs:

| Engine | Release to −40 dB |
|---|---|
| sfizz | 230–244 ms |
| FluidSynth | 249–259 ms |
| AVAudioUnitSampler | 244–264 ms |
| alphaTab | 284–309 ms |

The Bass Trombone is 185–214 ms on every engine; its samples have short natural tails.

**Largest level step between neighbouring keys (sweep, sfizz).**

| Part | Before (dB) | After (dB) |
|---|---|---|
| E♭ Bass | 8.8 | 1.9 |
| Trombones | 5.4 | 3.2 |
| Horns | 4.5 | 1.3 |
| Every other part | — | ≤ 3.2 |

The Bass Trombone's lowest key, A0, is still 7.6 dB off.

**Full band through one alphaTab synth** (18 parts on the app channel plan): the mix differs from the sum of the solo renders by −134 dB, so there is no voice limit or stealing. The unison test gives −146 dB, so no note ends early. AVAudioUnitSampler uses one sampler per part with 64 voices each.

## 6. Balance

The target is `balance_lu`: loudness in the band at the same dynamic, relative to the Solo Cornet desk. It is brass-band practice set as a heuristic, and it still needs to be confirmed by listening with players:
- The solo cornets and the basses carry the band.
- Soprano, repiano, flugel and solo horn sit about 3 LU under the solo cornets.
- The back-row cornets, horns and baritones sit 4–6 LU down, with second parts 1 LU under firsts.
- The trombones sit just under the cornets.
- The euphonium is the second solo voice.
- The percussion supports.

Measured on the Mikkel golden arrangement (`sounds/render.py`, dry stems, LU relative to Solo Cornet). The score's writing also moves these numbers: a part with fewer notes or a softer register reads lower.

| Part | Target | Before | After |
|---|---|---|---|
| Soprano Cornet | −3 | — (not in the score) | — |
| Repiano Cornet | −3 | −6.1 | −2.9 |
| 2nd Cornet | −4 | −7.0 | −4.0 |
| 3rd Cornet | −5 | −7.1 | −5.0 |
| Flugelhorn | −3 | −6.1 | −2.3 |
| Solo Horn | −3 | −7.6 | −2.1 |
| 1st Horn | −5 | −8.7 | −4.3 |
| 2nd Horn | −6 | −8.7 | −5.5 |
| 1st Baritone | −5 | −8.4 | −4.2 |
| 2nd Baritone | −6 | −8.4 | −5.2 |
| 1st Trombone | −3 | −9.1 | −2.7 |
| 2nd Trombone | −4 | −8.6 | −3.5 |
| Bass Trombone | −3 | −9.2 | −3.6 |
| Euphonium | −1 | −3.7 | −2.5 |
| E♭ Bass | −1 | −2.8 | −0.2 |
| B♭ Bass | −1 | −4.3 | −0.3 |
| Percussion | −6 | −9.1 | −5.9 |

**In the apps.** With the app channel gains applied, the test-phrase levels land within 2 LU of the target on every part, in FluidSynth, AVAudioUnitSampler and alphaTab (`checks.py phrases`, 0 balance failures). Before, the same check was 3–6 LU off on AVAudioUnitSampler and alphaTab.

## 7. Sources and licences

| Source | Licence | Use |
|---|---|---|
| VSCO 2 CE brass (Versilian Studios) | CC0 1.0 | trumpet, horn, tenor trombone, tuba |
| University of Iowa MIS (L. Fritts) | "may be used for any projects, without restrictions" | trumpet, horn, tenor and bass trombone, tuba |
| MS Basic (MuseScore) | MIT: keep `MS Basic_License.md` | drum kit, and the GM baseline tier |
| OpenAIR IRs (University of York, Usina del Arte) | CC BY 4.0: credit in About | room |

The project is non-commercial (docs/plan/apps-plan.md §7). Attribution text is in `sounds/manifest.json`.

**Libraries considered and not used.** Their licences were not re-checked online for this change; the notes are what the earlier survey in `docs/plan/research-sound-and-mobile-ml.md` §1 found.
- **Philharmonia Orchestra samples.** Free for music, but the terms forbid redistributing the samples as a sample library, which a bundled SoundFont is. They have no brass-band instruments either.
- **Sonatina Symphonic Orchestra** (Creative Commons Sampling Plus 1.0, a retired licence). Orchestral trumpet, horn, trombone and tuba only; nothing that VSCO and Iowa do not already cover.
- **Virtual Playing Orchestra.** A mix of other libraries under their own terms, Philharmonia included. Not clean to redistribute.
- **Freesound CC0.** Single cornet, flugelhorn or euphonium notes turn up, but not chromatic multi-dynamic sets from one player and one microphone. Mixing players makes the band inconsistent, which is the main flaw of mixing VSCO and Iowa today.

No free, redistributable library has a cornet, flugelhorn, E♭ tenor horn, baritone, euphonium or brass-band basses. They are derived as follows:

| Part | Derived from | Adaptation |
|---|---|---|
| Cornets and soprano | trumpet | EQ |
| Flugel | horn, with the top from trumpet | spectrally matched to the horn |
| Tenor horn | F horn | EQ |
| Baritone and euphonium | tenor trombone | different EQ each; the euphonium is darker |
| Basses | tuba | EQ |

The EQ chains, and the reasons for them, are in `mapping.json` `targets[].why`. The spectral-match curves are in `regions.json`. The centroids from `timbre_probe.py` against ChoraleBricks and URMP are unchanged from sounds/README.md; the new extensions are matched to their primary library, not to those references.

## 8. Listening material (not in git)

| What | Path |
|---|---|
| Before/after per engine: Solo Cornet, Flugel, Solo Horn, Euphonium, 1st Trombone, E♭ Bass (held note, repeated 16ths, detached scale, range sweep) | `data/sounds/ab-test/phrases-before-after/{sfizz,fluid-band,fluid-mobile,avsampler,alphatab}-{before,after}.mp3` |
| Mikkel golden, 60–100 s, offline realistic tier, before and after | `data/sounds/ab-test/phrases-before-after/mikkel-realistic-{before,after}.mp3` |
| Full renders | `data/runs/sound/realistic/` (before) and `data/runs/sound/realistic-after/` |
| Blind A/B, new realistic vs the MuseScore baseline (protocol in `sounds/ab-test/protocol.md`) | `data/sounds/ab-test/after-vs-musescore/listener-{1..5}` |
| Blind A/B, new vs old realistic | `data/sounds/ab-test/after-vs-before/listener-{1..5}` |

The previous built instruments and SoundFonts are kept in `data/sounds/before/{built,band}`.

For the A/B sets, keep `key.json` away from listeners and score with `sounds/ab-test/score.py DIR`.

## 9. Remaining gaps

- **Velocity curves differ by engine, and the apps cannot fix it.** At velocity 80 every engine matches. Soft playing does not:
  - AVAudioUnitSampler ignores the SoundFont's velocity modulator and spans 36–44 dB from velocity 30 to 127, against about 16–24 dB in FluidSynth. So pp plays about 14 dB too soft. Rewriting its curve crashes on engine shutdown.
  - alphaTab uses amplitude ∝ velocity, so pp plays about 6 dB too soft.
  - Next step: a SoundFont-side fix, i.e. per-layer levels chosen against each engine's curve, or velocity remapping in the players before note-on.
- **Bass Trombone A0–B♭0** (outside the comfortable range): stretched 12 semitones, 7.6 dB level step.
- **alphaTab B♭ Bass B♭0:** one click about 25 ms after the note-off. B♭0 is outside the comfortable range.
- **Not measured:**
  - alphaTab at loop wrap and seek (it probably stops voices dead there too).
  - Real-time behaviour on a physical Android phone (xrun count, sfizz memory of about 100 MB estimated).
  - Studio in a browser.
- **The missing-sounds state needs showing in the UI.** It exists in all three apps, with en/nb copy, and is being shown one line above the player. Apple's text is to move into `Localizable.xcstrings`.
- **Sizes grew with the range extensions and baked layer copies.**

  | File | Size |
  |---|---|
  | Band SF2, 24-bit | 292.6 MB |
  | Band SF2, 16-bit (Apple and Windows bundle) | 195.1 MB |
  | Phone SF2 (Android APK and Studio) | 77.3 MB |

  Options if that is too much: an on-demand download (with the size in plain MB and "works offline after"), or 22.05 kHz for the upper band.
- **Instruments are still derived.** Tenor horn, baritone, euphonium, flugelhorn, soprano cornet and the brass-band basses are approximated from orchestral instruments. The real fix is recording our own; see below.

## 10. Recording our own samples

The plan is in `sounds/recording-plan.md`:
- one player per instrument;
- every semitone;
- pp/mf/ff sustain and staccato;
- a dry room, a fixed ORTF pair at 2 m, the same gain across the band;
- about one day per instrument.

**Priority**, by how far each derived sound is from the real instrument and how exposed the part is:
1. euphonium (a solo voice; currently trombone);
2. tenor horn;
3. flugelhorn;
4. baritone;
5. B♭ cornet (soprano if a player is available);
6. E♭ and B♭ bass.

**Dropping them in:**
- Each new library goes into `fetch.py`/`manifest.json` as a source.
- A target's `source` then points at it, and the `extend` entries stay as the fallback for any notes the player could not play.
- `checks.py coverage` and `checks.py phrases` are the acceptance gates.
- `timbre_probe.py` should be re-fit against the recordings, which also finally gives real cornet, tenor horn and euphonium references.
