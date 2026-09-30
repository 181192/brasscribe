# Trumpet: a soloist's range for the lead, and a trumpet seat

The owner wants to be able to add a trumpet. This plan does three things:

- it checks the claims of an earlier analysis;
- it designs what is built now: **(a)** a soloist range for the lead, and **(b)** "Trumpet in B♭" in "What do you play?";
- it describes two follow-ups that are **not built now**: **(c)**, instrument facts read from the core on every platform, and **(d)**, a trumpet sound preset (§5).

**Status (2026-09-29): (a), (b) and (d) done, (c) open.**
- (a) The soloist range is on `main`, and its golden was promoted (the old one is in `data/golden-backups/before-soloist/`).
- (b) Trumpet in B♭ and the trumpet seat are in the core, the engine, Studio, and "What do you play?" on Android and Apple (released in v0.2.0). Windows plays and names a Trumpet part, but has no "What do you play?" on `main`.
- (d) The Trumpet part now plays its own trumpet preset (bank 7) from the `sounds-2026.09.29` pack, so §3.3's "keeps the Solo Cornet's sound" and the P3-5 answer in §8 describe the state before it.
- Left: (c), instrument facts from the core on every platform (§5.1), and owner question 3 (§9).

Line numbers refer to `157d9df` (`main`). The measurement scripts are in [`trumpet/`](trumpet/):

- `sweep.sh` runs the Rust path over a set of ranges
- `lead_octaves.py` counts the lead notes that change octave
- `part_diff.py` diffs the parts
- `soloist_rule.py` compares the soloist rule with today's placement on ChoraleBricks
- `musescore_ranges.py` reads the ranges from the MuseScore app bundle

The review's findings are answered point by point in §8.

---

## Short answer

- **The real loss is range, and the placement makes it worse.**
  - Today 116 of Mikkel's 694 solo notes are written in another octave. Python and Rust give the same result.
  - 89 of them sit in five phrases that reach 83–84, above the cornet's playable 82.
  - The other 27 would still move with no limit at all. `best_shift` counts notes inside the *reading* range (55–79) and breaks ties toward its middle, 67. That drops 22 intro notes an octave and raises 5 closing notes one (§1.3).
- **(a) Soloist range.** In **faithful** mode only, the band's own lead is written in the octave the soloist played.
  - The lead's range is a new **soloist range**: 52–84 for the B♭ cornet (the qa tool's "solo cornet" row) and 52–85 for the B♭ trumpet (MuseScore's pro range).
  - A phrase keeps the notes that fit, and only a note outside the range moves.
  - On Mikkel, 0 of 694 notes move.
  - On 93 ChoraleBricks brass stems, with SwiftF0's own transcription as input, trumpet and flugelhorn go from 26 % and 11 % moved to **0 %** (§2.5).
  - Standard, easier, the quartet and "tune on your part" (`lead=seat`) are byte-identical to before.
  - The new golden goes in its own directory, so `main` and every other branch stay green.
- **(b) Trumpet.** A new instrument, "Trumpet in B♭" (`bb-trumpet`), and a new seat, **Trumpet** / «Trompet», in "What do you play?".
  - The seat takes the lineup's lead part: Solo Cornet in the bands, 1st Cornet in the quartet. That part is then written and labelled **Trumpet**, and it keeps the Solo Cornet's sound.
  - The band stays cornet-only, with 18 parts. There is no trumpet section seat, no C trumpet and no new sound.
  - A solo take is written for Trumpet in B♭.
- **Mikkel's soloist** is Ole Edvard Antonsen, a trumpet soloist. But the repo's own notes on the concert video see "cornet-like proportions" at 0:10 and a wider bell later (`docs/songs/mikkel.md:14`). So the instrument on this recording is not settled, and nothing in this plan depends on it.
- **Follow-ups (plan only).**
  - (c) makes every platform read instrument facts from the core: names, labels, section, ranges and `tune`. About 30 copies are matched by name today (§1.5).
  - (d) adds a raw-trumpet SoundFont preset and republishes the sound pack.

---

## 1. The earlier findings, checked

| Finding | Verdict | Evidence |
|---|---|---|
| Instruments are plain data in `instruments.rs` / `instruments.py` | **True** | `instruments.rs:46-67` and `:128-176`, `instruments.py:35-58` and `:88-110`. |
| B♭ cornet and B♭ trumpet notate the same: −2, treble, GM 56 | **True** | MuseScore 4.7.5 `bb-trumpet`: chromatic −2, diatonic −1, program 56 (§1.2). They differ in range, and in sound id: `brass.trumpet.bflat` against `brass.cornet`. |
| cornet-a/b are trumpet samples with a cornet EQ | **True** | `sounds/mapping.json:35`, `:82`. cornet-a is Iowa MIS trumpet and cornet-b is VSCO 2 CE trumpet, each through RBJ biquads baked in by `sounds/build.py:250-299`. |
| Solo layer is MIDI 53–84, lead limit 82, 116 of 694 (17 %) drop an octave | **True, on both paths** | §1.3. On the Rust CLI, 116 notes move: 111 down and 5 up. That is the same as the Python golden. `composition.json` is byte-identical, and the MusicXML differs only in writer formatting. |
| With a lead range up to 89 only 13 move, top 84 | **Only with the reading range widened too** | §1.3. Raising only the limit (84–89) leaves 27. 13 needs reading = limit = (52,89), and then all 13 move *up*. |
| The listed name-matched copies | **True, but incomplete** | §1.5 has about 30. |
| Unchecked: MuseScore ranges | **Checked** | §1.2 |
| Unchecked: Rust path | **Checked** | §1.3 |
| Unchecked: why 13 still move | **Explained** | §1.3: the reading-range count and centre tie-break in `best_shift` |
| Unchecked: cornet or trumpet soloist | **Unresolved** | Antonsen is a trumpet soloist. `mikkel.md:14` sees a cornet-like instrument at 0:10. The solo voice's `instrument_hint` is "trumpet/cornet". |

### 1.2 MuseScore ranges

MuseScore 4.7.5 (`/Applications/MuseScore 4.app`) compiles `instruments.xml` into the binary. The templates under `Contents/Resources/templates` carry full `<Instrument>` blocks, which `trumpet/musescore_ranges.py` reads. The review cross-checked them against `share/instruments/instruments.xml` at tag v4.7.5 and they agree.

| MuseScore id | Name | amateur (A) | pro (P) | transpose | sound id | program |
|---|---|---|---|---|---|---|
| `bb-trumpet` | Trumpet in B♭ | 52–**80** | 52–**85** | −2 / −1 | `brass.trumpet.bflat` | 56 |
| `bb-cornet` (brass-band template: `c-cornet`) | Solo Cornet … | 52–79 | 52–82 | −2 / −1 | `brass.cornet` | 56 |
| `eb-cornet` | Soprano Cornet | 57–84 | 57–87 | +3 / +2 | `brass.cornet.soprano` | 56 |
| `flugelhorn` | Flugelhorn | 52–79 | 52–82 | −2 / −1 | `brass.flugelhorn` | 56 |

The core's cornet (`pro (52,82)`, `comfortable (52,79)`) already matches MuseScore. A trumpet has three semitones more at the top, so Mikkel's 84 (C6 sounding, written D6) is playable on a trumpet and not on a cornet by MuseScore's numbers.

The repo's QA tool disagrees for the solo cornet. `qa/tools/musicxml_readability.py:48` gives `"solo cornet"` an extreme of written D6, which is sounding 84. `"cornet"` gets written C6, sounding 82. §2.2 settles which wins.

### 1.3 Mikkel on the Rust path, and what makes notes move

The setup is `brasscribe-core arrange-layers` on `data/mikkel/repro/layers` with the pinned contour (the conformance `mikkel/layers` case). `lead_octaves.py` compares each solo-layer note with the Solo Cornet note at the same onset. `sweep.sh` edits the B♭ cornet's `reading` and `reading_limit` for each row, then restores the file.

| Cornet reading / limit (sounding) | Rule | Moved | Top | Note |
|---|---|---|---|---|
| (55,79) / (52,82) | today | **116** | 82 | = golden |
| (55,79) / (52,84) | today | 27 | 84 | = `mikkel-arranged-band.before-cornet-limit` |
| (55,79) / (52,85), (52,86), (52,89) | today | 27 | 84 | the limit no longer binds |
| (55,82) / (52,84) | today | 20 | 84 | the qa "solo cornet" row |
| (55,84) / (52,86) or (52,89) | today | 17 | 84 | |
| (52,85) / (52,85) | today | 20 | 84 | |
| (52,89) / (52,89) | today | **13** | 84 | the earlier analysis's number: all 13 move up |
| (55,79) / (52,85) | phrase kept as played when it fits the limit | **0** | 84 | the rule in §2 gives the same on Mikkel |
| (55,79) / (52,82) | same rule | 97 | 82 | the rule alone, without the range |

The two "as played" rows used a one-line prototype hook at the top of `best_shift`. When `ASHEARD` is set, the hook returns shift 0 for a tune phrase whose notes all lie inside the limit:

```rust
if !prefer_low && std::env::var("ASHEARD").is_ok() && pitches.iter().all(|&p| limit.0 <= p && p <= limit.1) { return Some(0); }
```

It was reverted after the measurement. Run it with `ASHEARD=1 docs/plan/trumpet/sweep.sh 55,79,52,85`.

**Why notes move with room to spare.** `best_shift` (`arranger.rs:99-128`, `arranger.py:58`) scores each octave shift in two steps:

1. The number of notes inside the **reading** range `preferred()`, not inside the limit.
2. On a tie, the distance of the phrase's mean from the middle of that range (67 for 55–79), plus the jump from the previous phrase.

So, with only the limit raised to 84:

- **22 notes drop.** These are the intro phrases, ticks 0–3552, pitches 69–84. The phrase at tick 252 (71–84) drops because more of its notes land in 55–79 an octave down: the count. The others (69–76) fit either octave, and the lower one is nearer 67: the tie-break.
- **5 notes rise.** This is the closing phrase at ticks 9198–9384 (57–67). The upper octave is nearer the middle and nearer the previous phrase's last note.

Widening the reading range only moves the middle. At (52,89) the middle is 70.5: the intro no longer drops, but the phrases at ticks 1188 and 8766–9384 rise instead. That is the earlier analysis's 13.

The soloist rule removes the tie-break for the lead: a note that fits is written as played (§2.2).

### 1.4 Side effects if the range were simply widened

The review measured these (`docs/research/15-trumpet-critique.md` §1.2), and they agree with the code. Placement runs before `apply_difficulty` (`arranger.rs:794`, then `difficulty.rs:163`). So widening the cornet's `reading_limit` would change the standard and easier leads as well.

Standard and easier then fold the high phrases back note by note (`difficulty.rs:144` `fold`). That raises the octave switches inside phrases from 43 to 47 (standard) and from 68 to 72 (easier). That per-note flipping is exactly what `743c04d` removed from placement.

Widening `reading` would raise standard's lead to 82–84 and easier's to 80. This plan does neither. The soloist range is a separate field, used only by the faithful soloist placement and the lead's range check (§2).


### 1.5 Every hardcoded copy of instrument facts

This merges the earlier list, the review's §1.5 and a full audit. "Today with a trumpet" is what a part or seat for Trumpet in B♭ gets now.

| Where | What | Keyed by | Today with a trumpet |
|---|---|---|---|
| `core/.../talking_score.rs:810-834` `nb_part_name` | 20 nb part names. The FFI's `seats()` and `part_name_nb` read them | exact name | English name in the nb UI |
| `talking_score.rs:836-858` `instrument_nb` | substring replaces (Cornet→kornett, " in B♭"→" i B") | contains | «trumpet i B» |
| `engine/.../talking_score.py:440-458` `NB_PART_NAMES`, `instrument_nb` | a Python copy of the two above | name / contains | the same |
| `engine/.../schemas.py:13-15` `Seat` Literal | 18 seat ids, and from there `engine/openapi.json`, `studio/src/api/schema.d.ts`, `apps/android/engine-client/openapi.json`, the Windows test fixture | id | 422 before `profiles.py:63` `_check_seat` runs |
| `engine/.../profiles.py:251` | "solo cornet & brass band (draft)" | literal | wrong title |
| `studio/src/lib/validate.ts:11-31` `RANGES`, `:35-49` `CROSSING_PAIRS` | ranges per part name | name | no range check |
| `studio/src/lib/talkingxml.ts:36-43` `NB_PARTS` | nb names | name | English name |
| `studio/src/lib/navigator.ts:225-238` | instrument name by transposition (−2 → "Cornet in B♭") | chromatic | "Cornet in B♭" (Flugelhorn has the same bug today) |
| `studio/src/views/run.ts:277-280` `seatName` | title-cases the seat id | id | "Trumpet" by luck |
| `qa/tools/musicxml_readability.py:46-60` `RANGES` | written ranges by part-name substring | contains | unchecked |
| `apps/apple/.../ScoreKit/Score.swift:198-233` `Section.init`, `defaultSeat` | section and pan | name contains | `.other`, panned centre |
| `apps/apple/App/Seats.swift:132-150` | tile order, 5 localized tile titles | instrument id | last tile, no nb title |
| `apps/apple/App/PracticeModel.swift:146-148`, `ScoreKit/CoreBridge.swift:66-71` | "Solo Cornet" / "1st Cornet" as the lead | literal | not "your part" when the soloist is the lead |
| `apps/android/.../ui/WhatDoYouPlayScreen.kt:56-68` `TILES` and strings.xml:573-584 (nb :571-582) | tiles, order and labels | instrument id | **dropped**: `TILES.filter` at :158 hides it |
| `apps/android/.../RustCoreBridge.kt:114` | drops the core's `tune` | – | "Who plays the tune?" wrong (being fixed on `fix/user-flow`) |
| `apps/android/model/.../Pitch.kt:75-86` `Instrument` enum | en/nb names, key label, chromatic, program | enum | no entry |
| `apps/android/.../ui/ReviewScreen.kt:117` | instrument from chromatic, first match | chromatic | "Cornet in B-flat" |
| `apps/android/.../MyInstrument.kt:112,139-144`, `Lineup.kt:14-16,36`, `PlayViewModel.kt:863,1224` | quartet aliases, leads, part → layer | name | the soloist is not the lead |
| `apps/android/.../score/SoundPack.kt:25-35` | SFZ folder list, cornet siblings | target id | no `trumpet` folder |
| `apps/windows/.../Playback/BrassSoundSet.cs:17-32` `PartMap` (used without mapping.json) | sound folder | contains | no brass sound |
| `apps/windows/.../TalkingScore/MusicXmlTalkingScoreBuilder.cs:443-484` | its own nb tables | name / replace | English name |
| `apps/windows/.../ViewModels/ScoreViewModel.cs:159,281` | play-along part = first name containing "Solo" | contains | Solo Cornet, not the soloist |
| `apps/windows/.../Seats/SeatCatalog.cs:100-124` (branch `feat/my-instrument-windows`) | `TileKey`, `TileOrder`, `TuneInstruments` | instrument id | last tile, English, no tune |
| `apps/windows/tests/.../PartSoundTests.cs:80` | renames "3rd Cornet" to "Trumpet in B♭" and expects the cornet preset | name | breaks once "trumpet" gets its own preset |
| `sounds/mapping.json` `resolve` (keywords `["trumpet","Solo Cornet"]` :1366, `instruments` `"brass.trumpet"` :1451), `sounds/partsound.py:70-80`, `partsound-vectors.json:317`, `seating.json` | the resolver, which is ported to Kotlin (`BandSound.kt:42-85`), C# (`PartSoundResolver.cs:20-64`), Swift (`PartSoundResolver.swift:31-82`) and TypeScript (`partsound.ts:31-70`) | name / keyword / sound id | plays Solo Cornet. `brass.trumpet.bflat` and «trompet» miss and reach only the program-56 fallback |
| `core/.../arranger.rs:617` `BAND_LEADS`, `:632-633` `PAD_PARTS` and `CHOIR_PARTS`, `:262-282` layer routing; `arranger.py:560-593` | the arranger's roles for the band's own parts | name | fine: a trumpet that takes the lead part is `lineup.lead`; `BAND_LEADS` gains "Trumpet" for the soprano doubling (`:891`) |
| `instruments.rs:562` `TOP_INSTRUMENTS` | tune-on-top instruments | id | a trumpet lead voices the inner parts wrongly unless it is added |

The arranger's role lists are arranging policy for the band's own parts, not instrument facts. They stay as they are.

---


---

## 2. (a) The soloist range for the lead

### 2.1 Data

**`Instrument.solo`.** A new field, `solo: Option<(i32, i32)>` (Python `solo: tuple[int, int] | None = None`). It holds the sounding range a soloist plays on this instrument. `solo_range()` returns it, and falls back to `pro`.

| Instrument | `pro` | `solo` | Source |
|---|---|---|---|
| B♭ cornet | (52,82) | **(52,84)** | `qa/tools/musicxml_readability.py:48`: "solo cornet", extreme written D6. MuseScore has no soloist field. |
| B♭ trumpet (§3) | (52,85) | None (= pro) | MuseScore 4.7.5 `bb-trumpet` P |
| every other | as today | None | |

The section cornet parts keep MuseScore's `pro` 82, so the cornet-limit fix (`743c04d`) stands for them. The qa row wins only for the soloist, because it is the repo's only source for a soloist's top.

**`Lineup.lead_moved: bool`.** Set by `lead_lineup` (`instruments.rs:533`, `instruments.py` twin) when it moves the tune onto the seat's part. `Lineup::soloist_lead()` is true when the lineup is none of these:

- `satb` (the quartet)
- `as_played` (a solo take)
- `lead_moved`

So it covers the band's and the small band's own lead, and a trumpet that took the lead part (§3.3).

### 2.2 Placement

This goes in `arrange_layers_opts` (`arranger.rs:794`) and its twin (`arranger.py:728`). The existing `place_line` call becomes:

```text
if difficulty == faithful && lineup.soloist_lead() && in_register(solo, lead.instrument.solo_range())
    place_soloist(solo, lead)          # new
else
    place_line(solo, lead)             # today, unchanged
```

- **`in_register`.** At least `SOLOIST_SHARE` = 0.95 of the solo layer's notes lie inside `solo_range()`.
  - A recording in another register keeps today's placement. That includes a euphonium played on the phone with no seat set.
- **`place_soloist`.** It goes phrase by phrase, over the same phrases as today (`phrases()`):
  - **A lone outlier moves alone.** A note outside the range whose neighbours in the phrase are inside, each 7 or more semitones away (`OUTLIER_JUMP`), is almost always a tracker octave error. It moves by the fewest octaves into the range, with the warning `"{part}: moved {p} to {q} at tick {t} (outside the range)"`. That is `place_as_played`'s format, so `inspection.py:97` `_MOVED` reads it.
  - **Then the phrase as a whole.** A phrase that fits is written as played. One that doesn't moves as a whole by the fewest octaves that fit it, with ties going to the shift nearest the previous note, so its contour is kept. A phrase that no octave fits is placed the way a non-soloist lead is (`place_phrase`: split at its largest leaps).
  - **Why not fold every outside note.** A phrase that peaks above the range (an arch to 88, a trill 84/86) would lose its peak one note at a time and flip direction. That is the bug `743c04d` removed (review P1-4). Unit tests on both sides pin the arch, the run and the trill, and conformance has `layers-transpose-up-3`, where the lead reaches 87.
  - Then `hold_small_gaps`, as today.
- **Why lone outliers first.** A single tracker outlier, such as a harmonic an octave up, must not move the whole phrase. §2.5 measures this: moving a whole phrase leaves trumpet stems 10.5 % moved, and moving only the outliers leaves 0 %.
- **Unchanged:** standard and easier (placement by the reading range, limit 82, then `fold`), the quartet, `lead=seat` for a band part, solo takes (`place_as_played` keeps `pro`), and the non-layered arrangers.

### 2.3 The range check

`Lineup::check(part_name, pitch)`, new, with a Python twin. For the lead of a `soloist_lead()` lineup:

- the hard limit is `solo_range()`;
- the soft limit stays `comfortable`.

Every other part keeps `Instrument::check`. `validate_part(lineup, part, pitches)` sits next to `validate_range` (`instruments.rs:382`, `instruments.py:259`), and these switch to it:

- `music/tests/test_band_export.py:52`
- the review's `music/tests/test_range_invariants.py`

The soft limit is deliberately not widened. A soloist above the amateur top (79 on a cornet, 80 on a trumpet) is still told so, as today. On Mikkel that is 44 notes on the cornet lead (above 79) and 34 on a trumpet lead (above 80). All of them are "uncomfortable" and none are "impossible".

**The validators that (a) needs, in the same commit as the placement:**

| Validator | Change |
|---|---|
| Studio fallback, `studio/src/lib/validate.ts:14` | `"Solo Cornet": R([52, 84], [52, 79])`. The table is keyed by part name, and Solo Cornet is the soloist lead of both band lineups. With `lead=seat` it is a band part whose placement never passes 82, so the looser hard limit changes nothing there. |
| Engine validation (`inspection.py:101`) | Nothing. It reports the arranger's warnings, and the soloist placement warns only for notes it moved. |
| qa readability, `musicxml_readability.py:48` | Nothing. The "solo cornet" row already reaches written D6. |
| Apple, Android, Windows | None of the three has a range validator (§1.5). |

Reading the range from the core's data (a `PartInfo` over FFI or OpenAPI) is follow-up (c). No payload carries ranges today, so (a) makes the one-row table change instead.

### 2.4 Per difficulty

| Lead | faithful | standard | easier |
|---|---|---|---|
| Solo Cornet (band, small band) | **soloist**: as played within (52,84) | reading (55,79), limit (52,82), fold | easy (55,75), limit (52,82), fold |
| Trumpet (a trumpet seat took the lead part, §3.3) | **soloist**: as played within (52,85) | reading (55,79), limit (52,82): the Solo Cornet's notes | the same as Solo Cornet |
| 1st Cornet (quartet), a `lead=seat` band part | as today | as today | as today |

### 2.5 Evidence

**Mikkel, on the Rust path.** The prototype widened the range at the lead's call site only (`arranger.rs:794`), not on the cornet instrument, and kept phrases that fit as played. Every Mikkel solo note is inside (52,84), so the rule in §2.2 gives the same result:

| Part | Notes, today → soloist | Changed | Top |
|---|---|---|---|
| Solo Cornet | 694 → 694 | 116 back to the played octave | 82 → 84 |
| Repiano Cornet | 204 → 211 | 23 | 72 → 67 |
| 2nd Cornet, 3rd Cornet | 204 → 211 | 9 each | 65 |
| Flugelhorn | 237 → 249 | 44 | 69 → 77 |
| Solo Horn | 254 → 256 | 30 | 60 → 65 |
| 1st Horn, 2nd Horn | 254 → 256 | 10, 2 | 59 |
| 1st/2nd Baritone, 1st/2nd Trombone | same | 6, 2, 6, 2 (re-voiced) | same |
| Soprano, Euphonium, Bass Trombone, basses, percussion | unchanged | 0 | |

The inner parts get back the notes the cornet-limit fix had turned into rests (`14730d0`). There are also no more split warnings or octave switches inside phrases on the lead.

**More than one piece.** `soloist_rule.py` puts every ChoraleBricks brass stem (93 stems, 10 chorales) on the small band's Solo Cornet as a faithful lead. That is the phone's solo take with no seat set. Each placed note is compared with the annotated note of the same pitch class within 0.1 s.

Two inputs are used:

- **played**: the annotation itself, as if tracking were perfect;
- **tracked**: SwiftF0's raw transcription of the stem, with no voting and so with its outliers.

| Instrument | Line | Stems in register | Today moved | Soloist rule moved | Phrase-shift variant |
|---|---|---|---|---|---|
| Trumpet | played / tracked | 20 of 20 | 4.0 % / **25.7 %** | 0.0 % / **0.0 %** | 0.0 % / 10.5 % |
| Flugelhorn | played / tracked | 20 of 20 | 0.7 % / 10.9 % | 0.0 % / 0.0 % | 0.0 % / 1.7 % |
| French horn | played / tracked | 11 of 11 | 56.4 % / 57.6 % | 0.2 % / 0.2 % | 9.8 % / 11.0 % |
| Baritone | played / tracked | 13 of 24 | 93.5 % / 96.0 % | 45.0 % / 45.9 % | 54.5 % / 55.0 % |
| Trombone | played / tracked | 2 of 8 | 100 % / 100 % | 71.9 % / 77.6 % | 80.3 % / 86.1 % |
| Tuba | played / tracked | 0 of 10 | 100 % / 100 % | 100 % / 100 % | 100 % / 100 % |

"Phrase-shift variant" moves a whole phrase when any of its notes is outside. It is the rule this plan does not take.

After the step 1 review (P1-4), the rule as built moves a note alone only when it is a lone outlier, and otherwise shifts the whole phrase. Its numbers now fall between the two columns. On this table trumpet and flugelhorn stay at 0 %, and horn goes to 9.8 % / 11.0 % (phrases that dip below E3 move up whole). In the solo-instruments benchmark, which is the full solo-take path, `trumpet.cornet_moved` is 5.3 % (23.2 % today). The rest are unchanged. The contour is kept in every case.

**What it says:**

- **Tracker outliers.** On tracked trumpet lines today's placement moves a quarter of the notes, because stray notes drag whole phrases to another octave. The soloist rule moves none. The review's worry, that keeping the played octave also keeps tracker octave errors, doesn't show here: an outlier outside the range is folded note by note, and the notes around it stay put.
- **The gate.** Trombone and tuba lines sit below the cornet, and the gate keeps today's placement for all tuba stems and 6 of 8 trombone stems.
- **Behaviour change for low takes.** Baritone chorale voices that stay above E3 (13 of 24) and every horn stem pass the gate. They are now written on the Solo Cornet in the octave played, low on the staff, where today they are moved up an octave. That is what "faithful" promises, and a player who sets their seat gets their own instrument anyway.

The Mikkel intro phrases at ticks 0 and 156 (2 notes and 1 note) are the solo line alone, where the stems are clean (`mikkel.md`). There is no ground truth for their octave. The rule writes them as heard.

### 2.6 Golden, without breaking anyone

`data/golden` is one directory, symlinked into every worktree. `core/conformance/.../run.py:180-187` compares against it and exits 1 on any difference. So the golden is **not** re-saved in place.

- **The new output** goes to `data/golden/mikkel-arranged-band.soloist`, with its manifest. The recipe is the one from `14730d0`: orchestra-with-soloist, `--reuse data/mikkel/repro`, no heavy models.
- **In the same commit**, every consumer that compares *the new code's* output with the golden points at `.soloist`:
  - `core/conformance/brasscribe_conformance/cases.py:108`
  - the Windows `NativeCoreBridgeTests.cs:20` `GoldenNotes` count, and `TestPaths.cs`
  - `music/tests/test_seats.py`
  - `eval/baselines.json`, `eval/brasscribe_eval/difficulty_bench.py`, `suites.py`
  - `qa/reports/mikkel-golden-readability.json`
  - the full list: the tests that turn red when `make check-all` runs with the old golden and the new code
- **Fixture-only readers stay on the old directory.** These are the apps' playback and notation tests that only load the MusicXML.
- **At merge**, one commit (`chore: promote the soloist golden`):
  - renames `mikkel-arranged-band` to `mikkel-arranged-band.before-soloist-range` and `.soloist` to `mikkel-arranged-band`;
  - reverts the repointed paths.

  This is done by whoever merges, after the owner's go.
- **The benchmark doc** `docs/research/10-benchmark-results.md` gets the Mikkel faithful rows re-measured. Its standard, easier and quartet rows must not move, which proves §2.4.

**Expected diff against the old golden.** These are the §2.5 numbers, verified again on the real implementation in step 1:

- `composition.json` is byte-identical;
- Solo Cornet: 694 notes, top 84, 116 notes back in the played octave;
- the inner parts: Repiano, 2nd and 3rd +7 each, Flugelhorn +12, the Horns +2, and the baritones and trombones re-voiced;
- the rest unchanged;
- the talking score, BRF, MIDI, MP3 and PDFs follow.

---

## 3. (b) "Trumpet in B♭" in "What do you play?"

### 3.1 The instrument

```text
TRUMPET  id "bb-trumpet", name "Trumpet in B♭", short "Tpt.", chromatic −2, diatonic −1, treble
         pro (52,85), comfortable (52,80)            MuseScore 4.7.5 bb-trumpet
         reading (55,79), reading_limit (52,82)      the cornet's: standard/easier write the same notes
         solo None (= pro)
         roles Melody, Solo, Countermelody, UpperHarmony
         gm_program 56, musescore_id "bb-trumpet", sound "brass.trumpet.bflat", section "cornets"
```

- `INSTRUMENTS` gets 12 entries.
- `TOP_INSTRUMENTS` (`instruments.rs:562`) gains `bb-trumpet`, so the inner parts are voiced under a trumpet lead exactly as under the Solo Cornet.
- `BAND_LEADS` (`arranger.rs:617`, Python twin) gains "Trumpet", so the Soprano's climax doubling in standard and easier (`arranger.rs:891`) follows the Trumpet lead too.

### 3.2 The seat

```text
Seat { id: "trumpet", part: "Trumpet", reads: ["treble"] }                       tune: true
SEAT_PARTS "trumpet": [Some("Solo Cornet"), Some("Solo Cornet"), Some("1st Cornet")]
own part: Part { name "Trumpet", instrument TRUMPET, players 1, short "Tpt.", midi_bank Some(1) }
```

- **`Seat::band_part`** (`instruments.rs:412`) becomes `Seat::own_part`. It is the band part for the 18 band seats, and `Trumpet` for the new one. Every caller changes to it, including `pipeline.rs:368`, the solo take's window, which becomes 52–85 for a trumpet.
- **A solo take for the trumpet seat** is one part, "Trumpet", written as played (`seat_lineup`).
- **The engine.** `schemas.py:13` `Seat` gets `"trumpet"`. The OpenAPI is regenerated into `engine/openapi.json`, `studio/src/api/schema.d.ts`, `apps/android/engine-client/openapi.json` and the Windows fixture.

### 3.3 The trumpet takes the lead part: swap in place, not a 19th part

In the full and small band (not the quartet), a trumpet seat **takes the lineup's lead part in place**. `with_seat(lineup, seat)` in `composition_lineup` (`arranger.rs:944`) runs right where `with_reading` runs today, so the same thing happens when a device re-arranges the score.

The Solo Cornet part:

- becomes "Trumpet", `Tpt.`, Trumpet in B♭;
- keeps its players and `midi_bank` 1;
- stays the lead.

The rule behind it: a seat whose own part is not in the lineup takes the part it maps to, when that part is the lineup's lead. Trumpet is the only such seat.

- **Notes.** Identical to the default score. The soloist range becomes the trumpet's 85, and Mikkel still tops out at 84.
- **Sound.** The existing cornet sound:
  - The band SoundFont goes by `<midi-bank>1` (the Solo Cornet preset).
  - The realistic tier and every resolver port map the name "Trumpet" to Solo Cornet through the existing `"trumpet"` keyword (`mapping.json:1366`, vector `partsound-vectors.json:317`).
  - Windows without `mapping.json` needs a `("Trumpet", "cornet-b")` row in `BrassSoundSet.PartMap` (`BrassSoundSet.cs:17`), with a test.
  - MusicXML carries `<instrument-sound>brass.trumpet.bflat</instrument-sound>`, so MuseScore plays a trumpet.
- **`seat_part`** returns `{part: "Trumpet", exact: false, same_key: true, takes: "Solo Cornet"}`.
  - `takes` is new. It is the lineup part the seat's part replaced, and it is on the FFI `SeatPart` record and in the C ABI JSON, with the bindings regenerated.
  - The apps use it for the notice (§3.4), and to hide "Who plays the tune?": the tune is already on the player's part.
- **The quartet is left alone.** A trumpet seat maps to 1st Cornet like any other same-key seat, with the existing same-key notice. The apps' quartet logic is keyed on "1st Cornet" (`Seats.swift:210-228`, `MyInstrument.kt:112`, `Lineups.cs:62`), and the quartet is out of scope.

**Why swap, not insert a 19th "Trumpet" part in front of the band.**

- Swapping keeps the score's shape: 18 parts, the same banks, MIDI channels and layer routing, and the same "your part" plumbing.
- Inserting a part touches `test_band_midi.py:45` (17 pitched channels, already on a second MIDI port past 15), `BAND_LEADS` layer routing, the Solo Cornet's role, and every client's idea of the lead (`PracticeModel.swift:146`, `Lineup.kt:14`, `ScoreViewModel.cs:159`).
- It would also need a sound preset (§5 (d)) to be worth it.
- A soloist in front of a full cornet section is a follow-up, if the owner wants both instruments (§9).

### 3.4 UX: Android and Apple, en and nb

**"What do you play?"** A 12th tile, **Trumpet** / «Trompet», goes right after Cornet:

- its sub-line is "in B♭" / «i B», so it isn't confused with the cornet (user-flow review P3-3);
- there is one part, so no "Which part?";
- it is treble only, so no "You read".
- Android: `WhatDoYouPlayScreen.kt:56-68` `TILES`, with strings in `values` and `values-nb`.
- Apple: `Seats.swift:132-150`, the order plus `Localizable.xcstrings`.
- `tune` comes from the core. Android's `RustCoreBridge.kt:114` gets it from `fix/user-flow`.

**The notice when the trumpet takes the lead part.** A trumpet is never an exact band part, so it shows in the **full band** too. Android and Apple have only small-band and quartet forms, so there is one new pair per lineup. The part names are the core's (`part_name_nb`), and the seat word is lower case in running text.

| Key | English | Bokmål |
|---|---|---|
| takes, full | The full brass band has no trumpet part. You get the Solo Cornet part, written for trumpet. | Fullt brassband har ingen stemme for trompet. Du får stemmen til Solokornett, skrevet for trompet. |
| takes, small | The small band has no trumpet part. You get the Solo Cornet part, written for trumpet. | Det lille bandet har ingen stemme for trompet. Du får stemmen til Solokornett, skrevet for trompet. |
| takes, short (banner), full | The full brass band has no trumpet part — Solo Cornet, written for trumpet | Fullt brassband har ingen stemme for trompet — viser Solokornett, skrevet for trompet |
| takes, short, small | The small band has no trumpet part — Solo Cornet, written for trumpet | Det lille bandet har ingen stemme for trompet — viser Solokornett, skrevet for trompet |
| quartet | (existing `mapped_same_quartet`) This quartet has no trumpet. Your part here is 1st Cornet, the closest: the same key and clef. | Kvartetten har ingen trompet. Her er stemmen din 1. kornett, den nærmeste: samme stemming og nøkkel. |
| tile | Trumpet · in B♭ | Trompet · i B |
| part | Trumpet (you) | Trompet (deg) |

- **The templates** are `%1$s` = the seat word ("trumpet" / «trompet») and `%2$s` = the `takes` part's display name.
- **Wording.** «Fullt brassband» is the lineup label (`values-nb/strings.xml:226`). «ingen stemme for trompet» avoids a compound built from a template (review P2-3).
- **An older engine.** If the engine has seats but not `trumpet`, it answers 422. The apps map a 422 on a job with a seat, outside the quartet and `lead=seat` cases they already handle (`PlayViewModel.kt:675-676`, `CompanionService.swift:303`), to the existing "too old to write for your instrument" line (`engine_too_old_seat`).
- **Windows.** `main` has no "What do you play?". On `feat/my-instrument-windows` (`SeatCatalog.cs`), the trumpet tile already appears from the core's `seats()` with the core's `nbName`. That branch needs `bb-trumpet` in `TileOrder` and a `Seat_Tile_Trumpet` string, which is sent to its owner (§7). On `main`, Windows gets:
  - the `PartMap` row;
  - the nb talking-score rows (`MusicXmlTalkingScoreBuilder.cs:443-484`: "Trumpet" → «Trompet», "Trumpet" → «trompet»).

### 3.5 Names (one row per existing table)

| Table | Row |
|---|---|
| `talking_score.rs:810` `nb_part_name`, `engine/.../talking_score.py:440` `NB_PART_NAMES` | "Trumpet" → «Trompet» |
| `talking_score.rs:836` `instrument_nb`, `talking_score.py:452` | ("Trumpet", "trompet"), so "Trumpet in B♭" → «trompet i B» |
| `studio/src/lib/talkingxml.ts:37` `NB_PARTS` | Trumpet: «Trompet» |
| `studio/src/lib/validate.ts:11` `RANGES` | `Trumpet: R([52, 85], [52, 80])` |
| `studio/src/lib/validate.ts:35` `CROSSING_PAIRS` | `["Trumpet", "Repiano Cornet"]` |
| Windows `MusicXmlTalkingScoreBuilder.cs:443` | the two rows above |
| `qa/tools/musicxml_readability.py:46` | `("trumpet", (54, 57, 84, 87))`, written: pro 52–85 and the solo cornet's comfort top |

`studio/src/lib/navigator.ts:225` names the instrument by transposition, so a trumpet reads "Cornet in B♭", as a flugelhorn does today. That is fixed by (c), not here.

The engine title stays "… solo cornet & brass band (draft)" (`profiles.py:251`), which is also for (c).

---

## 4. Tests and acceptance for (a) and (b)

### 4.1 Conformance (Rust = Python)

- **New Mikkel variants** in `cases.py` `MIKKEL_VARIANTS`:
  - `layers-seat-trumpet` (`--seat trumpet`): the notes equal `mikkel/layers`, and the lead part is "Trumpet";
  - `layers-minimal-seat-trumpet`;
  - `layers-quartet-seat-trumpet`: the output equals `layers-quartet`, and your part is 1st Cornet.
- **Solo takes.** `SOLO_SEATS` gets `("tp", "trumpet")` on the ChoraleBricks trumpet stems.
- **The rest must not move.** `core/target/conformance` is diffed before and after each step:
  - After (a), only the faithful band and small-band layered cases change: `mikkel/layers`, `layers-key-bb`, `layers-transpose-down-3`, `layers-lang-nb`, `layers-seat-euphonium-bass-clef`, `layers-minimal-seat-2nd-baritone`, and any faithful solo take with no seat.
  - Every standard, easier, quartet and `lead-seat` case is byte-identical.
  - The commit message lists both sets.

### 4.2 Unit tests (Rust, with a Python twin for each)

- **`place_soloist`:**
  - a phrase inside the range is unchanged;
  - an outlier moves alone, with the "moved" warning;
  - a phrase mostly outside takes the fewest octaves.
- **`in_register`.** A line with less than 95 % inside gives today's output, byte for byte.
- **Soloist scope.** It is off for standard, easier, `satb`, `as_played` and `lead_moved`.
- **`Lineup::check` / `validate_part`.** 83–84 on the Solo Cornet lead are "uncomfortable", not "impossible". On Repiano, and on a `lead=seat` Solo Cornet, they are "impossible", as today.
- **Seats:**
  - `seat_part("band", "trumpet")` and `seat_part("minimal", "trumpet")` return `Trumpet` with takes Solo Cornet;
  - `seat_part("quartet", "trumpet")` returns 1st Cornet, same key;
  - `seat_lineup("trumpet")`;
  - `Seat::own_part` for all 19 seats;
  - the SEATS count 18 → 19 (`test_seats.py:44`);
  - `lead=seat` with trumpet is a no-op.
- **Names.** `nb_part_name("Trumpet")` is «Trompet» and `instrument_nb("Trumpet in B♭")` is «trompet i B» (core and engine).
- **Studio.** `validate.ts` passes the golden's lead at 84 and flags 85 on Solo Cornet; `talkingxml` says «Trompet».
- **Apps.**
  - Android and Apple: the tile and its nb label, the takes notice for full and small band, and the 422 mapping.
  - Windows: `PartMap` resolves "Trumpet" to `cornet-b`.
  - The FFI `SeatPart.takes` round-trips in each bridge's tests.

### 4.3 Acceptance criteria

1. **Mikkel faithful, full band.** Solo Cornet writes all 694 solo notes as played, and its top is 84. The inner-part counts are as in §2.6, and there are no "impossible" notes on any part.
2. **Mikkel standard, easier and quartet** are byte-identical to before, in both arrangers. So is every `lead=seat` case.
3. **Nothing else turns red.** `main` and other branches stay green: the old golden is untouched until the promotion commit.
4. **Seat trumpet** (band take):
   - the lead part is "Trumpet" / «Trompet», with `<instrument-name>Trumpet in B♭</instrument-name>` and `<midi-bank>1</midi-bank>`;
   - the notes equal the default score;
   - it plays the Solo Cornet sound on every platform;
   - the full-band notice shows in en and nb.
5. **A trumpet solo take** is one "Trumpet" part in the octave played, with the 52–85 window.
6. **Picking Trumpet.** "What do you play?" on Android and Apple offers Trumpet, en and nb, and "Who plays the tune?" isn't offered for it. Windows gets the same when `feat/my-instrument-windows` lands.
7. **The checks pass.** `make check` is green for every touched area, conformance included.
   - Apple UI tests run only through `scripts/mac-vm.sh` when on `main`, never on the host.
   - The phone is checked for the tile and notice through `emulator-pool.sh acquire --phone`. The current debug build is reinstalled afterwards, and nothing is uninstalled.

---

## 5. Follow-ups, plan only (not built now)

### 5.1 (c) Instrument facts from the core on every platform

§1.5 lists about 30 copies. The design:

- **One place for the facts.** Add `name_nb`, `label`/`label_nb` (the picker names), `key_label`/`key_label_nb`, `section` → `section_seat`, and `Part.name_nb` to `instruments.rs`/`.py`. A conformance case, `brasscribe-core instruments --json` against the Python dump, keeps the two tables identical.
- **Export.** Over UniFFI and the C ABI:
  - extend `instruments()` and `seats()`;
  - add `lineup_parts(LineupOptions) -> [PartInfo]`, with the effective range check per part;
  - add `bc_instruments` and `bc_lineup_parts`.
- **Engine.** `GET /v1/instruments`, and the `Seat` enum built from `SEAT_IDS`.
- **Clients.**
  - Studio: `validate.ts`, `talkingxml.ts`, `navigator.ts` and `run.ts`.
  - Apple: `Section`, `Seats.swift`.
  - Android: `TILES`, `Pitch.kt`, `ReviewScreen`.
  - Windows: nb tables, `SeatCatalog`.
  - Each reads these instead of its own table.
- **Kept on purpose.** `BrassSoundSet.PartMap` stays as the Windows fallback when a build ships without `mapping.json` (dev builds, sideloaded packs; review P2-4), unless every build is shown to ship it.
- **Proof.** A test instrument fixture must flow through every client's unit tests with no platform code touched.
- **Dependencies.** It depends on `feat/my-instrument-windows` and on Apple UI tests through the VM, and it gets its own plan and review round.

### 5.2 (d) A trumpet sound

- **Target.** A `mapping.json` target `trumpet`:
  - Iowa MIS trumpet sustain, which covers 52–87 chromatically;
  - VSCO 2 CE staccato;
  - `eq: []`, range [52, 85].
- **Part and resolver.** A band SoundFont preset for "Trumpet" at bank 7. The resolver keyword "trumpet", plus a new "trompet", and `brass.trumpet(.bflat)`, move to it. That changes playback for foreign scores with trumpet parts, which is why it belongs here and not in (b).
- **Vectors.** The four ports' vector suites are regenerated. `PartSoundTests.cs:80` renames "3rd Cornet" to a non-trumpet name.
- **Build and publish.**
  - Rebuild with `band.py --bits 16` and `mobile_soundfont.py`.
  - Check the mobile file against alphaTab's heap on the phone (it is 77 MB today, at the edge: `apps/android/README.md:87`).
  - Pin `band_sounds.py pin`.
  - The pre-release (`gh release create sounds-… --prerelease`) creates a tag, so **the owner publishes it**. The pin commit follows.
- **When.** It waits for owner questions 3 and 4 (§9).

---

## 6. Build order

Each step is a group of conventional commits with their tests, and is pushed once per group (review P2-5: `ci.yml` runs on every push). Each step is reviewed before the next.

**Step 1 (a).**
- `feat(core): write a faithful soloist's lead in the octave played`: Rust and Python, `solo`, `lead_moved`, `place_soloist`, `Lineup::check`, `validate_part`, the Studio `validate.ts` row, unit tests, and the conformance diff.
- `chore: save the soloist golden next to the current one`: `.soloist`, the repointed consumers, readability, baselines, the benchmark doc and the Windows count.

**Step 2 (b), core.**
- `feat(core): Trumpet in B♭ and a trumpet seat that takes the lead part`: data, `own_part`, `with_seat`, `SeatPart.takes`, names, the CLI, conformance cases, and FFI/C ABI with the bindings regenerated.
- `feat(engine): trumpet seat`: the Literal and `talking_score.py` rows, with OpenAPI regenerated for every client.
- `feat(studio): trumpet names and range`

**Step 3 (b), apps.**
- `feat(android): trumpet in What do you play`
- `feat(apple): trumpet in What do you play`
- `feat(windows): play and name a Trumpet part`

All of it is merged to `main` (v0.2.0 shipped it).

---

## 7. Coordination

- **`fix/user-flow`** touches `instruments.rs`/`.py`. Its changes:
  - `with_reading` takes the seat;
  - `seat_lineup` refuses percussion;
  - `seat_part.same_key` uses the reading;
  - `composition_lineup` gets a new "empty" part source;
  - `RustCoreBridge.kt` passes `tune`, and `Seats.swift` changes too.

  It leaves the `SEATS` and `SEAT_PARTS` rows alone. Step 2 goes on top of its commits: the trumpet work rebased on them once they were pushed. `with_seat` goes next to its `with_reading`. For a trumpet `same_key` stays true, because both are treble in B♭.
- **`feat/my-instrument-windows`** gets the two-line `TileOrder`/string change for the trumpet tile.
- **Goldens.** §2.6. Nothing in `data/golden/mikkel-arranged-band` changes before the promotion commit.

---

## 8. The review's points

| Point | Answer |
|---|---|
| Review §1.1: 116 reproduces; 13 needs a wider reading range; the 22 intro moves come from the tie-break | Agreed and reproduced independently (§1.3). The short answer now says it: 22 down and 5 up, from the reading-range count and the centre tie-break. |
| Review §1.2: a range change leaks into standard/easier | The soloist range is its own field, used only in faithful soloist placement (§2.2, §2.4). §4.1 holds standard and easier byte-identical. |
| Review §1.3: 84 on a cornet reverts `743c04d`; `check`/`validate.ts` flag it; qa row against MuseScore | Section cornets keep 82. The lead is checked against `solo` through `Lineup::check`, and Studio's row changes in the same commit (§2.3). MuseScore wins for the section, the qa row for the soloist (§2.1). |
| Review §1.4: trumpet 52–80/52–85, `brass.trumpet.bflat`, 30 uncomfortable | Used as is (§3.1). The soft limit stays. The trumpet lead's notes above 80 (34 of the 694 source notes; the review counts 30 after placement) are truly above the amateur top, and none of them is impossible (§2.3). |
| Review §1.5: missing copies | Merged into §1.5. (b) adds one row per existing table (§3.5). The refactor is (c). |
| Review §1.6: pack cost, mobile heap, Literal 422 | (d) is deferred (§5.2). The 422 maps to the existing "too old" line (§3.4). |
| P1-1: the golden re-save breaks everyone | A new directory, the consumers repointed in the same commit, and a promotion commit at merge (§2.6). |
| P1-2: over-scoped | Agreed: (c) and (d) are follow-ups (§5). |
| P1-3: (a) needs its validators | They go in the same commit as the placement: `Lineup::check`, `validate_part`, Studio's row. The engine's validation reports only warnings (§2.3). |
| P2-1: as-played on more than one piece, and tracker octave errors | Measured on 93 ChoraleBricks stems, played and tracked. The rule moves note by note inside a phrase, which is why tracked trumpet goes from 25.7 % to 0 % (§2.5). The behaviour change for low takes is stated. |
| P2-2: 19th part against swapping | Swap in place, with the reasons in §3.3. |
| P2-3: nb copy | «Fullt brassband …», «ingen stemme for trompet» (no template compound), «Deg: Trompet» is not shown (the tune is already on the part), and "A trumpet soloist" is dropped along with the soloist option (§3.4). |
| P2-4: `PartMap` | Kept, and gets a Trumpet row (§3.3, §5.1). |
| Step 1 review, P1-4: a phrase past the solo range lost its peak note by note | Fixed: only a lone outlier moves alone, otherwise the whole phrase shifts (§2.2). The review's `test_soloist_edges.py` is taken in with Rust twins, and so is the ported `test_range_invariants.py`. |
| Step 1 review, P3-4: the fast conformance tier reuses stale Python references | Fixed in `scripts/check.sh`: the references are reused only while a hash of the Python sources matches. |
| Step 2 review, P2-6: when no whole shift fits, the soloist falls back to the section cornet's placement (Mikkel +1 semitone moved 193 notes) | Fixed: the phrase is split at its leaps inside the solo range, and a lone outlier moves only when that makes its phrase fit. Mikkel +1 now moves 29 notes and +2 moves 97 (main: 276 and 476), each by one octave. |
| Step 2 review, P2-7: Studio announces a Trumpet part as "Cornet in B♭" | Fixed: a part named for a trumpet is "Trumpet in B♭" / «trompet i B». |
| Step 3 review, P2-8: an older engine answers seat "trumpet" with a 422 | Android and Apple send the job once more as solo-cornet (the same notes). Android says the computer is too old for the instrument. Apple opens Solo Cornet with its part notice. Windows sends no seats on main. |
| Step 3 review, P3-5: the Trumpet part keeps the Solo Cornet's 4 players | Kept on purpose: it plays the layered Solo Cornet desk sound until the (d) follow-up gives it its own preset. |
| Step 3 review: an older app opening a score with a "Trumpet" part | Apple's `Section.init` matches names, so it puts the part in `.other` (centre pan) with no band sound seat. The band sound resolver still maps "Trumpet" to the Solo Cornet. The (c) follow-up removes the name matching. |
| The golden | Promoted at the owner's go: `.soloist` is now `data/golden/mikkel-arranged-band`, and the old one is kept in `data/golden-backups/before-soloist/`. |
| P2-5: CI per push | One push per step group (§6). |
| P3: `mikkel.md:14`; the resolver keyword goes with (d); §6.4 goes with (c) | The soloist is recorded as unresolved (§1). The keyword stays until (d), and the data-only test is in (c). |
| Review: soprano doubling via `tune_on_top` would turn on for a flugelhorn `lead=seat` | Not changed to `tune_on_top`. `BAND_LEADS` (`arranger.rs:617`) gains "Trumpet". A Trumpet part only ever exists as the lead it took, so the Soprano doubles it in standard and easier exactly as it doubles the Solo Cornet. Flugelhorn `lead=seat` is unchanged. |

---

## 9. Questions for the owner

Questions 1 and 2 were answered with defaults on 2026-09-29. The owner can change both.

1. **The cornet soloist's top.** **Default: 84** (written D6, the qa "solo cornet" row). It covers Mikkel's top note and stays one step under MuseScore's trumpet top. A trumpet seat gets 85, MuseScore's professional trumpet top.
2. **The low solo takes.** **Default: keep them in the octave played.** With no seat set, horn and upper baritone takes are written on the Solo Cornet in the octave played (§2.5). A note outside the solo range is moved, and it carries a range warning. A test pins this: `test_a_low_take_in_the_cornets_range_is_written_as_played`.
3. **A soloist in front of the band.** Should a separate "Trumpet" part stand above a full cornet section (the insert model, §3.3), for a conductor with a guest trumpeter? That comes with (d).
4. **(d).** Should the sound pack be rebuilt and republished with a raw trumpet preset? If the mobile pack goes over the heap, is the fallback the cornet sound?
