# 02 — Accessibility requirements specific to tablature and fretted-instrument practice

Scope: what Fretscribe needs beyond generic WCAG 2.2 AA, because it (a) records audio, (b) renders tab/notation, (c) is used with both hands on an instrument, often at music-stand distance, and (d) exports scores. Generic app accessibility (labels, focus order, contrast of ordinary UI) is assumed and only mentioned where tab changes the answer.

Baseline target: WCAG 2.2 AA for all UI and web/desktop surfaces (EN 301 549 v3.2.1 clause 9–11 maps to it for non-web software), plus Apple HIG / Android accessibility guidance on mobile. Selected AAA criteria are recommended where musicians clearly benefit (noted inline).

---

## 1. Blind and low-vision guitarists: how songs are learned today

### 1.1 Current practice

| Route | What it is | Implication for Fretscribe |
|---|---|---|
| Learning by ear | Still the dominant route. Slow-down/loop tools plus repeated listening. Remote lessons with teachers experienced with blind students. | Accessible **playback, loop and slow-down** are as valuable as the tab itself. The practice player must be fully operable by screen reader and keyboard/pedal. |
| Spoken note-for-note audio lessons | e.g. Bill Brown's "string-and-fret-by-string-and-fret" recordings; NLS BARD has ~700 downloadable instructional titles (AFB AccessWorld). | Proves the target phrasing: **string + fret + duration, spoken**. That's the model for our screen-reader output. |
| Text tab (ASCII) read with a screen reader | Raw ASCII tab is readable char-by-char but vertically aligned columns are meaningless linearly. Users convert it with tools. | Never expose tab only as a 2-D grid of characters. Provide a linearised instruction view. |
| Tab-to-instructions converters | **Lunar Tabs** (Android + desktop, open source; Guitar Pro / Power Tab input → per-measure text such as "Play third string second fret, quarter note"; string/fret mode vs chord-name mode; navigate by 1 or N measures; voice commands; "stomp mode" via accelerometer; MIDI-guitar following; detects repeated measures — e.g. 118 bars, 10 unique). **Guitar Tab Reader for JAWS** (script: "First string: Third fret and slide up to Seventh fret"). Web tools that output "plain text playing instructions" (AppleVis thread). | Direct prior art. Users complain existing tools are glitchy/abandoned and that Guitar Pro / Ultimate Guitar render tab as inaccessible images. A maintained, native, screen-reader-first tab view is a real gap. |
| Braille music | Music Braille Code 2015 (BANA) §26.14: TAB **cannot be represented directly**; it must be converted to staff notation first. Converters work from MusicXML: Sao Mai Braille / SMB Online (free), BrailleMUSE (free web), FreeDots (open source), GOODFEEL (commercial). MuseScore 4 has live braille translation + 6-key braille input. | MusicXML export must carry **real pitch** so braille converters produce correct staff braille; string/fret is supplementary data. |
| Braille tablature codes | **Owens System of Braille Tablature** (Owens & Pieck; NBA, Jan 2025, rules rev. May 2025; free PDF/BRF): strings as letters a–h (1 = highest string), frets as upper-cell digits with dot 3 (1–10) / dot 6 (11–20), rhythm on a parallel line, chords written highest-to-lowest in chord enclosures. **BrailleTAB** (Québec): linear code, strings as letters, `a:1` = A string fret 1, no capital/number signs. | No automatic MusicXML→Owens converter exists. A **COULD**: a plain-text linear export close to BrailleTAB/Owens conventions that a braille display can read directly. Do not claim braille tab compliance without a transcriber review. |
| Music-reading apps | AccessMusic (iOS): MusicXML, VoiceOver measure-by-measure, low-vision single-measure view; no tab. MuseScore: note/rest-only arrow navigation, bar/beat in status, NVDA/JAWS/Orca. | Confirms navigation unit conventions: **bar → beat/event → note**, with position ("bar 12, beat 3") always available. |
| Tools | Talking tuners, accessible metronomes (spoken tempo, haptic pulse). | A built-in tuner/metronome must be speech/haptic-capable or we should not ship one visual-only. |

### 1.2 Screen-reader tab representation

**Conventions (announce once per song, repeat on demand):** instrument, number of strings, tuning low→high ("Drop D: D A D G B E"), capo ("capo 2; frets are relative to the capo"), string numbering ("string 1 is the high E"). Default fret numbers **relative to the capo** (that's what tab shows), with a setting for "absolute to nut". Re-entrant tunings (ukulele gCEA, some mandolin/12-string courses): say "re-entrant" in the tuning summary; string numbering stays physical (string 4 = high g on uke). Seven-string: string 7 = low B. For "courses" (mandolin), treat a course as one string.

**Navigation hierarchy:** section (verse/chorus if known) → bar → event (beat position with one or more simultaneous notes) → note. Every level has a "where am I" query: "Bar 12 of 64, beat 3, in Chorus 2".

**Verbosity levels (user setting, plus a quick toggle):**

| Level | Single note | Chord / double-stop | Technique | Uncertain note |
|---|---|---|---|---|
| Terse (fluent players) | "3-2", spoken "three two" (string, then fret; order configurable). Avoid "G2"-style string-letter forms, which clash with pitch names. | "Chord: 5-3, 4-2, 3-0" or chord name if recognised: "C major, open" | suffix: "3-2 h 3-4" ("hammer to 4") | prefix "?": "maybe 3-2" |
| Standard (default) | "String 3, fret 2, eighth" | "Strum: string 5 fret 3, string 4 fret 2, string 3 open, quarter" | "String 3, fret 2, hammer-on to fret 4" / "bend up a whole step" / "slide to 7" / "palm mute" | "String 3, fret 2, uncertain" |
| Full (learners) | "Beat 2 and: G string, second fret, note A, eighth note, first finger suggested" | as standard + chord name + pitches | technique spelled out + direction ("pick down") | "Uncertain: string 3 fret 2, also possible string 4 fret 7" |

Rules:
- Put the **most-needed information first** (string, fret) and duration last; users skip ahead mid-utterance.
- Say "open" for fret 0 and "muted" / "dead note" for x; never read "zero" or "x".
- Chords: read low→high string by default (strumming order), setting for high→low (Owens/braille order).
- Collapse repeats: "Bar 17: same as bar 9" (Lunar Tabs shows this cuts learning time a lot).
- Offer a **chord-name mode** alongside string/fret mode (Lunar Tabs prior art).
- Let users "play this event/bar" from the screen-reader cursor (audio sample of what's being read).

**VoiceOver / TalkBack patterns:**
- One accessibility element **per event** (not per glyph, not per drawn line). Bars as container groups with a heading-like label ("Bar 12").
- iOS: custom **rotor** entries: Bars, Sections, Uncertain notes, Techniques. `accessibilityCustomActions` on each event: "Play", "Loop from here", "Mark fixed", "Show alternatives". Adjustable trait (swipe up/down) on the bar container to step bars.
- Android: TalkBack custom actions (`AccessibilityNodeInfo.AccessibilityAction`) for the same set; `setCollectionInfo`/`CollectionItemInfo` to expose bar/event positions; headings for bars/sections so "navigate by heading" works.
- Desktop/web: roving tabindex inside a `role="application"`-free structure preferably (`grid` only if real 2-D navigation is exposed: rows = strings, columns = events); live region only for explicit position queries, not for every cursor move during playback.
- **Speech vs audio conflict:** screen-reader speech during **recording** gets captured by the mic and during **playback** competes with the music. While recording: suppress app announcements, confirm start/stop/level-clipping with haptics and short earcons; recommend headphones. During playback: option "announce only between loops/bars" and a follow-cursor that does not move accessibility focus unless asked.

## 2. Low vision

- **Resize and reflow (1.4.4, 1.4.10):** At 400% / 320 CSS px width, tab must **re-break into fewer bars per line**, not scroll horizontally. A single bar that is still too wide may scroll horizontally inside its own region (tab is "content requiring two-dimensional layout" and falls under the exception), but the page must not. Native apps: honour Dynamic Type / Android font scale for fret numbers and all labels; the score zoom is separate from and additive to system text size.
- **Text spacing (1.4.12):** labels, lyrics, chord names must survive 1.5 line height / 0.12em letter spacing without clipping. Fret digits in tab are graphics-positioned; keep them inside a box that grows.
- **Music-stand distance:** at ~60–100 cm, fret digits should render at ≥ 6–8 mm cap height in "stand mode" (roughly 24–32 pt on a tablet). Provide a "performance view": 1–2 systems per screen, big digits, thick string lines, high contrast, no chrome. AccessMusic's one-measure-at-a-time low-vision mode is a good precedent.
- **Stroke weight:** string lines ≥ 1.5 px at 1× zoom, fret digits in a bold, open-counter font with distinct 1/7 and 3/8 and 0 vs 8 (e.g. a tabular-figure sans). Knock out the string line behind each digit (standard tab practice) so digits don't strike through.
- **Contrast (1.4.3, 1.4.11):** fret digits and technique text ≥ 4.5:1 (target 7:1, AAA 1.4.6, for performance view). String lines, bar lines, cursor, loop region edges, confidence outline ≥ 3:1 against background.
- **Dark and high-contrast modes:** dark mode as a proper theme, not an inversion (inverted PDFs render grey digits). Respect iOS "Increase Contrast", Android "High contrast text", Windows Contrast Themes (`forced-colors` on web). Cursor and uncertain marks must stay visible in forced colours (use outline/shape, not just background colour).
- **No colour-only meaning (1.4.1):** uncertain notes need a **shape** cue (dashed ring or "?" superscript) plus the accessible label; string identity must be readable from position/label, never only from colour.
- **Magnifier compatibility:** follow cursor should keep the current event near a stable screen position so Zoom/Magnifier users aren't chasing it.

## 3. Motor: hands are on the instrument

- **Hands-free transport is a core feature, not an add-on.** Minimum command set: play/pause, next/previous bar, loop on/off, set loop start/end at cursor, tempo −/+, restart loop, record start/stop.
- **Bluetooth page turners / foot pedals:** AirTurn and similar pedals act as HID keyboards and send arrow keys or Page Up/Page Down (some can send MIDI). Map those keys by default (Next = →/↓/PgDn, Previous = ←/↑/PgUp), and allow **remapping** of each pedal key to any command. Support MIDI CC/note input from pedals where platform allows (CoreMIDI / Android MIDI / Web MIDI).
- **2.1.4 Character Key Shortcuts:** every single-key shortcut (space = play, L = loop…) must be remappable or disablable, and only active while the score has focus.
- **Voice control:** support OS voice control first (iOS Voice Control, Android Voice Access, Windows Voice Access). This depends on **2.5.3 Label in Name**: visible text "Loop" → accessible name starts with "Loop". An in-app voice command mode is a COULD; it conflicts with microphone capture and with the music itself (the app is listening to a loud guitar), so it can only work in playback/practice, with push-to-talk via pedal.
- **Motion / "stomp" input:** if we add accelerometer-triggered actions (Lunar Tabs stomp mode), 2.5.4 Motion Actuation requires a UI alternative and a way to switch it off.
- **Switch access:** all functions reachable with iOS Switch Control / Android Switch Access; scanning order sane (transport first, score second).
- **Targets (2.5.8):** AA minimum 24×24 CSS px; recommend **44×44 pt (iOS) / 48×48 dp (Android)** for everything and larger (≥ 64 pt) for transport buttons in practice mode, since the user reaches over a guitar body with a pick in hand.
- **Dragging (2.5.7):** loop region handles, tempo sliders, note-edit drags must all have single-pointer alternatives: tap "set loop start here", ± steppers, typed values.
- **Timing (2.2.1, 2.2.2):** no auto-dismissing toasts that carry actions ("Undo" must stay until dismissed or be reachable in history). Auto-scrolling follow mode is moving content → pause/stop control required (it's tied to playback, so pausing playback satisfies it, but also allow "follow off" while playing). Count-in length adjustable (1–4 bars).
- **Accidental activation (2.5.2 Pointer Cancellation, 3.3.4-like):** actions fire on up-event; destructive actions (delete recording, overwrite transcription) need confirm or undo. Palm/forearm resting on a tablet on a stand is common → an optional **"lock score"** mode that ignores touch on the score area while pedals/keyboard still work.
- **Recording controls:** start/stop must be pedal/keyboard-operable with a configurable pre-roll, so a player can start recording then get their hands in position.

## 4. Deaf and hard-of-hearing players

- **Visual metronome and count-in:** beat indicator using position/scale (a moving bar or pulsing dot) with accented downbeat by **shape/size**, not only colour. **2.3.1 Three Flashes:** at 180 BPM with subdivisions, a full-screen luminance flash exceeds 3 flashes/s. Keep flashing areas small (below the general-flash area threshold) or use non-luminance motion; honour Reduce Motion by switching to a static beat counter "1 2 3 4".
- **Haptic metronome:** phone/watch vibration pulse (Soundbrenner Pulse shows demand); note that phone vibration is inaudible to the mic only if the phone isn't on the instrument—warn during recording.
- **Playback position:** always-visible cursor on the current event; bar/beat readout; loop boundaries drawn.
- **Transcription confidence without hearing:** the uncertainty display must not depend on "listen and compare"; show alternative candidates visually.
- **Tutorial media:** captions for all speech (1.2.2), transcript; audio description (1.2.5) for any video that shows fretting hands, since visuals carry the information.
- **Audio-only feedback** (e.g. "clip!" beep, "recording started" chime) always has a visual and haptic counterpart.
- **Levels:** a visual input meter with clipping indicator (useful for HoH players setting input gain).

## 5. Cognitive and learning (dyslexia, ADHD, beginners)

- **Progressive disclosure:** default view = tab only (or tab + rhythm stems). Standard notation, chord diagrams, fingering, technique legend are opt-in layers. Beginner mode hides technique annotations the recognizer is unsure about.
- **Density control:** bars per line setting; "one line at a time" focus mode; dim everything except the current phrase during playback.
- **Consistent terminology (3.2.4):** pick one term set and use it everywhere: "string 1–6", "fret", "bar" (or "measure"—choose one), "loop", "uncertain". Put a glossary behind every technique abbreviation (h, p, /, \, b, r, PM, x) with a spoken/illustrated explanation.
- **Legend on demand:** tapping any tab symbol explains it in plain language.
- **Dyslexia:** avoid similar-looking abbreviations (h/b/p), allow font choice and spacing; don't use italics for meaning.
- **Error recovery (3.3.x):** unlimited undo for edits; recordings never destroyed by re-transcription (versions kept); clear "why was this marked uncertain" explanation.
- **Predictability (3.2.1/3.2.2):** changing tuning/capo shows a preview and asks whether to re-map frets—never silently rewrites the tab.
- **Consistent Help (3.2.6)** and **Accessible Authentication (3.3.8)**: local-first app should avoid accounts; if sync is ever added, no cognitive-function tests.
- **Short sessions / focus:** a looping practice mode with a single big "again" control suits ADHD practice patterns; avoid gamified timers that impose time limits.

## 6. Left-handed players

- **Tab does not mirror.** String order in tab is fixed (high string on top). Only **fretboard views and chord diagrams** mirror.
- Three distinct setups, each a setting:
  1. Left-handed instrument, strung normally for lefties → mirror fretboard/chord diagrams horizontally; tab unchanged.
  2. Right-handed instrument played flipped **without restringing** (e.g. Albert King, Dick Dale) → string order is reversed physically; string 1 is the low E under the hand. Offer a "reversed string order" option that relabels strings and chord diagrams; tab rendering can optionally flip top-to-bottom.
  3. Right-handed player → default.
- Mirroring must also apply to hand-position animations, finger-number diagrams, and any "which hand" wording ("fretting hand"/"picking hand" instead of "left/right hand").
- Transcription itself is hand-agnostic; only the display layer changes.

## 7. Colour

- Colour is never the only carrier of meaning (1.4.1). If strings or confidence are coloured, add label/position/shape.
- If string colouring is offered (common in beginner apps), use a **CVD-safe palette** such as Okabe–Ito (black, orange #E69F00, sky blue #56B4E9, bluish green #009E73, yellow #F0E442, blue #0072B2, vermillion #D55E00, reddish purple #CC79A7). Six strings need six hues; yellow fails contrast on white, so either draw coloured strings as thick lines with a darker outline or restrict yellow to dark mode. Check each against the background (≥ 3:1 for lines, 1.4.11) in light, dark and forced-colours.
- Confidence: use a single-hue lightness ramp *plus* a glyph (e.g. solid = confident, dashed ring = uncertain, "?" = very uncertain), not a red/green scale.
- Loop region and cursor: distinct in hue **and** in form (region = filled band with borders; cursor = vertical line with a caret).
- Verify with simulators (Sim Daltonism on macOS, Android "Simulate colour space", Chrome DevTools vision deficiencies).

## 8. Exports

- **MusicXML (for braille and other AT):** Music Braille Code 2015 translates TAB via staff notation, so every note must carry correct `<pitch>` (with the right octave for guitar's octave-transposing clef: treble clef with `clef-octave-change -1` for guitar, bass likewise), plus `<technical><string>`/`<fret>` as supplementary data. Also export `<staff-details>` with `<staff-lines>`, `<staff-tuning>` per string and `<capo>`, key/time signatures, `<harmony>` chord symbols, and correct `<beam>`/voices. Uncertain notes should not corrupt the export: keep the best candidate as the note and put uncertainty in a comment or `<other-notation>`/editorial marking so braille output stays clean. Test with SMB Online and BrailleMUSE; clean braille output is the acceptance test.
- **Standard notation + tab score as tagged PDF:** aim for PDF/UA-1 structure for everything textual (title, tuning, capo, legend, lyrics, chord names, page reading order, document language, bookmarks per section). Tab/notation glyphs cannot be meaningfully tagged; mark the score graphic as a Figure with alt text that points to the text-tab/instructions export and summarises (key, tempo, tuning, number of bars). Validate with **PAC 2024** and **veraPDF** (PDF/UA profile) and a manual screen-reader pass (NVDA + Acrobat, VoiceOver + Preview).
- **Text exports:**
  - ASCII tab (standard format, fixed-width, bar lines) for sighted and braille-display users who already use ASCII tab.
  - **Linear playing-instructions text** (same wording as the screen-reader "standard" level, one event per line, bar headings) — the most useful export for blind users; works with any screen reader, braille display, or TTS.
  - COULD: linear code close to BrailleTAB/Owens conventions, as a starting point for braille transcribers.
- **MIDI:** include tempo map, track names naming the instrument and tuning; useful for playback tools and MIDI-to-speech readers.
- **HTML export (COULD):** accessible HTML score (semantic bars, text instructions, SVG with `<title>`), readable on any device.

---

## 9. Ranked checklist

Priority tiers: MUST = needed for AA or for the core blind/motor use cases to work at all; SHOULD = strong benefit, plan for v1; COULD = later.

| # | Pri | Requirement | Maps to | Test method |
|---|---|---|---|---|
| 1 | MUST | Every tab event is a single accessible element with a label in string/fret/duration form; bar containers labelled "Bar n of N". | 1.3.1, 4.1.2; Apple HIG Accessibility; Android a11y | VoiceOver (iOS/macOS), TalkBack, NVDA/JAWS on Windows: swipe/arrow through 8 bars of a test song, compare utterances with the expected script. |
| 2 | MUST | Song-level announcement of instrument, tuning (low→high), capo and string-numbering convention; frets relative to capo by default. | 1.3.1, 3.3.2 | Same AT pass with drop-D + capo 2 song; verify announcement and that capo setting changes the reading. |
| 3 | MUST | Navigation by bar, event and note; "where am I" query gives bar/beat/section. iOS rotor + TalkBack custom actions for Bars / Uncertain / Techniques. | 2.4.x, 4.1.2 | VoiceOver rotor, TalkBack actions menu, keyboard on desktop. |
| 4 | MUST | Uncertain notes conveyed by text ("uncertain") in accessible name and by a non-colour visual shape; "next uncertain" navigation. | 1.4.1, 1.3.3, 4.1.2 | Greyscale screenshot check; AT pass; CVD simulator. |
| 5 | MUST | All playback/loop/tempo/record functions operable by keyboard and by HID page-turner keys (arrows, PgUp/PgDn) with remapping. | 2.1.1, 2.1.4 | AirTurn (or any BT keyboard) in HID mode on iPad, Android tablet, desktop; test all commands without touch. |
| 6 | MUST | Single-character shortcuts can be turned off or remapped; active only with score focus. | 2.1.4 | Keyboard test with a text field focused; remap test. |
| 7 | MUST | App speech suppressed during recording; recording state confirmed with haptic/visual cue; headphone guidance. Playback option to announce only between bars/loops. | (product) 1.4.2 related | Record with VoiceOver/TalkBack on; inspect captured audio for speech; subjective playback check. |
| 8 | MUST | Tab reflows (fewer bars per line) at 400% / 320 px without page-level horizontal scroll; follows Dynamic Type/font scale. | 1.4.4, 1.4.10 | Browser zoom 400% at 1280 px; iOS largest accessibility text size; Android font 200%, display size max. |
| 9 | MUST | Contrast: fret digits/text ≥ 4.5:1; string lines, bar lines, cursor, loop edges, confidence marks ≥ 3:1 in light, dark and high-contrast. | 1.4.3, 1.4.11 | Colour Contrast Analyser on screenshots of each theme; forced-colours check on Windows. |
| 10 | MUST | Nothing conveyed by colour alone (string identity, confidence, loop, selection). | 1.4.1 | Greyscale mode (iOS/Android colour filters). |
| 11 | MUST | Targets ≥ 24×24 CSS px everywhere; platform 44 pt / 48 dp for all controls; transport in practice mode ≥ 64 pt. | 2.5.8; Apple HIG; Material | Measure in Accessibility Inspector / Android Accessibility Scanner. |
| 12 | MUST | Every drag (loop handles, sliders, note edits) has a single-pointer alternative. | 2.5.7 | Complete loop setup and tempo change using only taps; with Switch Control. |
| 13 | MUST | Visible labels match accessible names so OS voice control works ("Tap Loop"). | 2.5.3 | iOS Voice Control, Android Voice Access, Windows Voice Access: run every transport command by voice during playback. |
| 14 | MUST | Visual metronome/count-in without flashes > 3/s over a large area; Reduce Motion alternative. | 2.3.1, 2.3.3 (AAA), 2.2.2 | Run at 240 BPM with sixteenths; PEAT/visual inspection; toggle Reduce Motion. |
| 15 | MUST | Auto-scrolling follow cursor can be paused/turned off independently of playback. | 2.2.2 | Manual. |
| 16 | MUST | MusicXML export carries correct pitch + octave-transposing clef, plus string/fret, staff-tuning, capo, chord symbols. | Interop (MBC 2015 §26.14) | Convert exports with SMB Online and BrailleMUSE; a braille music reader reviews 2 songs; round-trip into MuseScore and check with NVDA. |
| 17 | MUST | Linear text "playing instructions" export and ASCII tab export. | 1.1.1 (alt for score), EN 301 549 10.x | Open in Notepad/TextEdit with screen reader and a braille display; blind tester reads a bar back. |
| 18 | MUST | No auto-dismissing actionable toasts; destructive actions undoable; actions on pointer-up. | 2.2.1, 2.5.2, 3.3.4-style | Manual with slow Switch Control scanning. |
| 19 | SHOULD | Three verbosity levels (terse/standard/full) + chord-name mode, quick-toggle via rotor/action. | 3.3.5 (AAA) spirit | Blind tester task completion per level. |
| 20 | SHOULD | Repeated bars collapsed in speech ("same as bar 9"); "play this event/bar" from the AT cursor. | usability | AT pass on a song with repeats. |
| 21 | SHOULD | Stand/performance view: large digits (≥ 6–8 mm), thick lines, 7:1 text contrast, no chrome; one-line/one-bar focus mode. | 1.4.6 (AAA), 1.4.8 (AAA) | Read from 1 m distance test with low-vision tester; tablet on stand. |
| 22 | SHOULD | Haptic metronome and haptic confirmations for record/loop events. | Apple Haptics / Android haptics guidance | Manual on device and watch. |
| 23 | SHOULD | Tagged PDF: title, language, reading order, headings, legend/lyrics as text, score figure with alt text pointing to text export. | PDF/UA-1 (ISO 14289), EN 301 549 10.x | PAC 2024, veraPDF PDF/UA profile, NVDA + Acrobat reading pass. |
| 24 | SHOULD | Progressive disclosure: tab-only default, notation/diagrams/fingering as optional layers; symbol legend on tap. | 3.3.2, 3.2.4 | Beginner usability test; consistency audit of terms. |
| 25 | SHOULD | Left-handed settings: mirrored fretboard/chord diagrams; separate "reversed string order" (flipped, not restrung); "fretting/picking hand" wording. | inclusion | Visual check each mode; label consistency. |
| 26 | SHOULD | "Lock score" mode ignoring touches on the score while pedals/keyboard still work. | 2.5.2 related | Rest forearm on tablet during playback. |
| 27 | SHOULD | Pedal/MIDI mapping (MIDI CC/notes from foot controllers). | 2.1.1 extension | CoreMIDI/Android MIDI controller test. |
| 28 | COULD | CVD-safe string colouring (Okabe–Ito based) with shape backup; off by default. | 1.4.1, 1.4.11 | Sim Daltonism / Android colour-space simulation. |
| 29 | COULD | In-app push-to-talk voice commands in practice mode (not while recording); accelerometer "stomp" with UI alternative and off switch. | 2.5.4 | Test with amp noise; verify disable. |
| 30 | COULD | Braille-tab-like linear export (BrailleTAB/Owens-inspired) reviewed by a braille transcriber; accessible HTML score export. | — | Braille transcriber review. |

### Test matrix (minimum)

- iOS/iPadOS: VoiceOver (rotor, custom actions), Voice Control, Switch Control, Dynamic Type max, Increase Contrast, Reduce Motion, colour filters; Accessibility Inspector audit.
- Android: TalkBack (actions menu, headings), Voice Access, Switch Access, font/display size max, high-contrast text, colour correction; Accessibility Scanner.
- Desktop: NVDA + JAWS (Windows), VoiceOver (macOS), Orca (Linux, if targeted); Windows Contrast Themes; keyboard-only; 400% zoom.
- Hardware: one HID page turner (arrow + PgUp/PgDn modes), one MIDI foot controller, headphones for recording-with-AT test.
- Exports: SMB Online, BrailleMUSE, MuseScore round-trip, PAC 2024, veraPDF.
- People: at least one blind guitarist (screen reader), one low-vision player (stand distance), one player with limited hand mobility (pedal/voice only) per release cycle. Automated checks don't cover tab reading order or speech usefulness.

---

## Sources

- WCAG 2.2: https://www.w3.org/TR/WCAG22/ and Understanding docs: https://www.w3.org/WAI/WCAG22/Understanding/ (1.4.1 use-of-color, 1.4.10 reflow, 1.4.11 non-text-contrast, 1.4.12 text-spacing, 2.1.4 character-key-shortcuts, 2.2.2 pause-stop-hide, 2.3.1 three-flashes-or-below-threshold, 2.5.3 label-in-name, 2.5.4 motion-actuation, 2.5.7 dragging-movements, 2.5.8 target-size-minimum, 3.2.6 consistent-help, 3.3.8 accessible-authentication-minimum)
- EN 301 549 v3.2.1: https://www.etsi.org/deliver/etsi_en/301500_301599/301549/03.02.01_60/en_301549v030201p.pdf
- Lunar Tabs: https://prateektandon.com/lunar-tabs/ ; https://github.com/ProjPossibility/Lunar-Tabs-Desktop ; paper: https://www.researchgate.net/publication/268207116_Lunar_Tabs_An_Intelligent_Screen_Reader_Friendly_Guitar_Tab_Reader
- Guitar Tab Reader for JAWS: http://backtoworkblind.blogspot.com/2016/02/guitar-tab-reader-for-jaws.html
- AppleVis forum, accessible guitar tab reader: https://www.applevis.com/forum/macos-mac-apps/accessible-guitar-tab-reader
- AFB AccessWorld, Accessible Guitar Instruction and Music Resources: https://afb.org/aw/21/2/16906
- TrueFire VoiceOver optimisation: https://blog.truefire.com/announcements/truefire-optimizes-guitar-lessons-app-for-accessibility/
- AccessMusic (iOS): https://apps.apple.com/us/app/accessmusic/id6747299730
- Music Braille Code 2015 (BANA): https://www.brailleauthority.org/music/Music_Braille_Code_2015.pdf
- Owens System of Braille Tablature (NBA): https://www.nationalbraille.org/new-system-makes-guitar-tablature-accessible-for-blind-and-visually-impaired-musicians/ ; rules (rev. 2025-05-08): https://www.nationalbraille.org/wp-content/uploads/2025/05/Owens-Tablature-System-Rules_05-08-25.pdf
- BrailleTAB code: https://www.brailletab.com/en/braille-code/
- UKAAF, automated braille music transcription: https://www.ukaaf.org/wp-content/uploads/2024/03/Information-sheet-on-automated-braille-music-transcription_v14.pdf
- Sao Mai SMB / SMB Online: https://saomaicenter.org/en/smsoft/smb ; https://saomaicenter.org/en/smsoft/smb-online
- BrailleMUSE: https://braillemuse.net
- FreeDots: https://github.com/mlang/freedots
- Dancing Dots / GOODFEEL: https://en.wikipedia.org/wiki/Dancing_Dots
- Sound Without Sight braille music hub: https://soundwithoutsight.org/hub-articles/braille-music-hub/
- MuseScore accessibility: https://musescore.org/en/handbook/2/accessibility ; braille in MuseScore 4: https://www.mu.se/post/704tef5v71-accessibility-breakthrough-compose-in-br ; range-selection issue: https://github.com/musescore/MuseScore/issues/10228
- MusicXML 4.0 reference (technical/string/fret, staff-tuning, capo): https://www.w3.org/2021/06/musicxml40/
- Page turners in keyboard mode: https://newzik.com/en/resources-sheet-music-app/bluetooth-page-turner-sheet-music ; https://support.newzik.com/en/support/solutions/articles/77000152012-turning-pages-with-a-bluetooth-foot-pedal ; forScore devices: https://forscore.co/kb/category/17-devices-and-accessories/
- Visual/haptic metronomes for deaf musicians: http://bouncemetronome.com/features/accessibility/deaf-musicians ; https://www.soundbrenner.com/products/pulse-vibrating-metronome
- Apple accessibility (rotor, custom actions, HIG): https://developer.apple.com/design/human-interface-guidelines/accessibility ; https://developer.apple.com/documentation/uikit/uiaccessibilitycustomrotor ; https://developer.apple.com/documentation/objectivec/nsobject/1615150-accessibilitycustomactions
- Android accessibility (custom actions, collections, touch targets): https://developer.android.com/guide/topics/ui/accessibility/principles ; https://developer.android.com/reference/android/view/accessibility/AccessibilityNodeInfo.AccessibilityAction ; https://support.google.com/accessibility/android/answer/7101858
- Okabe–Ito palette: https://jfly.uni-koeln.de/color/
- PDF/UA and validators: https://pdfa.org/resource/iso-14289-pdfua/ ; PAC: https://pac.pdf-accessibility.org/ ; veraPDF: https://verapdf.org/
- ASCII tab: https://en.wikipedia.org/wiki/ASCII_tab
