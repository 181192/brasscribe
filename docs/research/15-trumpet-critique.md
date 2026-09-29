# Trumpet support: critique

Status (2026-09-29): all P1 and P2 findings are fixed on main, and trumpet shipped in 0.2.0 (Trumpet in B♭,
a trumpet seat that takes the lead, Android and Apple tiles). Still open: the Windows tile (Windows Play has no
"What do you play?" yet), a phone check, and P3-5 (the Trumpet part plays the layered Solo Cornet desk).

An adversarial review of trumpet support. Part 1 checks the background
claims before the plan. Part 2 reviews the plan, and Part 3 reviews the implementation as it landed.
Findings are ranked P1 (must fix before merge), P2 (should fix) and P3 (nice to have).

## Part 1: background claims, verified

### 1.1 The 116 octave moves reproduce, in both arrangers

Setup: the solo layer of `data/golden/mikkel-arranged-band/composition.json` (694 notes, MIDI
53–84; 14 notes above 82: nine on 83 and five on 84), arranged with `arrange_layers` on
`BRASS_BAND`. Each source note is compared with the Solo Cornet note at the same onset. The Python
and Rust arrangers give identical counts in every configuration below. For Rust, a scratch binary
linked `brasscribe-core` and swapped the lead instrument (`Box::leak`).

| Lead range (reading / limit, sounding) | Mode | Same octave | −12 | +12 | Moved |
|---|---|---|---|---|---|
| (55,79) / (52,82) (today) | faithful | 578 | 111 | 5 | **116** |
| (55,79) / (52,84) | faithful | 667 | 22 | 5 | 27 |
| (55,82) / (52,84) (qa "solo cornet" row) | faithful | 674 | 14 | 6 | 20 |
| (55,84) / (52,84) | faithful | 677 | 11 | 6 | 17 |
| (55,86) / (52,86) | faithful | 681 | 0 | 13 | 13 |

- **The simulation is the shipped golden.** The baseline faithful lead has the same pitch multiset as
  `parts/02-Solo-Cornet.musicxml`, written back to sounding: 694 notes, top 82.
- **116 is right:** 111 notes go down and 5 go up. The loss is range-driven: 89 of the 116 notes
  sit in the five long phrases that no octave fits under 82 (ticks 1356, 3810, 6348, 9804 and
  11850), which the arranger splits at their leaps.
- **"13 still move" does not hold for a limit-only change.** Raising only the placement limit to
  84 leaves **27** notes moved (22 down, 5 up). The 13 appears only when the *reading* range is widened
  to 86. That holds with a limit of 84 as well, so the reading range drives it, not the limit. All 13
  move **up**. A reading range above the placement limit is incoherent, so the "13" most likely
  came from a mis-set simulation.
- **The remaining 22 down-moves have nothing to do with range.** They are the intro phrases (ticks
  0, 156, 252, 648, 858 and 3444, pitches 69–84). `_best_shift` counts notes inside the *reading*
  range `preferred` (55,79), not the limit, and breaks ties by distance to the range centre (67). A
  phrase at 69–76 fits either octave, so the centre tie-break drops it by an octave. The phrase at
  tick 252 (71–84) drops because more of its notes land inside (55,79) an octave down. So a soloist
  range that raises only `reading_limit` still drops the first 20 seconds of the tune by an octave.
  To keep them, the soloist range has to raise `reading` too (or place faithful leads by the limit).
  Even then, 11 notes still drop at (55,84).
- The +5 are phrase 12 (tick 9198, 57–67), moved up by the same centre tie-break.

### 1.2 Side effects on the other difficulty modes (measured, both arrangers)

Placement runs before `apply_difficulty`, so a lead range change is not confined to faithful:

| Lead range | standard: −12 / octave switches in a phrase / max | easier: −12 / switches / max |
|---|---|---|
| today | 104 / 43 / 79 | 144 / 68 / 75 |
| limit 84 only | 56 / 47 / 79 | 110 / 72 / 75 |
| reading (55,82), limit 84 | – / 14 / 82 | – / 47 / 80 |

- **Limit-only:** the standard and easier ranges keep their tops (79 and 75), but their lead output
  and goldens change. There are *more* octave switches inside phrases (43 to 47, 68 to 72): the
  phrase is now placed high, and `_fold` folds the top notes one at a time to the octave nearest
  the previous note. That per-note flipping is what 743c04d removed from placement.
- **Widening `reading` on the instrument:** `mode_range` reads `instrument.preferred`, so standard's
  lead rises to 82 and easier's to 80 (`EASY_TOP_TRIM` is taken off the new top). Neither mode
  promises that any more. With (55,84), standard reaches 84, which is above a cornet's pro 82: an
  *impossible* note in a mode meant to be easier than faithful.
- In faithful, a soloist limit of 84 removes all 7 octave switches inside phrases and all 5
  split-at-leaps warnings. The faithful gain is real.

### 1.3 The cornet-limit "reads well" fix

743c04d (2026-09-27, "keep the Solo Cornet inside its playable range") lowered the B♭ cornet's
`reading_limit` from (52,84) to (52,82) *because* 12 Mikkel notes were written above a cornet's
playable top (MuseScore `bb-cornet` pro 82). A "soloist range" of 84 on a part that is still a
**Cornet in B♭** reverts that fix. `Instrument.check` (pro 82) would then report the 12 placed notes
on 83 and 84 (the same 12 as in 743c04d) as `impossible`, and so would Studio `validate.ts` (`CORNET = R([52, 82], …)`, keyed by
part name). The soloist range is only consistent if the lead's *instrument* changes to a trumpet
(pro 85). Otherwise the validators have to learn a soloist exception.

In the repo's own QA, `qa/tools/musicxml_readability.py:48` already gives `"solo cornet"` a wider
written row (extreme 86 = sounding 84, comfort 84 = sounding 82) than `"cornet"` (extreme 84 =
sounding 82). The QA tool and MuseScore disagree today, and the plan should say which one wins.

### 1.4 MuseScore ranges (instruments.xml, tag v4.7.5 = the installed MuseScore 4.7.5)

The installed app bundle compiles instruments.xml into the binary, so the ranges are from
`share/instruments/instruments.xml` at tag v4.7.5 (sounding MIDI):

| id | amateur (`aPitchRange`) | pro (`pPitchRange`) | transpose | MusicXML id | program | family |
|---|---|---|---|---|---|---|
| `bb-cornet` | 52–79 | 52–82 | −2 / −1 | `brass.cornet` | 56 (mute 59) | cornets |
| `bb-trumpet` | 52–**80** | 52–**85** | −2 / −1 | **`brass.trumpet.bflat`** | 56 (mute 59) | trumpets |
| `c-trumpet` | 54–82 | 54–85 | 0 | | 56 | trumpets |
| `flugelhorn` | 52–79 | 52–82 | −2 / −1 | | 56 | |
| `eb-cornet` | 57–84 | 57–87 | +3 / +2 | | 56 | cornets |

- A B♭ trumpet reaches 85 (pro), so Mikkel's 84 is playable. It is still above the trumpet's
  amateur top of 80. 34 of the 694 source notes are above 80, and with a limit of 84, **30 placed
  notes are above 80**. Under the current `check()` semantics, a "Trumpet in B♭" lead at faithful
  gets 30 `uncomfortable` range warnings, which surface in Studio and the validation endpoint.
- The MusicXML sound id is `brass.trumpet.bflat`, not `brass.trumpet`. The band resolver
  (`sounds/mapping.json` resolve.instruments) knows only `brass.trumpet` → Solo Cornet. A part
  that writes MuseScore's id, with a name that is not English, resolves only through the program-56 fallback.
- Cornet and trumpet share program 56. "A trumpet sound" is therefore a SoundFont preset question
  (bank), not a GM program one.

### 1.5 Name-matched instrument copies the background list misses

The background names talking_score.rs, Studio validate.ts/talkingxml.ts, Apple Score.swift,
Android SoundPack.kt, Windows BrassSoundSet.cs and engine schemas.py Seat. These are also
hardcoded, and each would miss or mislabel a trumpet:

| Where | What it hardcodes | A trumpet would… |
|---|---|---|
| `studio/src/lib/navigator.ts:225` | instrument name keyed by **transposition** (−2 → "Cornet in B♭" / «kornett i B») | be announced as "Cornet in B♭" (already true of Flugelhorn) |
| `engine/src/brasscribe_engine/talking_score.py:442,452` | `NB_PART_NAMES`, `instrument_nb` string replacements | come out as «trumpet i B», half-translated |
| `apps/windows/.../TalkingScore/MusicXmlTalkingScoreBuilder.cs:447` | its own nb part-name table (not the core's `nb_part_name`) | keep an English name in the Windows talking score |
| `apps/android/model/.../Pitch.kt:76` | `Instrument` enum: en/nb names, transposition, program | have no entry (the enum decides written pitch and key names) |
| `apps/android/.../MyInstrument.kt:112`, `Lineup.kt:14,36` | quartet aliases, lead names "Solo Cornet"/"1st Cornet" | not be recognised as the lead |
| `apps/android/.../ui/WhatDoYouPlayScreen.kt`, `apps/apple/App/Seats.swift:133,143` | instrument picker order and titles by instrument id | not appear in "What do you play" |
| `sounds/mapping.json` resolve (`keywords` "trumpet" → Solo Cornet; `instruments`), `sounds/partsound.py:73`, `partsound-vectors.json`, `seating.json` | the resolver every platform ports, plus its vectors and seat positions | play the cornet preset; «Trompet» misses the keyword (fallback only) |
| `qa/tools/musicxml_readability.py:46` | `RANGES` by part-name substring | go unchecked (no "trumpet" row) |
| `engine/src/brasscribe_engine/profiles.py:251` | title "solo cornet & brass band (draft)" | keep "solo cornet" in the title |
| `apps/windows/tests/.../PartSoundTests.cs:80` | renames "3rd Cornet" → "Trumpet in B♭" and expects the band SF2 to play it | already codifies trumpet = cornet preset, so a separate trumpet preset changes this test |
| `design/mockups/scores.js`, `design/mockups/music-stand.js`, site `index.html`/`guide`/`nb` | cornet part lists and copy | show no trumpet (docs only) |
| `core/brasscribe-ffi/src/lib.rs:607` `nb_part_name`, `c_api.rs` | the core's single nb table (good), but `seats()` exposes only `SEATS` | needs the new name here once and in no platform table |

The Bandroom apps (`apps/bandroom`) and braille (`engine/src/brasscribe_engine/braille.py`, which
ASCII-folds `partName`) have no instrument tables. They follow whatever name the score carries.
Braille would print "Trompet i B" when given the name, so nothing extra is needed there.

### 1.6 Cost facts for the plan

- Band SoundFonts: `brasscribe-band.sf2` is 293 MB, `-16bit` 195 MB and `-mobile` 77 MB, pinned in
  `sounds/band-sounds.json` as the pre-release `sounds-2026.09.27`. A new preset means a rebuild
  (`band.py --bits 16`, `mobile_soundfont.py`), the checks, a new pre-release, a pin bump and a
  new SHA256SUMS, and the Android/Apple/Windows release jobs refetch the pack. Every app bundle
  grows by the new preset's samples (the mobile SF2 is already at the alphaTab heap edge, see
  `apps/android/README.md:87`).
- The Solo Cornet preset is already trumpet samples EQ'd *toward* a cornet (`mapping.json`
  targets `cornet-a`/`cornet-b`, "less energy above ~3 kHz"). A "trumpet sound" is those samples
  without the cornet EQ. That is cheap in sample terms, but it still triggers the full pack
  republish above.
- Seats: `schemas.py:13` `Seat` is a pydantic `Literal`. An app that sends a new seat id to an
  older engine gets a 422, not a fallback.

### 1.7 A lead range change moves the whole band, and the quartet most

The pads and SATB voicing are placed under the lead (`arranger.py:769-771`, `_voice_satb_slots`), and
Soprano Cornet doubles it outside faithful. Only the lead's instrument was changed below. The counts
are the symmetric difference of (start, pitch, dur) against today, so one moved note counts twice.

| Lineup, mode | limit 84 | reading (55,82), limit 84 |
|---|---|---|
| band, faithful | Solo 178, Repiano 11, Flugel 6, 1st Tbn 6, 2nd and 3rd Cnt 5, horns 1 each | Solo 196, Flugel 18, Repiano 13, Solo Horn 6 … |
| band, standard | Solo 106, Repiano 15, Flugel 10, Soprano 6, … | Solo 172, Flugel 26, Repiano 17, Solo Horn 12 … |
| quartet, faithful | 1st Cnt 178, **2nd Cnt 82, Tenor Horn 77** | 196 / 108 / 96 |
| quartet, standard | 1st Cnt 106, **2nd Cnt 207, Tenor Horn 192** | 170 / 318 / 266 |

With the soloist range, no part other than the lead goes above its own pro. The quartet's inner voices
are re-voiced wholesale, though. A soloist range that also reaches the quartet's 1st Cornet (it is a
`bb-cornet` like the Solo Cornet) rewrites most of the quartet goldens, which is outside the owner's need.
It should apply to the band lineups' lead only, and the quartet goldens should come out byte-identical.

### 1.8 Compatibility in both directions

- Old engine, new app: the `Seat` `Literal` rejects a new seat id with a 422 (1.6).
- New engine, old app: this direction is more likely, because apps update more slowly than a paired
  engine. A score whose lead is renamed or re-instrumented reaches old name tables. Apple
  `Score.swift:202` `Section(name:)` sends "Trumpet …" to `.other`: no seat position and no section
  sampler. Android `Pitch.kt` and the Windows nb table have no entry. The resolver finds the preset
  only through the "trumpet" keyword (cornet preset). Keeping the part **name** "Solo Cornet" and
  changing only `<instrument-name>`/`<instrument-sound>` avoids every old-app break. Renaming the part
  does not.
- Contract: `engine/tests/test_api.py:126` checks that `engine/openapi.json` equals the rendered
  schema. The Android client copies it at build time (`apps/android/engine-client/build.gradle.kts:59`),
  so a new seat literal is one `pixi run openapi` plus a rebuild. There is no check that the apps
  accept every seat id the engine lists.

### 1.9 The decision the plan must make: cornet or trumpet

The repo has one piece of evidence: `docs/songs/mikkel.md:14`, cornet-like proportions at 0:10, a possible
switch later, "confirm by ear". It cannot be settled from the repo. The two answers need different fixes:

- **Trumpet lead:** the instrument becomes `bb-trumpet` (pro 85, amateur 80), and the 84s are legal.
  It needs a trumpet row in every name table, and at faithful it produces 30 `uncomfortable` warnings.
- **Cornet lead:** a "solo cornet" soloist row, like qa's written D6, plus a soloist exception
  in `Instrument.check`, `validate.ts` and inspection. MuseScore's pro 82 stays wrong for this player.

Either is defensible. What is not: a limit of 84 on a part still declared Cornet in B♭ with no validator
change, which is 743c04d reverted.

### 1.10 Proposed invariant test

`music/tests/test_range_invariants.py` runs the Mikkel golden for every lineup and mode and checks two
things: no part sounds outside its declared instrument's pro range, and the standard and easier leads
stay inside `mode_range`. It passes on main (15 tests, about 4 s). Setting the cornet's limit back to
(52,84) makes it fail on band, minimal and quartet faithful, so it catches a reverted 743c04d whatever
API the plan picks.

### 1.11 Baseline on main (157d9df)

`scripts/check.sh fast engine core conformance studio` is green: engine 74 s, core 71 s, conformance
262 s (15/15 cases, 461/461 files, 24/24 golden files), studio 11 s. A red result in a step review
is therefore caused by the trumpet changes.

## Part 2: review of docs/plan/trumpet.md (e741db8)

The plan takes up every Part 1 point. §1.3 re-measures the numbers independently and gets the same
counts, and §2 keeps the soloist range out of standard, easier and the quartet. The remaining problems:

**P1-1: re-saving the golden breaks main and every other worktree.** `data/golden` is one symlinked
directory for all worktrees. The conformance runner compares the Mikkel case file by file against it
(`core/conformance/brasscribe_conformance/run.py:180-187`) and exits 1 on any difference (`:224`).
The plan re-saves it before the code is merged. From then on, `check.sh conformance` is red on
main and in every other worktree, and so are the other golden tests (Windows `GoldenNotes`,
`music/tests/test_seats.py`). Announcing it does not fix that. Fix: write the new output to a new
directory (`mikkel-arranged-band.soloist`) and point `cases.py:108` and the other golden paths at it
in the same commit. Then the golden and the code that produces it travel together, and the old
directory stays valid for main until merge.

**P1-2: over-scoped for what the owner needs.** The owner wants a better Mikkel lead and a way to
play trumpet. That is the soloist range and the trumpet seat, plus a small part of the app and sound work.
- Option (c) It adds a new FFI surface, `bc_*` JSON calls and `/v1/instruments`. It refactors
  Studio, Apple, Android and Windows and deletes their tables, and it depends on the Windows
  "What do you play?" work, which was not merged. Acceptance needs Apple UI tests that cannot run on the host. It is a
  platform re-architecture, and neither goal needs it.
- Option (d) needs the owner to publish a 293/195/77 MB pack, plus a heap test on a physical phone.
  Until then the trumpet already plays the cornet preset, audibly, through the resolver's keyword
  and program-56 fallback.

Proposal:
- ship (a);
- for (b), add `bb-trumpet` and a soloist option that swaps the lead's *instrument* in place, with no
  19th part;
- add the trumpet seat mapped to Solo Cornet or 1st Cornet;
- give each app a tile;
- patch the name tables that exist today by one row each: `nb_part_name`, `instrument_nb` (Rust and
  Python), `talkingxml.ts`, `navigator.ts`, `validate.ts`, the Windows nb table, the resolver keyword
  «trompet» and `brass.trumpet.bflat`.

(c) goes in its own plan, and (d) waits for the owner's call on §9 Q3 and Q4.

**P1-3: (a) quietly depends on (c) for its validators.** §2.3 routes every validator through
`PartInfo.hard/soft`, which only exists once (c) is built. Until then, Studio's fallback
`validate.ts:14` (`"Solo Cornet": CORNET`, pro 82) reports the new golden's 14 notes on 83–84 as range
errors. The engine's `validate_range` and inspection do the same unless the soloist-range change updates them. That change
has to carry the soloist check into `validate_range` (Rust and Python), `inspection.py` and
`validate.ts` in one commit. The range-invariant test becomes "within the
part's hard limit (`Lineup::check`)", adapted to the new API once the soloist range lands.

**P2-1: the soloist rule changes more than Mikkel.** "Keep the phrase's octave whenever it fits
52–84, if ≥95 % of the solo is inside" applies to every layered faithful job whose solo sits in the
cornet or trumpet register, and that is nearly every orchestra-with-soloist recording. It also keeps
tracker octave errors that the centre tie-break folded. Two of the phrases it keeps are fragments of
2 notes and 1 note (ticks 0 and 156). Evidence beyond Mikkel is needed: run the layered references
the eval has (`difficulty_bench`, `arrange_bench`, the URMP and ChoraleBricks solos) before and after, and
report the octave agreement with the reference. `SOLOIST_SHARE = 0.95` is tested on only one piece,
and that piece is 100 % inside.

**P2-2: the soloist as a 19th part.** Inserting a part touches the part count, banks, channels
(`test_band_midi.py:45`), layer routing and mixing, and the Solo Cornet becomes a pad part. Every client
then has to learn who "your part" is (`PracticeModel.swift:146`, `Lineup.kt`, `ScoreViewModel.cs:159`).
Swapping the lead part's instrument to `bb-trumpet`, and its name to "Trumpet", gives the same
score for the soloist with 18 parts. The seat and "your part" logic stays keyed on
`lineup.lead`. Use the swap unless the owner wants both a trumpet and a solo cornet.

**P2-3: Norwegian copy.**
- The lineup is called «Fullt brassband» (`values-nb/strings.xml:226`). The notice should read
  «Fullt brassband har ingen trompet …» or «Det fulle brassbandet …», not «Det fulle bandet».
- `tune_seat` is «Deg: %1$s» with the part name, so it reads «Deg: Trompet», not «Deg: trompet».
- «Trompet i B» and «trompet i B» in running text match «kornett i B», which is right.
- «En {label_nb}solist» works for «trompetsolist». As a general template it breaks on hyphenated
  labels («Sopran-kornett»), so keep it as one string rather than a template.
- The English template "A {label} soloist" needs the label lower-cased: "A trumpet soloist".

**P2-4: the Windows regression without mapping.json.** §4.4 deletes `BrassSoundSet.PartMap`. Today it
resolves realistic sounds by name when `mapping.json` is missing, which is the case for dev builds and
the sideloaded pack. Keep it, or show that every Windows build ships `mapping.json`.

**P2-5: CI minutes.** `ci.yml` runs on every push to every branch (two Linux jobs, 20 min cap each,
`cancel-in-progress` per ref). Seventeen commits pushed one by one cost about 17 runs. Push in groups, and keep the platform checks local (`check.sh`). The platform workflows are dispatch-only,
so they cost nothing unless someone dispatches them.

**P3-1:** §1.5 "Mikkel's soloist plays trumpet" rests on who the performer is.
`docs/songs/mikkel.md:14` records a cornet-like instrument at 0:10, with a possible switch later.
Nothing depends on it, because the default keeps the Solo Cornet, but either soften the wording
or update mikkel.md.

**P3-2:** §5.2 re-points the resolver's "trumpet" keyword and `brass.trumpet` from Solo Cornet to
Trumpet. That changes the playback of every foreign score with trumpet parts. It belongs with (d);
if (d) is deferred, leave the keyword alone.

**P3-3:** §6.4, the "data only" test across three app suites, goes with (c).

## Part 3: reviews of the implementation

### The soloist range (c048793, 4609a3e, 7b710bf)

**Verified**
- Conformance run fresh (Python references regenerated), `--only mikkel`: 15/15 cases, 461/461 files and
  24/24 golden files identical against `mikkel-arranged-band.soloist`.
- Byte for byte against main's Rust output: standard, easier, minimal-easier, quartet, quartet-easier,
  key-bb and all four lead-seat cases are identical. The only difference is the random part ids in the
  talking-score `doc.json`, which also differ between two runs of main. Changed: only the faithful
  band and small-band cases, as the plan states.
- Mikkel faithful: all 694 notes in the played octave, top 84, and no Solo Cornet warnings. Standard and
  easier keep their −12 counts (104 and 144) and tops (79 and 75), unchanged from main.
- Rust = Python on the edge inputs below, identical in every case.
- `scripts/check.sh fast`: engine, core and studio pass. The ported invariant test (below) passes 15/15.
- The warning text `moved … (outside the range)` is read by `inspection.py:97` and `studio/src/views/run.ts:284`.

**P1-4: a phrase that goes past the solo range loses its peak note by note.** `place_soloist` keeps
a phrase's octave when at least half of its notes are inside. It then moves each outside note on its
own by the fewest octaves. For a real passage above the top, that chops the passage (Python and
Rust identical):

| Phrase (sounding) | place_soloist | today's _place_line |
|---|---|---|
| 76 79 81 84 **86 88 86** 84 81 79 | 76 79 81 84 **74 76 74** 84 81 79 (2 direction flips) | 64 … 76 … 67 (contour kept) |
| 72 … 83 84 **86 87** | … 83 84 **74 75** (a falling tenth in a rising run) | 60 … 75 (kept) |
| **84 86** 84 86 84 86 84 (a trill) | 84 **74** 84 74 84 74 84 (6 flips) | 72 74 72 74 … (kept) |

This is the per-note octave flipping that 743c04d removed from placement. It hits exactly the case
the soloist range invites: a trumpet or cornet lead that reaches 85–88. Fix: move a note on its own only
when it is a lone outlier (both neighbours inside the range, and a jump of 7 or more semitones to
each). Otherwise place the phrase with the old recursion on `solo_range()`: the whole-phrase shift with
the fewest octaves, else a split at the largest leap. The existing
`one_outlier_moves_alone_and_the_run_keeps_its_direction` still holds. The proposed test is
`music/tests/test_soloist_edges.py`: its 3 cases fail on c048793 (the lone-outlier case is `test_soloist.py`'s).

**P3-4: fast conformance reuses stale Python references.** `check.sh fast conformance` passes
`--skip-python` whenever `core/target/conformance/mikkel` exists (`scripts/check.sh:68`). A worktree
that changes `music/` therefore gets false DIFFs against the old references (10/15 here), and
could equally get a false green when Rust and a stale Python agree. Rerun the Python references when
`music/src` or `core/conformance` changed since they were written. This was already true on main.

**Accepted as designed:** the low-take gate (pinned by `test_a_low_take_in_the_cornets_range_is_written_as_played`,
owner default); `eval/baselines.json` `cornet_moved` drops to 0 for baritone, horn and trombone for the
same reason; key-bb (transposed up) falls back to today's placement through the gate.

The invariant test is ported to the new API (`music/tests/test_range_invariants.py`).
Nothing may be `impossible` under `Lineup.check`, and nothing may pass its instrument's pro range except the
band's soloist lead in faithful mode.

### P1-4 fix and the trumpet seat in the core (0299e1a, 7eaa411, a88a5ea; rebased on main 8cede40)

**Verified**
- `check.sh fast engine core conformance studio` passes. Conformance reran Python itself (the 7eaa411
  source hash) and got 20/20 cases, 602/602 files and 24/24 golden files.
- P1-4 is fixed: the arch, the run past 84, the trill and the phrase at 85–89 all keep their
  direction with no warnings, and a lone +12 outlier still moves alone. Mikkel is still 694/694.
- Trumpet seat, band and small band: the lead is `Trumpet` (`bb-trumpet`, bank 1), the part count is
  unchanged, and every part's notes equal the default lineup's. Top 84, nothing `impossible`.
  Quartet: `1st Cornet`, `takes` None, notes unchanged. `lead=seat` is a no-op in both. The solo take
  is one `Trumpet` part in 52–85.
- nb: «Trompet» and «trompet i B» appear in the engine, core, Studio talkingxml and the Windows
  talking score. Braille ASCII-folds the name («Trompet i Bb»).

**P2-6: the soloist fallback still uses the section cornet's placement.** When no whole-phrase
shift fits `solo_range()`, `place_soloist` hands the phrase to `_place_phrase`, which places by the
cornet's reading range (55,79) and limit 82. A long phrase with a few notes above 84 therefore falls
back to today's behaviour for the whole phrase. Mikkel with the solo transposed up:

| Solo up | Notes > 84 | Moved (trumpet seat) | Moved (main) |
|---|---|---|---|
| +0 | 0 | 0 | 116 |
| +1 | 5 | **193** (one of them −24) | 276 |
| +2 | 14 | 459 | 476 |
| +3 | 16 | 486 | 503 |

This is never worse than main, but one semitone takes it from 0 to 193. Fix: split at the largest
leap with `solo_range()` as both the preferred and the limit range, the recursion 743c04d
introduced. Then only the passage around the 5 notes moves.

**P2-7: Studio's navigator still calls a Trumpet "Cornet in B♭".** `studio/src/lib/navigator.ts:225`
names the instrument by transposition (−2 → "Cornet in B♭" / «kornett i B»), and that name is announced
on a mode change. A Trumpet part is announced as a cornet (so is a Flugelhorn, before this change). Key
the lookup by part name or by `<instrument-sound>` (`brass.trumpet.bflat`).

**P3-5:** the Trumpet part keeps the Solo Cornet's `players` = 4, so playback layers the Solo Cornet
desk (four cornet players) for the trumpet player's part, through the "trumpet" keyword. It sounds as
today, which is the agreed scope. Say so in the app notes, because it is audible in a solo passage.

**For the apps:** a new app must not send `seat: "trumpet"` to an older engine (the `Seat`
Literal rejects it with 422). An older app that opens a score with a `Trumpet` part puts it in
Apple `Section` `.other` (panned centre, not with the cornets).

### The apps (fd53c74 Android, ac5334d Apple, 66133ce Windows)

**Verified**
- `check.sh fast android apple` passes. Windows fast: 412/416 pass, 3 are skipped, and 1 fails:
  `StopWaitTests.On_the_ui_thread…` ("awaited stop took 493 ms"). It is a timing test in code the trumpet work
  doesn't touch, and it passes when rerun alone (4/4), so it is a flake and not from this change. No UI
  tests were run on the host.
- Android and Apple match. Both have the Trumpet / «Trompet» tile after Cornet with "in B♭" / «i B»,
  the takes notice in full and short form for the full band and the small band, full-band wording for
  the same-key and other-key notices, and "Who plays the tune?" hidden when the seat takes the lead.
- nb copy: «Fullt brassband har ingen stemme for trompet. Du får stemmen til Solokornett, skrevet for
  trompet.» It uses the lineup's own name, as P2-3 asked. Apple's xcstrings has the same text
  (positional `%1$@…%3$@`).
- `YourParts.resolve` / `PracticeModel` pick "Trumpet" in a score written for the trumpet and Solo Cornet
  in an older one, with the matching notice in each case.

**P2-8: a trumpet seat sent to an older engine is a generic error.** The app sends `seat: "trumpet"`
to the engine. An engine from before the trumpet seat knows seats but not this one, and its `Seat` Literal
answers 422 with no code. Android `rerunWithEngine` maps 422 only for the quartet and `lead=seat`, so
the player sees a generic engine error, and Apple `CompanionService.swift:303` behaves the same.
`seatIgnored` covers only engines that ignore seats altogether. Fix: on a 422 for seat `trumpet`, retry
once with `solo-cornet`. The core writes identical notes for the two (verified in the core review), so only the
part name differs, and the existing "too old to write for your instrument" line explains that.

**Parity gap (accepted, tracked):** Windows' "What do you play?" is not merged yet. The trumpet reaches it from the core's `seats()`, but it needs a
`TileOrder` entry and a tile string when it merges. There has been no phone check, and the
Apple host-app tests ran without the VM.

## Verdict

**Ship with fixes.** The owner's two goals are met: the Mikkel lead is written as played (694/694,
standard, easier and quartet byte-identical), and a trumpet player gets a Trumpet part in every
lineup. No P1 is open.

Fix before merge:
1. P2-8: retry an older engine's 422 for seat `trumpet` as `solo-cornet` (Android, Apple).
2. P2-7: Studio `navigator.ts` announces Trumpet (and Flugelhorn) as "Cornet in B♭"; key it by part
   name or `<instrument-sound>`.
3. At merge, run the golden promotion commit (`.soloist` → `mikkel-arranged-band`, paths reverted), as
   §2.6 of the plan says, and only after the owner's go.

Fix soon after (follow-ups):
4. P2-6: the soloist fallback uses the section cornet's placement. Mikkel one semitone up moves 193 of
   694 notes (main: 276). Split with `solo_range()` instead.
5. The Windows trumpet tile once Windows "What do you play?" merges; a phone check; P3-5 (the trumpet
   plays the layered Solo Cornet desk sound).

### Fix round (d68f8d70, 41a95432, 39a1658b, be3b7d15; rebased on main 394bbbc)

- **P2-6 fixed.** Notes moved on Mikkel with the solo transposed up: +1 moves 29 (was 193; main 276),
  +2 moves 97 (was 459; main 476), and +3 moves 274. Every move is a single octave, the −24 is gone, and
  Mikkel as recorded is still 694/694. The contour edge cases all keep their direction.
- **P2-7 fixed:** the navigator announces a trumpet-named part as "Trumpet in B♭" / «trompet i B».
- **P2-8 fixed:** a 422 without a code for seat `trumpet` is sent once more as `solo-cornet`, with
  reads and lead dropped. Android says the "too old" line, and Apple puts it in the part notice. Both
  have a test.
- `check.sh fast engine core conformance studio android apple` passes: conformance 20/20 cases,
  602/602 files, 24/24 golden files.
- **P1-5: the golden was promoted before the merge.** be3b7d15 renamed the shared
  `data/golden/mikkel-arranged-band.soloist` to `mikkel-arranged-band` while the trumpet code was not yet in
  main (394bbbc). `data/` is shared by every worktree, so main and every other worktree now compare
  against a golden whose Solo Cornet reaches 84, while their code writes 82. Their golden checks fail.
  Two options: restore now (the backup is in `data/golden-backups/before-soloist`), or merge at once.
  Resolved: the trumpet code merged to main with the promoted golden.

**Final verdict: ship.** The code is ready to merge. It must go in together with the golden promotion.
Until then the shared golden has to be restored, or main stays red.
