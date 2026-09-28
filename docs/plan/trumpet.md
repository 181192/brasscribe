# Trumpet: a soloist's range, a trumpet lead, and instrument facts from one place

The owner wants to be able to add a trumpet. This plan checks what an earlier analysis claimed, then designs five things:

- (a) a soloist range for the lead
- (b) "Trumpet in B♭" as a lead and a seat
- (c) instrument facts read from the core on every platform
- (d) a trumpet sound
- (e) tests and acceptance criteria

It is a plan only. No production code has changed.

Line numbers refer to `157d9df` (`main`). The measurement scripts are in [`trumpet/`](trumpet/):

- `sweep.sh` runs the Rust path over a set of ranges
- `lead_octaves.py` counts the lead notes that change octave
- `part_diff.py` diffs the parts
- `musescore_ranges.py` reads the ranges from the MuseScore app bundle

---

## Short answer

- **Mikkel's soloist plays trumpet.** "Mikkel" is Ole Edvard Antonsen's (*Landscapes*, 2007), and he is a trumpet soloist. The arrangement calls the part "Solo Cornet" only because the band's lead is called that.
- **The real loss is range, and a trumpet alone does not fix it.**
  - Today 116 of the 694 solo notes are written in another octave. This happens on both the Python and Rust paths.
  - Of those, 89 move because five phrases reach 83–84, above the cornet's playable 82.
  - The other 27 would move even with no limit at all. The placement pulls every phrase toward the middle of the *reading* range, 55–79.
- **Mode.** In faithful mode, the lead writes a phrase in the octave it was played in whenever it fits a **soloist range**. The soloist range is 52–84 on a B♭ cornet and 52–85 (MuseScore's pro range) on a B♭ trumpet. With this rule, 0 of 694 Mikkel notes move.
  - Standard and easier keep today's placement exactly. So do the quartet, "tune on your part" (`lead=seat`) for a band part, and any recording that is not in the soloist's register.
- **Trumpet** is a new instrument, `bb-trumpet`. It is used two ways:
  - as a **soloist part in front of the band** (option `soloist=bb-trumpet`, or a trumpet player choosing "You: Trumpet"), with the band's Solo Cornet then playing a band part;
  - as a **seat** ("What do you play? → Trumpet"). A solo take is written for Trumpet in B♭. In the lineups without a trumpet part, the player's part is Solo Cornet or 1st Cornet, in the same key.
  - The band lineups keep their cornets. There is no trumpet section seat and no C trumpet.
- **Instrument facts get one home.** Today about 30 copies are matched by name, id or transposition across Rust, Python, TypeScript, Swift, Kotlin and C# (§1.6).
  - Every platform will read names (en/nb), picker labels, section, ranges, sound and the seat's `tune` from the core, over FFI, the C ABI and a new `GET /v1/instruments`.
  - After that, the next instrument needs only data: the core tables, `mapping.json` and `seating.json`.
- **The trumpet sound** is Iowa MIS trumpet sustain plus VSCO 2 CE staccato, with **no cornet EQ**. That is a new band SoundFont preset, so the sound pack has to be republished. The owner publishes the pre-release, because it creates a tag (§5.4).

---

## 1. The earlier findings, checked

| Finding | Verdict | Evidence |
|---|---|---|
| Instruments are plain data in `instruments.rs` / `instruments.py` | **True** | `instruments.rs:46-67` and `:128-176`, `instruments.py:35-58` and `:88-110`. A field list, 11 statics, and lineups built from them. |
| B♭ cornet and B♭ trumpet notate the same: −2, treble, GM 56 | **True** | MuseScore 4.7.5 `bb-trumpet`: `transposeChromatic -2`, diatonic −1, program 56 (§1.2). They differ in range and sound id: `brass.trumpet.bflat` versus `brass.cornet`. |
| cornet-a/b are trumpet samples with a cornet EQ | **True** | `sounds/mapping.json:35` and `:82`. cornet-a is Iowa MIS trumpet and cornet-b is VSCO 2 CE trumpet, each with RBJ biquads (low shelf +2 at 350 Hz, a cut around 1.6–2.6 kHz, high shelf −5 at 3.2 kHz, a low-pass). The EQ is baked in by `sounds/build.py:250-299`. |
| Solo layer is MIDI 53–84, lead limit 82, 116 of 694 (17 %) drop an octave | **True, on both paths** | §1.3. The Rust CLI gives 116 (111 down, 5 up), the same as the Python golden. The Rust MusicXML differs from the golden only in writer formatting, and `composition.json` is byte-identical. |
| With a lead range up to 89 only 13 move, top 84 | **Only if the reading range is widened too** | §1.3. With only the limit raised to 84–89, 27 notes move. 13 needs reading = limit = (52,89), and then all 13 move *up*. |
| The listed name-matched copies | **True, and the list is incomplete** | §1.6 lists about 30. |
| Unchecked: MuseScore trumpet and cornet ranges | **Checked** | §1.2 |
| Unchecked: Rust path | **Checked** | §1.3 |
| Unchecked: why 13 still move | **Explained** | §1.3: the centre tie-break in `best_shift`, not range |
| Unchecked: cornet or trumpet soloist | **Trumpet** | The repo's own notes also say "trumpet lead + orchestra". The composition's solo voice has `instrument_hint: "trumpet/cornet"`. |

### 1.2 MuseScore ranges

MuseScore 4.7.5 (`/Applications/MuseScore 4.app`) compiles `instruments.xml` into the binary. The templates under `Contents/Resources/templates` carry full `<Instrument>` blocks, which `trumpet/musescore_ranges.py` reads. The critic cross-checked them against `share/instruments/instruments.xml` at tag v4.7.5 and they agree.

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
| (55,79) / (52,85) | phrase kept as played when it fits the limit | **0** | 84 | the rule proposed in §2 |
| (55,79) / (52,82) | same rule | 97 | 82 | the rule alone, without the range |

The two "as played" rows used a one-line prototype hook at the top of `best_shift`. When `ASHEARD` is set, the hook returns shift 0 for a tune phrase whose notes all lie inside the limit:

```rust
if !prefer_low && std::env::var("ASHEARD").is_ok() && pitches.iter().all(|&p| limit.0 <= p && p <= limit.1) { return Some(0); }
```

It was reverted after the measurement. Run it with `ASHEARD=1 docs/plan/trumpet/sweep.sh 55,79,52,85`.

**Why notes move with room to spare.** `best_shift` (`arranger.rs:99-128`, `arranger.py:58`) scores each octave shift in two steps:

1. The number of notes inside the **reading** range `preferred()`, not inside the limit.
2. On a tie, the distance of the phrase's mean from the middle of that range (67 for 55–79), plus the jump from the previous phrase.

So:

- The intro phrases (ticks 0–3444, 69–84) drop an octave, because more of their notes land in 55–79 an octave down, or, when they fit either way, because the lower octave is nearer 67.
- The closing phrases (ticks 8766–9384, 57–69) rise an octave toward the middle. They do this once the reading range is widened to (52,89), whose middle is 70.5.
- Widening the range only moves the middle: the moves change direction, and they don't go away. This is how the earlier analysis arrived at 13.

The rule "keep the phrase's octave when every note fits" removes the tie-break for the soloist (§2.1).

`part_diff.py` shows what that rule does to the rest of the band, at limit (52,85):

| Part | Notes (today → rule) | Changed | Top |
|---|---|---|---|
| Solo Cornet | 694 → 694 | 116 back to the played octave | 82 → 84 |
| Repiano Cornet | 204 → 211 | 23 | 72 → 67 |
| 2nd Cornet, 3rd Cornet | 204 → 211 | 9 each | 65 |
| Flugelhorn | 237 → 249 | 44 | 69 → 77 |
| Solo Horn | 254 → 256 | 30 | 60 → 65 |
| 1st Horn, 2nd Horn | 254 → 256 | 10, 2 | 59 |
| 1st and 2nd Baritone, 1st and 2nd Trombone | same | 6, 2, 6, 2 (re-voiced) | same |
| Soprano, Euphonium, Bass Trombone, basses, percussion | unchanged | 0 | |

These are the inner notes the cornet-limit fix turned into rests (`14730d0`), coming back now that the tune sits where it was played.

### 1.4 Side effects if the range were simply widened

The critic measured these (`docs/research/15-trumpet-critique.md` §1.2 on `review/trumpet-critic`), and they agree with the code. Placement runs before `apply_difficulty` (`arranger.rs:794`, then `difficulty.rs:163`). So widening the cornet's `reading_limit` would change the standard and easier leads as well.

Standard and easier then fold the high phrases back note by note (`difficulty.rs:144` `fold`). That raises the octave switches inside phrases from 43 to 47 (standard) and from 68 to 72 (easier). That per-note flipping is exactly what `743c04d` removed from placement.

Widening `reading` would raise standard's lead to 82–84 and easier's to 80. This plan does neither. The soloist range is a separate field, used only by the faithful soloist placement and the lead's range check (§2).

### 1.5 The soloist

Ole Edvard Antonsen is a trumpet soloist, and "Mikkel" is a trumpet feature with orchestra. The brass-band arrangement of it is still a "solo cornet & brass band" piece, because that is the band's convention. Both are right:

- the default output keeps the Solo Cornet as the lead, with its soloist range;
- the trumpet is an option (§3).

### 1.6 Every hardcoded copy of instrument facts

This merges the earlier list, the critic's §1.5 and a full audit. "Today with a trumpet" is what a part or seat for Trumpet in B♭ gets now.

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
| `core/.../arranger.rs:617` `BAND_LEADS`, `:632-633` `PAD_PARTS` and `CHOIR_PARTS`, `:262-282` layer routing; `arranger.py:560-593` | the arranger's roles for the band's own parts | name | fine: the soloist is always `lineup.lead` (§3.3) |
| `instruments.rs:562` `TOP_INSTRUMENTS` | tune-on-top instruments | id | a trumpet lead voices the inner parts wrongly unless it is added |

The arranger's role lists are arranging policy for the band's own parts, not instrument facts. They stay as they are. A test checks that every part of every lineup variant gets a layer (§6).

---

## 2. (a) The soloist range for the lead

### 2.1 The rule

**A new field.** `Instrument.solo: Option<(i32, i32)>` (Python `solo: tuple | None`) holds the sounding range a soloist on this instrument plays. It defaults to `pro`. `Instrument::solo_range()` returns it.

**Soloist placement.** It applies when all of these hold:

1. The arrangement is layered (`arrange_layers_opts`, `arrange_layers`).
2. The difficulty is **faithful**.
3. The lineup is a band lineup (`band`, `minimal`). The quartet is not: its 1st Cornet is a chamber part, and `lead=seat` is refused there for the same reason.
4. The lead is the lineup's own lead, or the trumpet soloist part (§3.3). A band part that took the tune with `lead=seat` (Euphonium, Flugelhorn, Solo Horn) keeps today's placement. There the tune is being *arranged* onto another instrument, and the conformance cases for it stay identical.
5. **The recording is in the soloist's register.** At least 95 % of the solo layer's notes lie inside `solo_range()`. The constant is `SOLOIST_SHARE` = 0.95.
   - A take that is mostly outside (a euphonium player on the phone with no seat set) keeps today's placement. So its phrases never split between "as played" and "moved".
   - Mikkel has 100 % inside.

**Per phrase.** The same phrases as today (`phrases()`):

- Every note inside `solo_range()`: the phrase is written as played (shift 0).
- Otherwise: the octave shift with the fewest octaves that puts every note inside `solo_range()`. On a tie, the one nearest the previous note. Then today's split at the largest leap (`place_phrase`, keeping the previous piece's shift). As a last resort, per-note fitting. The range for all of these is `solo_range()` on both sides, not the reading range.

**Everything else is unchanged.** Standard and easier place by the reading range with `placement_limit()` (82 on a cornet), as today, and then fold. The cornet-limit fix (`743c04d`) stays whole for them, for every section cornet part, and for every lead that isn't a soloist.

**The solo take.** `place_as_played` (`arranger.rs:233`) uses `solo_range()` instead of `pro` for its hard range. Only the B♭ cornet sets `solo`. So only cornet-seat solo takes change, and only for notes at 83–84. No conformance case has one (`SOLO_SEATS` is baritone, trombone, tuba and horn).

### 2.2 Which range, per difficulty

| Lead instrument | faithful (soloist) | standard | easier |
|---|---|---|---|
| B♭ cornet (Solo Cornet, 1st Cornet) | `solo` **(52,84)**: the qa "solo cornet" row, written D6 | reading (55,79), limit (52,82) | easy (55,75), limit (52,82) |
| B♭ trumpet (§3) | `solo` = `pro` **(52,85)** (MuseScore P) | reading (55,79), limit (52,82): the same notes as a cornet lead | easy (55,75) |
| any lead in the quartet, or a band part that took the tune with `lead=seat` | as today | as today | as today |

**MuseScore or the qa row?** MuseScore's pro range wins for the section parts: the cornet's `pro` stays 82, and every Repiano, 2nd and 3rd Cornet note stays at or below 82.

The qa tool's "solo cornet" row is the only source in the repo for a *soloist's* cornet top. It says written D6, which is sounding 84. It becomes the cornet's `solo`. MuseScore has no soloist field, so this is a judgement call, and the owner decides it (§9, question 1). With 85 instead, Mikkel's output would be identical, because its top note is 84.

### 2.3 The lead's range check

`Instrument::check` stays as it is for every part. A new `Lineup::check(part, pitch)` checks the lead differently:

- **Impossible** outside `solo_range()`
- **Uncomfortable** outside `pro`
- **Ok** otherwise

A soloist is judged against a professional's range, not an amateur's. On Mikkel's faithful output this gives:

- **Solo Cornet:** 14 notes (nine on 83, five on 84) are uncomfortable, above the cornet's 82, and none are impossible. They are the notes a cornet soloist has to reach for, so the warning is true.
- **Trumpet:** no warnings. The critic's 30 "uncomfortable" (above the amateur 80) go away, because the amateur range isn't the soloist's yardstick.

`validate_range` (`instruments.rs:382`) and every validator read the effective ranges through the part facts in §4 (`PartInfo.hard` / `soft`), so Studio and the engine's validation endpoint agree.

### 2.4 How it interacts with the "reads well" per-phrase fitting

`743c04d` made phrase splitting keep the contour. A phrase no octave fits is split at its largest leap, and each piece keeps the previous piece's octave where it fits.

- The soloist placement uses that same recursion, with `solo_range()` as its window.
- With Mikkel inside the range, no phrase needs it. The 5 "split at its leaps" warnings of today's faithful output go, and so do the 7 octave switches inside phrases (critic §1.2).
- Standard and easier keep the split-and-fold behaviour exactly as it is. Their outputs are byte-identical before and after (§6.3).

### 2.5 Golden update

**Re-save.** `data/golden/mikkel-arranged-band` is re-saved deliberately, with the same recipe as `14730d0`: orchestra-with-soloist, `--reuse data/mikkel/repro`, no heavy models.

**Backup.** The old copy goes to `data/golden/mikkel-arranged-band.before-soloist-range`, with its manifest. `data/` is not in git, so the backup is the record, and the commit message lists the diff.

**Expected diff.** Checked with `part_diff.py` against the backup. The implementation has to reproduce these numbers; if it doesn't, it isn't finished.

- `composition.json` is byte-identical.
- Solo Cornet:
  - 116 notes return to the played octave, and the top is 84 (written D6);
  - no split warnings;
  - 14 notes are "uncomfortable" and none are "impossible".
- The inner parts get back the notes the cornet-limit fix turned into rests, as in §1.3: Repiano, 2nd and 3rd +7 each, Flugelhorn +12, the Horns +2. The baritones and trombones re-voice.
- Soprano, Euphonium, Bass Trombone, the basses and percussion are unchanged.
- The talking score, BRF, MIDI, MP3 and PDFs follow the MusicXML.

**What follows the golden:**

- `qa/reports/mikkel-golden-readability.json` is regenerated.
- `eval/baselines.json` and `docs/research/10-benchmark-results.md` get the Mikkel faithful rows re-measured with `difficulty_bench --mikkel`. The standard, easier and quartet rows must not change, which also proves §2.1.
- `apps/windows/tests/.../NativeCoreBridgeTests.cs:20` `GoldenNotes` is re-counted, as in `dff1c75`.
- Every other golden test that counts or hashes notes is found with `grep` over the apps' tests for the golden path and re-counted in the same commit.

**Conformance** after the step: every case is identical between Rust and Python, with all golden files matching. The `mikkel/layers`, `layers-lang-nb`, `layers-seat-euphonium-bass-clef` and `layers-key-bb`/`transpose` cases change their *reference* output, and all of them are faithful. Every standard, easier, quartet and `lead-seat` case keeps its previous output. That is checked by diffing `core/target/conformance` before and after.

---

## 3. (b) "Trumpet in B♭": a soloist and a seat

### 3.1 The instrument

```text
TRUMPET  id "bb-trumpet", name "Trumpet in B♭", short "Tpt.", chromatic −2, diatonic −1, treble
         pro (52,85), comfortable (52,80)            MuseScore 4.7.5 bb-trumpet
         reading (55,79), reading_limit (52,82)      = the cornet's: standard/easier write the same notes
         solo None (= pro)
         roles Melody, Solo, Countermelody, UpperHarmony
         gm_program 56, musescore_id "bb-trumpet", sound "brass.trumpet.bflat"
         section "cornets"                           sits and pans with the cornets
         name_nb "Trompet i B", label "Trumpet", label_nb "Trompet"   (fields from §4.1)
```

- `TOP_INSTRUMENTS` gains `bb-trumpet`, so the inner parts are voiced under a trumpet lead.
- `INSTRUMENTS` gets 12 entries. The trumpet goes after the cornet, and that is the picker order (§4).

### 3.2 One part name: "Trumpet"

The soloist part and the seat's own part are one part:

```text
ps("Trumpet", &TRUMPET, 1, "Tpt.", Some(7))     nb «Trompet»
```

- Bank 7 (1-based) is the first free bank on program 56. Solo Cornet is 1 and Flugelhorn is 6.
- One name keeps every table to one new row.
- "Trumpet" is unambiguous above a brass band, which has no trumpets.

The part is listed in `SOLOIST_PARTS` (new, in `instruments.rs` and `instruments.py`), not in a lineup. `part_banks()` walks it too.

### 3.3 The soloist in front of the band

**The option.** `soloist: Option<instrument id>`, with the values in `SOLOISTS = ["bb-trumpet"]`. It is recorded in `composition.arrangement["soloist"]` like the other options, so re-arranging on a device reproduces it. `composition_lineup` (`arranger.rs:922`) applies it after the seat.

**What it does.** `soloist_lineup(lineup, "bb-trumpet")`:

- **inserts** the `Trumpet` part at the top of the score (a soloist's staff goes above the band);
- makes it `lineup.lead`.

The band stays cornet-only, and the Solo Cornet stays in the score. It is then the band's lead without the tune, which is exactly the `lead=seat` case the arranger already handles:

- `layer_of` routes a `BAND_LEADS` part to the strings layer (`arranger.rs:266`);
- the conformance case `layers-lead-seat-flugelhorn` covers it today.

The full band has 19 parts and the small band 9.

**Soprano doubling.** In standard and easier, the soprano doubles the tune only when `BAND_LEADS.contains(&lead)` (`arranger.rs:891`). That check becomes `tune_on_top(lineup)`, so the Soprano doubles a trumpet soloist at climaxes the way it doubles the Solo Cornet. Faithful never doubles, so the golden is unaffected.

**Refused:**

- the quartet: "the quartet keeps the tune on its 1st Cornet", the same message as `lead=seat`;
- a `soloist` together with `lead=seat` on another seat: "choose one: the tune on your part or on a soloist".

**Title.** `profiles.py:251` takes the lead from the core:

- "{name} — solo trumpet & brass band (draft)";
- "solo cornet" without a soloist, as now.

The title comes from the lead instrument's `label`, lower-cased.

### 3.4 The trumpet seat

```text
Seat { id: "trumpet", part: "Trumpet", reads: ["treble"] }          tune: true
SEAT_PARTS "trumpet": [Some("Solo Cornet"), Some("Solo Cornet"), Some("1st Cornet")]
```

- **`seat_part`.** When the lineup has a `Trumpet` part (there is a soloist), `seat_part` returns it, with `exact: true`. Otherwise it returns the table's part, with `exact: false` and `same_key: true`.
- **`Seat::band_part`** (`instruments.rs:412`) becomes `Seat::own_part`. It looks the part up in `brass_band()` and then in `SOLOIST_PARTS`, so a seat is no longer assumed to be a band part.
- **`lead=seat` with seat `trumpet`** is the soloist: `soloist = bb-trumpet` is implied. So a trumpet player gets "Trumpet solo with band" through the existing "Who plays the tune?" question.
- **A solo take** (`seat_lineup("trumpet")`) is one `Trumpet` part, as played, with the hard range (52,85). A trumpet solo take is written for Trumpet in B♭, and the window already follows the seat's instrument (`pipeline.rs:366-370`, which moves from `band_part()` to `own_part()`).
- **A band take without a soloist** gives the player Solo Cornet (1st Cornet in the quartet). The notes are the same: the same key and clef.

### 3.5 UX (Android, Apple, Windows; en and nb)

**"What do you play?"**

- A 12th tile, **Trumpet** / «Trompet», after Cornet.
- Its key sub-line is "in B♭" / «i B». It comes from the core (§4.1), so it can't be confused with the cornet (user-flow review P3-3).
- One part, so no "Which part?". Treble only, so no "You read".

**The mapped-part notice**, when the lineup has no trumpet part:

- A trumpet is never an exact band part, so the notice now shows in the **full band** too.
- Android and Apple have only a small-band wording of the same-key notice, so they need a full-band one. The Windows branch already has it.
- The notice is one definite form per lineup, from the copy deck in `my-instrument.md` §3.8:

| Lineup | English | Bokmål |
|---|---|---|
| Full band | The full band has no trumpet. Your part here is Solo Cornet, the closest: the same key and clef. | Det fulle bandet har ingen trompet. Her er stemmen din Solokornett, den nærmeste: samme stemming og nøkkel. |
| Small band | The small band has no trumpet. Your part here is Solo Cornet, the closest: the same key and clef. | Det lille bandet har ingen trompet. Her er stemmen din Solokornett, den nærmeste: samme stemming og nøkkel. |
| Quartet | The quartet has no trumpet. Your part here is 1st Cornet, the closest: the same key and clef. | Kvartetten har ingen trompet. Her er stemmen din 1. kornett, den nærmeste: samme stemming og nøkkel. |

- The seat name inside the notice comes from the core's `label` / `label_nb`, lower-case in running text. The templates are keyed by lineup, not by seat, so the next instrument needs no copy.

**"Who plays the tune?"** It is shown for soloist recordings in a band lineup:

| Player | Choices (en) | Choices (nb) |
|---|---|---|
| a trumpet player | Solo Cornet (as usual) · **You: Trumpet** | Solokornett (som vanlig) · **Deg: trompet** |
| any other seat whose `tune` is true | Solo Cornet (as usual) · A trumpet soloist · You: {part} | Solokornett (som vanlig) · En trompetsolist · Deg: {part} |
| no seat | Solo Cornet (as usual) · A trumpet soloist | Solokornett (som vanlig) · En trompetsolist |

- The "A trumpet soloist" row comes from the core's `SOLOISTS`, labelled "A {label} soloist" / «En {label_nb}solist». That fits Norwegian compounding: «trompetsolist».
- "You: …" appears only when the core's `tune` is true (the Android fix on `fix/user-flow`).

**Score chips and the part picker** read "Trumpet (you)" / «Trompet (deg)». "Written for" reads "Written for Trumpet in B♭, treble clef" / «Skrevet for trompet i B, G-nøkkel».

**Older engines.** An older engine rejects seat `trumpet` or `soloist` with a 422 (`schemas.py:13`). The apps read the engine's `GET /v1/instruments` (§4.3):

- If the engine lacks it, or it has no trumpet, the apps don't send the new values.
- Instead they show the existing "old computer" line (`my-instrument.md` §3.8): "Brasscribe on your computer is too old to write for your instrument. Update it to use this."
- On-device arranging (the phone's core) always has the trumpet.

**Screens.** The mockups (`design/mockups/my-instrument-*.html`) get the 12th tile and the full-band notice before the apps change. The site's screenshots follow on the next capture, and the site copy stays as it is.

---

## 4. (c) Instrument facts from the core, on every platform

### 4.1 The data

These fields are added to both `instruments.rs` and `instruments.py`. The two stay identical, and a conformance case checks that (§6.1).

| Where | New field | Replaces |
|---|---|---|
| `Instrument` | `name_nb` ("Kornett i B", "Trompet i B", "Ess-bass") | `instrument_nb` replaces (Rust, Python engine, Windows); Android `Pitch.kt` names |
| `Instrument` | `label`, `label_nb`: the picker's everyday name ("Cornet"/«Kornett», "Trumpet"/«Trompet») | Apple's 5 Localizable titles, Android `TILES` and strings, Windows `TileKey` |
| `Instrument` | `key_label`, `key_label_nb`, derived from `chromatic` ("in B♭"/«i B», "in E♭"/«i Ess», "concert pitch"/«klingende») | Android key labels, Windows tile details, Studio `navigator.ts` |
| `Instrument` | `solo` (§2) | – |
| `Instrument` | `section` (exists), plus `SECTION_SEATS: section → (azimuth°, distance m)` | Apple `Section.init(name contains)` and `defaultSeat` |
| `Part` | `name_nb` ("Solokornett", "Trompet") | `nb_part_name` (Rust, Python engine, Studio, Windows) |
| order | `INSTRUMENTS` order is the picker order | Apple, Android and Windows tile orders |

`nb_part_name(name)` and `instrument_nb(name)` stay as functions, because foreign MusicXML still needs them.

- They first look the name up in the data: every part of every lineup, `SOLOIST_PARTS`, and every instrument's `name`.
- For names they don't know, they fall back to the substring table, which gets "Trumpet"→"trompet". That table then exists **only in the core**. The Python engine calls the Python mirror, which the conformance case keeps equal.

### 4.2 FFI and C ABI

These go into UniFFI (`core/brasscribe-ffi/src/lib.rs`) and the C ABI (`c_api.rs`, `core/bindings/c/brasscribe.h`, the .NET wrapper `BrasscribeCore.cs`):

- **`instruments()`**. It exists at `lib.rs:553`. It gains `name_nb`, `label`, `label_nb`, `key_label`, `key_label_nb`, `section`, `reading`, `reading_limit`, `solo` and `tune` (Melody or Solo role). `bc_instruments` is new (JSON), because the C ABI has none today.
- **`seats()`** (`lib.rs:636`, `bc_seats`). It exists and already carries `tune`. It gains `part` (the seat's own part name) and its `name_nb`.
- **`lineup_parts(LineupOptions) -> [PartInfo]`**, new, with `bc_lineup_parts`.
  - `LineupOptions` is `{lineup, seat, reads, lead, soloist}`.
  - `PartInfo` is `{name, name_nb, short, instrument, players, midi_bank, section, is_lead, is_bass, hard, soft}`.
  - `hard` / `soft` are the effective range-check limits (§2.3).
  - This is the one call that answers "what is this part?" for a score the core arranged.
- **`soloists()`** (`SOLOISTS` with their labels) and `section_seat(section)`, both new.
- **`part_name_nb`** (`lib.rs:610`, `bc_part_name_nb`) stays. `instrument_name_nb` is new.

The bindings are regenerated with `core/scripts/bindings.sh`. That covers Swift, Kotlin, the C header and the prebuilt artifacts through `scripts/core-artifacts.sh ensure`.

### 4.3 Engine and OpenAPI

- **`GET /v1/instruments`**, new. It returns `{instruments, seats, soloists, lineups: {full|minimal|quartet: [PartInfo]}}`, built from `brasscribe_music.instruments`. It is cheap and static. Studio and the apps (for engine jobs) read it.
- **`schemas.py:13`** `Seat = Literal[tuple(SEAT_IDS)]`, built from the data. `Soloist` is built the same way from `SOLOISTS`. The OpenAPI enum stays and follows the data.
- `ARRANGEMENT_DEFAULTS` (`profiles.py:36`) gets `"soloist": None`. `_check_seat` checks the §3.3 refusals.
- **`talking_score.py:440-458`** drops its copies and calls the mirror's `nb_part_name` / `instrument_nb`.
- **Regeneration.** `pixi run openapi` writes `engine/openapi.json`. From it come the Android client copy (`build.gradle.kts:59-60`), the Windows fixture and `studio/src/api/schema.d.ts` (`npm run gen:api`).

### 4.4 Each client

| Client | Change |
|---|---|
| Studio | `validate.ts` ranges come from `/v1/instruments` → `PartInfo.hard/soft` by part name for the job's lineup options. `CROSSING_PAIRS` stays: it is voicing policy for the band's part names. `talkingxml.ts` and `navigator.ts` read `name_nb` and the part's instrument, and `run.ts` `seatName` reads `seats`. Studio ships with its engine, so no fallback is needed. |
| Apple | `Section.init` → `PartInfo.section`, and `defaultSeat` → `section_seat`. `Seats.swift` tile order and titles come from `instruments()`: the five Localizable titles are removed and `label`/`label_nb` are used. `PracticeModel` and `CoreBridge` take the lead from `PartInfo.is_lead`. |
| Android | `WhatDoYouPlayScreen` tiles come from `instruments()` (label, key label). The per-instrument strings are removed. `Pitch.kt` `Instrument` enum → `InstrumentInfo`, with the enum kept only for the JVM `KotlinCoreBridge` fallback, which already returns no seats. `ReviewScreen` looks the instrument up by the part's id, not by chromatic. `MyInstrument`/`Lineup`/`PlayViewModel` read the lead from `PartInfo`. `SoundPack.INSTRUMENTS` comes from `mapping.json` targets, and `SIBLINGS` from a new `siblings` field there. |
| Windows | `BrassSoundSet.PartMap` is removed (`mapping.json` always ships, and without it the basic tier plays). `MusicXmlTalkingScoreBuilder` nb tables → core `bc_part_name_nb` / `bc_instrument_name_nb`. The play-along part is `PartInfo.is_lead`. `SeatCatalog` `TileKey`/`TileOrder`/`TuneInstruments` → `bc_instruments` + `bc_seats.tune`. That file is on the unmerged `feat/my-instrument-windows` branch (§8). |
| qa | `musicxml_readability.py` `RANGES` → `brasscribe_music.instruments`: written ranges from `reading`, `placement_limit()` and, for the lead, `solo_range()`. The "solo cornet" row becomes the data's `solo` (§2.2). |
| sounds | `mapping.json` gets the new parts and target (§5). `partsound.py --check` also checks that every part of `lineup_parts` for every lineup, soloist and seat part has a mapping entry, a bank and a seat. |

**After this, a new instrument is data only:**

- an `Instrument` and `Part` in both core tables (the conformance case keeps them equal);
- a `mapping.json` part and target;
- a `seating.json` entry;
- regenerated vectors and bindings.

No platform code changes. §6.4 has a test that holds this to account.

---

## 5. (d) The trumpet sound

### 5.1 Target

The new `mapping.json` target is `trumpet`:

- **Sustain:** Iowa MIS trumpet, "novib". It covers E3–E♭6, sounding 52–87, one sample per semitone (`data/sounds/raw/iowa-mis/trumpet/pitch`, 36 files), so all of the trumpet's pro range 52–85 is played from its own samples. The VSCO 2 CE trumpet's sustains stop around the cornet's range, and its file names need the analysis pass to settle the octave.
- **Staccato:** VSCO 2 CE trumpet `stac` (CC0). Iowa has none, and cornet-a cuts the sustains to 0.6 s instead.
- **EQ:** `eq: []`, only the DC block `build.py` always adds. The instrument's own sound is the point.
- **Range:** [52, 85]. **Level:** `TARGET_K_DB` like every target.
- `partsound.py --check` already accepts `iowa-mis` and `vsco2ce` as sources.

Why not cornet-a without its EQ? cornet-a is Iowa too, so the raw trumpet is audibly that recording without the cut above 3 kHz. That is the difference the owner asked for, and it keeps the licences as they are.

### 5.2 Shared mapping

- **`parts["Trumpet"]`:** `instrument: bb-trumpet`, one player `{target: trumpet}`, seat `solo-cornets`, `band_soundfont {program 56, bank 6 (0-based; 1-based 7), staccato_bank 70}`. The gain and balance come from the Solo Cornet's, as a starting point that `band.py` re-derives (`channel_gain_db`).
  - The seat is the Solo Cornet's, so the soloist changes the timbre, not the mix. A "soloist, front of the band" position is an owner question (§9).
- **`resolve.keywords`:** "trumpet" → `Trumpet` (was Solo Cornet), and a new "trompet" → `Trumpet`.
- **`resolve.instruments`:** `brass.trumpet` and `brass.trumpet.bflat` → `Trumpet`.
  - Foreign scores that label their parts as trumpets (a brass quintet from MuseScore) then play the raw trumpet rather than the cornet preset. That is more faithful, and it is a behaviour change, stated in the commit.
- **`seating.json`:** `Trumpet` is added to the `solo-cornets` seat's `parts`.
- **`siblings`:** `{cornet-a: [cornet-b], cornet-b: [cornet-a]}`, moved here from `SoundPack.kt`.
- **Regeneration.** `partsound.py --vectors` rewrites `partsound-vectors.json`. `VECTOR_INPUTS` gets "Trompet", "Trumpet 1" and "Solo Trumpet". The Kotlin, C#, Swift and TypeScript vector suites follow.
  - `PartSoundTests.cs:80` renames "3rd Cornet" to "Cornet III" instead of "Trumpet in B♭". It tests other writers' cornet names, and a trumpet is no longer one.

### 5.3 SoundFonts

- `band.py --bits 16` adds the Trumpet preset (sustain at bank 6, staccato at bank 70), and `mobile_soundfont.py` adds it to the mobile file. Both run offline on the Mac.
- **Mobile budget.** The mobile SF2 is 77 MB and sits at alphaTab's heap edge (`apps/android/README.md:87`). One sustain layer of 34 semitones at 22.05 kHz is about 3–5 MB. The build prints the new size.
  - **Acceptance:** the pack loads on the phone RFCY9141XEF with the full-band golden and no OutOfMemoryError (`emulator-pool.sh acquire --phone`; the current debug build is reinstalled afterwards and nothing is uninstalled).
  - If it doesn't load, the mobile file maps `Trumpet` to the cornet-a preset (`preset_of`, which `band.py` supports), and only the 16-bit pack carries the raw trumpet. That is a decision recorded in the commit, not a silent fallback.
- **Realistic tier.** `build.py` writes `data/sounds/built/trumpet/` (SFZ + SF2). Android's `SoundPack` folders come from the mapping (§4.4), and Apple's and Windows' realistic tiers find the folder by target.

### 5.4 Republishing the pack

`sounds/README.md:28` describes it. The steps:

1. Rebuild both files.
2. Run `sounds/tools/band_sounds.py pin --version sounds-2026.MM.DD`, which rewrites `band-sounds.json` and `SHA256SUMS`.
3. Publish the two files and `SHA256SUMS` as a pre-release with that tag.
4. Commit the pin.

**The owner does step 3** (`gh release create sounds-… --prerelease`). It creates a tag, and this work doesn't create tags. `release.yml` triggers only on `v*` tags, so publishing starts no workflow.

Until the pin lands, CI and local fetches keep the old pack. The Trumpet part then plays through the resolver's fallback: `Trumpet` has a mapping entry, but the SoundFont has no bank 6, so the apps' bank lookup falls back to the part's program, 56, which is the Solo Cornet preset. That is audible, never silent, and it is covered by a test (§6.2).

The pin commit comes last, on the same branch. Its message names the release.

---

## 6. (e) Conformance, tests and acceptance

### 6.1 Conformance (Rust = Python)

- **New case `instruments`.** `brasscribe-core instruments --json` (new CLI command) against `python -m brasscribe_music.instruments --json`: every instrument, part, seat, seat-part row, soloist and section seat, compared canonically. Nothing is left for the two tables to drift on.
- **New Mikkel variants** (`cases.py` `MIKKEL_VARIANTS`):
  - `layers-soloist-trumpet` (`--soloist bb-trumpet`)
  - `layers-lead-seat-trumpet` (`--seat trumpet --lead seat`); its arrangement must equal the one above
  - `layers-seat-trumpet` (a band take: your part is Solo Cornet, and the notes equal `mikkel/layers`)
  - `layers-minimal-soloist-trumpet`
  - `layers-soloist-trumpet-easier` (the trumpet's notes equal the Solo Cornet's in `layers-easier`)
- **Solo takes.** `SOLO_SEATS` gets `("tpt", "trumpet")` on the ChoraleBricks trumpet stems.
- **Refusals.** `soloist` with the quartet, and `soloist` with `lead=seat` on another seat, give the same error text on both sides.

### 6.2 Unit tests (Rust, with Python twins)

- **Soloist placement:**
  - a phrase inside `solo_range()` is unchanged;
  - a phrase above it takes the smallest shift;
  - a take with less than 95 % inside keeps today's placement, byte for byte;
  - standard and easier are unchanged;
  - the quartet and `lead=seat` Euphonium are unchanged.
- **`Lineup::check`:** for the lead, `solo` is hard and `pro` is soft; for other parts, as today.
- **`soloist_lineup`:**
  - 19 parts, with `Trumpet` first and as the lead;
  - Solo Cornet routed to the strings layer;
  - `TOP_INSTRUMENTS` voicing;
  - banks, and `part_banks()` including `Trumpet` → 7.
- **Seats:**
  - `seat_part("band", "trumpet")` gives Solo Cornet (not exact, same key), and with a soloist `Trumpet` (exact);
  - `seat_lineup("trumpet")`;
  - `lead_lineup` with a trumpet seat implies the soloist;
  - `Seat::own_part` for every seat.
- **Layers:** every part of every lineup variant (base lineups × seats × `lead` × `soloist`) gets a layer or is intentionally silent. This guards the arranger's name-keyed role lists.
- **Names:** `nb_part_name("Trumpet") == "Trompet"` and `instrument_nb("Trumpet in B♭") == "trompet i B"` from the data. A foreign "Trumpet 2" gets «Trompet 2» through the fallback table.
- **Sounds:**
  - `partsound.py --check` covers every `lineup_parts` part;
  - the vector suites on four platforms;
  - `test_band_midi.py:45`, the channel count, gets +1 for the soloist lineup;
  - `test_lineups.py` also compares `mapping.json` with the soloist and seat parts;
  - a player test: a `Trumpet` part with a pack that lacks bank 6 falls back to program 56 and is audible.

### 6.3 Holding everything else still

For each step, `core/target/conformance` before and after is diffed. Every case outside the ones §2.5 and §6.1 name must be byte-identical, and the commit message says so with the count.

### 6.4 "Data only" test

A throwaway test instrument (`test-only`, compiled under `cfg(test)` / a pytest fixture) with a part and a mapping entry must flow through:

- `instruments()`, `lineup_parts()`, `/v1/instruments`;
- the Studio validator, the talking-score names;
- the Android and Apple tile builders and the Windows `SeatCatalog`, each in its unit tests from a fixture JSON of the FFI output.

It must do this with no platform code touched. That is what "future instruments are data only" means, and this test is how it is kept.

### 6.5 Acceptance criteria

1. **Mikkel faithful, default lineup.** Solo Cornet writes all 694 solo notes in the played octave, and its top is 84. There are 14 "uncomfortable" range notes on the lead and none "impossible". The inner-part note counts are as in §2.5.
2. **Mikkel standard, easier and quartet** outputs are byte-identical to before (a) in both arrangers.
3. **`--soloist bb-trumpet`** gives a 19-part score with "Trumpet" on top:
   - `<instrument-sound>brass.trumpet.bflat</instrument-sound>`, `<midi-bank>7</midi-bank>`;
   - written a whole tone above sounding, in treble clef;
   - no range warnings;
   - Solo Cornet present, without the tune;
   - the title "… solo trumpet & brass band (draft)".
4. **A trumpet player** can pick Trumpet in "What do you play?" on Android, Apple and Windows, in en and nb:
   - a solo take gives one "Trumpet" part;
   - a band take shows the full-band notice and Solo Cornet as "your part";
   - "You: Trumpet" gives the soloist score.
5. **Norwegian** shows «Trompet», «Trompet i B» and «Solokornett» wherever part and instrument names appear: talking score (core, engine, Windows), Studio, the pickers, and the chips.
6. **The trumpet preset** plays raw trumpet samples (no cornet EQ) in the 16-bit and mobile packs, and in the realistic tier. The mobile pack loads on the phone.
7. **No name table is left** in Studio, Apple, Android, Windows or the engine for part names, instrument names, ranges, sections or tiles. `rg` over the clients for the old tables comes back empty, and §6.4 passes.
8. **The checks pass.** `make check` passes for every touched area, conformance included. Apple UI tests run only through `scripts/mac-vm.sh` when on `main`, never on the host.

---

## 7. Build order (phase B)

Each step is its own set of conventional commits, with its tests. The critic reviews each step before the next one starts.

**Step (a): soloist range.**
1. `feat(core): place a faithful soloist's phrases in the octave played`. Rust and Python: `solo`, `SOLOIST_SHARE`, `Lineup::check`, `place_as_played` range, unit tests, conformance diff.
2. `chore: re-save the Mikkel golden output with the soloist's range`. The golden with its backup, readability, baselines, the benchmark doc, the Windows count.

**Step (c): instrument facts from the core.**
3. `feat(core): instrument, part and seat facts in the core data`. `name_nb`, labels, key labels, `section_seat`, `lineup_parts`, the name functions from data, the `instruments` CLI and conformance case.
4. `feat(ffi): export instrument and lineup-part facts`. UniFFI, C ABI, .NET wrapper, bindings regenerated.
5. `feat(engine): serve instrument facts and take seats from the core data`. `/v1/instruments`, the Seat enum from data, `talking_score.py`, OpenAPI regenerated (engine, Studio types, Android client, Windows fixture).
6. `refactor(studio): read instrument facts from the engine`
7. `refactor(apple): read sections, tiles and part names from the core`
8. `refactor(android): read tiles, instruments and part names from the core`
9. `refactor(windows): read part names, leads and tiles from the core`
10. `refactor(sounds): SFZ folders and siblings from the mapping`, `refactor(qa): readability ranges from the instrument data`

**Step (b): trumpet.**
11. `feat(core): Trumpet in B♭ as a soloist and a seat`. Data, `soloist_lineup`, the seat, options through the CLI, FFI and composition, and conformance cases.
12. `feat(engine): soloist option and the trumpet title`
13. `feat(apple|android|windows): trumpet in What do you play and Who plays the tune`. The tile, the full-band notice, the soloist choice, en and nb, the old-engine line.
14. `docs(design): trumpet tile and full-band notice in the my-instrument mockups`

**Step (d): sound.**
15. `feat(sounds): raw trumpet target and the Trumpet part in the band mapping`. The target, part, resolver, seating, vectors and the four suites.
16. `build(sounds): band SoundFonts with the trumpet preset`. The build and a phone check. The owner publishes.
17. `chore(sounds): pin sounds-2026.MM.DD`, after the release exists.

Everything is pushed to `feat/trumpet` and nothing is merged.

---

## 8. Dependencies, coordination and conflicts

- **`fix/user-flow` (`flow-fix`)** changes `with_reading`'s reads-null default in `instruments.rs`/`.py`. Its fix to Android's `RustCoreBridge.kt:114` passes the core's `tune` through.
  - Steps 3, 8 and 11 touch the same functions and files.
  - This branch rebases on `fix/user-flow` once it lands, or takes its commits when step 3 starts.
  - `flow-fix` hears about it before step 3.
  - Its announced edits are these. `with_reading` takes the seat, `seat_lineup` refuses percussion, `seat_part.same_key` uses the reading, and `composition_lineup` gets a new "empty" part source. It leaves the `SEATS` and `SEAT_PARTS` rows alone.
  - The trumpet seat row and `own_part` go on top of those edits. `same_key` for `trumpet` → Solo Cornet stays true, because both are treble in B♭.
- **`feat/my-instrument-windows`** (13 commits, unmerged) holds Windows' "What do you play?" (`SeatCatalog.cs`).
  - Step 9's picker part and step 13's Windows part build on it after it merges.
  - If it hasn't merged by step 9, the Windows picker change waits, and the rest of step 9 goes ahead.
- **User-flow P1-3:** band and pop takes are always arranged for the small band or the quartet.
  - The soloist exists only in the layered arranger (orchestra-with-soloist and solo takes), which is also the only place the full band exists.
  - "A trumpet soloist" is therefore offered only for those recordings. That is the same rule as "Who plays the tune?" today.
- **Goldens:** `data/golden` is shared by every worktree through a symlink. The golden is re-saved (step 2) only after announcing it to the team lead, because other branches' golden tests see it at once.

---

## 9. Questions for the owner

1. **The cornet soloist's top.** Is 84 (written D6, the qa "solo cornet" row) right, or should it be 85 like the trumpet? Mikkel is the same either way. Default: 84.
2. **The soloist's position** in the mix: the Solo Cornet's seat (the default: only the timbre changes), or front-centre by the conductor?
3. **The mobile pack**, if the trumpet preset would push it past the heap: map the mobile Trumpet to the cornet-a sound, or trim another preset?
4. **Publishing** the sound pack pre-release (§5.4), when step 16 is ready.

---

## 10. The critic's review

The critic's background checks (`docs/research/15-trumpet-critique.md` §1) are addressed above:

| Critic point | Where |
|---|---|
| 116 reproduces; "13" needs a wider reading range too; the 22 intro down-moves come from the centre tie-break | §1.3: reproduced independently on the Rust CLI, same numbers |
| A range change leaks into standard/easier through `fold` | §1.4, §2.1: the soloist range is a separate field, used only in faithful soloist placement; §6.3 holds standard and easier byte-identical |
| 84 on a cornet reverts `743c04d` and trips `check` and `validate.ts` | §2.2 and §2.3: section cornets keep 82, and the lead is checked against `solo` (hard) and `pro` (soft) through the core's part facts on every validator; qa row versus MuseScore settled in §2.2 |
| MuseScore trumpet 52–80/52–85, `brass.trumpet.bflat`, 30 uncomfortable | §1.2, §2.3 (the soloist is judged by `pro`), §5.2 (resolver learns `brass.trumpet.bflat`) |
| Missing copies | §1.6 (merged), §4.4 |
| Pack republish cost, mobile heap, Literal 422 | §5.3, §5.4, §3.5 (old engine), §4.3 |

The plan-review points are added here as they come in.
