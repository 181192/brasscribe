# Screen-reader acceptance scripts: Brasscribe Play

These are **acceptance scripts for apps that are not built yet**. They define what "done" means for the accessible flow. Run them on every release candidate, one file per screen reader:

| Script | Platform | Screen reader |
|---|---|---|
| [voiceover-macos.md](voiceover-macos.md) | Play for macOS | VoiceOver |
| [voiceover-ios.md](voiceover-ios.md) | Play for iOS/iPadOS | VoiceOver |
| [talkback-android.md](talkback-android.md) | Play for Android | TalkBack |
| [narrator-windows.md](narrator-windows.md) | Play for Windows | Narrator |
| [nvda-windows.md](nvda-windows.md) | Play for Windows, and Studio in Firefox/Chrome | NVDA |
| [keyboard-desktop.md](keyboard-desktop.md) | macOS, Windows, Studio | none (keyboard only), plus the shortcut list |

## Test material

- `qa/fixtures/`: a short solo clip (8 bars, one instrument, with a known free-time opening), prepared locally and never committed as audio. **Open:** it doesn't exist yet. Until it does, use the first 60 s of `data/mikkel/mikkel.wav`, which contains the free-time intro.
- Expected score for spot checks: the Mikkel golden output, with the Solo Cornet part:
  - bar 2 beat 1: written B♭4, eighth, uncertain
  - bars 82–88 rest

## Shared flow (step IDs used by every script)

The expected announcements are in English. Run each script once in nb as well; the nb strings come from the String Catalog and [talking-score-spec.md](../../docs/accessibility/talking-score-spec.md). "Must contain" means the tokens must appear in this order. Platform role words ("button", "knapp", "adjustable") come after them.

| ID | Step | Must contain (en) |
|---|---|---|
| S1 | Launch | window/screen title "Brasscribe Play"; first focus on the main heading or the "Import" button |
| S2 | Import a file | "Import audio or video, button". The system file picker opens and is readable. After choosing: "Imported mikkel.wav, 4 minutes 6 seconds" |
| S3 | Record from the microphone | "Record, button" → after the permission prompt → "Recording started". The level meter has a value ("input level, good"). "Stop recording, button" → "Recording stopped, 1 minute 2 seconds" |
| S4 | "What is this?" | heading "What is this?"; 4 options, each with a position: "Solo instrument, 1 of 4", "Brass band, 2 of 4", "Orchestra with soloist, 3 of 4", "Pop or rock, 4 of 4"; "Continue, button" is dimmed until one is chosen |
| S5 | Transcribe, progress, cancel | status announcements without moving focus: "Transcribing, 10 percent, about 3 minutes left", then at most one every 10 s or per 10% step. "Cancel, button" → confirmation "Stop transcription? Keep going / Stop" → "Transcription cancelled". Start again → on completion "Transcription finished. 128 bars, 17 parts, 230 notes to review", and focus moves to the result heading |
| S6 | Review uncertain notes | "Review, 230 uncertain notes". "Next uncertain note" gives a talking-score announcement ending in "uncertain". The actions "Listen to this bar" (plays original then score, looped; "Playing bar 2, original") and "Mark as checked" ("Checked. 229 left") exist. Free-time bars announce "Ad lib, free time, bars 1 to 4…" |
| S7 | Choose output | "Lineup, Full band, pop-up button"; "Difficulty, Standard"; "Key, C major concert"; "Apply, button" → "Arranging…" → "Arrangement ready". Choices are remembered on re-run (3.3.7) |
| S8 | Parts | "Parts, list, 18 items"; "Solo Cornet, 2 of 18"; opening it: "Solo Cornet part. Written pitch, Cornet in B-flat"; the toggle "Concert pitch, switch, off" → on: "Concert pitch" |
| S9 | Playback, loop, speed | "Play, button" → "Playing, bar 1" (status). Pause → "Paused, bar 5 beat 3". "Speed, 100 percent, adjustable": step down → "95 percent". Loop without dragging: "Loop from bar, text field" 12, "to bar" 16, "Set loop" → "Loop set, bars 12 to 16". "Loop, switch, on". "Mute Solo Cornet, toggle, off" → "on". "Count-in, switch"; "Metronome, switch" |
| S10 | Play-along | "Play along, button" → "Your part Solo Cornet is muted. Count-in 1 bar". Count-in numbers are **spoken or shown**, both configurable. No flashing. Stop → "Stopped" |
| S11 | Talking-score navigation | next/previous note, beat, bar, part, uncertain note; go to bar 82 → "bars 82 to 88: rest, 7 bars"; read bar; play this bar. The strings must match [talking-score-vectors.json](../../docs/accessibility/talking-score-vectors.json) exactly for the vector cases |
| S12 | Export | "Export, button" → a format list containing: MusicXML score, MusicXML parts, PDF, MIDI, Audio, Talking score text, Braille BRF. Choose "Braille BRF", part "Solo Cornet", then "Save" → "Exported Solo Cornet as braille, file Mikkel - Solo Cornet.brf". The BRF opens in a BRF viewer or on a braille display with part and bar structure intact. Also "Talking score text" → an HTML file with headings per part and bar |
| S13 | Errors | unsupported file: "Can't open notes.docx. Choose an audio or video file." Companion missing: "Can't reach the computer engine. Start Brasscribe on your computer, then try again." DRM source: "This app blocks recording. Import a file instead." Each is announced when it appears and is reachable afterwards |
| S14 | Preferences | at the largest text size, every S1–S12 control is reachable and nothing is truncated. Reduced motion stops cursor animation. High contrast / increase contrast switches the theme. Nothing overrides the system screen-reader speech rate or verbosity |

## Pass / fail

**Pass:** every step above completes eyes-free and every "must contain" string is heard.

**Fail (blocker):** any of these.
- A control without a name ("button", "unlabelled").
- A step that needs sight, or a mouse or touch drag.
- Focus lost: it jumps to the top of the window or to nothing after an action, a dialog closing, or a transcription finishing.
- A keyboard or gesture trap.
- A state change that is **not** announced within 2 s (play, pause, loop, mute, export done, error).
- A talking-score vector mismatch.

**Fail (major):**
- Wrong order of announcement tokens.
- Progress announced more often than every 10 s.
- Role or state missing (a toggle announced as a button without on/off).
- nb string missing (English read in the nb run).
- Note names pronounced wrongly by the nb voice (e.g. "Ess" read as the letter S; log the voice and engine).

**Minor:** verbose or duplicated speech, or a redundant hint.

## Result record (copy per run)

```
Script: voiceover-ios.md    App build: …    OS: …    Screen reader version: …    Voice: …    Lang: en|nb
Step | Result (pass/blocker/major/minor) | Heard (verbatim) | Note
S1   |                                    |                  |
…
```

Store results under `qa/results/<platform>/<date>.md`.
