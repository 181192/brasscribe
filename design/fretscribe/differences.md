# Fretscribe vs Brasscribe: what carries over and what differs

Sources: the three independent research reports in
[`docs/fretscribe/research/`](../../docs/fretscribe/research/) (UX, accessibility, tab domain), read
against Brasscribe's [`design/README.md`](../README.md), [`design/system.md`](../system.md) and
[`design/brand/brand.md`](../brand/brand.md).

The short version: the **rules** carry over almost unchanged; the **flow**, the **main screen**, the
**meaning of uncertainty** and the **editing model** do not. Brasscribe hands a band a score.
Fretscribe hands one player a practice object: the recording plus a tab they can loop, slow down and
play along with, with both hands on the instrument.

## Carries over as is

| Brasscribe rule | Why it holds for Fretscribe |
|---|---|
| Native first, brand second: platform controls, fonts, navigation | Same four platforms, same apps shell |
| One primary button per screen; toggles never ink-filled | Same reasoning; practice mode has one primary, Play |
| The score owns colour; chrome stays neutral | Tab needs colour even more for cursor, loop and marks |
| Never colour alone | Also required for string identity if strings are ever coloured (off by default) |
| Voice: calm, specific, on your side; no "AI", no "we"; every error has a way forward | Competitors are criticised for paywalls, ads and overclaiming; honesty is the differentiator |
| Details for the tech person, collapsed | Same pairing and engine story |
| Progress with plain steps, time left and a confirming Cancel | Same engine |
| Leaving never loses work silently; Finish later (N left) | Same |
| Music stand view | Even more central: it becomes the default practice view (see below) |
| Appearance: Match system / Light / Dark, system contrast wins, PDFs stay light | Same |
| Tokens pipeline: DTCG `tokens.json`, generated per platform, contrast gate | Reused as tooling; Fretscribe gets its own token values |
| Focus ring in ink/paper, never an uncertainty hue | Same |
| Motion: fast/base/slow, reduced-motion fallbacks | Same, plus the metronome rule below |
| Pairing with the computer, Bandroom | Shared; one Bandroom serves both apps |

## Differs, and why

### 1. The flow: settle the whole song first, then the notes

Brasscribe: What is this? → Transcribing → Check the notes → How should the score be? → Score.

Fretscribe needs a **song check before any tab is shown**. Most whole-song wrongness is global: E♭ or
half-step-down tuning, a recording off A440, capo, octave (bass, ukulele high or low G). Fixing 200
frets by hand and then discovering the song was in E♭ is the worst failure in the category. The UX
report calls this the most important screen in the product.

```
Record / Open → What is this? (just my instrument · full song → which part)
  → Writing down the notes → Check the song (tuning · reference pitch · capo · octave · key · tempo)
  → Check the notes (pitch first) → Tab + practice
```

Brasscribe's "How should the score be?" (band, difficulty, key) has no counterpart after review. Its
Fretscribe relatives are the song check (before review) and "Play this in…" (position, on demand).

### 2. Uncertainty has three meanings, not one

| Kind | Brasscribe | Fretscribe |
|---|---|---|
| The pitch may be wrong | "?" above the note; boxed "?" when very unsure | Same "?" family, above the tab column, with a threshold that shows only the worst notes by default |
| The pitch is right; the string/fret is one of several | n/a | **No mark.** Alternatives on tap; a pinned string shows a pin in edit mode only |
| No valid fingering (out of range) | Range checks in the arranger | Strong "!" with the words, linking to "Change tuning", since the usual cause is the wrong tuning or instrument |

Keeping "?" for doubtful pitch makes the two products read alike where they mean the same thing.

### 3. Two ways to fix a note

Brasscribe's review has Keep and Change note. Fretscribe needs two separate paths, with separate words
and gestures, because players hate "right note, wrong place" more than a wrong note:

- **Pitch:** one semitone up or down, or pick a candidate by ear, with the bar looped slowly around it.
- **Place:** same pitch, other string (cycle through the valid positions), or for a phrase, "Play this
  around fret N / in open position / on these strings", which re-solves the neighbours so they stay
  playable.

Every note keeps its **provenance**: written by Fretscribe, checked, or changed by you. Writing the
notes down again never overwrites your changes, and each bar can go back to Fretscribe's version.

### 4. The main screen is practice, not a score

- The source recording is the default sound, with the tab synth as an option. (Brasscribe defaults to
  the band sounds, with the recording as the option.)
- Fine speed steps (5% or less) with pitch kept, a speed trainer, gapless repeats, several saved
  repeats and section markers.
- A fixed cursor with the tab scrolling past, at least two bars ahead, readable at arm's length.
- Reopens exactly where you left off: song, repeat, speed, view.

### 5. Hands-free is a core feature

Brasscribe has keyboard shortcuts. Fretscribe makes Bluetooth page-turner pedals work by default
(arrows and PgUp/PgDn, remappable), adds **Lock the tab** so a resting forearm triggers nothing, and
makes practice-mode transport targets at least 64 pt. Voice control depends on visible labels matching
accessible names, which Brasscribe already requires.

### 6. "What do you play?" becomes the instrument, set up

Brasscribe asks for a seat, a part and a clef. Fretscribe asks for:
- instrument and number of strings (guitar 6/7/8, bass 4/5/6, ukulele with high or low G, mandolin,
  later banjo)
- default tuning, with custom tuning per string
- handedness: right, left, or left-handed playing a right-handed instrument upside down
- level, which only sets defaults (open position, notation on or off, how many technique marks)
- what you read: tab with rhythm, tab and notation, or notation only

**Tuning and capo are per-song and always visible** as a chip ("E♭ standard · capo 2"). Changing capo
asks one question: keep the sound (new frets) or keep the shapes (new sound).

### 7. Left-handed players

New for Fretscribe. Tab never mirrors by default; fretboard views and chord diagrams do. Upside-down
players get reversed string order in diagrams. Mirrored tab exists only as an opt-in.

### 8. Capture needs a preflight

A level meter with too-quiet, too-loud and noisy warnings, a tuner check, external interface input, and
a headphones note when playing along while recording (the phone speaker bleeds into the mic). Bass gets
an octave check, since phone mics barely hear a low B.

### 9. Output

- **Formats:** MusicXML with string and fret, PDF (clean or with marks), MIDI and ASCII tab in the first
  version; Guitar Pro later (alphaTab can export GP7), since it is the tab world's interchange format.
- **For blind players:** a plain-text "playing instructions" export.
- **What:** one instrument, not band parts. A one-page chart option for band use.

### 10. Screen reader, recording and metronome

- Tab is read as one element per beat, grouped by bar, at three levels of detail, with tuning and capo
  announced once and frets relative to the capo. Brasscribe's talking score is a separate text view;
  Fretscribe needs the tab itself to be navigable.
- **App speech is silent while recording** (it would be recorded), and start and stop are confirmed by
  haptics.
- Visual metronome: movement or a small area, never a full-screen flash (more than three flashes a
  second at fast tempos). Haptic metronome as an option.

### 11. Layers instead of views

Tab with rhythm is the default everywhere. Standard notation, chord names, chord diagrams, fingering and
technique marks are layers you turn on. Brasscribe's "As written / Concert pitch" switch has no
counterpart; guitar notation is always written an octave up (treble 8vb), which is the convention, not a
choice.

### 12. Words

Brasscribe's glossary is band-room English and Norwegian. Fretscribe's is the practice room:

| Concept | Brasscribe | Fretscribe |
|---|---|---|
| The finished notation | score | tab (tab and notation, when both) |
| One player's music | part | part (only when a full song has several) |
| Make notation from audio | write down the notes | write down the notes |
| The instrument set-up | What do you play? | Your instrument (tuning, capo, strings) |
| Where on the neck | n/a | position, string, fret |
| Repeat a passage | Repeat bars 12 to 13 | Repeat bars 12 to 13 (same) |
| Silence one part | Mute my part | Mute the guitar (only when parts exist) |

"Bar", "Repeat", "Count-in", "Speed", "Keep", "Finish later", "Share or print" stay the same.

## Open questions for players

1. Do tab readers read "?" above a fret number as "check this note"? Test alongside Brasscribe's open
   question about the same mark.
2. Do beginners want to choose a position, or one best tab with Easier / As played?
3. Is editing on the phone used at all, or only on a tablet and computer?
4. Pedals or voice for hobby players?
5. Ukulele and mandolin players: tab first or notation first?
