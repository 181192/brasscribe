# Fretscribe UX research: what fretted-instrument players need

Status: desk research, September 2026. Evidence base: app-store listings and reviews, vendor documentation, player forums (Mandolin Cafe, Banjo Hangout, Ukulele Underground, MuseScore, Harmony Central, Ultimate Guitar, TalkBass), trade press and one arXiv paper. There are no interviews or usability tests behind this report. Vendor pages are marked **(vendor)**. Points not directly sourced are tagged **(inference)** or **(domain convention)**.

---

## 0. The thesis in five sentences

1. For fretted instruments, a transcription has **two independent kinds of error**: *wrong pitch* (a detection error) and *right pitch in the wrong place* (the string/fret choice doesn't match how the player would play it). Competitors blur the two, and users hate the second kind the most, because the tab "looks wrong" even when every note is right.
2. Most whole-song wrongness comes from **global settings** (tuning, half-step-down, off-A440 reference pitch, capo, octave, high/low-G ukulele), not from individual notes. The app has to settle these *before* anyone edits a single note.
3. Players almost never want a finished score. They want **a practice object**: the recording plus the tab, looped and slowed, with a cursor they can follow from a metre away while their hands are on the instrument.
4. The phone is on a stand or on the floor and **the hands are busy**. Every practice control needs a non-touch route (pedal/keyboard, large targets, possibly voice), and the screen needs to be legible at arm's length.
5. The tab-world interchange format is **Guitar Pro (.gp/.gp5)**, not MusicXML. The brief lists MusicXML/PDF/MIDI only; that is a gap (see R19).

---

## 1. Personas and jobs-to-be-done

| # | Persona | Core job ("When I…, I want to…, so I can…") | What's fretted-specific | Kills the product for them |
|---|---|---|---|---|
| P1 | **Ear-learner beginner** (6–18 months in, learns from YouTube/UG) | When a song I love has no good tab, I want a playable tab of the riff so I can learn it tonight. | Needs *playable* positions (open/first position where possible), chord names, capo shown as "capo 2", not transposed frets. Can't yet tell a wrong note from a wrong position. | Unplayable stretches; frets 9–14 rendered as open strings on a higher string (a documented Guitar2Tabs complaint); jargon; paywall at 20 s. |
| P2 | **Gigging cover-band player** | When the setlist gets a new song on Tuesday for Saturday, I want the parts (riff, solo, fills) fast, in the band's key and tuning, so I can learn them and bring a chart to rehearsal. | Eb/drop tunings, capo vs transpose, "the band plays it a whole step down". Wants a clean one-page chart or print. Stage use: pedal-driven, dark mode, big type. | Wrong tuning assumption producing a whole tab of wrong frets; no print/PDF; tiny tab on a phone at arm's length. |
| P3 | **Bassist** | When I learn a song, I want the bassline (not the guitar) with the right octave and string, so I can play along with the record. | Phone mics roll off the low end: low E on a 4-string is 41 Hz and low B on a 5-string is 31 Hz, so detection errors are often **octave** errors. Ghost notes, slides and slaps matter. 5-string players choose position vs the low B. | Octave-wrong lines; transcribing the kick drum or the guitar instead; 4-string-only assumptions. |
| P4 | **Teacher** | When a student brings a song, I want a clean, correct-enough tab of the exact part in minutes, which I can annotate, simplify, slow down and send to them. | Needs position/fingering control ("do this in 5th position"), simplified arrangement, left-hand fingering numbers, a shareable link or PDF, and teaching-level variants. | Can't edit quickly; exports that break in Guitar Pro/MuseScore; no way to share a practice-ready loop. Soundslice owns this job today. |
| P5 | **Songwriter capturing ideas** | When I stumble on a riff while noodling, I want to capture it *and how I played it* (tuning, capo, position), so I can reproduce it next week. | Voice memos lose the *how*: which tuning, capo, and where on the neck. The riff is often in an odd tuning. | More than 2 taps to record; forced to set up a project first; loses the raw audio. |
| P6 | **Fingerstyle / classical player** | When I transcribe an arrangement, I want polyphony (bass + melody + inner voices) with proper voice separation and standard notation with fingering. | Classical readers want **standard notation first** with string numbers (circled 1–6), LH fingers 1–4 and RH p-i-m-a; tab is secondary. Fingerstyle players want tab + rhythm + let-ring. | Single-voice output; no rhythm in tab; no notation. |
| P7 | **Left-handed player** | I want the app to respect my orientation where it matters (fretboard diagrams, chord boxes) and *not* where it doesn't (the tab staff). | **Non-obvious:** lefties on left-handed guitars read tab exactly like righties, because the low string is still nearest their face. Mirrored *diagrams* help; a mirrored *tab staff* is the wrong default (a minority want it, so offer it as an opt-in). Upside-down players (right-handed guitar flipped, not restrung) are the exception: their string order is reversed. | A "lefty mode" that mirrors the tab by default; or no lefty option at all for fretboard/chord views. |
| P8 | **Ukulele / mandolin / banjo hobbyist** | I want tunes from recordings (fiddle tunes, folk, pop uke covers) in the tab my community reads. | Ukulele: re-entrant **high-G vs low-G** changes which string a note goes on. Mandolin: fifths tuning, paired courses, strong standard-notation culture (fiddle crossover). 5-string banjo: short 5th drone string starting at fret 5, written as the *bottom* line of tab in the usual convention; fretted 5th-string notes are numbered by the neck's fret position (so its first fret reads 6), not from the string's own nut **(domain convention, unverified)**; rolls and fast patterns. | The guitar model forced onto their instrument; banjo 5th-string frets numbered wrong; high-G tabs with notes on the wrong string. |

**Jobs ranked by frequency (inference, from which features competitors monetize and which reviews complain):** (1) learn a specific part of a specific song, (2) practise it along with the record at reduced speed, (3) capture my own idea, (4) produce a chart or tab to give someone, (5) a full engraved score. The product should be designed in that order; engraving is last.

---

## 2. Physical context: what's different when there's a guitar in your lap

| Situation | Consequence for UX |
|---|---|
| **Both hands on the instrument.** The fretting hand is on the neck and the picking hand is over the strings. Removing either breaks the loop. | Every practice action (play/pause, loop again, back one bar, slower/faster, next section) must work **without touch**: Bluetooth page-turner pedals (AirTurn and similar pedals send keystrokes and are already supported by Songsterr, UG, forScore), hardware keyboard shortcuts (Songsterr has Space, L, S, C, N), and optionally voice. The default mapping must be sensible for 2-button pedals. |
| **Phone on a music stand, desk, mic clip or floor**, 50–150 cm away. | Tab digits must be legible at arm's length: large type, a "stage/practice" density mode, a **fixed cursor with scrolling score** (Guitar Pro's 2025 mobile prototype adds exactly this), and no small chrome. GP mobile users complain the bottom bar "cannot be hidden and wastes too much space" and that tab on iPhone is "one horizontal line… virtually unusable". |
| **Portrait vs landscape.** | Tab is a horizontal medium. Landscape phone = 2–3 systems; portrait phone = a narrow strip. Support both, but practise mode should default to whichever gives ≥2 bars of lookahead. (inference) |
| **Capture with the phone mic** in a bedroom, rehearsal room or living room. | Acoustic guitar is fine. Amplified electric is loud, distorted and reverberant. Bass lows are rolled off by phone mics. Other instruments bleed in. Yousician documents room noise and echo, its own playback feeding back into the mic, and trouble hearing low E/A strings. So capture needs input metering, a "too quiet/too loud/too noisy" preflight, and an **external input** path (USB-C/Lightning interface, iRig-style adapters). |
| **Playback and capture at the same time** (play along while recording). | The phone speaker bleeds into the mic. Either require headphones for simultaneous use, or treat them as separate modes. (Yousician evidence) |
| **Tuning drifts; capo moves; tuning changes mid-session** (drop D for one song, Eb for the next). | Tuning and capo must be **per-song settings that are always visible** (a header chip: "Eb std · capo 2") and changeable in one tap, with an explicit choice between "keep the sound, recompute the frets" and "keep the frets, change the sound". Guitar Pro's capo dialog exposes exactly this choice ("Keep the fingering"). A built-in tuner matters: Fender Play reviewers complain it forces a separate tuner app. |
| **Looping and slowing down is the practice.** | Looping must be **gapless** (Soundslice's "perfect looping" is a selling point). Tempo steps must be fine: GP mobile's 10% steps get criticized as jumping 180→162 BPM. Slowed audio must sound acceptable: GP mobile playback is "mediocre below 50%". A speed trainer (auto-ramp) is expected (Soundslice, Guitar Pro). |
| **Short sessions, repeated**: 20 minutes a day on the same 8 bars. | The app must reopen **exactly where you left off**: song, loop region, speed, and view. (inference) |

---

## 3. Competitive teardown

### 3.1 Map of the field

| Product | Core promise | Transcribes audio? | Tab editing | Practice tools | Exports | Loved | Hated |
|---|---|---|---|---|---|---|---|
| **Songsterr** | Huge library of multi-track tabs with realistic playback | Yes, recently: "AI tabs" from a YouTube link | Web tab editor (E key); community edits | Speed, loop (L), count-in (C), metronome (N), mute/solo, pitch shift, tuner, chords with capo | GP, MIDI (Plus); **no MusicXML** | Synced playback, accuracy of popular tabs, keyboard shortcuts | Free tier limits (5–20 s of audio on mobile), pop-ups; **AI edits overlaying human tabs** ("destroying the original tablature"); missing notes |
| **Ultimate Guitar (+ Tab Pro)** | Largest chord/tab library | No | Limited | Autoscroll, transpose (paid), Tab Pro playback, left-handed chord diagrams | Print | Library size, chords for everything, lefty mode | Paywall on the top results, unskippable 30 s ads, subscription traps, wrong free tabs |
| **Guitar Pro (desktop + mobile)** | The tab editor; .gp is the de-facto tab format | No | Desktop: full. Mobile: weak ("writing tabs is abysmal", one track, can't edit existing files) | Speed trainer, loop, fretboard view (lefty option), tunings for 3–10 strings, capo with "keep fingering" | GP, MusicXML, MIDI, PDF, audio | Desktop editor, format ubiquity | Mobile display (one-line tab), poor mobile sound, coarse tempo steps. New mobile app announced at NAMM 2025 adds fixed cursor, dark mode, speed trainer |
| **Klangio Guitar2Tabs** (closest direct competitor) | Audio → tab | Yes (live, file, YouTube) | Editor for paid subscribers; piano roll view | Playback, metronome/count-in | PDF, MIDI, MusicXML, GP5 | Clean single-guitar input works "close to a competent human on a first pass" | **Fret positions**: high-fret notes shown as low frets on a higher string, "not playable". Struggles with 3+ note chords, distortion, palm mutes, bends. Can't separate instruments. 20 s free limit; ticket pricing; 3.4★ on iOS |
| **Moises** | Stem separation + practice | Chords only (plus stems) | Edit chords | Stems, pitch/tempo, count-in, metronome, setlists, **capo mode**, Easy/Medium/Advanced chord voicings | Audio | Stems and practice loop, capo mode that keeps the key | Wrong chord roots sometimes |
| **Chordify** | Chords for any song | Chords only | Chord edits | Loop, transpose, capo | Print (paid) | Speed of "good enough" | Missing/wrong chords; defaults to triads, missing 7ths, sus and dim chords |
| **Yousician / Fender Play** | Gamified or video lessons | No (Yousician listens to judge you) | No | Guided practice | — | Structure for beginners | Mic misrecognition marks correct playing as wrong; Fender Play has no tuner and teaches only song excerpts |
| **Soundslice** | Notation synced to real recordings | No (manual transcription tool) | Excellent web editor (bends, slides, harmonics, tapping), imports GP/MusicXML/PDF | Gapless loop, drag-to-loop, slowdown, speed training, fretboard, transpose, multi-recording sync, keyboard shortcuts | MusicXML, etc. | Teachers: "the single most valuable tool in my teaching toolbox" | Paid for teachers; manual work |
| **Transcribe! / AnyTune** | Human transcription aids | Assistive only (spectrum view) | No tab | Slowdown, markers, multiple saved loops, pitch shift | — | Markers and loops, "incredibly useful" | You still do all the transcription by ear |
| **MuseScore** | Free notation | No | Tab entry exists but is painful: mode confusion (number keys change duration instead of fret), linked staff/tab where you can't choose the string, tab corruption on tuning changes | Playback | MusicXML, GP import | Free, notation quality | "Like pulling teeth" for tab entry; its own team ran a "Improving the experience of Guitarists" initiative |

### 3.2 Patterns worth copying

- **Keyboard/pedal-first player** (Songsterr: Space, L, S, C, N, M). Single-letter shortcuts map naturally onto pedal keystrokes.
- **Capo mode that keeps the song's key but changes the shapes** (Moises), and GP's explicit "keep the fingering" choice when you set a capo.
- **Voicing difficulty levels** (Moises: Easy/Medium/Advanced). For Fretscribe, the tab equivalent is "open position / as played / one position".
- **Drag across notes to loop**, gapless loops, speed trainer (Soundslice).
- **Multiple saved loops and section markers** (Transcribe!).
- **Tuning shown at the start of the first bar** (Songsterr), which should be kept but also promoted to a persistent header chip.
- **Real-recording sync**: the tab cursor follows the *actual recording*, not a MIDI rendition (Soundslice). For Fretscribe this comes for free: the source audio *is* the recording.

### 3.3 Anti-patterns to avoid

- 20-second previews, ticket and credit systems, unskippable ads (Klangio, Songsterr free, UG). Fretscribe is free; say so loudly, because it's a differentiator in itself.
- Machine output overwriting human work (the Songsterr AI-edits backlash). Keep **provenance**.
- One-line tab on phones; chrome you can't hide (GP mobile).
- Coarse tempo steps (GP mobile).
- Mode-heavy tab entry where number keys mean different things per mode (MuseScore).
- Treating chords as triads only (Chordify).

### 3.4 What people do with transcriptions afterwards

Evidence-based, in order:
1. **Practise along in the app**: the main use for Songsterr, Soundslice, Moises and Chordify.
2. **Fix and then export to a real editor** (Guitar Pro above all, then MuseScore). This is why every AI competitor exports GP, and why Songsterr's lack of MusicXML is called out.
3. **Print/PDF**, for teachers and band charts ("make easier to print" is a Guitar2Tabs review request).
4. **Share** a link or file with students or bandmates (Soundslice Teacher plan).

Editing on a phone is the exception, not the rule: GP mobile reviewers explicitly prefer a computer for writing. So phone editing must be **fast and narrow** (fix this note or phrase) rather than a full editor.

---

## 4. Wrong and uncertain notes: how players handle them, and what the editor must do

### 4.1 The error taxonomy (from reviews and cleanup guides)

| Error class | Example | Frequency / evidence | Right fix UX |
|---|---|---|---|
| **Global: tuning/reference** | Song is in Eb standard (half step down) or recorded off A440 (e.g. A452): every fret number is off by one or unplayable | Very common in rock and blues; forum threads on half-step-down and off-440 references. The cleanup guide's step 1 is "verify tuning, capo and instrument settings match" **(vendor)** | **Detect and confirm before showing the tab**: "This sounds like Eb standard (−1 semitone). Use Eb tuning / Transpose to E / Keep as-is". Also a ± cents reference offset. |
| **Global: capo** | Open-chord song played with capo 2 transcribed as barre chords at frets 2–4 | Implied by the prominence of capo modes (Moises, Songsterr chords, GP "keep fingering") | Capo suggestion: "Looks like open shapes + capo 2". One-tap apply. |
| **Global: octave** | Bass line an octave high; uke line placed for low-G when the player has high-G | Octave slips are the #1 error in the cleanup guide **(vendor)**; phone mic bass roll-off; uke high/low-G confusion | Instrument/octave confirmation at import; whole-track octave shift. |
| **Position/fingering** | Right pitch, wrong string: a solo at the 12th fret rendered as open strings and low frets | Klangio's most specific complaint; the "doesn't reflect how you'd actually play them" quote **(vendor review)**; research treats string/fret assignment as a separate problem | **Phrase-level position lock** ("play bars 5–8 around fret 7") plus a **one-tap alternate position** per note ("same pitch, other string": cycle through the 2–5 valid positions). The recomputation must keep neighbouring notes playable. |
| **Pitch** | Wrong note (neighbour semitone, harmonic mistaken for fundamental) | Common with distortion, bends, 3+ note chords | Tap note → step ±1 semitone → hear it immediately against the recording. |
| **Missing / ghost notes** | Chord missing inner voices; bass or vocal bleed as phantom notes | Cleanup guide **(vendor)**; Klangio can't separate instruments | Delete; "add note at cursor"; chord re-voicing from a palette of shapes. |
| **Rhythm** | Note half a beat off; tuplets mangled | Cleanup guide **(vendor)** | Snap to grid; nudge ±1 subdivision; tap-tempo re-beat. |
| **Techniques** | Bends notated as two notes; slides and hammer-ons missed | Klangio "inconsistent" on bends and slides **(vendor)** | Technique toggles on a selected note/pair (h, p, /, \, b, ~, PM, x). |

### 4.2 Recommended order of correction (built into the flow)

1. Instrument, tuning, reference pitch, capo, octave (global; asked or suggested first).
2. Section structure and loop regions.
3. Pitch errors within the looped section (low-confidence notes first).
4. Rhythm.
5. Position/fingering (phrase locks, then per-note alternatives).
6. Techniques.

This matches the independent cleanup guide's order and prevents the worst waste, which is fixing 200 frets by hand and *then* discovering the song was in Eb.

### 4.3 Uncertainty display

- Mark low-confidence notes visually (colour + shape, never colour alone) and **list them** so the user can step through them ("7 unsure notes: next ›"). (inference; required for accessibility)
- Distinguish *pitch-uncertain* from *position-uncertain*. A note can be certain in pitch but have three equally good positions. Those two need different affordances and different wording. (inference from the error split)
- Tap an unsure note → auto-loop 1–2 beats around it at 50–75% speed, show the top 2–3 candidates, and let the user pick by ear. (inference; this mirrors how Transcribe! users loop tiny regions)
- **Provenance:** machine-generated vs user-confirmed vs user-edited notes must be distinguishable, and re-running transcription must never silently overwrite user edits. (Songsterr AI-edits backlash)

### 4.4 Tab editing on a phone: concrete interaction model (inference)

- **Selection is by note, not by cursor.** Tap a digit to select it and a compact **fretboard strip** appears (mirrored for lefties if they choose), showing all valid positions for that pitch. Tap one to move the note there.
- **Numeric fret entry** via a big 0–24 pad; up/down swipe on a digit to move ±1 fret (pitch change); left/right swipe to move to an adjacent string at the same pitch (position change). The two gestures map to the two error classes.
- **No modes**: the same tap does the same thing everywhere (MuseScore's mode confusion is the counter-example).
- **Undo/redo always visible**; "revert to machine version" per bar.
- **Hear it immediately**: every edit plays the note, and optionally the original audio at that spot, A/B.
- Phone editing covers corrections. Full composition and multi-track arrangement belong to desktop/tablet and GP/MuseScore via export.

---

## 5. Core user flows

### 5.1 First run / setup (target: under 60 s, all skippable)

1. Welcome: one screen saying "Free, on-device, no account". No sign-in.
2. **Instrument** picker with pictures: guitar 6/7/8, bass 4/5/6, ukulele (soprano/concert/tenor: **high-G or low-G**; baritone DGBE), mandolin, 5-string banjo (open G default), "other/custom".
3. **Default tuning** (list + custom per string; show note names *and* Hz). A reference pitch field (A = 440 default) sits behind "advanced".
4. **Handedness**: right / left / left-playing-upside-down (right-handed guitar, not restrung). Explain in one line: "Tab stays the same; diagrams and the fretboard flip."
5. **Level** (optional): beginner / intermediate / advanced. This only sets defaults: open-position preference and simplification, notation on/off, and the verbosity of techniques.
6. **Notation preference**: tab only / tab + rhythm / tab + standard / standard only (the classical and mandolin audience).
7. Mic permission, requested *at first capture*, not here. (inference; permission-priming practice)
8. Optional: pair the companion engine (explain what it's for: full songs with band, stems). Skippable; offer later on the first full-song import.

### 5.2 Capture / import

1. Big **Record** button on the home screen (≤1 tap from app open, and from a lock-screen/home widget if possible) for idea capture (P5).
2. Before/while recording: live input meter plus a clipping/too-quiet/noisy warning; a tuner check ("your low E is 18 cents flat"); **current tuning and capo chip**, editable.
3. Stop → choose scope: **"Just my instrument (single line)"**, which runs on device, or **"Full song / band recording"**, which needs the companion engine and shows its status ("Desktop engine: connected / not found / how to set up").
4. Import: file picker, share-sheet ("Open in Fretscribe" from Voice Memos, Files, Drive, WhatsApp), and a desktop drag-and-drop. For band recordings, choose **which part** (guitar 1/2, bass) once the engine has separated stems.
5. **Global check screen** before any tab is shown: detected tuning offset / reference pitch, suggested capo, key, tempo/time signature, instrument octave. Each shows accept / change. This is the single most important screen in the product.
6. Processing with progress; the recording stays playable with a waveform while it runs.

### 5.3 Review and correct

1. Result opens in **Review mode**: tab (+ notation if enabled), unsure notes marked, summary "142 notes · 9 unsure · 3 position suggestions".
2. Section/loop markers are auto-proposed (intro/verse/riff by repetition) and renamable.
3. "**Next unsure**" steps through the uncertain notes: auto-loop around each, candidates, pick.
4. Phrase selection → "**Play this in…**" (open position / as low as possible / around fret N / on these strings) → recompute positions for the phrase.
5. Note-level edits per §4.4.
6. Technique annotation.
7. Mark bars "checked" (optional progress).

### 5.4 Practise

1. Big transport; the source recording plays by default, with synthesized tab playback as an optional overlay or mix (Soundslice's "synth and real recordings at the same time").
2. Loop: drag across the tab or waveform, or tap a section marker; saved loops list.
3. Speed: fine steps (1–5% or BPM), pitch preserved; **speed trainer** (start at 60%, +5% every N clean loops up to 100%).
4. Count-in (1–2 bars), metronome, with click volume independent of track volume.
5. **Follow cursor** with fixed-cursor scrolling; large "practice view" with ≥2 bars of lookahead; optional fretboard view (lefty-aware).
6. **Hands-free**: pedal/keyboard mapping (default 2-pedal layout: left = back to loop start / previous section, right = play/pause; long-press = slower/faster), plus screen-stays-awake.
7. Transpose / capo change (both "keep sound" and "keep shapes").
8. Resume exactly where you left off.

### 5.5 Export / share

1. Export: **Guitar Pro (.gp)** (see R19), MusicXML (with string/fret technical data so tab survives the round trip), MIDI, PDF (tab, tab + notation, and chord chart variants; one-page "band chart" option), and the original audio.
2. Share sheet: file, or a PDF for print. No cloud dependency; an optional share link could come later, not in the core.
3. Export always states the tuning and capo on the page header.

### 5.6 Library

1. List of songs/ideas with: title, instrument, tuning chip, capo, date, "unsure notes left", and practice progress (last speed reached).
2. Filters by instrument/tuning (the gigging player wants "all my Eb songs"); setlists (Moises has these).
3. Idea inbox for quick captures (untitled, auto-named by date/key/tempo).
4. Local-first storage with an export/backup-all option; desktop and phone sync over the same local network as the engine (inference, consistent with local-first).

---

## 6. Ranked UX requirements

Ranked by impact on "is this tab usable for me". **MUST** = without it the product fails its core job; **SHOULD** = strong differentiator or expected; **COULD** = nice.

| Rank | ID | Requirement | Tag | Evidence |
|---|---|---|---|---|
| 1 | R1 | **Global check before first view**: detect and confirm tuning offset (incl. Eb/half-step-down and off-A440 reference in cents), capo, key, tempo, and instrument octave; one tap to accept or change. | MUST | Cleanup guide step 1 "verify tuning, capo, instrument" (vendor); half-step-down and A452 reference threads (UG, Harmony Central); octave slips as the top error (vendor) |
| 2 | R2 | **Playable positions by default**: string/fret assignment that minimizes hand shifts and respects span, with a level-based preference (open position for beginners). Never put high-fret melodic lines on open strings of a higher string. | MUST | Guitar2Tabs reviews "frets 9–14… as open, 1, 2, 3 on a higher string… not playable"; "doesn't reflect how you'd actually play them" (vendor review); Noise2Fret playability losses (arXiv) |
| 3 | R3 | **Separate the two correction paths**: *pitch* (±semitone, pick a candidate) vs *position* (same pitch, other string; phrase "play around fret N"). Distinct gestures and wording. | MUST | Error taxonomy §4.1; Klangio notes-right/positions-wrong; MuseScore users can't change string when tab and staff are linked |
| 4 | R4 | **Uncertainty marking + "next unsure" navigator** with auto-loop around the note and top candidates to pick by ear. Colour + shape, not colour alone. | MUST | Product brief (marks unsure notes); Transcribe! loop-tiny-region workflow; Klangio dev admits "far from perfect" (inference for navigator) |
| 5 | R5 | **Tuning and capo as always-visible per-song state**, one tap to change, with explicit "keep the sound / keep the shapes" choice. Custom tunings per string, 4–8 strings. | MUST | Guitar Pro "Keep the fingering" capo option and 3–10 string tunings; Moises capo mode; Songsterr tuning shown at bar 1 |
| 6 | R6 | **Gapless looping + fine-grained, pitch-preserving slowdown** (≤5% steps) with decent audio quality down to ~50%. | MUST | Soundslice "perfect looping"; GP mobile "10% steps… 180 to 162 BPM", "mediocre below 50%" |
| 7 | R7 | **Hands-free control**: Bluetooth pedal/keyboard keystrokes remappable to play/pause, loop restart, prev/next section, slower/faster; screen stays awake in practice mode. | MUST | AirTurn pedals send keystrokes and are supported by Songsterr/UG/forScore; Songsterr single-key shortcuts |
| 8 | R8 | **Arm's-length practice view**: large tab digits, fixed cursor with scrolling score, hideable chrome, ≥2 bars lookahead, dark mode; reopens on the same song, loop, speed and view. | MUST | GP mobile "one horizontal line… unusable", "bottom bar cannot be hidden"; GP 2025 prototype adds fixed cursor + dark mode; resume state is (inference) from daily short sessions |
| 9 | R9 | **Instrument models done right**: ukulele high-G/low-G (re-entrant), baritone uke, mandolin (fifths, courses), 5-string banjo (short 5th string from fret 5, conventional bottom tab line), 7/8-string guitar, 5/6-string bass. | MUST | Ukulele Underground/UkuTabs on high/low-G tabs; banjo tab conventions (Joff Lowson, Banjo Hangout, MuseScore 5th-string thread) |
| 10 | R10 | **Provenance and non-destructive re-runs**: machine / confirmed / user-edited states; re-transcribing never overwrites user edits; per-bar "revert to machine". | MUST | Songsterr users on "AI garbage edits overlaying official tabs" |
| 11 | R11 | **Capture preflight**: input meter, clipping/noise warnings, built-in tuner check, external interface input; warn that simultaneous playback needs headphones. | MUST | Yousician: noise, echo, own playback picked up by mic; Fender Play criticized for having no built-in tuner |
| 12 | R12 | **Bass-specific safeguards**: octave sanity check and suggestion; prefer an interface/line-in; ignore kick drum in full-song mode. | MUST | Phone mics weak in lows (bass tuner app docs); Yousician trouble with low E/A |
| 13 | R13 | **Handedness done correctly**: mirror fretboard view and chord diagrams for lefties; keep the **tab staff unmirrored by default**, with an opt-in mirrored-tab toggle; separate "upside-down player" option that reverses string order in diagrams. | MUST | UG and GP lefty modes mirror diagrams/fretboard; forum consensus that lefties on lefty guitars read standard tab; a Sibelius help thread shows some players do want a left-handed tab staff |
| 14 | R14 | **Free, no paywalled previews, no account.** Say so on first run and in store copy. | MUST | Guitar2Tabs 20 s limit and ticket pricing; Songsterr 5–20 s mobile limit; UG ads and subscription complaints |
| 15 | R15 | **Record from home in ≤1 tap**, with tuning/capo/position stored with the idea. | SHOULD | Songwriter-capture apps' positioning ("never forget how to play that riff") (vendor); Voice Memos lacks the "how" |
| 16 | R16 | **Speed trainer** (auto-ramp tempo across loops) and count-in with independent click volume. | SHOULD | Soundslice speed training; GP Speed Trainer; Songsterr count-in; Moises count-in praised |
| 17 | R17 | **Phrase-level "play this in position N / on these strings"** recompute, and a "simplify" option (drop inner voices, open-position chords). | SHOULD | Moises Easy/Medium/Advanced voicings; teacher persona; Klangio position complaints |
| 18 | R18 | **Section markers and multiple saved loops**, auto-proposed from repetition, named by the user. | SHOULD | Transcribe! markers and "multiple loops can be saved and recalled" |
| 19 | R19 | **Guitar Pro export** (.gp or .gp5), plus MusicXML that carries string/fret technical data so tab survives import into MuseScore/Sibelius/Dorico. *Gap vs the brief, which lists MusicXML/PDF/MIDI only.* | SHOULD (arguably MUST for P2/P4) | Every AI competitor exports GP (Klangio, Songscription, Songsterr); Songsterr criticized for no MusicXML (vendor review) |
| 20 | R20 | **Notation modes per audience**: tab only / tab+rhythm / tab+standard / standard with string numbers and LH/RH fingering (p-i-m-a). | SHOULD | Classical notation conventions (Berklee, classicalguitar.org); mandolin/fiddle standard-notation culture (Mandolin Cafe) |
| 21 | R21 | **Source recording as the playback track**, with optional synth tab overlay and part mute/solo (stems when the companion engine is present). | SHOULD | Soundslice real-recording sync and "synth + real recordings at the same time"; Moises stems; Songsterr mute/solo |
| 22 | R22 | **Technique notation** (h/p, slides, bends with amount, vibrato, PM, dead notes, harmonics, let-ring, slap/pop for bass), editable as toggles on a selection. | SHOULD | Soundslice supports "bends, slides, harmonics, tapping"; Klangio inconsistent bends/slides (vendor) |
| 23 | R23 | **Chord layer**: chord names above tab with extended chords (7, maj7, sus, dim), capo-relative shape names, lefty-aware diagrams. | SHOULD | Chordify triad-only complaints; Moises capo mode |
| 24 | R24 | **Print-ready PDF**: one-page band chart, tuning/capo in header, tab + optional notation. | SHOULD | Guitar2Tabs "make easier to print"; teacher and gigging personas |

---

## 7. Open questions to validate with real players

1. How often is the "global check" (R1) wrong enough to annoy? That needs measurement on real recordings: Eb and drop tunings are common in the rock/metal crowd, rare with uke players.
2. Do beginners (P1) actually want position choice, or one "best" tab? Hypothesis: one best tab, plus a "harder/easier" toggle.
3. Is on-phone editing used at all, or do people correct on a tablet/desktop? GP mobile evidence suggests phones are for reading and practising. Test before investing in the phone editor beyond R3/R4.
4. Pedal adoption among hobbyists vs gigging players: is a keyboard/pedal enough, or is voice control ("again", "slower", "from verse") worth it, given that it competes with the mic during capture?
5. Ukulele and mandolin communities: tab-first or notation-first? Evidence is mixed; the notation-mode setting (R20) hedges.
6. Is comparing two takes or recordings of the same part (Soundslice's multi-recording sync) worth building? Deferred as a later feature.

---

## Sources

Competitor products and reviews
- Songsterr help (shortcuts, loop, count-in, tuning display): https://www.songsterr.com/help
- Songsterr App Store: https://apps.apple.com/us/app/songsterr-tabs-chords/id399211291
- Songsterr reviews (Trustpilot): https://www.trustpilot.com/review/www.songsterr.com
- Songsterr review aggregation: https://justuseapp.com/en/app/399211291/songsterr-tabs-chords/reviews
- Ultimate Guitar left-handed mode (help center): https://help.ultimate-guitar.com/en/articles/7936916-mobile-optimizing-for-left-handed-players-enabling-left-handed-mode-in-the-tabs-app
- Ultimate Guitar reviews (Trustpilot): https://www.trustpilot.com/review/www.ultimate-guitar.com?page=2
- Ultimate Guitar Pro review (Guitar Chalk): https://www.guitarchalk.com/ultimate-guitar-pro-review/
- Guitar Pro mobile reviews: https://justuseapp.com/en/app/400666114/guitar-pro/reviews
- Guitar Pro App Store reviews: https://apps.apple.com/us/app/guitar-pro/id400666114?see-all=reviews&platform=iphone
- Guitar Pro NAMM 2025 mobile prototype: https://www.guitar-pro.com/blog/p/48507-namm-show-2025-the-prototype-of-the-new-guitar-pro-mobile-app-unveiled
- Guitar Pro 8 tuning tutorial: https://www.guitar-pro.com/blog/p/44384-tutorial-how-to-change-the-tuning-of-a-track-in-guitar-pro-8
- Guitar Pro 7.6 tips (capo / keep fingering): https://www.guitar-pro.com/blog/p/31896-14-guitar-pro-7-6-tips-you-need-to-know
- Guitar Pro Fretlight / left-handed setting: https://support.guitar-pro.com/hc/en-us/articles/360000297438-GP8-Discover-the-Fretlight-technology
- Guitar2Tabs App Store (ratings, reviews): https://apps.apple.com/us/app/guitar2tabs-transcribe-riffs/id1589660528
- Guitar2Tabs Google Play: https://play.google.com/store/apps/details?id=com.klangio.guitar2tabs&hl=en_US
- Klangio Guitar2Tabs product page (vendor): https://klang.io/guitar2tabs/
- Klangio reviews (Trustpilot): https://www.trustpilot.com/review/klang.io?page=2
- Klangio review (music tech educator): https://www.musictechhelper.com/blog/audio-to-sheet-music-meet-klangio
- AI guitar tab generators comparison (vendor, Songscription ranks itself first): https://www.songscription.ai/blog/best-ai-guitar-tab-generators
- Moises Chord Finder (vendor): https://moises.ai/features/chord-finder/
- Moises Guitar Capo Mode (vendor): https://moises.ai/features/guitar-capo-mode/
- Moises discussion (JustinGuitar community): https://community.justinguitar.com/t/check-out-the-moises-app/142726
- Moises App Store reviews: https://apps.apple.com/us/app/moises-the-musicians-app/id1515796612?see-all=reviews
- Chordify reviews (Trustpilot): https://www.trustpilot.com/review/chordify.net
- Chordify App Store reviews: https://apps.apple.com/us/app/chordify-songs-chords-tuner/id1073624757?see-all=reviews&platform=ipad
- Chordify thread (Gretsch-Talk): https://gretsch-talk.com/threads/chordify.175955/
- Yousician guitar review: https://beginnerguitarhq.com/yousician-guitar-review/
- Yousician sound recognition support article: https://support.yousician.com/hc/en-us/articles/201576782-Guitar-sound-recognition-issues
- Fender Play review (TheGuitarLesson): https://www.theguitarlesson.com/fender-play-review/
- Fender Play reviews: https://justuseapp.com/en/app/1226057939/fender-play-guitar-lessons/reviews
- Soundslice practice guitar (vendor): https://www.soundslice.com/practice-guitar/
- Soundslice notation/tab editor (vendor): https://www.soundslice.com/notation-editor/
- Soundslice teachers (vendor): https://www.soundslice.com/teachers/
- Soundslice synth + real recordings (vendor): https://www.soundslice.com/blog/265/new-play-synth-and-real-recordings-at-the-same-time/
- Transcribe! overview: https://www.seventhstring.com/xscribe/overview.html
- Transcribe! review (Online Lead Guitar): https://onlineleadguitar.com/transcribe-review/
- AnyTune App Store: https://apps.apple.com/us/app/-/id415365180
- MuseScore: Improving the experience of guitarists: https://musescore.org/en/node/326995
- MuseScore: changing fret/string with linked staff: https://musescore.org/en/node/109906
- MuseScore: tablature corruption with alternate tunings: https://musescore.org/en/node/386202
- MuseScore: switching to tab edit mode: https://musescore.org/en/node/141476

Hardware / physical context
- AirTurn (app compatibility incl. Songsterr, UG, forScore): https://www.airturn.com/products/airturn-ped-500
- Musicnotes hands-free page turn support: https://help.musicnotes.com/hc/en-us/articles/205202895-Hands-Free-Page-Turn-Support
- Bass tuner apps and phone mic low-frequency response: https://play.google.com/store/apps/details?id=com.teamgugu.basetuner&hl=en_US
- Bass guitar tuning (low B 31 Hz, low E 41 Hz): https://en.wikipedia.org/wiki/Bass_guitar_tuning

Transcription errors and playability
- How to clean up AI-generated guitar tabs (vendor): https://tabtify.com/blog/how-to-clean-up-ai-generated-guitar-tabs
- Noise2Fret: playability-aware audio-to-tab transcription (arXiv): https://arxiv.org/html/2608.30854v1
- Fretting-Transformer: MIDI-to-tablature (arXiv): https://arxiv.org/html/2506.14223v1
- Half-step-down and reference pitch (Ultimate Guitar forum): https://www.ultimate-guitar.com/forum/showthread.php?t=1072937
- Half-step-down and reference pitch (Harmony Central): https://www.harmonycentral.com/forums/topic/1297379-if-standard-tuning-is-440-what-is-12-step-down/
- Converting songs to A440 (TalkBass): https://www.talkbass.com/threads/how-to-convert-songs-to-440-a.1010800/page-2
- "Why are guitar tabs so wrong" (AnandTech forums): https://forums.anandtech.com/threads/why-are-guitar-tabs-so-damn-wrong-all-the-time.8490/post-22875174

Instrument conventions
- Low-G vs high-G ukulele (UkuTabs): https://ukutabs.com/ukulele-guides/low-g-vs-high-g-ukulele/
- High-G tabs on a low-G uke (Ukulele Underground): https://forum.ukuleleunderground.com/threads/tabs-in-hi-g-on-low-g-uke-how-to.103234/
- Reentrant tuning: https://en.wikipedia.org/wiki/Reentrant_tuning
- How to read banjo tablature: https://jofflowson.com/how-to-read-banjo-tablature/
- 5-string banjo 5th string in MuseScore: https://musescore.org/en/node/273169
- Banjo drone string discussion (Banjo Hangout): https://www.banjohangout.org/archive/293071
- Tabs vs notation (Mandolin Cafe): https://www.mandolincafe.com/forum/archive/index.php/t-91840.html
- Notation/tab software (Mandolin Cafe): https://www.mandolincafe.net/home/forum/general-mandolin-topics/general-mandolin-discussions/139930-notation-tab-softwares/page2
- Classical guitar notation (classicalguitar.org): https://www.classicalguitar.org/2009/01/how-to-read-classical-guitar-music/
- Guitar notation basics (Berklee Online): https://online.berklee.edu/takenote/guitar-notation-basics/
- Tab orientation debate (Acoustic Guitar Forum): https://www.acousticguitarforum.com/forums/showthread.php?t=644529
- Tab orientation debate (Harmony Central): https://www.harmonycentral.com/forums/topic/1704480-dont-you-think-tab-is-upside-down/
- Left-handed tab staff (Sibelius help center): https://www.sibelius.com/cgi-bin/helpcenter/chat/chat.pl?com=thread&start=755455&groupid=3&guest=1

Idea capture
- Song idea capture apps (vendor, Songcage): https://songcage.com/blog/best-apps-for-capturing-song-ideas-fast/
- Songscape (vendor): https://www.songscape.app/
