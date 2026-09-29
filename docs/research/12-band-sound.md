# 12 — Band sound: every part, every lineup, no GM fallback, no chopping

**Owner feedback:** "The real-life sounds aren't as convincing as we thought and often just fall back to MIDI instruments. We need support for each instrument in each band lineup. It must sound natural and balanced. The worst thing that can happen is that the sound breaks up or chops."

**Status (2026-09-29).** Landed on every platform. Sections 1–11 describe the work as first built, with the `sounds-2026.09.27` pack. The pinned pack is now `sounds-2026.09.29` (`sounds/band-sounds.json`): 16-bit 200.3 MB, phone 70.8 MB. Its changes and the current make-up gains (Apple 31.5 dB, alphaSynth 5 dB, sfizz 4 dB; `sounds/playback-levels.json`) are in §12.

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
- **Headroom.** Superseded by the shared output stage (§11): unity master volume, +4 dB make-up gain and the tanh limiter shared with Apple and Android.
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

**Libraries considered and not used.** Their licences were not re-checked online for this change. The first three rows come from the survey in `docs/plan/research-sound-and-mobile-ml.md` §1; the Freesound note is my own assessment.
- **Philharmonia Orchestra samples.** Free for music, but the samples "must not be sold or made available 'as is' (i.e. as samples or as a sampler instrument)", and a playback app is a sampler instrument. The site lists the euphonium under the tuba family; whether the download contains it was not verified.
- **Sonatina Symphonic Orchestra** (Creative Commons Sampling Plus 1.0, a retired licence). Orchestral trumpet, horn, trombone and tuba only; nothing that VSCO and Iowa do not already cover.
- **Virtual Playing Orchestra.** Redistribution is allowed with credit, but it bundles samples from other libraries under their own licences. It has no cornet, flugel or euphonium.
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
  - Apple now remaps velocity before note-on so it plays at alphaSynth's levels (§11, score dynamics). Soft playing is then as soft on Apple as on Android and Windows; all three remain softer than FluidSynth.
- **Bass Trombone A0–B♭0** (outside the comfortable range): stretched 12 semitones, 7.6 dB level step.
- **alphaTab B♭ Bass B♭0:** one click about 25 ms after the note-off. B♭0 is outside the comfortable range.
- **Not measured:**
  - alphaTab at loop wrap and seek (it probably stops voices dead there too).
  - Real-time behaviour on a physical Android phone (xrun count, sfizz memory of about 100 MB estimated).
  - Studio in a browser.
- **Every build bundles the band sounds; users never download them.** The SoundFonts are built files, not in git, and the repository is private, so they are published as assets of a pre-release in this repository (`sounds-2026.09.27` when this was written; `sounds-2026.09.29` now) and bundled at build time:
  - `sounds/band-sounds.json` pins the pack: the release tag plus the size and sha256 of each file;
  - `sounds/tools/band_sounds.py fetch` (`pixi run fetch-sounds` locally, `.github/actions/band-sounds` in CI, cached per pin) downloads them with `gh release download` and checks them against the pin and the release's SHA256SUMS;
  - the Android, Apple and Windows release jobs and the Bandroom Windows job use it, and **fail** when the files cannot be had or a hash does not match.

  A new pack: rebuild, `band_sounds.py pin --version sounds-YYYY.MM.DD`, then publish the files and SHA256SUMS under that tag (see the script's docstring).
- **Who bundles which file.** Android, iOS/iPadOS and both Bandroom apps: `brasscribe-band-mobile.sf2` (77 MB then, 70.8 MB in `sounds-2026.09.29`). macOS and Windows Play: `brasscribe-band-16bit.sf2` (195 MB then, 200.3 MB now). Bandroom puts it under `band/` with `mapping.json` and passes the folder to the engine as `BRASSCRIBE_BAND_SOUNDS_DIR`, which serves it to Studio at `/assets/band/`. The engine's MP3 export does not use it: that is MuseScore's own sounds.
- **Memory is not measured on devices.**
  - Apple loads each part's preset into its own sampler, in memory (needed against cause 1). The sustain samples of all 17 brass presets add up to about 270 MB at 16-bit, or 535 MB if the sampler keeps float32 and does not share samples between instances. That is fine on a Mac, but has to be measured on an iPhone before release. A quartet or the minimal band loads a fraction of it.
  - Android's alphaTab holds the whole phone SoundFont as floats: about 155 MB, against about 117 MB before. The full 16-bit file ran out of memory at 298 MB of floats.
- **The missing-sounds line has not been seen running.** It is shown one line above the player bar on Android, Apple and Windows (info icon, en/nb copy, the path under a Details disclosure). Android builds. The Apple app target (it needs the Verovio framework) and the WinUI project (it needs Windows) were not built here.
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

## 11. Playback loudness: one target on every app

**Problem.** The Play apps played the band at different levels, and the original recording at whatever level it was recorded. Apple's band went through +26 dB of make-up gain and a soft limiter, but the recording and the metronome bypassed it. Windows' band ran at master 0.5, about 10 dB under Apple's. Android's had no stage at all. So switching Hear: Band ↔ Recording, or pressing "Listen to this bar", jumped in level.

**The target** lives in `sounds/playback-levels.json`. `sounds/playback_levels.py --vectors` writes `sounds/output-stage-vectors.json` from it, and `--check` (stdlib, in CI) fails when the two drift apart.
- **Band stage.** Make-up gain, then a memoryless soft limiter: `y = x` up to 0.8 (−1.9 dBFS), `sign(x)·(0.8 + 0.18·tanh((|x| − 0.8)/0.18))` above it, approaching a ceiling of 0.98 (−0.18 dBFS). It has no attack or release, so it cannot pump, and below 0.8 every part keeps its level, so mute and solo keep the balance.
- **Band calibration.** The full-band test phrase (`phrases.json` "band") lands at **−12 LUFS integrated (±1 LU)**, peaking at or under the ceiling. Each band path has its own measured make-up gain: Apple +26 dB (environment node, parts metres away), alphaSynth on Android and Windows +4 dB at unity master volume, sfizz +4 dB (the `sounds-2026.09.29` pack moved Apple to +31.5 dB and alphaSynth to +5 dB; §12) (its parts are balanced to the SoundFont's).
- **Recording.** The original recording is measured once, as a whole (EBU R128 integrated), when it loads, and plays at **the loudness the band plays that arrangement at**: the arrangement's estimated band loudness, clamped to [−20, −10] LUFS, or −16 LUFS when there is no arrangement. Gain = clamp(target − measured, −30, +12) dB, and the limiter follows the gain, so a boost cannot clip. A mono file is measured as dual mono (+3 dB), because it plays from both speakers. It is never normalised per bar, so a soft bar stays softer than a loud one.
- **Band estimate** (`recording.band_estimate`). From the arrangement's pitched notes, with no rendering: estimate = −1.2 + 10·log10(Σ d·10^(L(v)/10) / U). d is each note's length in quarter notes and v its velocity by the dynamics rules. L(v) is the phrase's pitched loudness at that velocity (`alphatab_lufs`). U is the score time in which any pitched note sounds. So the part count enters as the energy of the parts sounding together, and the marks enter through L. Percussion is left out. The −1.2 dB offset is fitted on the golden, and the rule is checked on two more measurements (`sounds/playback_levels.py --calibrate`):

  | | measured | estimate |
  |---|---|---|
  | Golden, its dynamics (Windows) | −11.80 | −11.82 |
  | Golden, every note at velocity 80 (Apple, before the remap) | −15.95 | −15.96 |
  | Full-band phrase | −12.00 | −11.90 |

  Each app takes the notes from its own score model and is held to the Python reference on two scores (`band_estimate_scores` in the vectors, 0.01 LU): `sounds/band-estimate-score.musicxml` (marks, accents, a chord, rests, percussion; every part starts with its own mark, because alphaTab carries the previous part's last mark into a part without one) and the Old Hundredth fixture (all f: −13.6 LUFS).
- **Metronome.** The click peaks at **−10 dBFS (±1.5 dB)** after the output, about 9 dB under the full band's peak and below the limiter's threshold.
- **Score dynamics.** Every app plays the score's dynamics by alphaTab 1.8.4's rules (`dynamics` in `playback-levels.json`). Android and Windows get them from alphaTab itself; Apple copies them in ScoreKit (`Dynamics`, `MusicXMLParser`):
  - A `<dynamics>` mark holds from where it is read until the next one, in document order. A part starts at f.
  - Velocities are alphaTab's `MidiUtils.dynamicToVelocity`: ppp 15, then 16 per step, so pp 31, p 47, mp 63, mf 79, f 95, ff 111, fff 127.
  - sf, sfz, fz and sfp play as ff and hold like any other mark, as alphaTab plays them. `<sound dynamics>` is ignored.
  - An accent adds 16, and a strong accent (marcato) adds 32.
  - Hairpins are the one difference. Apple moves the velocity linearly across a `<wedge>` to the mark at its end, or one step when there is no mark. alphaTab 1.8.4 draws hairpins but plays them flat, so on Android and Windows the level jumps at the next mark.
  - One more small difference: alphaTab carries the previous part's last mark into a part that has no mark before its first note. Apple starts every part at f.
  - On the golden score, every note that both engines play at the same tick gets the same velocity (5,844 of 5,844). The only differences are tie splits.
- **Sampler velocity curve.** AVAudioUnitSampler ignores the SoundFont's velocity modulator and follows a much steeper curve than alphaSynth, which plays amplitude ∝ velocity. So Apple remaps each velocity before note-on (`dynamics.sampler_velocity.apple_*`; `PlaybackLevels.samplerVelocity`, applied only to the engine's sequence, never to MIDI export).
  - The knots were measured on the full-band phrase at one velocity through both engines, 12 dB under each gain so nothing reaches the limiter, with the same SoundFont.
  - Pitched parts are matched level for level.
  - Percussion is matched in shape, anchored at velocity 90. Apple seats the kit at 6 m, where it sits about 8 dB under alphaSynth's at every velocity, which is a balance question, not a velocity one.
- **Loudness meter.** Each app has its own BS.1770 meter, with K-weighting, 400 ms blocks at 75 % overlap, and the −70 LUFS absolute and −10 LU relative gates. The meters use pyloudnorm's filters and are held to the pyloudnorm vectors within 0.1 LU.

**Per app**

| | Apple (`PlaybackKit`) | Android | Windows (`Brasscribe.Play.Core`) |
|---|---|---|---|
| Band stage | `OutputStageAU` on the band bus | `StagedSynthOutput` wraps alphaTab's synth output (a reflection swap of the worker API's private `_output`, since alphaTab 1.8.4 builds its Android output inside the view with no hook); sfizz runs the same curve in C++ (`cpp/output_stage.h`) on its mix | `BufferedSynthOutput` applies `OutputStage` to every sample as it arrives |
| Stop fade | Sampler volumes, before the stage | alphaTab master volume, before the stage; sfizz fades after its limiter | On the output, after the stage |
| Recording | Its own `OutputStageAU` after the time-pitch unit. Measured off the main thread when loaded; the gain is applied at the next start, never mid-play. The mixer spreads mono equal-power, so +3 dB is made up. Stop fades it over 80 ms. | `LevelMatch` measures the recording and the engine's rendered score once each, and plays every "Listen to this bar" slice with that gain and the limiter | `RecordingLevel` measures the decoded WAV off the UI thread and sets `MediaPlayer.Volume`. Stop fades it over 80 ms. |
| Metronome | Bypasses the stage, at its own level | Through the stage, volume 1 | Through the stage, volume 1 |
| Tests | `LoudnessTests`, `OutputStageTests`, `DynamicsLevelTests`, ScoreKit `DynamicsTests` (`swift test --no-parallel`) | `OutputStageTest`, `LevelMatchTest` (JVM); `PlaybackLevelTest` (emulator: phrase through alphaTab and the stage, metronome, C++ curve against Kotlin); `OutputStageInstallTest` (emulator: the app's own player is staged after opening a score, playing and stopping) | `PlaybackLevelTests` (`tools/check-macos.sh`) |

**Measured, before → after.** Peak dBFS / integrated LUFS.

| | Apple | Android (alphaTab, emulator) | Windows (alphaSynth, macOS) |
|---|---|---|---|
| Full-band phrase | −1.1 / −11.7 → unchanged | −4.35 / −16.2 (no limiter) → −0.65 / −12.2 | −10.2 / −22.2 → −0.57 / −12.2 |
| Golden arrangement (Mikkel) | −2.8 / −15.95 → unchanged; with dynamics −0.18 / −12.17 | not rendered | −6.7 / −21.9 → −0.18 / −11.8 |
| Metronome click | −9.8 (phone SF2 −10.7) → unchanged | −15.1 → −11.1 | −19.4 → −9.4 |
| Recording (`captured.wav`, stereo, −14.9 LUFS) | −14.9 (file level) → −16.0, peak −4.4 | file level → −16 | file level → −16 (turned down) |
| Engine's rendered score (Listen to this bar) | — | about −4.6 LUFS → −16 | — |

Apple test variants of the recording: −8 dB gives −28.2 LUFS in the file and −16.3 played, +8 dB gives −12.3 and −16.0, mono −6 dB gives −26.2 and −16.1, mono +6 dB gives −14.3 and −16.0. A −20 dB copy stops at the +12 dB cap. Before this change, a mono recording played 3 dB under its measured level, because of the equal-power spread. The meter reads the 4.5-minute `captured.wav` in 1.7 s in a debug build.

**Apple dynamics, before → after.** Integrated LUFS of the phrase's pitched parts, 12 dB under each app's band gain, so nothing reaches the limiter (`DynamicsLevelTests`). Before, every mark played at velocity 80.

| Mark (velocity) | alphaSynth | Apple before (80) | Apple at the table velocity, no remap | Apple remapped |
|---|---|---|---|---|
| pp (31) | −40.33 | −24.06 | −47.59 (−7.3) | −40.36 (−0.0) |
| p (47) | −36.71 | −24.06 | −40.36 (−3.7) | −37.63 (−0.9) |
| mp (63) | −28.36 | −24.06 | −30.33 (−2.0) | −28.43 (−0.1) |
| mf (79) | −24.72 | −24.06 | −24.27 (+0.5) | −24.72 (0.0) |
| f (95) | −22.25 | −24.06 | −20.43 (+1.8) | −22.20 (+0.1) |
| ff (111) | −17.04 | −24.06 | −13.62 (+3.4) | −16.20 (+0.8) |

p is the worst fit. The sampler's velocity layers jump 5 dB between 55 and 56, so no velocity gets closer. The golden arrangement on Apple measures −15.96 LUFS before, −9.27 with the table velocities and no remap, and −12.17 remapped, against Windows' −11.84. The full-band phrase test sends velocities 80 and 90 straight to the samplers, so it still measures −11.70. With the remap the sequence applies, it measures −12.24, against Windows' −12.21.

**Gaps**
- **The estimate knows the notes, not the synth.** It reads score time, not seconds, so a score whose tempo changes a lot weights its slow passages less than it plays them. It does not model the limiter, the Apple hairpins, a part's own mix gain, or grace notes (left out; alphaTab takes their time from the main note). On the three measurements above it is within 0.1 LU. The clamp to [−20, −10] keeps a very soft or very loud score from pushing the recording far from the range the band plays in.
- **Windows cannot boost.** `MediaPlayer.Volume` stops at 1, so a recording quieter than its target keeps its own level (more often now that loud scores ask for up to −10 LUFS); only a louder one is turned down. Boosting would need the recording on its own audio path, not the media player.
- **Android's two streams add up unchecked.** With sfizz on, alphaTab (kit and metronome) and sfizz are limited separately and summed by the system mixer, so neither limiter bounds the sum. The sfizz gain is set by design and was not measured: there is no SFZ pack here, and `sfizz_player.cpp` was only syntax-checked against the sfizz and Oboe headers, not built or run.
- **Android mono playback** is assumed to reach both speakers at full level (dual mono). This was not measured on a device.
- **Android's clip player** fades over about 15 ms on stop, not 80 ms. The fade blocks its caller.
- **Not run here:** the WinUI app (the `MediaPlayer` volume and fade are type-checked only), the Apple app target, and any physical phone.

## 12. The low end, a solo cornet, a trumpet and a band kit (pack `sounds-2026.09.29`)

**What made the low end sound bad.** Measured on the Mikkel golden, Old Hundredth, a minimal-band pop take and a full-band solo take, through Apple (PlaybackEngine, offline), alphaSynth (the Windows player; Android plays the same synth) and FluidSynth. The render harnesses are `RenderHarnessTests` in PlaybackKit and in the Windows tests (env-gated).

1. **One waveform doubled.** Parts that shared a target played the same sample for the same key: Solo/1st/2nd Horn, 1st/2nd Baritone, 1st/2nd Trombone. Baritone, euphonium and trombone were the same VSCO recordings under different EQ, and so were E♭ and B♭ bass. The golden has 1,553 same-source unison onsets (horns 571, trombone family 511, cornets 471). A unison summed to +6.02 dB at correlation 1.00 (horns, baritones, trombones), +5.85 dB at 0.92 (the basses) and +5.8 dB at 0.91 (baritone with trombone): one louder instrument, not a section, and a comb filter where the EQs differ. The limiter's rare hits on the golden came from these parts.
2. **Held notes pumped.** Loops were cut from decaying stretches. On the low brass the level stepped 2–4.5 dB at every seam (end quieter than start), and the loop body swung 3–8 dB, a sawtooth every 0.7–1.2 s on a held bass note. `checks.py loops` passed it, because it tested waveform continuity only.
3. **Apple's hall drowned the band.** Without a room IR (the app), "Concert hall sound" is the environment node's medium hall at −6 dB with sampler reverb blend 0.35. It made the band 9.7 dB louder than the dry room (wet 9.2 dB over direct, against the 4.5 dB the reference renderer is calibrated to), with a further +1.6…+3.4 dB at 63–125 Hz. Turning the hall off dropped the band by 9.7–11.3 LU.
4. **The kick carried the sub-bass.** MS Basic's kick has −5 dB of its energy below 60 Hz; the golden's 20–60 Hz band was mostly the kick.

Not the cause:
- **The limiter** is memoryless and active on 0.1% of golden samples.
- **Sample stretch** is at most 3 semitones in the comfortable ranges.
- **The 1–4 kHz level** of the euphonium (−28.2 dB re 100 Hz–1 kHz) and the B♭ bass (−36.7) is within the references (baritone −30.6; tuba −32.2 in ChoraleBricks, −36.0 in URMP). The trombones are 5–9 dB duller than the references, and EQ does not fix it (the VSCO mf samples lack the upper partials). That is left as is.

**What changed.**
- **Desk variants.** Same-source parts play different recordings per key (§ Band SoundFont in `sounds/README.md`). Every pair now sums to +2.8…+3.4 dB (median), with median correlation −0.05…0.09 and no key above 0.9.
- **Steady loops.** The sustain is held at the level of its first half second. The loop is placed where level and brightness match and nothing dips inside it. The pump median is 0.31 dB (was 1.10), p95 1.03 (2.85), max 2.56 (46.9).
- **Apple hall.** Reverb level −10.7 dB, with a −4 dB low shelf at 250 Hz on the reverb. The hall now adds as much energy as the dry room gives up to `dry_room_gain_db` (+5 dB, applied when the hall is off). Hall minus room: golden +0.4 dB total, 63 Hz −2.5 dB re 1 kHz. Loudness: golden −12.00 / −13.43 LUFS (hall / room), Old Hundredth −14.75 / −15.39, pop take −15.97 / −16.93 (before: −12.11 / −23.19, −20.00 / −25.07, −22.11 / −27.20).
- **Band kit.** VSCO muted concert bass drum, concert snare and clash cymbals. The bass drum has −21 dB of its energy below 60 Hz, against −5 for the MS Basic kick.
- **Solo cornet and trumpet.** See `sounds/README.md`. The solo cornet now sits about 1.4 LU further in front of the band on the golden than the old desk sound did.

**Levels after** (the gates, all against the staged pack):

| | Apple | alphaSynth (Windows; Android same synth) |
|---|---|---|
| Full-band phrase | −12.43 LUFS (gain 31.5 dB, was 26) | −12.80 (gain 5 dB, was 4); Android emulator −12.88 |
| Golden arrangement | −12.00 (hall), −13.43 (room) | −11.48 desktop, −11.54 phone SoundFont |
| Metronome click | unchanged | −9.41 dBFS (click −1 dB through the stage) |

- The alphaSynth velocity knots were re-measured. The band estimate offset was refitted to −0.17 on the golden (−11.54 measured, −11.54 estimated); the phrase estimates −12.28.
- The engine's MP3 (MuseScore's own sounds, not this pack) measures −4.6 LUFS, peaking at 0.0 dBFS; it is out of scope here.

**Sizes.** 16-bit 195.1 → 200.3 MB; phone 77.3 → 70.8 MB. Loops now end earlier, which pays for the solo cornet, the trumpet and the kit. On Android the score screen uses 35–45 MB less Java heap.

**Open.**
- **Apple per-part balance.** Against alphaSynth, on the golden stems with the solo cornet as reference, Apple plays most parts 2.4–5.3 dB hotter. This was already the case before (0…+5.7 dB), and comes from the environment node's seating (HRTF, distance), not from the pack.
- **The pop kit** needs a style signal from the arranger before anything can select it.
- **Velocity layers.** The alphaSynth phrase still jumps 6 dB between mp and mf and 5.7 dB between f and ff, at the three-layer splits.
