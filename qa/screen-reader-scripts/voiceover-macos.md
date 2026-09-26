# VoiceOver on macOS: Play acceptance script

This is an acceptance script for an app that is not built yet. Step IDs, expected strings and pass/fail rules are in [README.md](README.md).

**Setup**
- VoiceOver on (Cmd+F5). VO = Control+Option.
- Verbosity: default. Voice: the system English voice, then a Norwegian voice (e.g. Nora) for the nb run.
- Quick Nav **off** for the first run; repeat S11 with Quick Nav on and single-key Quick Nav on. Our single-key score shortcuts must not fire while VO single-key Quick Nav is active, or vice versa.
- Build under test: Play (SwiftUI, macOS target).
- Audit with Xcode Accessibility Inspector first (Audit tab: no warnings). This isn't possible on the dev machine without Xcode; run it on a Mac with Xcode.

| ID | Do | Expect (VoiceOver) | Pass if |
|---|---|---|---|
| S1 | Launch Play. VO+F2 twice (window chooser) | "Brasscribe Play, window"; VO+Right from the top reaches "Import audio or video, button" within 3 moves | title and first control correct |
| S2 | VO+Space on Import. In the NSOpenPanel choose `mikkel.wav` and press Return | open panel readable (system). Then "Imported mikkel.wav, 4 minutes 6 seconds" (announcement), and focus lands on the "What is this?" heading | announcement heard; focus not lost |
| S3 | Go to "Record", VO+Space; accept the microphone prompt; wait 5 s; VO+Space on "Stop recording" | "Recording started"; the level meter VO+Right: "Input level, good, level indicator"; "Recording stopped, …" | states announced; meter has a value |
| S4 | VO+Right through the options; VO+Space on "Solo instrument"; VO+Right to "Continue" | "Solo instrument, radio button, 1 of 4"…; "Continue, dimmed, button" before choosing, "Continue, button" after | positions and dimmed state heard |
| S5 | VO+Space Continue; wait; VO+Space "Cancel"; choose "Stop"; restart; wait for completion | progress announcements (`AccessibilityNotification.Announcement`) at 10% steps; "Transcription cancelled"; then "Transcription finished. …" and VO cursor on the result heading | ≤ 1 progress per 10 s; completion moves focus |
| S6 | VO+U → rotor "Uncertain notes" → Down arrow; VO+Cmd+Space (Actions) → "Listen to this bar"; then "Mark as checked" | "bar 2, beat 1: B-flat 4, eighth note, uncertain"; Actions menu lists "Listen to this bar, Mark as checked, Play this bar, Loop this bar"; "Checked. 229 left" | rotor exists; custom actions listed and working (EN 301 549 11.5.2.11–12) |
| S7 | Go to "Lineup" pop-up, VO+Space, choose "Minimal band"; "Apply" | "Lineup, Full band, pop-up button"; "Arranging…" then "Arrangement ready" | values heard |
| S8 | VO+U → rotor "Parts" → "Solo Cornet"; VO+Space; find "Concert pitch" switch, VO+Space | "Solo Cornet part. Written pitch, Cornet in B-flat"; "Concert pitch, on, switch" and "Concert pitch" announcement | mode announced once, not per note |
| S9 | Play (VO+Space); Pause; on "Speed", VO+Shift+Down to interact, then VO+Down/Up (or the slider's arrow keys); fill "Loop from bar" 12, "to bar" 16, "Set loop"; toggle "Loop"; "Mute Solo Cornet" | "Playing, bar 1" / "Paused, bar 5 beat 3"; "Speed, 95 percent, slider"; "Loop set, bars 12 to 16"; "Mute Solo Cornet, on, toggle button" | loop set without dragging; states heard |
| S10 | "Play along" VO+Space; listen to the count-in; Stop | "Your part Solo Cornet is muted. Count-in 1 bar"; spoken "1, 2, 3, 4" if "Speak count-in" is on | no flashing; stop heard |
| S11 | VO+Shift+Down into the score. VO+U rotors: "Bars" (Down to bar 12), "Beats", "Notes", "Parts". Go to bar via Actions → "Go to bar" → 82. Actions → "Read bar", "Play this bar" | strings match the vectors: "bar 12, beat 1: …"; "bars 82 to 88: rest, 7 bars" | exact match; VO+Shift+Up leaves the score |
| S12 | Cmd+E (Export); VO+Right through the formats; select "Braille BRF", part "Solo Cornet"; Save in the NSSavePanel | format list with 7 items; "Exported Solo Cornet as braille, file Mikkel - Solo Cornet.brf" | file exists; with a braille display connected, the BRF opens in a BRF viewer (open question: which viewer on macOS) |
| S13 | Import `notes.docx`; disconnect the engine and start a transcription that needs it | error text announced; VO+Right reaches the message text | announced and reachable |
| S14 | System Settings → Accessibility → Display: Increase contrast, Reduce motion; text size (Settings → Accessibility → Display → Text size, per app); repeat S8–S9 | theme switches; cursor jumps instead of gliding; no truncation | as README |

**Platform checks**
- The score view uses `.accessibilityElement(children: .contain)` with custom rotors, and exposes the current note in `.accessibilityValue`.
- The player bar has `.accessibilityAddTraits(.startsMediaSession)` on Play.
- The playback position uses `.updatesFrequently`, and does **not** post an announcement every beat.
- Audio cues are never the only feedback (EN 301 549 4.2.4).
