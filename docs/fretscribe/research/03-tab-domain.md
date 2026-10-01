# 03 — Tab domain: what "correct, readable, idiomatic tab" means

Audience: designers (display) and engineers (fingering step, export). Scope: guitar 6/7/8-string, bass 4/5, ukulele (incl. re-entrant), mandolin, 5-string banjo.

The report works with three layers throughout:

- **Pitch/time layer**: what the machine hears, meaning onsets, pitches, durations, and possibly techniques.
- **Fingering layer**: the deterministic step that picks string and fret.
- **Rendering layer**: tab, optional standard notation, and exports.

Most "wrong tab" complaints come from the fingering layer, even when every pitch is right. Most "ugly tab" complaints come from the rendering layer.

---

## 1. Display conventions

### 1.1 Tab alone vs tab + standard notation

| Mode | When | Notes |
|---|---|---|
| **Tab + standard notation (linked)** | Default for guitar and bass on tablet/desktop. This is the published-book norm (Hal Leonard, Guitar Pro default). | The standard staff sits above and the tab below, joined by a brace or bracket. One underlying note list drives both. Editing either one updates both. |
| **Tab with rhythm** (stems/beams under or through the tab) | Default on phone and whenever standard notation is hidden. | Tab without rhythm is only acceptable as ASCII export. On screen it drops the one thing a recording-derived transcription knows well: timing. |
| **Tab only, no rhythm** | ASCII export only. | See §6.5. |
| **Standard notation only** | Optional, for readers who don't use tab. | Guitar sounds an octave lower than written: treble clef with a small 8 below (`G2` / "treble 8vb"). Bass uses bass clef, also sounding an octave lower. Ukulele and mandolin use plain treble clef at pitch. Banjo uses treble 8vb. |
| **Slash / rhythm notation** | Strummed passages with chord names. | Slash noteheads show the strum rhythm. Accent and up/down marks go above. This is the idiomatic answer for "rhythm guitar with chords". Don't write out a six-note chord on every eighth note unless the voicing or rhythm really changes. |

Rhythm-in-tab rules:
- Stems go **down** from below the tab staff. This is the Guitar Pro and alphaTab default.
- Beam by beat, following the time signature (e.g. 6/8 in groups of three eighths).
- Rests appear in the tab rhythm line.
- Half notes use a stem with no beam. Some styles circle the fret number, which is the older convention, so pick one.
- Whole notes get no stem.
- On a linked staff pair, rhythm under the tab is optional and off by default, because the standard staff already carries it.

### 1.2 String order and labels

- **The top line is the highest-pitched string (string 1), and the bottom line is the lowest.** This is universal for modern tab: guitar, bass, uke, mandolin, and US-style banjo.
  - Exception: old Seeger-style banjo tab is inverted. Never produce it, but flag it on import if detected.
- One line per string, or per course for mandolin.
- String-name labels (e.g. `E A D G B e`, bottom to top) go at the left of the first system, and only there.
  - Use lowercase `e` for the high E when the tuning repeats a letter.
  - For non-standard tunings, show labels on **every system's first line**, or at least the first system of each page.
- Header block above the first system: instrument, tuning (e.g. `Drop D: D A D G B E`), capo (`Capo 3`), and tempo.

### 1.3 Tuning and capo

- **Fret numbers are relative to the capo.** With capo 3, the open string is `0`, and a note on the 5th actual fret is written `2`.
  - This is universal practice in songbooks, Guitar Pro, and Ultimate Guitar. Players read chord shapes, not absolute frets.
- The header says `Capo 3`. The standard-notation staff shows **sounding** pitch.
- Chord names above the staff: show **shape names** (what you finger) by default. Offer an option for sounding names, or both, as `C (Eb)`.
  - Songbooks do both. Shape names are the more common default for capo songs aimed at players.
- Drop and alternate tunings go in the header, plus string labels on each system.
  - If a string is tuned below standard, the fingering step must know its real open pitch. For example, the low string in Drop D is D2, so D2 = fret 0 on string 6.
- Partial capos (e.g. Kyser drop-D capo) are rare. Model them as a per-string capo fret (`capo: [0,2,2,2,2,0]`) so the data model doesn't need to change later. Display can wait.

### 1.4 Chord diagrams and chord names

- Chord names above the staff (standard notation, or tab if tab-only), aligned to the beat where the chord changes.
- Chord diagram (fretbox) conventions:
  - Vertical strings, lowest string on the left.
  - The nut is a thick top line. Otherwise a starting-fret number (`5fr`) sits to the right of the first fret.
  - Dots for fretted notes; `o` for open; `x` for muted.
  - A barre is a curved line or a bar across the dots.
  - Optional finger numbers 1–4 and T (thumb) inside or below the dots.
- Diagrams are usually shown once, in a "chords used" grid at the top of the song, and optionally again above the first occurrence. Don't repeat them on every change: clutter.
- The diagram must match the voicing the fingering step chose. If the tab says `x32010`, the diagram must too. A generic C-major diagram above a different voicing reads as a bug.
- Instrument diagram widths: guitar 6 (7/8), bass rarely uses diagrams, uke 4, mandolin 4, banjo 5.
  - On banjo, the 5th string is usually drawn short, or omitted when unused.

### 1.5 Structure

- Bar numbers go at the start of every system, plus rehearsal letters or section labels (`Intro`, `Verse 1`, `Chorus`) boxed above the staff.
  - Section labels are the main navigation aid for players. Worth auto-suggesting from structure analysis, but user-editable.
- Repeats:
  - Repeat barlines, volta brackets (1st/2nd endings), D.S./D.C./Coda/Fine.
  - Multi-bar rest counts for tacet sections.
  - Simile marks (`%`) for repeated rhythm-guitar bars.
- **Auto-folding identical bars into repeats is a v2 feature.** It needs a note-for-note, fingering-for-fingering identity check. Otherwise it hides transcription differences between repeats.

### 1.6 Glyph-level details

| Item | Convention |
|---|---|
| Multi-digit frets (10–24) | Written as one number centred on the line. The column width grows to fit, so never split digits across positions. In ASCII, pad other strings with `-` so columns align. |
| Ties | A tied-into note is shown in parentheses `(5)` in tab, or omitted after the first note. The tie arc is drawn in standard notation. Guitar Pro shows the parenthesised number and alphaTab follows it. Pick parentheses and apply them consistently. |
| Rests | Standard rest glyphs in the rhythm line or the standard staff. In tab-only mode, rests go centred in the tab staff. |
| Dead / muted notes | `x` on the string (percussive, no pitch). |
| Ghost notes | Fret number in parentheses `(5)`, which is the same glyph as a tie continuation. Disambiguate by context: a tie is always preceded by the same string and fret. Some engravers use smaller type for ghosts. |
| Let ring | `let ring - - - ┐` bracket above the tab, over the span. |
| Palm mute | `P.M. - - - ┐` bracket above the tab. |
| Accents / staccato | Standard articulation glyphs, shown on the notation staff, or above tab if tab-only. |
| Dynamics | On the notation staff; rarely on tab-only. |
| Tempo | ♩ = 120 at the top; tempo changes where they happen. |
| Time signature | On the tab staff too. In tab-only it is commonly drawn large and spanning the staff; alphaTab and Guitar Pro both render it. |

### 1.7 Extended-range layouts

- **7-string guitar** (B1 E2 A2 D3 G3 B3 E4): 7 lines. 8-string (F#1 or E1 low) uses 8 lines. Line spacing is the same as 6-string, so the staff simply gets taller.
- **5-string bass** (B0 E1 A1 D2 G2): 5 lines. 6-string bass adds a high C3.
- **4-string bass**: 4 lines.
  - Bass tab often has **no standard notation** in rock and metal material, and rhythm under the tab is then mandatory.
  - Jazz and legit bass material uses bass clef first, with tab optional.
- **Line count always equals the tuning array length.** Never hard-code 6.

---

## 2. Technique notation

Each technique below is placed on three separate capability axes, so the scope does not overpromise:

- **R** = render, edit, and export (the data model and glyph exist, and the user can add it).
- **D** = the machine can **auto-detect** it from audio with useful reliability.
- **U** = user-annotate only.

Current audio research shows detection works for slides, bends, and percussive hits (TART, 2026). Most other techniques are "render + user-annotate" in v1.

### 2.1 Guitar (also applies to bass where relevant)

| Technique | Tab glyph | Notes | R | D | Priority |
|---|---|---|---|---|---|
| Hammer-on / pull-off | Slur arc over the two fret numbers, labelled `H` / `P` above | Direction is inferred from pitch (up = H, down = P). Needs same string, so it **constrains fingering**: both notes must be on one string. | v1 | v1 (partial: legato onset without pick attack is detectable-ish) | v1 |
| Slide (legato / shift) | `/` up, `\` down between frets. `S` over a line in notation | Slide-in from below / out downwards: `/5`, `5\`. The slide constrains both notes to the same string. | v1 | v1 | v1 |
| Bend (with amount) | Curved arrow up from the fret number with amount: `½`, `full`, `1½`, `¼` | Amount in semitones: ½ = 1 semitone, full = 2. The notated fret is the **unbent** fret, and the target pitch is implied. The fingering step must pick the fret below the heard pitch. **Pitch detection must not "correct" a bend to the target fret.** | v1 | v1 (pitch glide) | v1 |
| Release | Arrow back down, `B-R` or line down | Bend then release to the original pitch. | v1 | v1 | v1 |
| Pre-bend | Vertical arrow before the note, `PB`, fret in parentheses | Silent bend, then struck. Hard to tell apart from a fretted note at the target pitch. Detectable only from bend-release context, or never. | v1 | U | v1 render / U |
| Vibrato | `~~~~` wavy line above the tab | Wide vibrato uses a thicker or double wave. | v1 | v2 (pitch-modulation depth/rate) | v1 |
| Tapping | `T` above the note (right-hand tap), often with circled fret | Guitar Pro uses `T`. Common in metal and prog. | v1 | U | v1 render |
| Natural harmonic | `<12>` (angle brackets), `N.H.` / `Harm.` | Written at the touched fret (12, 7, 5, 4…). Sounding pitch ≠ fret pitch, so the fingering step must know the harmonic series. | v1 | v2 | v1 render |
| Artificial harmonic | `A.H.` with fretted note plus touch point (e.g. `5 (17)`) | Two-number notation. | v2 | U | v2 |
| Pinch harmonic | `P.H.` above, fret number | Sounding pitch is a partial of the fretted note. | v1 | v2 | v1 render |
| Tap harmonic | `T.H.` | Rare. | later | U | later |
| Palm mute | `P.M.` bracket | Very common in rock/metal rhythm. Should show up as a timbre-classifier target. | v1 | v2 | v1 |
| Muted / dead note | `x` | Percussive. Detection is feasible (TART "percussive hits"). | v1 | v1 | v1 |
| Strum direction | `⊓` (down), `V` (up) above the staff; or arrows | Detection from onset sweep direction across strings. That signal is weak from a mono mix, so treat it as later research. | v1 | later | v1 render |
| Arpeggiate / rake | Wavy vertical line before the chord | | v1 | v2 | v1 render |
| Fingerpicking p-i-m-a | Letters above or below the notes (p = thumb, i, m, a; `c`/`ch` = little finger) | Classical and fingerstyle. Left-hand fingers use 1–4. Circled numbers ①–⑥ mean the **string** in standard notation. | v2 | later | v2 |
| Tremolo picking | Slashes through the stem (1–3 = 8th/16th/32nd) | In tab, use a rhythm-line slash. Don't write 32 fret numbers. | v1 | v1 (repeated onsets at the same pitch → collapse) | v1 |
| Whammy bar dive / return | `w/bar` with contour line and semitone amounts | | v2 | v2 | v2 |
| Grace notes | Small fret number before the main note, with slash | Often slide or hammer grace. | v1 | v1 | v1 |
| Trill | `tr` + wavy line; alternate fret in parentheses | | v2 | v2 | v2 |
| Fade in / volume swell | `<` hairpin or swell glyph | | later | later | later |
| Let ring | Bracket | See §1.6. Also affects notated durations. | v1 | v1 (sustain overlap) | v1 |

### 2.2 Bass specifics

- **Slap `T` (thumb) and pop `P` (pluck)** above the tab.
  - Conflict: `P` is also "pull-off" in guitar tab. Guitar Pro and alphaTab use `S` for slap and `P` for pop on bass, with pull-offs written as slurs. Pick `S`/`P` for bass and keep pull-off as slur-only there.
  - Priority: v1 render, v2 detect. The attack spectrum of slap and pop is distinctive.
- Ghost notes (parenthesised) and dead notes (`x`) are very frequent in funk bass. v1.
- Harmonics (natural at 12/7/5) are common. v1 render.
- Hammer/pull/slide as on guitar.
- Tab without standard notation, with rhythm under the tab, is the norm for rock/pop bass.

### 2.3 Ukulele

- Strumming dominates, so **chord names + diagrams + slash rhythm with strum arrows** are the primary output for most uke users. Note-by-note tab is the secondary output.
- Fingerpicking uke tab uses the same technique set as guitar, minus palm mute. Hammer/pull/slide are enough.
- Priority v1: strum rhythm view (slashes + `⊓`/`V`) and chord diagrams.

### 2.4 Mandolin

- **Tremolo picking** is *the* signature technique (bluegrass, Italian style). Show slashes on stems. v1.
- Double stops are common.
- Chop chords (off-beat muted chord) are notated as chord name + `x` or staccato slash. v2.
- Cross-picking pattern annotations: later.

### 2.5 5-string banjo

- **Rolls** (forward, backward, forward-reverse, alternating thumb): notated as the individual picking notes in tab, with **right-hand finger letters T / I / M** above or below.
  - Bluegrass Scruggs style repeats 8-note roll patterns over chords. Reading tab note-by-note is the norm.
  - Showing a roll-pattern name ("forward roll") is optional sugar. v2.
- Hammer-on / pull-off / slide as guitar, with the same `h` / `p` / `sl` letters. Very frequent. v1.
- Choke (a bend on banjo): v2.
- Melodic and clawhammer styles: clawhammer uses `T`/`I` or `M` plus "drop-thumb" notation. Later.
- Most banjo tab has rhythm under the tab (eighth-note beams) and no standard notation. Banjo readers rarely read standard notation.

### 2.6 v1 technique set (render + edit + export)

- Hammer-on, pull-off
- Slides (legato, shift, in/out)
- Bend / release / pre-bend with amount
- Vibrato
- Natural and pinch harmonics
- Palm mute
- Dead notes, ghost notes
- Let ring
- Tapping
- Grace notes
- Tremolo picking
- Strum direction
- Arpeggio
- Slap/pop
- Ties

v1 **auto-detect** subset:
- Slide, bend/release (from pitch glide), vibrato (maybe)
- Dead notes / percussive hits
- Legato H/P (low-confidence, off by default)
- Tremolo-collapse
- Let-ring from sustain overlap

Everything else: user-annotated.

---

## 3. Instrument specifics

### 3.1 Tuning tables (sounding pitch, string 1 first)

| Instrument | Standard tuning (string 1 → n) | Tab lines | Notation clef |
|---|---|---|---|
| Guitar 6 | E4 B3 G3 D3 A2 E2 | 6 | Treble 8vb |
| Guitar 7 | E4 B3 G3 D3 A2 E2 B1 | 7 | Treble 8vb |
| Guitar 8 | E4 B3 G3 D3 A2 E2 B1 F#1 | 8 | Treble 8vb |
| Bass 4 | G2 D2 A1 E1 | 4 | Bass 8vb |
| Bass 5 | G2 D2 A1 E1 B0 | 5 | Bass 8vb |
| Ukulele (re-entrant, "high G") | A4 E4 C4 **G4** | 4 | Treble |
| Ukulele (linear, "low G") | A4 E4 C4 G3 | 4 | Treble |
| Baritone uke | E4 B3 G3 D3 | 4 | Treble 8vb |
| Mandolin | E5 A4 D4 G3 (courses) | 4 | Treble |
| 5-string banjo (open G) | D4 B3 G3 D3 **G4** (5th, short) | 5 | Treble 8vb |

### 3.2 Ukulele re-entrant G

- The tab line order is **string order, not pitch order.** The bottom line is the G4 string, which is *higher* than C4 on the line above it. The tab looks identical for high-G and low-G, and only the tuning header differs.
- **Fingering consequence:** "lowest string = lowest pitch" is false.
  - The fingering step must work from an explicit per-string open-pitch array, never from the string index.
  - With re-entrant tuning, G4 can be played open on string 4 *or* at fret 3 on string 3 (E4+3). Campanella (let-ring across strings) fingerings deliberately use this. Scale runs that alternate strings for ringing overlap are idiomatic uke and baroque-guitar practice.
- Range: C4 is the lowest available pitch on high-G uke. Notes below C4 from the recording are **out of range**. Flag them, or transpose by octave with a visible marker. Never drop them silently.

### 3.3 Mandolin courses

- 4 courses of paired unison strings, tuned in fifths like a violin. **One tab line per course.**
- Fingering treats a course as one string.
- Fifths tuning means a hand span of ~4 frets covers a full fifth. The standard "one finger per fret" box is 4 frets wide; 5-fret stretches (e.g. 0-2-4-5-7 patterns) are usually handled by the 4th finger reaching.
- Open strings are used a lot; bluegrass favours open-string drones.

### 3.4 Banjo short 5th string

- The 5th string starts at the **5th fret** and is tuned G4 (open G tuning).
- **Numbering convention:** the 5th string's frets are numbered as on the full neck.
  - Open = `0`. The first fret *on the 5th string* is written **`6`**, not `1`.
  - A capo'd 5th string (railroad spikes or a 5th-string capo, commonly at 7 for A tuning) keeps full-neck numbering, e.g. open = `7`, if the tab is written absolute. Many books instead treat it as `0` relative to its capo.
  - This is a real inconsistency across sources. Store the absolute fret and make the display a setting.
- The fingering step must treat the 5th string as having **no frets 1–5** (unavailable). Its open pitch (G4) is higher than strings 2–4, so it is re-entrant, similar to uke.
- Standard tunings to support: open G (gDGBD), double C (gCGCD), G modal/sawmill (gDGCD), open D (f#DF#AD).

### 3.5 Bass tab conventions

- 4 or 5 lines, rhythm under the tab, often with no standard notation.
- Common drop tunings: Drop D (D1 A1 D2 G2); B E A D G for 5-string; half-step down.
- Hand span on bass is narrower in frets than on guitar because the scale is longer (34" vs 25.5"). See §4.2.
- Idiomatic bass fingering favours **one-finger-per-fret in the low region with pivoting** (Simandl uses 1-2-4 over a 3-fret span in low positions).
- Frequent open-string use, especially E and A as pedals.
- Octave shapes (root + 2 strings up + 2 frets up) are idiomatic.

### 3.6 Drop and alternate tunings

- Drop D (DADGBE) and Drop C/B/A for metal are common. Also DADGAD, Open G (DGDGBD), Open D, Open E, Nashville (high-strung), and half-step / whole-step down (Eb standard).
- Tuning **detection** is valuable. If the lowest heard pitch is D2 on a guitar, suggest Drop D, or whole-step down if everything else also fits.
  - Tuning can be inferred by trying candidate tunings and minimising fingering cost plus out-of-range notes.
  - The user always confirms.
- Drop tunings make **one-finger power chords** (0-0-0 or 5-5-5 across the three low strings) idiomatic. The fingering step's chord-shape cost must reward these.

### 3.7 Left-handed players

- **Tab is not mirrored.** Left-handed players read the same tab: the top line is still the highest string, and fret numbers are identical.
- **Chord diagrams** *may* be mirrored (high string on the left) as a per-user display preference. Several apps offer this (e.g. Ultimate Guitar, Chordify). Default is not mirrored.
- **Fretboard visualisations** (if the app shows a neck) should mirror for lefties.
- Upside-down players (right-hand-strung guitar flipped, e.g. Albert King style) invert the string order physically. Tab stays standard. Low priority for special handling.
- Finger labels (p-i-m-a, 1–4) are unchanged.

---

## 4. Fingering / playability rules

### 4.1 Problem shape

For each onset group (single note or chord), the candidates are:
- all `(string, fret)` assignments where `open_pitch[string] + fret == pitch`,
- with `0 ≤ fret ≤ max_fret[string]` and, on banjo string 5, `fret == 0 || fret ≥ 6`,
- with no two notes of a chord on the same string (for mandolin, one note per course).

A chord of *k* notes produces a set of **voicings**. The search space is a sequence of candidate states, one per onset group.

**Deterministic solver: Viterbi / DP over states.**
- A state is a voicing plus an estimated **hand position** (index-finger fret).
- Cost = Σ per-state cost + Σ transition cost.
- This is the classic formulation: Sayegh 1989 "optimum path" and Radisavljevic & Driessen 2004 path-difference learning. Later Burlet & Hindle and many others use variants.
- It is exact, fast (states × transitions per onset is small), explainable, and reproducible, which suits "deterministic".
- Enumerated voicings per chord are typically < 50 for 6-string guitar, so no heuristic search is needed.

### 4.2 Hand span: measure in millimetres, not frets

- Fret *n* is at distance `d(n) = L · (1 − 2^(−n/12))` from the nut, where L = scale length (guitar 628–650 mm, bass 864 mm, uke soprano 330 mm / tenor 430 mm, mandolin ~350 mm, banjo ~660 mm).
- The stretch between the lowest and highest fretted fret in a hand position is `d(hi) − d(lo)`.
- Resulting guitar comfort spans:
  - **4 frets at positions 1–5** (≈ 110–120 mm on a 648 mm scale) is the comfortable "box".
  - 5 frets at 1–5 is a stretch (acceptable, costed).
  - 6 frets is a stretch only above ~fret 7.
  - Around fret 12+, a 5–6 fret span becomes comfortable.
- A single mm threshold (≈ 100–110 mm comfortable, ≈ 140 mm hard limit for an average adult hand, both tunable) yields correct behaviour on every instrument without per-instrument fret rules.
- The same rule automatically makes uke and mandolin spans wider in frets and bass narrower. This is what players actually do.

### 4.3 Cost terms (what the fingering step should obey)

Per state:
1. **Span**: penalty rising steeply above the comfortable mm threshold; infeasible above the hard limit.
2. **Height on the neck**: mild penalty for high frets, relative to the instrument's usual register. Prefer lower positions all else equal, **but** see "Exceptions" below.
3. **Open strings**: a *small bonus* in open-position material (folk, pop, bluegrass, uke). A *penalty* when the passage sits high and an open string would need a large jump.
   - Open strings free a finger, so they're "free" for span purposes. They count as fret 0 without constraining hand position.
4. **Chord-shape playability** (per voicing):
   - Max 4 fretting fingers, where a barre counts as one finger covering ≥ 2 strings at the lowest fret of the shape and adjacent strings on the same fret.
   - Muted strings inside a voicing need a damping finger, so penalise interior `x`.
   - Prefer **known shapes** (CAGED forms, power chords, triads on adjacent string sets). A small lookup of idiomatic shapes per instrument gives a strong bonus. This is the single biggest win for chord readability.
   - Thumb-over for the bass note (fret on string 6) is an idiomatic exception: allow at small cost in "pop/folk" style.
5. **Physical impossibility**: two notes on one string/course; a bend on an open string; a slide or legato that crosses strings.

Per transition:
1. **Position shift**: cost ∝ mm moved by the index finger, with extra cost when there is **no time** to move (short inter-onset interval). Shifts during rests or on open strings are cheap.
2. **String crossing**: small cost per string skipped. It matters for speed; picking hand economy.
3. **Keep a phrase on one string** when the phrase is legato (H/P/slide detected or annotated) or is a vibrato/bend line. Technique constraints are **hard**: a bend needs a fretted note, a slide pair shares a string, and H/P pairs share a string.
4. **Consistency**: the same passage repeated should get the same fingering. Cache by pitch/rhythm n-gram and reuse, or add a cost for deviating from the fingering chosen at the previous occurrence.
5. **Sustain / let-ring**: if a note is still sounding (overlapping duration) when the next note starts, the next note **must be on a different string**. It also cannot be on a string the hand must mute. This is often the deciding constraint for fingerstyle arpeggios.

### 4.4 When humans deliberately choose otherwise

These are the cases a naive "lowest position" rule gets wrong, and they justify a *style* parameter plus user override:
- **Timbre**: the same pitch sounds warmer on a thicker string higher up. Blues and jazz solos often sit at frets 5–12 on strings 2–4 rather than open position. Classical scores mark this with circled string numbers.
- **Bends and vibrato** need fretted notes and prefer strings 1–3 in positions 5–15. A solo with bends pulls the whole phrase up the neck.
- **Campanella / cross-string ringing** (uke, harp-style guitar, banjo melodic style): consecutive scale notes deliberately on different strings, with higher frets on lower strings. This violates "minimise frets".
- **Riff/pattern shape preservation**: metal and rock riffs are usually played as one moveable shape. A riff transposed up a fourth moves to the next string set at the same frets, even when open strings could do it.
- **Open-string pedals / drones** in drop tunings, DADGAD, and bluegrass. The pedal stays open while the melody moves high, so the span rule must treat open strings as free.
- **Pickup/slide approach**: players often slide into a note from 2 frets below on the same string. The fingering must keep that string.
- **Artist fidelity**: users transcribing a known recording want "how the artist played it", which can be unusual (e.g. Hendrix thumb-over). This is only resolvable from audio timbre (string identification) or a user override.

Implication: expose a **style preset** (open/folk, rock/riff, lead/solo, classical, bass, bluegrass, campanella). The preset re-weights costs, and the per-note override pins a string. The DP then re-solves around pinned notes: pins become hard constraints and neighbours reflow.

### 4.5 Literature and reported accuracy

Different tasks and datasets; **do not compare these numbers across rows.**

| Work | Task | Data | Reported result |
|---|---|---|---|
| Sayegh 1989 | Symbolic → tab, optimum-path (Viterbi/DP) | — | Foundational DP formulation; no benchmark. |
| Radisavljevic & Driessen 2004 | Symbolic → tab, DP with learned transition costs | Small | Path-difference learning of cost weights. |
| Tuohy & Potter 2005–06 | Symbolic → tab, genetic algorithm + ANN fingering | Small tab corpus | GA outperforms simple heuristics on playability. |
| Radicioni et al. 2004 | Fingering as constraint satisfaction / graph search | — | Cognitive-constraint model. |
| Heijink & Meulenbroek 2002 | Human study of left-hand fingering choice | Classical guitarists | Players minimise hand-span / stretch and favour lower positions. This is the empirical basis for span cost. |
| Barbancho et al. 2012 | Audio → tab, HMM with fret/string states + playability | Classical/acoustic guitar | HMM over fingering states from audio. |
| Burlet & Hindle 2013–15 | Symbolic → tab, A*/graph search; DNN fingering | — | Graph-search baseline often reused as "A*". |
| **TabCNN** (Wiggins & Kim, ISMIR 2019) | **Audio → tab**, frame-level, 6 × 21 softmax | GuitarSet (acoustic, hexaphonic-annotated) | Multipitch F = 0.826, **tab F = 0.748**. |
| SynthTab (Zang et al., 2023–24) | Audio → tab, pre-training on synthesised audio from DadaGP tabs | Synth + GuitarSet/EGDB | Improves cross-dataset generalisation of TabCNN-style models. |
| **Fretting-Transformer** (2025) | **Symbolic MIDI → tab**, T5 encoder-decoder | DadaGP, GuitarToday, Leduc | Pitch acc 97.23 %, **tab acc 68.56 %**. With overlap correction: 99.92 % / **72.15 %**. Beats A* and Guitar Pro's auto-tab. |
| Kaliakatsos-Papakostas et al. (SMC 2022) | Symbolic → tab, ML with stretch constraints + augmentation | Tab corpora + augmented | Augmentation helps even monophonic cases (no single headline figure checked). |
| Hsu et al., 2026 (arXiv 2607.26440) | Symbolic → tab, note-event tokens + pitch-validity constrained decoding | DadaGP, Leduc | Improves tab accuracy over Fretting-Transformer (abstract only; figures not verified). |
| **TART** (Gupta et al., 2026) | Audio → MIDI → technique classifier → audio-conditioned T5 fingering | GuitarSet, EGDB (+ noisy variants) | String-fret Tab F1 71.8 % (given MIDI). **End-to-end Tab F1 54.08 %**. Detects slides, bends, percussive hits. |
| Noise2Fret (Simionato & Bigo, ISMIR 2026) | Audio → tab via diffusion, with hand-span and positional auxiliary losses | GuitarSet, GOAT | Outperforms baselines (abstract only; figures not verified). |

**Datasets:**
- **GuitarSet**: ~3 h acoustic, hexaphonic pickup annotations of string and fret; CC BY 4.0. The standard audio → tab eval set.
- **EGDB**: electric guitar, DI + amp renders.
- **GOAT** (ISMIR 2025): 5.9 h DI electric guitar, Guitar Pro tabs + tokens, many techniques; ~29.5 h after amp augmentation.
- **DadaGP**: 26,181 Guitar Pro songs + tokenizer; CC BY 4.0 **by request**. The tabs transcribe copyrighted songs, so use it for **research/eval only, never bundled**.
- **Leduc**: François Leduc's guitar tab collection, used as a clean small set.

**What ~70 % tab agreement means for engineers:**
- Symbolic-to-tab agreement with human tabs tops out around 70 %. This is mostly a **ceiling set by ambiguity**, not error: many fingerings are equally valid, and human tabs themselves disagree.
- So:
  1. Evaluate the fingering step on **(a) playability violations** (span, impossible chords, broken technique constraints): target 0 hard violations. Evaluate it separately on **(b) agreement** with GuitarSet / GOAT ground truth, as a secondary number.
  2. Use GuitarSet string labels as a regression test for the DP cost weights. Tune weights (optionally learned, à la Radisavljevic & Driessen) against agreement.
  3. End-to-end audio → tab is ~50–75 % tab F in research. The pitch layer dominates the error budget. The deterministic fingering step is the *easy, reliable* part and should stay deterministic and explainable.
  4. Learned models (Fretting-Transformer, TART's fingering stage) are useful as **baselines to beat or match**, not required for v1.

**String identification from audio** (timbre: the same pitch on different strings sounds different) exists in research (e.g. Abeßer 2012; Kehling et al. 2014; TabCNN learns it implicitly). It is weak on mixed or amped audio.
- v1: purely playability-based fingering.
- v2: optionally feed a per-note "string likelihood" as a soft cost term.

---

## 5. Showing uncertainty without clutter

Two different kinds of "unsure" need **different treatments**.

### 5.1 Pitch/timing uncertainty (the note may be wrong)

> **Superseded in the design** (`design/fretscribe/brand/brand.md`, Colour): the doubt mark is a "?" above the tab column with the numeral in the doubt colour, never an outline, circle or parentheses around the numeral, because those already mean ghost notes, ties and half notes in tab. MusicXML carries doubt as a note colour plus the confidence in `<other-notation>`, never as parentheses.

- Mark the note itself: a **dotted or dashed outline, or a hollow/lighter-weight fret numeral**, plus a small marker in the standard-notation notehead (e.g. a grey ring). Also show a subtle tick above the bar.
- **Not colour-only.** Colour can reinforce (amber), but the shape must carry the meaning, both for colour-blind users and for B/W PDF.
- A threshold slider ("show marks below X % confidence") lets users dial clutter. The default shows only the worst ~5–10 % of notes.
- Tap or hover shows alternatives: "E4 (62 %) · D#4 (21 %) · ghost/none (10 %)", plus play-the-snippet.
- Bar-level summary: a thin confidence strip under the system (a heat line), for scanning a long song. Toggleable.
- Onset/duration uncertainty (e.g. a triplet vs a dotted rhythm): mark the beam or rhythm group, not each note. Offer rhythm alternatives on tap.

### 5.2 Fingering ambiguity (the note is right; the string/fret is one of several valid choices)

- **No mark by default.** Multiple valid fingerings are normal, not errors. Marking them would put marks on most notes.
- On tap: show the alternatives ("also: 3rd string fret 9 · 4th string fret 14"), and let the user **pin** a string.
  - Pinning re-solves the DP locally, so neighbours reflow to stay playable.
  - Pinned notes get a tiny, persistent pin indicator in edit mode only.
- Optional "fingering heat" mode for power users: notes where the chosen fingering's cost is close to the runner-up get a faint underline.
- Out-of-range notes (below the lowest open string, above the max fret) are a **third category**. They are flagged strongly (red `!`), because no valid fingering exists. Common cause: wrong tuning or wrong instrument chosen, so link to "change tuning".

### 5.3 Export behaviour

> **Superseded in the design** (`design/fretscribe/brand/brand.md`, Colour): the doubt mark is a "?" above the tab column with the numeral in the doubt colour, never an outline, circle or parentheses around the numeral, because those already mean ghost notes, ties and half notes in tab. MusicXML carries doubt as a note colour plus the confidence in `<other-notation>`, never as parentheses.

- **PDF**: pitch-uncertain marks optional (default off for "clean print", on for "review print").
- **MusicXML**: map pitch uncertainty to `<notehead parentheses="yes">` or a `color` attribute, *plus* a note-level `<other-notation>` / processing-instruction carrying the confidence.
  - Other software will just see coloured noteheads, which degrades gracefully.
  - Never encode uncertainty by changing pitch or fret values.
- **MIDI**: no marks (optionally put them in a separate track as marker meta-events).
- **ASCII**: optionally a `?` line under the tab columns.

---

## 6. Interop

### 6.1 MusicXML tab encoding

**Tab staff:**
- `<clef><sign>TAB</sign><line>5</line></clef>`.
- `<staff-details>` with `<staff-lines>n</staff-lines>` plus one `<staff-tuning line="k"><tuning-step/><tuning-alter/><tuning-octave/></staff-tuning>` per string. Line 1 is the **bottom** line, i.e. the lowest string.
- Optional `<capo>`.
- The `show-frets="numbers|letters"` attribute allows letter tab, relevant only for lute.

Per note:
- `<notations><technical><string>s</string><fret>f</fret></technical></notations>`.
- String 1 = highest string.
- Keep `<pitch>` **correct and sounding-consistent with the transposition**. Readers that ignore tab still read pitch.

**Linked notation + tab:**
- Either **one part with two staves**: `<staves>2</staves>`, staff 1 treble-8vb, staff 2 TAB. Notes are duplicated per staff with `<staff>` numbers, or MuseScore-style exported as two parts.
- Or two separate parts.
- MuseScore exports linked staves as one part with two staves. Guitar Pro exports tab + notation similarly.
- Test import in MuseScore 4, Guitar Pro 8, and Dorico. Behaviour varies.

**Techniques under `<technical>`:**
- `<hammer-on type="start">H</hammer-on>` / `<pull-off>`, paired with `<slur>`.
- `<bend><bend-alter>2</bend-alter><release/></bend>`, or `<pre-bend/>`.
- `<harmonic><natural/>|<artificial/></harmonic>`.
- `<tap>`, `<fingering>` (left hand), `<pluck>` (p-i-m-a), `<up-bow>`/`<down-bow>` for strum direction by convention.

Elsewhere:
- `<slide>` / `<glissando>` in `<notations>`.
- `<ornaments><wavy-line>` (vibrato).
- `<notehead>x</notehead>` for dead notes.
- `<notehead parentheses="yes">` for ghosts.
- Palm mute and let ring as `<direction>` with `<words>P.M.</words>` plus dashes. Palm mute is the `<other-technical>` "palm mute" text in MusicXML 4.0 practice. Varies by app.
- The MusicXML tutorial itself says bend and harmonic support is "sporadic" across software.

**Capo:**
- The spec says `<capo>` "changes the open tuning of the strings specified by `<staff-tuning>` by the specified number of half-steps".
- Reading: `<staff-tuning>` = **uncapoed** tuning, and `<fret>` = **capo-relative**. Pitch = staff-tuning + capo + fret.
- **Needs a round-trip test**: export capo 3, then import in MuseScore 4 and Guitar Pro 8 and check both the displayed frets and the playback pitch. Exporters are known to disagree.
- Fallback if importers mishandle it: bake the capo into `<staff-tuning>` and add a text direction "Capo 3". Frets stay capo-relative either way.

Chords:
- `<harmony>` for chord names.
- `<frame>` for chord diagrams: `<frame-strings>`, `<frame-frets>`, `<frame-note>` with `<barre>`.

Bottom line: MusicXML is the **primary interchange export for v1**. It is lossy for some techniques but universal.

### 6.2 Guitar Pro (.gp / .gpx / .gp5)

- **GP3/4/5** (`.gp3/.gp4/.gp5`): binary, reverse-engineered, stable.
- **GP6** (`.gpx`): container with a proprietary compression (BCFZ).
- **GP7/8** (`.gp`): a **zip containing `Content/score.gpif`** (XML, "GPIF").
- **There is no public spec** from Arobas. All support is reverse-engineered (TuxGuitar, alphaTab, PyGuitarPro).

Libraries:
- **alphaTab** (MPL-2.0): imports GP3–8, MusicXML, Capella, alphaTex. **Exports GP7 (since 1.2) and alphaTex (since 1.7).**
- **PyGuitarPro** (LGPL-3.0): reads and writes GP3/4/5 only. GPX/GP7+ are out of scope.
- **TuxGuitar** (LGPL): reads and writes GP3–5 and imports GP6/7-ish. Java.

Feasibility:
- **Import**: GP files are what users already have, but import isn't needed for recording → tab. It *is* needed for a "compare my transcription to a tab I have" feature. v2 via alphaTab.
- **Export**: GP7 via alphaTab's exporter is feasible, and it preserves techniques much better than MusicXML because GP's technique model is the de facto guitar standard. v2.
- **Legal**: file-format interoperability via reverse engineering is broadly lawful for interop (EU Software Directive art. 6, US interop fair use). Don't use "Guitar Pro" branding beyond nominative ("Export to Guitar Pro format"). No licence from Arobas is needed to read or write the format; that's the TuxGuitar/alphaTab/MuseScore precedent.

Licensing notes for a phone app:
- **MPL-2.0** (alphaTab) is file-level copyleft. You can ship it in a closed app if modifications to *alphaTab's own files* are published. Fine for iOS and Android.
- **LGPL-3.0** (PyGuitarPro, TuxGuitar) clashes with iOS static linking and App Store terms in practice (relinking requirement). **Avoid shipping LGPL code in the iOS app.** Server-side or desktop dynamic-link use is OK.
- **DadaGP / tab-site content**: never bundle. The tabs are transcriptions of copyrighted works.

### 6.3 alphaTab / alphaTex

- alphaTab is the most complete open **tab renderer**: tab + standard notation, linked staves, full GP technique set, rhythm under tab, chord diagrams, playback via SoundFont, and a web/.NET/Kotlin (Android) target. MPL-2.0.
  - Strong candidate for **the on-screen renderer on web/desktop**. Evaluate mobile performance (it runs in WebView; there is a Kotlin/Android build).
- **alphaTex** is a text markup for tab: e.g. `:4 3.3 5.2 {h} 7.2 | ...`, meaning duration, fret.string, and effects in braces.
  - Useful as a **debug/test fixture format** and as a human-editable export.
  - Its syntax has changed between versions (a major overhaul in 1.7), so pin the version.

### 6.4 MuseScore, Verovio

- **MuseScore 4** (GPL-3.0): good tab (linked staves, most techniques, GP import). Useful as the **reference importer** for MusicXML round-trip tests. GPL means don't embed; drive it as an external tool in CI (`mscore -o out.pdf in.musicxml`) for export-validation only.
- **Verovio** (LGPL-3.0): MEI/MusicXML engraving to SVG. **Initial** guitar/staff-like tab support landed in 6.1.
  - Treat it as immature for guitar techniques. It is not a v1 renderer for tab-heavy output. It may be fine for the standard-notation half.
  - Also LGPL, with the same iOS caveat (it's often compiled to WASM, which is arguably dynamic, but get a legal read).

### 6.5 ASCII text tab

This is the conventions users expect from Ultimate Guitar and similar sites.

```
Tuning: Drop D (D A D G B E)   Capo: none   Tempo: 96
[Verse]
e|-----------------|-----------------|
B|-----------------|-----------------|
G|-----------------|---------7b9r7---|
D|-0-0-5-0-0-7-0---|-0-5h7-----------|
A|-0-0-5-0-0-7-0---|-0---------------|
D|-0-0-5-0-0-7-0---|-0---------------|
   PM - - - - -|
```

- String names at the left.
  - Lowercase `e` for high E.
  - Tuning letters reflect the actual tuning (`D` bottom for Drop D).
  - Re-entrant uke uses `A E C G` top to bottom.
- `|` at barlines, with the same bar width across strings. **Every string line of a system has identical character length.**
- Multi-digit frets widen the column on *all* strings (pad with `-`). Chords are vertical columns.
- Technique letters:

  | Letters | Meaning |
  |---|---|
  | `h` | hammer-on |
  | `p` | pull-off |
  | `/` `\` | slides |
  | `s` | slide, unspecified |
  | `b` | bend, e.g. `7b9` = bend from 7 to fret-9 pitch |
  | `r` | release |
  | `pb` | pre-bend |
  | `~` | vibrato |
  | `x` | dead |
  | `( )` | ghost |
  | `<12>` | natural harmonic |
  | `PH` | pinch harmonic |
  | `t` | tap |
  | `PM` | palm mute (line under the tab) |
  | `\|>` or `S` / `P` | bass slap/pop line |

  Add a legend at the end listing the letters used.
- Rhythm is not encoded. Optionally add a rhythm line above (`q e e s s`) or spacing proportional to duration (1 dash ≈ 1/16th at fixed resolution).
  - **Default: proportional spacing** at one column per 16th, and wider for tuplets. It reads best.
- Wrap at ~80 characters per system; section headers in `[brackets]`; chord names on a line above the tab, aligned to columns.

---

## 7. Prioritised scope

### v1 (credible, playable, exportable)

Display:
- Tab with rhythm under the tab.
- Linked standard-notation staff (toggle).
- Slash-rhythm + chord-name view for strummed material.
- Header: instrument, tuning, capo, tempo.
- String labels; bar numbers; section labels.
- Repeat barlines and voltas (user-placed).
- Multi-digit frets, ties, rests, dead/ghost notes, let ring, palm mute.
- 6/7/8-string guitar, 4/5-string bass, uke high-G/low-G, mandolin.
- Phone layout: tab-only with rhythm, 1–2 bars per line, with pinch/zoom.

Instruments and tuning:
- Per-string open-pitch arrays.
- Standard + common alt tunings (Drop D/C/B, Eb, DADGAD, Open G/D/E).
- Capo with capo-relative frets.
- Tuning suggestion from range; user confirms.

Fingering:
- Viterbi/DP with mm-based span, shift cost with timing, open-string handling, chord-shape table, and let-ring/sustain constraint.
- Technique hard constraints (bend/slide/H-P same string).
- Repeat-consistency.
- Style presets (≥ 3: open/folk, rock/riff, lead).
- Per-note string pin with local re-solve.

Techniques:
- **Render/edit**: the §2.6 set.
- **Auto-detect**: slide, bend/release, dead notes, tremolo collapse, let-ring.

Chords:
- Chord names above the staff.
- Chord diagrams matching the chosen voicing.
- "Chords used" grid.

Uncertainty:
- Pitch-uncertain mark (shape + colour, threshold slider).
- Fingering alternatives on tap only.
- Out-of-range flag.

Export:
- MusicXML (tab + notation, techniques that map cleanly, capo per §6.1, validated by round-trip in MuseScore).
- PDF (clean / review variants).
- MIDI.
- ASCII text tab.

Eval harness:
- GuitarSet (audio → tab) and a symbolic set (GuitarSet MIDI → tab agreement).
- Playability-violation count as a hard gate.

### v2

- GP7 export (alphaTab exporter); GP3–8 import (compare against user-supplied tabs).
- 5-string banjo (short-string constraint, T/I/M finger letters, roll display, gDGBD/gCGCD tunings, configurable 5th-string numbering).
- Auto-detect: vibrato, palm mute, harmonics (natural/pinch), slap/pop, legato H/P on by default once validated, strum direction if feasible.
- Artificial harmonics, whammy bar, trills.
- p-i-m-a and left-hand finger numbers (auto-suggested for fingerstyle preset).
- Auto-fold repeated sections into repeats/simile after an identity check.
- String-identification soft cost from audio timbre.
- Campanella, classical, and bluegrass presets.
- Left-handed mirrored chord diagrams and fretboard view.
- Partial capo display; baritone uke; 6-string bass.
- alphaTex export.

### Later

- Clawhammer banjo notation, mandolin chop / cross-picking annotations.
- Tap harmonics, volume swells, fade-in; complex whammy contours.
- Learned fingering model (Fretting-Transformer-style) as an optional alternative to the DP. Only if it beats the DP on agreement *without* raising violations.
- Multi-instrument band scores (guitar + bass + uke parts from one mix).
- Lute/letter tab (`show-frets="letters"`), 12-string (paired courses like mandolin), Dobro/lap steel (bar notation), pedal steel.
- MEI/Verovio output once its tab support matures.

---

## Sources

- MusicXML 4.0 — staff-details: https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/staff-details/
- MusicXML 4.0 — capo: https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/capo/
- MusicXML 4.0 — tablature tutorial: https://www.w3.org/2021/06/musicxml40/tutorial/tablature/
- MusicXML 4.0 — technical element: https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/technical/
- TabCNN (Wiggins & Kim, ISMIR 2019): https://archives.ismir.net/ismir2019/paper/000033.pdf
- GuitarSet: https://guitarset.weebly.com/ , https://zenodo.org/records/3371780
- Fretting-Transformer (2025): https://arxiv.org/abs/2506.14223
- Note-event tokenization + constrained decoding (2026): https://arxiv.org/abs/2607.26440
- TART technique-aware transcription (2026): https://arxiv.org/abs/2609.11904
- Noise2Fret playability-aware diffusion (ISMIR 2026): https://arxiv.org/abs/2608.30854
- GOAT dataset (ISMIR 2025): https://arxiv.org/abs/2509.22655 , https://zenodo.org/records/17706552
- DadaGP (ISMIR 2021): https://arxiv.org/abs/2107.14653 , https://github.com/dada-bots/dadaGP
- SynthTab: https://arxiv.org/abs/2309.09085
- Electric guitar tones / EGDB robustness: https://arxiv.org/abs/2405.14679
- ML MIDI → tab with augmentation (SMC 2022): https://arxiv.org/abs/2510.10619
Classic fingering literature below is cited from domain knowledge; DOIs/links were not re-checked for this report and should be verified before quoting.

- Sayegh, "Fingering for String Instruments with the Optimum Path Paradigm", Computer Music Journal 13(3), 1989: https://doi.org/10.2307/3680010
- Radisavljevic & Driessen, "Path Difference Learning for Guitar Fingering Problem", ICMC 2004: https://quod.lib.umich.edu/i/icmc/bbp2372.2004.018
- Heijink & Meulenbroek, "On the complexity of classical guitar playing: functional adaptations to task constraints", J. Motor Behavior 34(4), 2002: https://doi.org/10.1080/00222890209601952
- Tuohy & Potter, "A genetic algorithm for the automatic generation of playable guitar tablature", ICMC 2005: https://quod.lib.umich.edu/i/icmc/bbp2372.2005.083
- Barbancho et al., "Automatic transcription of guitar chords and fingering from audio", IEEE TASLP 20(3), 2012 (HMM over fingering states)
- Burlet & Hindle, "Isolated guitar transcription using a deep belief network", PeerJ CS 2017: https://peerj.com/articles/cs-109/
- alphaTab (MPL-2.0): https://github.com/CoderLine/alphaTab , exporter docs: https://alphatab.net/docs/guides/exporter
- PyGuitarPro (LGPL-3.0, GP3–5): https://github.com/Perlence/PyGuitarPro
- TuxGuitar: https://en.wikipedia.org/wiki/TuxGuitar
- Verovio (tab support since 6.1): https://www.verovio.org/ , https://book.verovio.org/toolkit-reference/input-formats.html , https://github.com/rism-digital/verovio/issues/4452
- MuseScore handbook — tablature: https://musescore.org/en/handbook/4/tablature
- SMuFL (tab/fretted-instrument glyph ranges): https://www.w3.org/2021/03/smufl14/tables/fretted-instrument-techniques.html
