# 17 — Fast notes and trills: an independent baseline and review

Status (2026-09-29): the fixes reviewed here are on main (contour onsets for the solo line, the dense quantizer on evidence, faithful mode only), with the promoted fast-notes golden. The faithful Solo Cornet readability limit of 65 % 16ths still needs the owner to check the bars in [`docs/plan/fast-notes.md`](../plan/fast-notes.md) §7.4 by ear. Trill notation (F5, with the written-part accidental rule of P2-5), triplets with timing jitter and single-beat takes are done ([plan §8](../plan/fast-notes.md)). Open follow-ups: semitone trills with no band behind, and the sextuplet recall the evidence rule gave back.

Date: 2026-09-29. This is a review of the fast-notes work (fast runs, and rapid two-note alternation: lip trills, shakes and valve trills on cornet and trumpet). It was written before that plan arrived, so that its numbers can be checked against an independent measurement. The probes are [`fastnotes/probe.py`](fastnotes/probe.py) (audio → segmentation → line → quantization) and [`fastnotes/quant_probe.py`](fastnotes/quant_probe.py) (quantization alone, Python against the Rust CLI). Treat the numbers as findings to re-derive, not as baselines.

## Short answer

Today's solo path loses fast material at **four separate points**. A fix at one point is invisible, or even harmful, unless the others are fixed or measured too:

1. **Segmentation (SwiftF0 `segment_notes`, `pitch_hold_ms=80`).**
   - A slurred semitone trill comes out as **one note at every rate from 8 to 16 notes/s**.
   - A whole-tone or lip trill survives at 8/s and collapses at 10/s and above.
   - Legato sextuplets and 32nds keep 11 of 17 notes.
2. **Quantization (`GRIDS` penalties, then `monophonize`).**
   - This loss is independent of audio, and it is **the same in Python and Rust** (the Rust CLI was checked on the same input).
   - With *perfect* onsets on a steady grid, a sextuplet run keeps **6 of 17 notes** and 32nds keep **5 of 17**. Triplet 8ths keep 16 of 24, and the ones that survive are written as 8ths.
   - A trill at 10–14/s keeps 8–10 of 24 notes, even when segmentation is perfect.
   - Nothing reports the loss.
3. **Free time.** Inside a `plan_free_time` region only grids 1 and 2 are allowed. There, even plain 16ths keep **13 of 24**, and cadenzas are exactly where solo runs and trills live.
4. **Line extraction (`lines.rs`: `MIN_DUR` 60 ms, 50 ms onset merge).** This is the ceiling at about 16 notes/s, where 62 ms notes sit right at the cut.

The **false-note trade-off is sharp.** The one knob that recovers trills, a lower `pitch_hold_ms`, turns vibrato into notes:

| pitch_hold_ms | semitone trill 8/s | semitone trill 12/s | vibrato ±50 c 5.5 Hz | vibrato ±100 c 6 Hz | vibrato ±150 c 7 Hz |
|---|---|---|---|---|---|
| 80 (today) | 1 of 24 | 1 of 24 | 1 note ✓ | 1 ✓ | 1 ✓ |
| 40 | 24 ✓ | 2 | 1 ✓ | 1 ✓ | **22 notes** |
| 20 | 24 ✓ | 24 ✓ | **16 notes** | **20 notes** | **24 notes** |

(Dry synthetic audio, after `line()`.) Mikkel's solo already moves by more than 100 cents in the middle of 9 % of its notes ([11, short answer](11-overlaps-and-in-between-tones.md)). A global hold change would therefore turn real vibrato into false trills. Any trill detection has to be a **dedicated oscillation detector on the contour**, not a lower global hold.

**Traps that exist today and must not get worse:**
- **A scoop of 3 semitones over 150 ms segments as two notes at every hold.** The main note's onset moves past a 50 ms tolerance. At 80 bpm `monophonize` happens to merge the two back into one, but at faster tempi that will not hold.
- **A 2-semitone scoop over 80 ms** is clean at hold 80, but becomes two segments at 40.
- **A 4-semitone fall adds a note at every hold,** dry and with a band.
- **Repeated tongued notes on one pitch merge into one note at every hold.** 8 repeated 8ths at 100 bpm, each with a 20 ms tongue stop, come out as 1. Double and triple tonguing on one pitch are the commonest "fast notes" in band parts, and pitch segmentation alone cannot see them.

## 1. Where fast notes are lost (code)

| Stage | Where | What drops fast notes |
|---|---|---|
| Segmentation | `ml/adapters/swift-f0/transcribe.py:7` (`pitch_hold_ms=80.0`), with ports in `apps/android/pitch/.../NoteSegmenter.kt:23` and `apps/apple/.../OnDeviceKit/SoloTranscriber.swift` | Each note costs β = hold/16 ms. A one-semitone change needs more than 80 ms, and a *return* to the previous pitch needs twice that (swift_f0 `music.py:48-52`). A semitone trill is suppressed by design. `segment_notes` lives in the third-party `swift_f0` package pinned in `uv.lock`. |
| Consensus | `core/.../pipeline.rs:396-398` | Only clusters that contain SwiftF0 survive (`c.sources.contains("sw")`). MuScriptor and Basic Pitch cannot add a note that SwiftF0 missed. |
| Line | `core/.../lines.rs` (`MIN_DUR = 0.06`, 50 ms merge) | Notes under 60 ms are dropped. Of two onsets under 50 ms apart, the higher note is kept. |
| Quantization | `quantize.rs:17` / `quantize.py:20`: `GRIDS = {1:0, 2:.01, 4:.03, 3:.06, 6:.12}` per note, then `monophonize` | The per-note penalty makes grid 2 beat grid 3 on exact triplets (0.086 against 0.18), and grid 6 almost never wins. There is no grid 8 (32nds). Notes that snap to the same tick are dropped silently. The source comment already says "Revalidate on busier material". |
| Free time | `quantize.rs` `FREE_GRIDS = [1, 2]`, with the ranges from `plan_free_time` | Inside the ranges, 16ths and anything faster collide. |
| Slow tempo | `choose_level` (below 90 bpm with dense notes it doubles the grid) | This *helps*: 16ths and 32nds at 72–80 bpm survive. A fix to `GRIDS` must not double-count it. |
| Written durations | `pipeline.rs` `PART_HOLD_WITHIN = beat/2` | Detached notes are written as staccato 8ths. Check that fast 16ths do not turn into 8ths with rests. |
| Difficulty | `difficulty.rs:71` `merge_sixteenths` (standard and easier) | It merges 16ths by design. A trill symbol has to survive it, or be simplified on purpose. |

## 2. Independent measurements (synthetic)

**What `fastnotes/probe.py` synthesises.**
- A cornet-like additive tone with a continuous phase, so a slur has no re-attack. It has about 8 cents of low-passed pitch jitter. Without the jitter, SwiftF0 jumps an octave on a perfectly periodic C5.
- Tonguing, as a 20 ms stop and a 12 ms attack.
- A hall: RT60 2 s, with the reverb 3 dB under the direct sound.
- A band bed: sustained triads about 12 dB under the solo.

**How to read the table.** The probe runs segment → line → quantize at holds 80, 40 and 20. The script regenerates the full table; the key rows are below. Each cell is `segments/line/quantized/onset-F1`, with F1 at 50 ms on the line output.

| Case | dry h80 | hall h80 | hall+band h80 | dry h40 | hall+band h40 |
|---|---|---|---|---|---|
| control: quarters @80, tongued | 9/9/9/1.00 | 9/9/9/1.00 | 9/9/9/0.89 | same | same |
| control: 8ths @100, slurred | 9/9/9/1.00 | 9/9/9/0.89 | 9/9/8/0.89 | same | same |
| control: repeated 8ths, one pitch, tongued | **1**/1/1/0.22 | 1 | 1 | 1 | 1 |
| 16ths @120, slurred | 17/17/17/1.00 | 16/16/15/0.85 | 14/14/14/0.84 | 1.00 | 17/17/17/1.00 |
| 16ths @144, slurred | 14/14/12/0.77 | 12/12/11/0.83 | 13/13/11/0.73 | 17/17/17/1.00 | 17/17/17/1.00 |
| sextuplets @120, slurred | 11/11/**7**/0.64 | 10/9/5/0.54 | 10/10/7/0.59 | 17/17/**6**/1.00 | 17/17/**6**/1.00 |
| 32nds @96, slurred | 11/11/**5**/0.64 | 11/11/6/0.64 | 10/10/6/0.67 | 17/17/**5**/1.00 | 17/16/**5**/0.97 |
| semitone trill 8/s | **1**/1/1/0.00 | 1 | 2 | 24/24/24/1.00 | 5/5/4/0.28 |
| semitone trill 12/s | 1 | 1 | 1 | 2 | 2 |
| whole-tone trill 10/s | 3/3/2/0.15 | 3 | 2 | 24/24/**10**/1.00 | 22/22/11/0.96 |
| lip trill (partials 8–9) 12/s | 1 | 1 | 1 | 24/24/**9**/1.00 | 23/23/8/0.98 |
| shake (minor 3rd) 12/s | 2 | 1 | 1 | 24/24/**9**/1.00 | 25/25/9/0.98 |
| vibrato ±50 c 5.5 Hz (1 note) | 1 ✓ | 1 ✓ | 1 ✓ | 1 ✓ | 1 ✓ |
| vibrato ±100 c 6 Hz (1 note) | 1 ✓ | 2 ✗ | 2 ✗ | 1 ✓ | 2 ✗ |
| vibrato ±150 c 7 Hz (1 note) | 1 ✓ | 1 ✓ | 2 ✗ | **22 ✗** | 2 ✗ |
| scoop −3 st / 150 ms (1 note) | **2 segs ✗**, F1 0 | 2 ✗ | 2 ✗ | 2 ✗ | 2 ✗ |
| scoop −2 st / 80 ms (1 note) | 1 ✓ | 1 ✓ | 1 ✓ | **2 segs ✗**, F1 0 | 2 ✗ |
| fall −4 st / 200 ms (1 note) | 2 ✗ | 1 ✓ | 2 ✗ | 3 ✗ | 4 ✗ |

**Quantization alone** (`quant_probe.py`), with exact onsets on a steady grid. The Rust column is `brasscribe-core quantize`, which runs polyphonic with `auto_level`; its distinct-start counts equal Python's in every row.

| Material (24 notes) | Python, monophonic | Python, distinct starts | Rust, distinct starts |
|---|---|---|---|
| 16ths @120 | 24 | 24 | 24 |
| triplet 8ths @120 | **16** | 16 | 16 |
| sextuplets @120 | **9** | 9 | 9 |
| 32nds @100 | **7** | 7 | 7 |
| trill 10/s @120 | 10 | 10 | 10 |
| trill 14/s @120 | 8 | 8 | 8 |
| 16ths @120 inside free time | **13** | – | – |
| sextuplets @72 (grid doubled) | 16 | – | – |
| 16ths @72, 32nds @80 (grid doubled) | 24 | – | – |

Onset jitter (50 trials of 32 notes) barely changes this. 16ths hold at 1.00 up to 10 ms of jitter, and fall to 0.94 at 100 bpm and 0.85 at 140 bpm with 20 ms. Triplets stay at about 0.70 and sextuplets at about 0.35, whatever the jitter.

**Real trumpet vibrato** ([`fastnotes/real_vibrato.py`](fastnotes/real_vibrato.py)).
- The input is the 35 Iowa MIS "Trumpet.vib.ff" sustains (E3–D6), each one note, dry and convolved with a measured hall (OpenAIR Usina del Arte, `usina_main_s2_p3`).
- The table counts extra notes per sustained note after `line()`. Every extra note is a false note, and for a trill detector a false trill.

| | hold 80 (today) | hold 40 | hold 20 |
|---|---|---|---|
| dry | 0.14 | 0.49 | 1.11 |
| hall | 0.40 | 0.86 | 1.71 |

- The worst cases are **Db5 (5 notes dry at hold 80, 11 at 40)**, and C4, C5 and D5 in the hall (5–6 notes).
- **Real vibrato is already a false-note source today, and it gets worse the moment segmentation is loosened.** This is the negative control every trill change has to pass: no increase at any hold, dry or hall.

**Caveats.**
- The audio is synthetic, except the vibrato sustains and the hall.
- A brass-like spectrum with a weak fundamental made SwiftF0 jump an octave on C5–D5. The probe therefore uses a falling spectrum and jitter. Real lip trills live exactly in that C5–C6 register, so octave flips there are a live risk on real audio.
- The hall is a noise impulse response, not a measured room.
- The band bed is sustained chords, not a separated stem with artifacts.

These numbers set a lower bound on the problem. They are not a substitute for real brass.

## 3. What a plan must contain (checklist used for the review)

**Eval set**
- **Real brass is required, not optional.**
  - Candidates with ground truth: URMP trumpet stems have 158 notes with an IOI under 125 ms, mostly in `09_Jesus`, `10_March`, `20_Pavane`, `31_Slavonic`, `42_Arioso` and `43_Chorale`. For "band behind", use the solo stems plus `AuMix`.
  - These are scales, turns and ornaments: `20_Pavane` has 9 a-b-a turns. There are no sustained trills.
  - A small **hand-annotated set** is needed as well:
    - Mikkel's fast passages or trills, which bring a real hall, a real band and real separation.
    - A few own recordings of a lip trill, a valve trill and a shake.
  - Store the annotations under a new `data/eval/fastnotes/` path, never in `data/golden`.
- **Synthetic is fine as a sweep** (rate × interval × articulation × room × band), with the adversarial traps above as **must-stay-one-note** cases.

**Metrics**
- **Onset F1** at 50 ms (the repo convention), and at 25 ms for material over 12 notes/s. At 16/s a 50 ms window spans most of the 62 ms IOI, so it credits wrong notes.
- **Measure after quantization, at the score** (MusicXML note count and position). A segmentation-only F1 overstates every fix. Example: sextuplets @120 at hold 40 score F1 1.00, yet only 6 of 17 notes are written.
- **Alternation survival.** For each reference trill, the output must contain a trill (or at least 80 % of the alternations) on the right two pitches, with the right upper and lower note and the right interval.
- **False-note rate on the traps:** extra notes per second on vibrato, scoops, falls and reverb tails. The gate is zero new false notes on the must-stay-one-note set.
- **Readability:** tuplets per bar, the smallest written value, notes per beat against the difficulty mode, and a MusicXML round trip through MuseScore.
- **Regressions:**
  - `brasscribe bench cpu`, with no metric beyond tolerance.
  - The ChoraleBricks solo suites (slow legato brass) unchanged.
  - The Mikkel golden diff explained note by note, into a **new** golden directory.

**Parity, caches and fixtures**
- **Segmentation changes touch three implementations:** Python, Kotlin (`NoteSegmenter.kt`) and Swift (`SoloTranscriber.swift`), plus their parity tests. `segment_notes` is third-party (`swift_f0`, pinned). A Python-side change has to live in repo code, as a wrapper or reimplementation in `transcribe.py`, never in a patched venv.
- **Caches and fixtures.** A segmentation change changes the adapter fingerprint, so every cached SwiftF0 output is invalidated. It also changes the CI fixtures in `eval/fixtures/choralebricks-solo/` and `eval/fixtures/contours/`. Refreshing them needs `python -m brasscribe_eval.ci_data --pin`, with `eval/baselines.json` and doc 10 updated together.
- **Quantization changes touch two implementations:** `quantize.py` and `quantize.rs`, plus the conformance suite.
- **Cost on phones.** A contour oscillation detector must cost O(frames) per note, with no FFT per frame. Measure it on a phone (the S25 is available), within the existing solo-pipeline budget.

**Notation**
- **Trill mark vs written-out notes.**
  - A trill mark (`<trill-mark/>` plus `<wavy-line>`) with the upper note shown (an accidental above it) is easier for amateurs to read than 24 written-out 32nds.
  - Written-out notes are better for a measured alternation at 8th or 16th speed, and for "faithful".
- **Easier.** "Easier" should fall back to the main note with *tr*. A lip trill or shake should be marked as *shake* or *lip trill* text, not as a trill between partials that reads like a valve trill.

## 4. Review of the plan

This reviews `docs/plan/fast-notes.md` at `0be82714`, before the fixes. The plan is good.

**What the plan gets right.**
- **The diagnosis.** The stage waterfall with oracle and tracked beats covers the four loss points.
- **The segmenter stays unchanged.** `segment_notes` and its Kotlin and Swift ports are left alone, and the new work reads the contour in `music/` and the core. That avoids the fixture, fingerprint and parity churn.
- **The ablation is reported honestly.** The plan shows that the crude fix breaks the scoop and vibrato controls.
- **The gates are stated before and after, and data/golden is never modified in place.**
- **Its numbers agree with this doc** where both measured the same thing: the quantizer's own loss, and the hold/vibrato trade-off.

The new measurements below come from [`fastnotes/plateau_rule.py`](fastnotes/plateau_rule.py) and [`fastnotes/dip_rule.py`](fastnotes/dip_rule.py). Both apply F1's split rules, as the plan states them, to material that must stay one note.

### P1: fix these before building

**P1-1. F1's split rules fire on real vibrato in a hall, and on one-sided lip vibrato. The controls are too thin to see it.**
- **The pitch rule.** F1 splits after 3 frames within ±35 c of another semitone, and alternations A-B-A split at 3 frames.
  - Real Iowa vibrato in the Usina hall: 4 of 35 sustained notes get a foreign plateau, with **11 A-B-A runs, which are false trills**. Dry: 1 note, 4 A-B-A runs.
  - Synthetic vibrato *below* the note, the usual brass lip or jaw vibrato: −100 c at 5.5 Hz gives **7 A-B-A runs dry and 5 in the hall** on one 2-second note. −120 c at 6 Hz gives 7 and 3.
  - Centred ±100 c and ±120 c give 12–16 foreign plateaus per note (false 3-note wiggles).
  - Even centred ±60 c, the plan's own control width, gives 8 plateaus dry once 8 cents of natural jitter is added. The plan's claim that "vibrato never reaches 65 c" is not true of real playing: Mikkel moves more than 100 c inside 9 % of its notes (doc 11).
- **The loudness rule.** A re-tongue is a dip of at least 6 dB between peaks at least 50 ms apart.
  - The same 35 real vibrato sustains give **0 false re-tongues dry, but 36 in the hall**: A5 7, Ab5 10, Db6 5. The pitch moving through room resonances modulates the level by more than 6 dB.
  - Mikkel is a concert-hall recording, so every held note with vibrato there is at risk.
- **The controls in the plan cannot catch this.**
  - There are 9 control clips × 2 renders.
  - There is one vibrato setting (±60 c, centred).
  - No control is rendered in the room or through separation, except one vibrato and one scoop.
  - There is no amplitude vibrato.
- **Required.**
  - A trill needs evidence that vibrato cannot give: at least 6 changes, *flat* plateaus on both pitches (low within-plateau slope and variance), and a dwell ratio (time on a plateau against time in transit). Test the square-wave against sine-wave distinction explicitly.
  - Re-tongue splits need a dip whose depth is measured against the local envelope, plus an onset cue (a spectral-flux or high-frequency attack), not a level dip alone.
  - Grow the controls:
    - vibrato: centred ±60, ±100, ±150 c; one-sided −100 and −120 c; 5–7 Hz;
    - amplitude (breath) vibrato of ±3 dB at 5 Hz;
    - a scoop of −300 c over 150 ms, and a doit;
    - a rip (glissando up the partials).
  - Render every control dry, in the room and separated. Include `real_vibrato.py`, and gate on it in the hall, not just dry.
  - Add a **Mikkel false-split proxy**: of today's written solo notes of at least 300 ms, how many does F1 split? This is the only real brass + band + hall + separation check available for false notes.

**P1-2. The eval set has no real brass with a band and separation that also has ground truth.**
- `sep` is 10 sample clips over a SoundFont bed, and only 2 of them are slurred alternations. URMP runs on the solo stems only.
- **Required.** Also run the single-trumpet URMP mixes through Mega-53, then score them against the same URMP annotations: `09_Jesus` (tpt+vn), `10_March` (tpt+sax), `18_Nocturne`, `20_Pavane`. That gives real brass, real accompaniment, real separation artifacts and exact notes.
- Hand-annotate two short Mikkel fast passages (about 60 notes) under `data/eval/fast-notes-mikkel/`. Proxy counts cannot show false notes.
- Grow `sep` to include every control, and at least 8 slurred-alternation clips.

**P1-3. Readability is not gated. F3 will produce rhythms amateurs cannot read.**
- Grid 8, a collision cost, and "shift the rest to the next free slot at the finest grid" will mix 16ths, sextuplets and 32nds from beat to beat. This is worst with small0 beat errors.
- Concrete cases that must hold:
  - 16ths @140 with 20 ms onset jitter stay 16ths. Today 0.85 of them survive; they must not turn into 32nds and rests.
  - A rubato 16th run on small0 beats must not change grid more than once per bar.
- **Required.**
  - Readability metrics per clip and on Mikkel, with a gate: grid changes per bar inside a figure, the share of 32nds and tuplets, rests inside a slurred figure, and a MusicXML round trip through MuseScore.
  - A shifted note is a rhythm the player did not play. Prefer the next simpler tuplet that holds all the onsets, and mark the note with "?". Report how many notes are shifted.

**P1-4. The phone path is not the desktop path, and nothing gates it.**
- Android's `SoloPipeline.kt:61` builds `Contour(times, pitchHz, loudnessDb)` with **no confidence**, so the core gets `confidence: None`. F1's "confident frames" tuning and plateau test then run on a different signal on the phone than on the desktop. The Apple path needs the same check.
- The only phone-to-desktop parity suite, `solo-ondevice.part_files_identical_frac`, **already fails** (0.125 against 1.000 at the base commit), so a new divergence would go unseen.
- **Required.**
  - Pass the confidence through Kotlin and Swift, or define F1 without it.
  - Fix, or at least explain and re-baseline, `solo-ondevice` before F1 lands.
  - Add a conformance case that feeds the core a contour *without* confidence.

### P2: fix these during the build

**P2-1. F2 lowers `line()` to 30 ms and 20 ms for the whole solo line.**
- Alone it gains +0.02 to +0.03, and it lets reverb and separation blips through. At 30 ms, 2 contour frames make a note.
- **Required.** Apply the lower thresholds only to notes that F1 produced (inside a detected fast figure). Add a reverb-tail control: a legato leap in the hall, where the previous pitch rings on for 2–3 frames after the change.

**P2-2. Slow and legato stability on real audio.**
- The chorale gate (≥ 0.705) is good.
- **Required.** Also gate on Mikkel: outside the fast passages (the plan's own `fast_passages()`), the count of written notes changed should be about 0, each change listed.

**P2-3. F1b (Basic Pitch notes without SwiftF0).**
- Basic Pitch makes **4.69 extra notes per vibrato note** in the plan's own controls.
- **Required.** F1b needs the full P1-1 control set, in the hall and separated, before it is even measured. The default answer is no.

**P2-4. F3 and `choose_level`.**
- The plan leaves `choose_level` alone, which is right. Doubled grids below 90 bpm already rescue 16ths and 32nds (`quant_probe.py`: 16ths @72 keep 24 of 24).
- **Required.** Add a fixture showing that a doubled beat never gets grid 8 on top of the doubling, which would be a 64th.
- **Required.** Free time: allowing the full set when `FREE_GRIDS` collide is right. Check that it still writes rubato quarters and 8ths as quarters and 8ths on the URMP and chorale free-time passages (`freetime` suite unchanged).

**P2-5. F5 notation.**
- The accidental over the trill must come from the **spelled** written part: after transposition, and in the key in force at that bar. It must not come from concert MIDI numbers.
  - Example: a trill that straddles a mid-piece key change from the key plan (`keys.py`).
  - Example: an upper note that the speller writes as a sharp in one part and a flat in another (E♭ horn against B♭ cornet).
  - The upper note of an alternation of 3 semitones or more is not a trill auxiliary at all: write it as *shake*.
- The lower note as the main note is right for lip trills.
- Playback plays the main note only. Say so in the part, too, since players practise against playback.
- "Easier" with a 3rd or octave shake should read *shake*, never *tr*.

**P2-6. Mikkel golden.**
- A new sibling `data/golden/mikkel-arranged-band.fast-notes` is fine. `data/` is shared by every worktree, so:
  - write it **once**, from the final code;
  - never overwrite `mikkel-arranged-band`;
  - keep a manifest with the commit that built it.
- Repointing 30 files across three apps is a large blast radius. Move the path behind one constant per platform in the same change, so promoting it at merge is a one-line change.

### P3: nice to have

- **P3-1. Parity detail.** The circular-mean tuning and the ±35 c and 6 dB boundaries decide splits exactly at the threshold. Use the `py::` summation helpers in Rust, and add fixtures with frames exactly at 35 c and exactly 3 frames.
- **P3-2. Gate the 25 ms onset F1 as well,** for material over 12/s. At 16/s the 50 ms window is already halved by the IOI rule; report the 25 ms figure anyway.
- **P3-3. Sample sizes.** Report n (clips, notes) and a bootstrap interval next to each gate. "No increase" on 9 control clips cannot resolve 0.1 extra notes per note.
- **P3-4. `upper_share`.** Keep it as a regression metric after F1. A collapsed alternation should show the main (lower) note, which is the one F5 writes.

## 5. Reviews of the implementation

### Harness and frozen suite (`0be82714`, `9eb6b87a`)

**Rerun.** I checked out `9eb6b87a` in a detached worktree and ran `brasscribe bench fast-notes` with that tree's own `eval/` and `music/`. All 24 metrics reproduce the baseline exactly, so the suite passes.

**Findings.**
- **The error path is correct.** On `repeat-i0-t150-s8-tongue-samples`, small0 finds a single beat, and `arrange_layers_song` raises `ValueError: need at least two beats`. The bench scores that clip as empty, which counts as a loss. It is not dropped, so the result is not biased.
- **The same input fails in production today (P3, not new).** A short, fast solo take with one tracked beat fails the whole transcription instead of falling back to a free-time grid.
- **The frozen suite covers less than the plan's own gates.** It freezes `samples` and `room` only. `sf2`, `sep` and the room/separated controls are not in CI yet.
  - Once the P1-1 controls exist, freeze the room and separated controls too, so that "no increase in extras" is gated in CI, not only in the doc.
- **Improvements beyond tolerance fail the gate** (`status = improved`), as for every suite. Each fix step must update `baselines.json` and the plan doc in the same commit.

### F3, F1, F2 and the confidence plumbing (`634a6cf7..206fe1a3`)

**What I reran.** Everything ran in a detached worktree at `206fe1a3`:
- the music tests (248 pass) and `cargo test -p brasscribe-core` (all pass);
- `brasscribe bench cpu`;
- my own adversarial clips ([`fastnotes/adversarial_clips.py`](fastnotes/adversarial_clips.py)), tracked with the fast-notes harness and scored with its bench, at the base `9eb6b87a` and at the head;
- the Mikkel arrangement, with and without the dense quantizer.

**Bench cpu: 16 pass, 5 fail.**

| Suite | Result | Assessment |
|---|---|---|
| `fast-notes` | fails only on improvements | Written recall 0.32 → 0.55 (oracle) and 0.27 → 0.50 (small0). Fall extras 1.63 → 0.13, scoop extras 0.75 → 0.25. The baseline refresh is still to come. |
| `mikkel-golden`, `solo-ondevice` | fail | Expected until the new golden lands. |
| **`readability`** | **fails, regressed** | See P1-b. |
| **`solo-instruments`** | **fails, regressed** | `q_hit` (the share of wrong notes marked "?") drops from 0.438 to 0.333 for trumpet, and from 0.463 to 0.333 for flugelhorn. Fewer wrong notes are flagged on the chorale stems. |

**Adversarial clips, written stage, base → head** (oracle beats):

| Case | Result |
|---|---|
| Sextuplet run, slurred (dry / band / hall) | 0.06 → **0.44 / 0.39 / 0.44** |
| 16ths @144, slurred (band / hall) | 0.75 → 1.00, and 0.56 → 0.75 |
| Scoop −300 c (dry, line stage) | 2 extras → 0 |
| Wide, one-sided and ±150 c vibrato controls | **no increase anywhere** |
| Semitone trill 12/s, slurred, one glide frame per change | 0.04 → **0.04**: not split at all |
| Whole-tone trill 10/s, slurred | 0.00 → 0.15: split, but see P1-a |

The measured Usina hall position is too wet for any stage, at base and head alike. It is not a regression.

#### P1-a. A split names every note a semitone off when SwiftF0's label is a compromise pitch

- **The code.** `split_note` (`onsets.py`, and `onsets.rs:178`) sets `delta = tracker pitch − main plateau` and adds it to every plateau.
- **Why that goes wrong.** On a collapsed alternation, SwiftF0's DP labels the note with a pitch between the two plateaus, because its μ minimises the capped error across both. The split then moves every note.
- **Examples.**
  - My whole-tone trill C5–D5 is written **C♯5–D♯5**: every note is wrong, with the timing right.
  - the proposed tests reproduce it for M2, m3 and m2 alternations: {68, 70} instead of {67, 69}, {73, 75} instead of {72, 74}, {69, 72} instead of {67, 70}.
- **Why the tests miss it.** The existing `test_slurred_trill_splits_into_its_notes` passes the note in at the lower pitch (67), so it never sees this.
- **Fix.** Name a plateau by its own semitone, `s` (tuned). Carry over only an octave: `delta = 12 · round((pitch − main) / 12)`. Then rerun `alt_kept` and `upper_share`: some of today's "kept" alternations may be on the wrong pitches.

#### P1-b. The dense quantizer fails the existing readability gate on Mikkel

The `readability` suite checks the Mikkel arrangement against `qa/reports/mikkel-golden-readability.json`. The Solo Cornet part:

| | base | head | head with `dense=False` (F1 + F2 only) |
|---|---|---|---|
| written solo notes | 694 | 877 | 718 |
| tuplet % | 0.3 | **14.7** | 0.2 |
| 16th % | 38.4 | **53.0** | 39.9 |
| printed accidentals (`<accidental>`) | 50 | **349** | 64 |
| tie-stub % | 1.8 | 3.9 | 1.4 |
| gate violations | 0 | 4 (16ths, tie stubs, accidentals 34.8 % > 25, one colour-only "?") | 1 (16ths 39.9 > 35) |

**Findings.**
- **Printed accidentals explode.** In bar 4 (D major, written) the pitches are the same as at base (B5 C♯6 C♯6 D6), but the head prints ♯ on both C♯s, the tied continuation included. The part's divisions go to 10080 per quarter once sextuplets and 32nds appear.
  - Look at music21's `makeNotation` accidental pass on these parts. This is the Python reference writer, so check the Rust writer against it too.
- **Rubato breaks the grid** ([`fastnotes/dense_probe.py`](fastnotes/dense_probe.py)).
  - A 16th run with ±10 % tempo drift puts 25 % of its beats on sextuplets and changes grid every other beat. With 15 ms of jitter as well, 36 % of beats become sextuplets.
  - Triplet 8ths with 15 ms of jitter: half the beats are written as 16ths.
  - `SWITCH` = 0.5 is weaker than the weighted snap error. Within a figure, prefer keeping the previous beat's grid and shifting the note ("?") over switching. That means `SWITCH` ≥ `COLLIDE`, or a whole-figure grid choice.
- **Gate.** The `readability` suite must pass, with its baseline refreshed only after the causes above are fixed. Tuplet % on the Mikkel Solo Cornet should stay near base.

#### P2

- **P2-a. Real semitone trills are not split.** With one glide frame between 5-frame plateaus (dwell 0.78–0.83), F1 does not split, because span 1 needs dwell ≥ 0.85. The bench's 12 ms crossfade synthesis is easier than real lip or valve trills.
  - Calibrate the threshold on real trills (own recordings), or require dwell ≥ 0.85 only when fewer than about 8 changes are present.
  - The real-vibrato set shows how far the threshold can drop safely.
- **P2-b. `q_hit` regressed on the chorale stems** (see the table). Recalibrate or explain before the baseline moves.
- **P2-c. Where Mikkel's new notes come from.** F1 alone adds 24 notes (13 inside notes that base held for a quarter or longer). The dense quantizer adds 159 more by keeping collisions. The provisional 93-note Mikkel reference is built from contour plateaus, the same signal F1 splits on. It cannot tell true notes from false splits, so do not use it as a gate. Hand-annotate instead (P1-2 of the plan review).

**Proposed tests**, now on main as `test_split_names_plateaus_by_their_own_semitone`, `test_split_keeps_an_octave_correction_only` and `test_semitone_trill_with_a_transit_frame_splits` in [`music/tests/test_onsets.py`](../../music/tests/test_onsets.py), and `test_rubato_sixteenths_keep_one_grid` in [`music/tests/test_quantize_dense.py`](../../music/tests/test_quantize_dense.py). At `206fe1a3`, 5 split-pitch cases, the octave case, the one-glide-frame semitone trill and the rubato-grid case fail.

### Fixes (`af9aadc7`, `4659b0c4`, golden sibling rebuilt at 11:48)

**Reran:**
- the music tests (252 pass), `cargo test` (pass), and my proposed tests (**8 of 8 now pass**);
- the dense probe, `bench cpu`, the adversarial clips, and the Mikkel readability check.

**P1-a (split pitches): fixed.**
- My whole-tone trill C–D is now written C–D.
- Written recall on that trill went from 0.00 to **0.75 dry, 0.70 in a hall, and 0.70 under the band bed**.
- The semitone trill under the band bed went from 0.04 to 0.83.

**P1-b (dense quantizer): mostly fixed.**
- Solo Cornet tuplets went from 14.7 % back to **0.3 %**. Printed accidentals went from 349 back to **66**. Tie stubs are at 1.3 %.
- Rubato 16ths stay on one grid (0 switches per beat).
- **Still failing:** the `readability` gate, on `sixteenth_pct` **63.6 % > 35 %** (base 38.4 %). The Solo Cornet now has 616 16ths, against 309 at base, and 866 solo notes against 694.
  - If those notes are real, faithful mode is simply denser.
  - If they are not, they are false notes on the only real brass-band recording.
  - Nothing measures which: the provisional Mikkel reference is circular (P2-c).
  - `solo_diff.py` finds 28 new onsets inside notes that base held for a quarter or longer. Seven of them are a semitone from the held pitch, the typical vibrato or bend split.

**Side effects of the stricter "evidence" rule for tuplets.**
- Sextuplet runs lost part of the earlier gain: dry and hall 0.44 → 0.33, band 0.39 → 0.11 (base 0.06).
- Triplet 8ths with 15 ms of jitter are still written as 16ths in half the beats.
- The slurred semitone trill without a band still does not split (0.04).

**`bench cpu`: 18 pass, 3 fail.**

| Suite | Result | Why |
|---|---|---|
| `mikkel-golden`, `solo-ondevice` | now pass | They read the rebuilt sibling golden, written one minute after `af9aadc7`. |
| `readability` | fails | `sixteenth_pct`, see above. |
| `solo-instruments` | fails | `q_hit` 0.438 → 0.333 (trumpet) and 0.463 → 0.333 (flugelhorn). Not addressed. |
| `fast-notes` | fails | `ctl-vibrato.extra` 0 → 0.05. This comes from the newly frozen separated vibrato clip (SwiftF0's own extras, identical at every stage). It is a baseline refresh, not a code regression. |

**Other checks.**
- On my adversarial vibrato and scoop controls, no case got worse.
- One octave-leap tune in the measured hall lost one of 8 notes (0.25 → 0.12). That render is unusable at base too.

## 6. Verdict (superseded by the final check in §5)

**Ship with fixes.** The direction is sound, and the measured gains are real and independently reproduced:
- Runs and whole-tone trills come through in the hall and under a band.
- The quantizer no longer silently drops fast notes.
- Python and Rust match.
- `data/golden` was not modified in place.
- The phone contour now carries confidence.

**Required before merge:**
1. **The readability gate passes on Mikkel,** or the owner explicitly accepts a higher 16th share for the faithful Solo Cornet. That acceptance needs evidence: hand-annotate two Mikkel fast passages (about 60 notes) plus the 28 new onsets inside held notes, and show that most of the added notes are real.
2. **`solo-instruments` `q_hit`** is recalibrated or explained. Fewer wrong notes marked "?" is the opposite of F4's intent.
3. **The `fast-notes` baselines** are refreshed, with the separated-vibrato note, in the same commit as the doc numbers.
4. **The sibling golden** is rebuilt from the final commit once items 1–3 land, with the manifest naming that commit.

**Follow-ups (not blocking):**
- Semitone trills without a band bed.
- Triplets with jitter.
- Win back the sextuplet recall that the evidence rule gave up.
- F5 (trill notation) stays optional. Build it only with the written-part accidental rule from P2-5.

### Final check (`59ad5309`)

**What I reran, at `59ad5309` (before the rebase onto main `740bb417`):**
- The music tests (252 pass), `cargo test` (pass), and my proposed tests (8 of 8 pass).
- **`brasscribe bench cpu`: 21 of 21 pass.**
  - `readability` now runs all three difficulties.
  - `solo-instruments` has the new `q_missed` gate.
  - `mikkel-golden` matches the sibling golden byte for byte, rebuilt from `e688670f`, the last code change.
- My adversarial clips: no regression beyond the earlier numbers. Trills: C–D is written 0.75 dry and 0.70 in a hall and under a band. The scoop control is clean.

**The earlier items are closed, with one owner decision left.**

**"?" marks: fixed.**
- The drop in `q_hit` is explained: there are fewer wrong notes left to mark.
  - Trumpet: 16 wrong notes → 3. Flugelhorn: 17 → 8.
  - Recall and F1 rise for every instrument.
- The new gated `q_missed` (wrong notes without a "?") falls: trumpet 0.93 → 0.25, flugelhorn 0.87 → 0.62.

**Bend and vibrato splits: reduced.**
- Semitone splits inside notes that base held for a quarter or longer: 7 → 5.
- New onsets inside held notes: 28 → 26.
- Solo notes: 866 → 860, against 694 at base.

**Readability: passes, but only with a threshold change that needs the owner's approval.**
- Standard and easier pass the unchanged thresholds.
- Faithful passes only because the Solo Cornet limit for `sixteenth_pct` was raised from 35 to **65**, for that one part.
- The current value is 63.6 %, so the new limit was set just above the output.
- This is acceptable only if the owner listens to the bars in `docs/plan/fast-notes.md` §7.4 and agrees that the added 16ths are played. There is still no hand-annotated ground truth on Mikkel.

**Not verified by me:**
- The Windows and Apple PlaybackLevel failures, which the report attributes to main's new band SoundFont.
- The engine `scutil` failure.

**Verdict: ship**, on two conditions:
1. The owner signs off the §7.4 bars, which is the price of the 65 % limit.
2. The full tier is rerun after the rebase onto `740bb417`. It must show that the LUFS failures clear against main's sound pack and that conformance stays 413/413.

**Follow-ups (not blocking):**
- Semitone trills with no band behind.
- Triplets with timing jitter.
- The sextuplet recall that the evidence rule gave back.
- F5, trill notation.
