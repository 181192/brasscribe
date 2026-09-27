# Kvartett: a third output option

This plan adds a brass quartet as a third lineup, next to the full brass band and the small band. It covers what the quartet is, every place in the stack that has to change, and the order to build it in. It is a plan only. No production code has changed.

Line numbers refer to commit `fd41d61`.

---

## Short answer

**Instrumentation.** 1st Cornet (B♭), 2nd Cornet (B♭), Tenor Horn (E♭) and Euphonium (B♭). This is the standard quartet of the British brass-band world, and the Salvation Army built most of its quartet repertoire on it ([Trumpet Journey](https://www.trumpetjourney.com/2021/06/10/brass-chamber-groups-the-quartet/), [Score Exchange example](https://www.scoreexchange.com/scores/brass-quartet-for-2-cornets-tenor-horn-and-euphonium-96058.html)). Norwegian brass bands follow the British layout, so a Norwegian player will recognise it. I have not checked the rules of the Norwegian ensemble championships, which allow other combinations. Offer one quartet, with no variants in this change. If players ask for more, the first variant would be E♭ Bass in place of Euphonium, for a deeper bass. A trumpet–horn–trombone–tuba quartet or a brass quintet belongs to another tradition and is out of scope.

**What it costs.** All four instruments already exist in `instruments.py` and `instruments.rs`, with transposition, clef and every range. The work is in two places:
- The arrangers look up "Solo Cornet", "E♭ Bass" and "B♭ Bass" by name in about 15 places. A quartet has no E♭ Bass, so `lineup.by_name("E♭ Bass")` raises. The lineup has to carry its own roles: which part is the lead, which is the bass, whether there is a second bass, and the SoundFont bank of each part.
- Apps and tables assume two lineups. Most of these are `x == minimal ? "minimal" : "full"` ternaries, and a third value falls through to "full" without any error.

**Arranging for four voices** is four-part chorale writing. Melody goes to the 1st Cornet, bass to the Euphonium, and the harmony is voiced for 2nd Cornet and Tenor Horn, following SATB rules. ChoraleBricks brass4, our main brass benchmark, is itself a brass quartet playing SATB chorales, so it gives a ground truth for each voice.

**Solo takes** have no harmony to arrange. The quartet stays disabled for solo and on-device takes until a melody harmoniser exists.

**Size.** One implementation agent can build it in 9 ordered steps (§6). Step 1 is a refactor that must leave every golden and conformance output byte-identical.

---

## 1. The quartet

### 1.1 Parts

| Part (score order) | Instrument id | Sounding range used for placement (MIDI) | Written | Clef | SoundFont bank | nb name |
|---|---|---|---|---|---|---|
| 1st Cornet | `bb-cornet` | reading 55–79, limit 52–84 | M2 above | treble | 1 (the Solo Cornet preset) | 1. kornett |
| 2nd Cornet | `bb-cornet` | reading 55–79 | M2 above | treble | 4 | 2. kornett |
| Tenor Horn | `eb-tenor-horn` | reading 48–70 | M6 above | treble | 1 (the Solo Horn preset) | Althorn |
| Euphonium | `euphonium` | reading 40–67, limit 34–72 | M9 above | treble | 3 | Eufonium |

The ranges and transpositions come from `music/src/brasscribe_music/instruments.py:89-108` and `core/brasscribe-core/src/instruments.rs`. Nothing new goes into instrument knowledge. There is one player per part and no percussion.

**Part names.** Use the names quartet parts are printed with. "2nd Cornet" and "Euphonium" already exist in the band tables. That leaves two new names, **"1st Cornet"** and **"Tenor Horn"**, to add to every table that matches on part name (§2.8). The alternative is to reuse the band seat names ("Solo Cornet", "Solo Horn"). That needs no table changes, but prints "Solo Cornet" on a quartet part. Open question 1.

### 1.2 How the voices map

| Source | Band (today) | Quartet |
|---|---|---|
| melody / solo layer | Solo Cornet | 1st Cornet |
| bass / bass layer | E♭ Bass, B♭ Bass an octave lower | Euphonium only, placed low in its reading range (`prefer_low`), with no second bass |
| harmony / pads, choir | Flugelhorn, horns, baritones, cornets, trombones | 2nd Cornet (alto) and Tenor Horn (tenor), voiced together per slot |
| countermelody (strings top line) | Euphonium | dropped: the Euphonium is the bass (open question 3) |
| drums | Percussion | dropped, with a warning in `arr.warnings` |
| soprano doubling at climaxes | Soprano Cornet | none |

Chorale bass lines reach C2–D2 (36–38), which is below the Euphonium's comfortable floor of 40. `_place_line` with the Euphonium's `reading_limit` (34) keeps most phrases in the written octave. The rest move up an octave for the whole phrase, which is also what a quartet arranger would do. With the tenor voice capped at the bass (`floor`), this never makes the bass cross the tenor.

### 1.3 Voicing rules (quartet only)

Today's `_voice_slot` (`arranger.py:141-162`, `arranger.rs`) fills parts greedily from high to low. It doesn't look at the pair of inner voices together, and it doesn't check for parallels. With four voices every note is exposed, so the quartet gets its own voicer, `voice_satb`. It only runs when the lineup says `satb=True`, which keeps the band outputs unchanged. For each harmony slot it searches every (alto, tenor) pair inside the parts' ranges (about 25 × 23 candidates, which is cheap) and scores them:

Hard rules (a candidate that breaks one is rejected):
- no crossing: S ≥ A ≥ T ≥ B. Unisons are allowed only between A and T.
- spacing: S–A ≤ 12 and A–T ≤ 12 semitones (T–B is free)
- every note is a chord tone of the slot's pitch-class set

Scored, in this order (lexicographic, so the Rust port can match exactly):
1. chord coverage. The third must be present, the root is preferred for doubling, and the fifth may be left out.
2. parallel perfect fifths or octaves between any pair of voices from the previous slot (S and B included). Count them and keep the count as low as possible.
3. total movement |ΔA| + |ΔT| from the previous slot (smooth voice leading)
4. deterministic tie-break: the higher alto first, then the higher tenor

If no candidate passes the hard rules, the slot falls back to `_voice_slot`, and the fallback is logged as a warning. The benchmark (§4) counts the parallels and spacing faults that remain.

### 1.4 Difficulty

`faithful`, `standard` and `easier` apply as they do now (`difficulty.py`). Two changes:
- `SOLO_PART = "Solo Cornet"` (`difficulty.py:28`, `difficulty.rs:24`) becomes the lineup's lead part.
- `_fold` works on each part separately, so for `easier` it can push the Tenor Horn above the 2nd Cornet. For `satb` lineups the inner parts are voiced straight into the mode's range (`easy_range` for easier, `preferred` for standard) and are not folded afterwards. Lead and bass are still folded as they are today.

### 1.5 The layered solo-with-band case

`arrange_layers` with the quartet lineup:
- solo layer → 1st Cornet (`_place_line`, as for Solo Cornet)
- bass layer → Euphonium (`_place_line(prefer_low=True, bass_overflow_up=refit)`)
- pads (strings and keys) and brass choir are merged into one set of harmony slots (`harmony_slots(strings + keys + brass, end)`) and voiced with `voice_satb` for 2nd Cornet and Tenor Horn. Figuration is on for every mode except faithful, as now.
- countermelody, drums and soprano doubling: none (§1.2)
- dynamics: `layer_of_part` becomes lineup-aware. For the quartet, 1st Cornet → solo, 2nd Cornet and Tenor Horn → strings, Euphonium → bass.

On a solo take, bass and orchestra are empty, and three parts would be written as rests only. Engine profile `solo` and the apps' on-device path should refuse `quartet` with a clear message. The pickers disable the card for those takes, using the existing `canArrange` gate. Open question 2.

---

## 2. Touch points

### 2.1 Lineup model (the refactor that makes the rest possible)

| File | Change |
|---|---|
| `music/src/brasscribe_music/instruments.py:129-175` | `Lineup` gets `lead: str`, `bass: str`, `second_bass: str \| None`, `satb: bool = False`. Set `BRASS_BAND` and `MINIMAL_BAND` to their current values ("Solo Cornet", "E♭ Bass", "B♭ Bass"). Add `QUARTET = Lineup("Brass quartet", [...], lead="1st Cornet", bass="Euphonium", second_bass=None, satb=True)` with the banks from §1.1. Add `LINEUPS = {"band": BRASS_BAND, "minimal": MINIMAL_BAND, "quartet": QUARTET}` and `lineup_by_name()`, accepting "full" as an alias for "band". |
| `core/brasscribe-core/src/instruments.rs:212-275` | The same: fields on `Lineup`, `quartet()`, `lineup_by_name(&str) -> Result<Lineup, String>` |

### 2.2 Python arrangers and difficulty

| File:line | Change |
|---|---|
| `music/src/brasscribe_music/arranger.py:165-209` `arrange` | `lineup.lead` / `lineup.bass` / `lineup.second_bass` instead of the names at `:171`, `:174`, `:183`. Skip the B♭ Bass octave-down when there is no second bass. Use `voice_satb` for the inner parts when `lineup.satb`. |
| `arranger.py:226-238` `layer_of_part` | Takes the lineup (lead → solo, bass/second_bass → bass). The band keeps its current mapping. |
| `arranger.py:347-426` `arrange_layers` | `:371`, `:374`, `:380`, `:403`, `:408`, `:419` read the lineup roles. Satb branch as in §1.5. |
| `arranger.py` (new) | `voice_satb(pcs, alto, tenor, soprano_at, bass_at, prev, ranges)` |
| `music/src/brasscribe_music/difficulty.py:28,132` | `SOLO_PART` → `lineup.lead`. Satb inner parts are not folded (§1.4). |
| `music/src/brasscribe_music/musicxml.py:519-521` | `_band_midi` reads banks from `arrangement.lineup`, not `BRASS_BAND` (the writer needs the lineup passed in: `write_musicxml(..., lineup=)`) |
| `musicxml.py:525-536` `build_band_score` | `layer_of_part(arrangement.lineup, name)` |
| `eval/brasscribe_eval/arrange_layers_song.py:96,267-280` | `--lineup band\|full\|minimal\|quartet`, `lineup_by_name` |
| `eval/brasscribe_eval/arrange_song.py:36-44` | new `--lineup` (default minimal), passed to `arrange`, written to `comp.arrangement` when not the default |
| `eval/brasscribe_eval/musescore_roundtrip.py:51` | `lineup_by_name(opts.get("lineup"))` |

### 2.3 Rust core, CLI and conformance

| File:line | Change |
|---|---|
| `core/brasscribe-core/src/arranger.rs:199` `layer_of_part`, `:278-308` `arrange_with`, `:484-583` `arrange_layers_opts` | as in Python, one to one, including `voice_satb` with the same scoring order |
| `core/brasscribe-core/src/difficulty.rs:24,168` | `SOLO_PART` → `lineup.lead`, satb inner parts not folded |
| `core/brasscribe-core/src/notation/score.rs:1777` `band_midi` | banks from the arrangement's lineup, not `brass_band()` |
| `core/brasscribe-core/src/musicxml.rs:16-66` | pass the lineup through to `band_midi` |
| `core/brasscribe-core/src/pipeline.rs:174,239-243,494,508-511` | `lineup_by_name`, accepting "quartet". `arrange_composition` reads the lineup for non-layered compositions too. |
| `pipeline.rs:535` `arrange_song` | gets a lineup argument (`SongOptions { lineup }`, default minimal) and records it in `comp.arrangement` |
| `core/brasscribe-cli/src/main.rs:6,189` | `--lineup band\|full\|minimal\|quartet` for `layers`, and new for `song` |
| `core/conformance/brasscribe_conformance/cases.py:24-30` | `MIKKEL_VARIANTS` += `("layers-quartet", ["--lineup", "quartet"])`, `("layers-quartet-easier", ["--lineup", "quartet", "--difficulty", "easier"])`. For each chorale: `song` and `bench` cases with `options: ["--lineup", "quartet"]`. |
| `core/conformance/brasscribe_conformance/reference.py:69-79` | the `song` and `bench` kinds ignore `options` today. Pass them on (to `arrange_song` and to `evaluate(comp, lineup)`). |
| `core/brasscribe-core/tests/reference_fixtures.rs` + `tests/fixtures/` | a `voice_satb.json` unit fixture, produced by `brasscribe_conformance.fixtures` from the Python reference |
| goldens `data/golden/mikkel-arranged-band*` | **must not change**. No quartet golden goes into `data/golden`. The conformance run checks the quartet cases against the Python reference instead. |

### 2.4 FFI and bindings

Lineup is a **string** end to end (`LayersSongOptions.lineup`, `brasscribe-ffi/src/lib.rs:156`; C ABI `c_api.rs:191`). There is no enum to extend, so the layered path needs only doc changes:
- `brasscribe-ffi/src/lib.rs:156` and `c_api.rs:96`: docs say `"band" | "minimal" | "quartet"`
- `core/dotnet/Brasscribe.Core/BrasscribeCore.cs:29`: doc

Keep it a string. An enum would break every Swift, Kotlin and .NET caller for no gain.

The gap is `arrange_musicxml(composition_json, arranger)` (`lib.rs:68-90`, C `c_api.rs:80`). It takes an *arranger* ("auto", "layers", "minimal"), not a lineup. The apps call it to re-arrange after an edit or on the "Choose output" screen, and pass `"minimal"` for the small band, which selects the non-layered arranger. That is a mismatch today, and it can't express a quartet. Add, without changing the old function:
- UniFFI `arrange_musicxml_with(composition_json: String, options: ArrangeOptions) -> String`, where `ArrangeOptions { lineup, difficulty, key: Option<String>, transpose: Option<i32> }` is a `uniffi::Record` with defaults
- C `bc_arrange_with(json, options_json, out, err)`, with the same JSON keys as `bc_arrange_layers_song`

Regenerate with `core/scripts/bindings.sh`. That rewrites `core/bindings/{swift,kotlin,c}`, `core/swift/BrasscribeCore/.../brasscribe_ffi.swift` and `core/android/brasscribe-core/.../brasscribe_ffi.kt`. Add the P/Invoke to `core/dotnet/Brasscribe.Core/BrasscribeCore.cs`.

### 2.5 Engine

| File:line | Change |
|---|---|
| `engine/src/brasscribe_engine/schemas.py:10` | `Lineup = Literal["full", "minimal", "quartet"]`; description at `:133-134` |
| `engine/src/brasscribe_engine/profiles.py:37` | `LINEUPS = ("full", "minimal", "quartet")`. `solo()` (`:153-176`) rejects `quartet` with a `ValueError` ("a quartet needs harmony; record the whole group"). |
| `profiles.py:139-149` `brass_band` | nothing to change once `arrange_song` has `--lineup`: `stages._arrangement_flags` (`stages.py:107-123`) finds the flag through `--help` and passes it on. Today it fails the stage. |
| `engine/src/brasscribe_engine/cli.py:222` | `choices=["full", "minimal", "quartet"]` |
| `engine/src/brasscribe_engine/api.py:347,375` | no code change (the typed `m.Lineup` carries it) |
| `engine/src/brasscribe_engine/talking_score.py:443-447` | nb names: "1st Cornet" → "1. kornett", "Tenor Horn" → "Althorn" |
| `engine/openapi.json:1043` + enum | regenerate: `pixi run openapi` |
| `engine/tests/test_accessible.py:59-62,94-95,149` | `quartet` accepted. `lineup=quartet` on the test profile no longer fails. Solo + quartet → 422. |
| braille (`braille.py`) | no change: it takes part names from the MusicXML as they are |

### 2.6 Studio

- `studio/src/api/schema.d.ts:810,1082-1084`: `npm run gen:api`
- `studio/src/lib/validate.ts:13-42`: ranges for "1st Cornet" and "Tenor Horn", and the pairs `["1st Cornet","2nd Cornet"]`, `["2nd Cornet","Tenor Horn"]`, `["Tenor Horn","Euphonium"]` for the crossing check
- `studio/src/lib/talkingxml.ts:37`: nb names
- `studio/src/i18n.ts:455-457`: the profile descriptions say "arranged for a small band". Add "or a quartet" to brass-band.

Studio has no lineup picker, so there is nothing else to change.

### 2.7 Play apps

**Apple**
| File:line | Change |
|---|---|
| `Packages/BrasscribeKit/Sources/ScoreKit/CoreBridge.swift:20-21` | `case quartet = "quartet"` |
| `App/Views/OutputView.swift:86-90` | third radio: "Quartet" / "4 players, one on each part", disabled when the take has no harmony (solo) |
| `App/RustCoreBridge.swift:29-33` | call `arrangeMusicxmlWith` with the lineup and difficulty. Replace the ternary with a `switch`. |
| `App/OnDeviceSoloService.swift:63` | `switch`. `.quartet` is never reached (the picker disables it), but the switch must be exhaustive. |
| `Packages/BrasscribeKit/Sources/TranscriptionKit/CompanionService.swift:177-179` | `switch`: "full", "minimal", "quartet" |
| `App/Piece.swift:130` | subtitle: `switch` with "Quartet" |
| `App/PartNames.swift:8-13` | "1st Cornet": "1. kornett", "Tenor Horn": "Althorn" |
| `scripts/make-string-catalog.py:143,197` + `App/Localizable.xcstrings` | "Quartet" → "Kvartett", "4 players, one on each part" → "4 musikere, én på hver stemme"; regenerate the catalog |
| `App/ScreenshotScenes.swift:14-16` | one library item with `.quartet` |
| `AppTests/AppTests.swift:78-85` | a quartet arrange gives 4 parts |
| `docs/screenshots/*output*.png` | retake with `scripts/screenshots.sh output` |

**Android**
| File:line | Change |
|---|---|
| `app/src/main/kotlin/no/brasscribe/play/PlayViewModel.kt:114-116` | `QUARTET(R.string.lineup_quartet, R.string.lineup_quartet_desc)` |
| `PlayViewModel.kt:122` | `when (lineup)` → "full" / "minimal" / "quartet" |
| `PlayViewModel.kt:616` | re-arrange through `arrangeMusicXmlWith(comp, lineup)`, not the arranger ternary |
| `PlayViewModel.kt:723`, `ui/ScoreScreen.kt:91`, `ui/ReviewScreen.kt:263` | "my part" defaults to "Solo Cornet" and falls back to index 0, which is 1st Cornet in the quartet. That is fine, but use the lineup's lead when it is known. |
| `ui/OutputScreen.kt:74,91` | `listOf(FULL, MINIMAL, QUARTET)`. Quartet enabled only when `canArrange` and the take is not solo. |
| `ui/ScoreOptions.kt:102` | the label comes from the part count (`> 1` → "Full band"). Use the recorded lineup (`composition.arrangement.lineup`). |
| `ui/PartNames.kt:12-17` | nb names |
| `core-bridge/.../RustCoreBridge.kt:72` | `when`: pass "quartet" through (today anything but "minimal" becomes "band") |
| `model/.../CoreBridge.kt:17-18,89`, `engine-client/.../Models.kt:53-54` | docs and the new bridge method |
| `app/src/main/res/values/strings.xml:219-225`, `values-nb/strings.xml:217-223` | `lineup_quartet` "Quartet" / "Kvartett", `lineup_quartet_desc` |
| `engine-client/openapi.json` | `./gradlew :engine-client:syncOpenApi`. `EngineContractTest` compares the enums. |
| `core-bridge/src/test/.../RustCoreBridgeTest.kt:84-86` | a quartet case |
| `docs/screenshots/design/08-output-*.png` | retake |

**Windows**
| File:line | Change |
|---|---|
| `src/Brasscribe.Play.Core/ViewModels/OutputOptionsViewModel.cs:10` | `enum Lineup { FullBand, MinimalBand, Quartet }` |
| `OutputOptionsViewModel.cs:135,169`, `ViewModels/MainViewModel.cs:57` | `switch` expressions. Re-arrange through `bc_arrange_with`. |
| `ViewModels/MainViewModel.cs:465`, `MainWindow.xaml.cs:115` | the label comes from the part count (`<= 6` → SmallBand, so a quartet would read "Small band"). Use the recorded lineup, and add `Library_Quartet`. |
| `src/Brasscribe.Play/Views/ChooseOutputPage.xaml:27-40` | third `RadioButton` `QuartetChoice` |
| `Views/ChooseOutputPage.xaml.cs:24,31` | index ↔ enum via a switch, not `== 1 ?` |
| `Bridge/NativeCoreBridge.cs:163-169` | pass "quartet" through |
| `Engine/EngineModels.cs:23,29-30` | docs |
| `TalkingScore/MusicXmlTalkingScoreBuilder.cs:439-452` | nb names |
| `Playback/BrassSoundSet.cs:16-31` | nothing: "1st Cornet" matches "Cornet" and "Tenor Horn" matches "Horn" |
| `tools/Strings/gen_resw.py:133-140` → `Strings/{en-US,nb-NO}/Resources.resw` | `LineupQuartet*`, `Library_Quartet`; regenerate |
| `tests/.../Fixtures/openapi.json` | copy the regenerated spec |
| `tests/.../AppFlowTests.cs:357-378`, `NativeCoreBridgeTests.cs:78-80,230-239` | quartet cases |
| `tools/Screenshots` | retake the output page |

### 2.8 Tables that match on part name

Every table must resolve "1st Cornet" and "Tenor Horn". If one doesn't, the result is a silent fallback, not an error.

| Table | Missing entry means |
|---|---|
| `core/brasscribe-core/src/talking_score.rs:811-831` `nb_part_name` | English name in the nb talking score |
| `engine/.../talking_score.py:443-447`, `studio/src/lib/talkingxml.ts:37`, Apple `PartNames.swift`, Android `PartNames.kt`, Windows `MusicXmlTalkingScoreBuilder.cs:439` | the same, per surface |
| `studio/src/lib/validate.ts:13-42` | the range check skips the part |
| `sounds/mapping.json` (parts) | **`sounds/render.py:387` skips the part: the MP3 export has no 1st Cornet or Tenor Horn** |
| `sounds/mapping.json` players, `sounds/seating.json` | "2nd Cornet" and "Euphonium" have 2 players in the band. Render the quartet with one player per part and quartet seat positions: a `lineups.quartet` override block that `render.py` picks up from `composition.arrangement.lineup`. |
| `sounds/descriptors.py:41-43` | the timbre probe skips the part (tooling only) |
| MusicXML `<midi-bank>` (§2.2, §2.3) | the phone players fall back to bank 0 |

### 2.9 Benchmark, docs and site

- `eval/brasscribe_eval/arrange_bench.py`: `evaluate(comp, lineup=MINIMAL_BAND)`. It uses `lineup.lead` / `lineup.bass` in place of `:78-85`, and adds the quartet metrics (§4).
- `eval/brasscribe_eval/suites.py:266-274,481`: the `arrange` suite adds `quartet.*` keys. A new `quartet-audio` suite runs on the cached fixtures (§4).
- `eval/baselines.json:146-170`: the new keys
- `eval/brasscribe_eval/difficulty_bench.py:33,103`: add `("quartet", QUARTET)` to the lineup loop
- `docs/research/10-benchmark-results.md`: a "Quartet arrangement" section with the numbers
- `music/README.md`, `core/README.md`, `eval/README.md`, `docs/plan/apps-plan.md`: mention the third lineup
- `design/mockups/choose-output.html:42-43,74-75` and `design/mockups/png/choose-output-*.png`: third card
- `site/guide/index.html:172`, `site/nb/guide/index.html:170`, `site/nb/index.html:132-136`, `site/shots/output-*.png`: "Full brass band, small band or quartet"

Existing inconsistency, not fixed here: the small band is "Lite korps" on Apple (`make-string-catalog.py:143`) and on the nb site, but "Lite band" on Android, Windows and in the mockup. The new label is "Kvartett" everywhere.

---

## 3. Acceptance criteria

1. **No regressions.** The Mikkel golden (`mikkel-golden` suite) stays byte-identical. So does every existing conformance case (`brasscribe_conformance.run`) and every `band`/`minimal` output. The refactor in step 1 is checked on its own before any quartet code exists.
2. **Python = Rust.** All new quartet conformance cases (Mikkel quartet and quartet-easier, and song and bench for all 10 chorales) produce identical `composition.json` and MusicXML in Python and Rust.
3. **Hard constraints** on every quartet output (chorales and Mikkel, all three difficulties):
   - 0 impossible notes and 0 uncomfortable notes
   - 0 voice crossings between adjacent parts
   - 0 S–A or A–T gaps above an octave, except in slots that fell back to `_voice_slot` (each one reported in the warnings)
4. **Name tables.** One test in Python and one in Rust walks every part of every lineup. Each part must resolve in the nb name table, in `mapping.json` and in the MIDI bank list. Each app gets one assertion that its `PartNames` has "1st Cornet" and "Tenor Horn".
5. **Exhaustive mapping.** Each app has a unit test that maps every `Lineup` case to its engine string and to its core string. `quartet` must never become "full" or "band".
6. **Engine.**
   - `POST /v1/jobs` with `lineup=quartet` on `brass-band` produces 4 parts with the right names, transpositions and `<midi-bank>`.
   - On `solo` it returns 422.
   - The MP3 export contains all four parts, with no "not in mapping.json" warning.
7. **Apps.**
   - The picker shows three cards in en and nb.
   - Quartet is disabled for a solo take and says why.
   - Choosing it on an engine job sends `lineup=quartet`.
   - The re-arrange path on device (after an edit) keeps the quartet.
   - The library subtitle reads "Quartet".
8. **Benchmark** (§4) numbers are recorded in `baselines.json` and at least meet:
   - `quartet.melody_kept` 1.0 and `quartet.bass_kept` ≥ 0.98 on the chorale reference
   - `quartet.alto_recall_pc` ≥ 0.85
   - `quartet.parallels_per_100` ≤ 2

---

## 4. Benchmark: ChoraleBricks brass4 as quartet ground truth

The brass4 set (`eval/brasscribe_eval/choralebricks.py:17-18`) is 10 chorales: S = trumpet, A = flugelhorn, T = baritone, B = tuba. Their alto and tenor lines lie almost entirely inside the reading ranges of 2nd Cornet (55–79) and Tenor Horn (48–70). So the original voices can be compared with ours pitch for pitch, not only as pitch-class sets.

**Symbolic** (in CI, no audio). Take `composition_from_reference` (`arrange_bench.py:39-51`) and hand the arranger A and T merged as one harmony stream, as today. Arrange for the quartet, then measure:

| Metric | Definition |
|---|---|
| `melody_kept`, `bass_kept` | as now, against 1st Cornet and Euphonium (octave allowed) |
| `alto_recall_exact`, `tenor_recall_exact` | share of A (T) reference notes with the same onset and **same pitch** in 2nd Cornet (Tenor Horn). This measures whether the voicer rebuilds the original inner voices from nothing but the harmony's pitch classes. |
| `alto_recall_pc`, `tenor_recall_pc` | the same, by pitch class |
| `harmony_fidelity` | as now (Jaccard of pitch-class sets) |
| `parallels_per_100` | parallel perfect 5ths and 8ves between any pair of voices, per 100 slot changes |
| `spacing_faults` | slots with S–A or A–T > 12 |
| `crossings`, `impossible`, `uncomfortable` | as now |

Run the original chorales through the same metric functions as a reference row. That shows how far Bach's own voicing is from "zero parallels" under our slot model, so the thresholds in §3.8 can be set against it.

**Audio** (in CI from cached fixtures, no model runs). Run `eval/fixtures/choralebricks-brass4` MuScriptor medium and Basic Pitch outputs through `arrange_song --lineup quartet` and score them with the metrics above against the reference. This is the whole path "record a quartet, get quartet parts" on real brass audio. Its numbers show how much transcription error costs on top of the arrangement.

Local only: a `--export` of one chorale to MusicXML and PDF, for a player to read through.

---

## 5. Merge conflicts to expect

Other branches are changing the apps' connection and pairing UI and the engine's presence endpoints. Files both sides touch:

| File | Branch | Likelihood |
|---|---|---|
| `apps/apple/Packages/BrasscribeKit/Sources/TranscriptionKit/CompanionService.swift` | `feat/apple-listen-stop-connection` (diff seen: +119 lines) | certain |
| `engine/openapi.json`, `apps/android/engine-client/openapi.json`, `apps/windows/tests/.../Fixtures/openapi.json`, `studio/src/api/schema.d.ts` | `feat/engine-presence-status`, `feat/engine-device-pairing` | high: all regenerated. Regenerate after rebasing, don't merge them by hand. |
| `engine/src/brasscribe_engine/api.py`, `schemas.py` | engine presence and pairing | medium (the quartet change to them is one line) |
| `apps/android/.../PlayViewModel.kt` | `feat/android-listen-stop-connection` | high |
| `apps/windows/.../MainViewModel.cs`, `MainWindow.xaml.cs` | `feat/windows-listen-stop-connection`, `feat/bandroom-windows` | high |
| string catalogs: Android `values*/strings.xml`, Apple `make-string-catalog.py` + `Localizable.xcstrings`, Windows `gen_resw.py` + `Resources.resw` | every app UI branch | high. Add strings at the end of each block and regenerate after rebasing. |
| screenshots under `apps/*/docs/screenshots`, `site/shots` | design branches | medium. Retake last. |

Do the app steps last and rebase onto `main` just before them.

---

## 6. Implementation steps

Each step ends green before the next one starts. Commands:

```sh
pixi run test                                                          # Python: engine + music
export PATH=$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH
(cd core && cargo test --release)                                      # Rust unit + reference fixtures
(cd core/conformance && uv run python -m brasscribe_conformance.run)   # Python vs Rust, goldens
pixi run bench-cpu                                                     # or: brasscribe bench ci --require-data
```

1. **The lineup carries its roles (no behaviour change).**
   - Python and Rust: add `lead`, `bass`, `second_bass`, `satb` and `lineup_by_name` to `Lineup`.
   - Replace every hardcoded "Solo Cornet", "E♭ Bass" and "B♭ Bass" lookup listed in §2.2 and §2.3 with the lineup's role fields.
   - `band_midi` and `_band_midi` take their banks from the arrangement's lineup.
   - `layer_of_part` takes the lineup.

   *Done when:* `pixi run test`, `cargo test` and the full conformance run pass with **every output byte-identical** to `main`, the Mikkel golden included. Commit it on its own.
2. **The quartet lineup and the SATB voicer, in Python.**
   - Add `QUARTET` and `voice_satb` (§1.3).
   - Add the quartet branches in `arrange`, `arrange_layers` and `apply_difficulty` (§1.4, §1.5).
   - Add `--lineup` to `arrange_song.py`, and "quartet" to `arrange_layers_song.py`.
   - Tests in `music/tests/test_band_export.py`, `test_difficulty.py` and `test_instruments.py`: 4 parts, names, transpositions, banks, no crossings, spacing, and a hand-made I–IV–V–I with no parallels. Also the name-table test (§3.4).

   *Done when:* `pixi run test` passes.
3. **Benchmark.**
   - Quartet metrics in `arrange_bench.py`, the `quartet-audio` suite, and the reference row from the original chorales.
   - Put the numbers in `baselines.json` and `10-benchmark-results.md`.
   - Tune the scoring order in `voice_satb` until it meets §3.8, and freeze it before porting.

   *Done when:* `brasscribe bench ci --require-data` passes, with the new keys present.
4. **Rust port and conformance.**
   - `quartet()`, `voice_satb`, the arranger, difficulty and `arrange_song` lineup, and the CLI `--lineup` for `layers` and `song`.
   - A `voice_satb.json` fixture.
   - Conformance cases for Mikkel quartet and quartet-easier, and for chorale song and bench, with options passed on in `reference.py`.

   *Done when:* `cargo test --release` passes and the conformance run is 100 % identical, old and new cases alike.
5. **FFI.**
   - UniFFI `arrange_musicxml_with(composition_json, ArrangeOptions)` and C `bc_arrange_with`.
   - Doc updates for lineup.
   - Run `core/scripts/bindings.sh`, then the .NET P/Invoke and a test in `core/dotnet/Brasscribe.Core.Tests`.

   *Done when:* `cargo test` and `dotnet test core/dotnet/Brasscribe.Core.Tests` pass.
6. **Engine, Studio and sounds.**
   - Engine: `schemas.py`, `profiles.py` (solo rejects quartet), `cli.py`, and the `talking_score.py` names. Run `pixi run openapi` and update `engine/tests`.
   - Studio: `npm run gen:api`, `validate.ts`, `talkingxml.ts` and `i18n.ts`, then `npm test`.
   - Sounds: the quartet entries and the one-player override in `sounds/mapping.json`, `seating.json` and `render.py`.
   - Rust `nb_part_name`.

   *Done when:* `pixi run test` and `(cd studio && npm test)` pass, and one brass-band job with `lineup=quartet` renders an MP3 with 4 audible parts.
7. **Apple.**
   - Rebase onto `main` first.
   - Apply the §2.7 Apple rows and regenerate the string catalog.

   *Done when:* `(cd apps/apple && make test)` passes.
8. **Android.**
   - Apply the §2.7 Android rows and run `./gradlew :engine-client:syncOpenApi`.

   *Done when:* `(cd apps/android && ./gradlew testDebugUnitTest lint)` passes.
9. **Windows, then screenshots and docs.**
   - Apply the §2.7 Windows rows and run `gen_resw.py`.
   - Retake the output screenshots on all three apps, the mockup PNGs and `site/shots`.
   - Update the site guide text and the READMEs.

   *Done when:* `(cd apps/windows && dotnet test tests/Brasscribe.Play.Core.Tests -c Release)` passes (on Windows CI; locally `tools/check-macos.sh`).

Steps 1–4 are the risky part. Steps 5–9 are wiring, and their order can change if the connection branches land in between.

---

## 7. Open questions for the owner

1. **Part names:** quartet-native "1st Cornet" / "Tenor Horn" (recommended, and the plan assumes them), or band seat names "Solo Cornet" / "Solo Horn" (no table changes, but the printed part says "Solo")?
2. **Solo takes:** hide or disable the quartet until there is a melody harmoniser (recommended), or allow it and write the three other parts as rests?
3. **Solo-with-band layered source:** drop the strings countermelody (recommended, since the Euphonium must carry the bass), or give it to the Tenor Horn in bars where the pads are silent?
