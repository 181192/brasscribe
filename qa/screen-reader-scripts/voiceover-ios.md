# VoiceOver on iOS and iPadOS: Play acceptance script

This is an acceptance script for an app that is not built yet. Step IDs, expected strings and pass/fail rules are in [README.md](README.md).

**Setup**
- Settings → Accessibility → VoiceOver on. Add these rotor items: Actions, Headings, plus the app's custom rotors, which appear automatically.
- Run on an iPhone (portrait, then landscape for 1.3.4) and an iPad.
- iPad: also run with a hardware keyboard and **Full Keyboard Access** (see keyboard-desktop.md, section "iPad").
- Audit with Xcode Accessibility Inspector against the simulator or device, plus `performAccessibilityAudit()` in the UI tests. The iOS SDK isn't on the dev machine; run it in CI or on a Mac with Xcode.

| ID | Do | Expect | Pass if |
|---|---|---|---|
| S1 | Launch | "Brasscribe Play" then "Import audio or video, button" | |
| S2 | Double-tap Import → Files picker → choose; or share a file from Files/Voice Memos to Play ("Open in Play") | "Imported old-hundredth.wav, 4 minutes 6 seconds"; focus on the "What is this?" heading | also works via the share sheet |
| S3 | Double-tap Record; allow the microphone; after 5 s, a **two-finger double-tap (Magic Tap)** stops recording | "Recording started"; Magic Tap → "Recording stopped, …" | Magic Tap toggles record/stop here and play/pause in the player (`.accessibilityAction(.magicTap)`) |
| S4 | Swipe right through the options; double-tap "Brass band"; "Continue" | "Solo instrument, 1 of 4"…, then "selected"; "Continue, dimmed, button" before selection | |
| S5 | Continue; wait; lock the screen, unlock; Cancel → Stop; restart | progress announcements throttled; progress continues after unlock (or a clear message if it can't run in the background); "Transcription cancelled"; completion moves focus to the result heading | no announcement flood; background behaviour stated |
| S6 | Rotor → "Uncertain notes", swipe down; rotor → Actions, swipe down to "Listen to this bar", double-tap; "Mark as checked" | the vector string "bar 2, beat 1: B-flat 4, eighth note, uncertain"; "Playing bar 2, original"; "Checked. 229 left" | |
| S7 | Lineup menu → "Minimal band"; Apply | "Lineup, Full band, pop-up button"; "Arrangement ready" | |
| S8 | Rotor → "Parts" → "Solo Cornet"; double-tap; "Concert pitch" switch | "Solo Cornet part. Written pitch, Cornet in B-flat"; "Concert pitch, switch button, on" | |
| S9 | Magic Tap (play/pause); on "Speed", swipe up/down (adjustable); fill the loop fields 12/16 with the keyboard, "Set loop"; "Mute Solo Cornet" | "Speed, 100 percent, adjustable" → "95 percent"; "Loop set, bars 12 to 16"; "Mute Solo Cornet, selected" | no drag needed (2.5.7) |
| S10 | "Play along"; count-in; Magic Tap to stop | "Your part Solo Cornet is muted. Count-in 1 bar" | spoken count-in heard or visual counter present |
| S11 | Focus the score. Rotor "Bars" → swipe down ×11; "Beats"; "Notes"; "Parts". Actions → "Go to bar" → 82. Actions → "Read bar" | vector strings; "bars 82 to 88: rest, 7 bars" | swipe right leaves the score to the next element (no trap) |
| S12 | Export → format list → "Braille BRF" → Solo Cornet → share sheet → "Save to Files" | "Exported Solo Cornet as braille…"; the file appears in Files | the BRF opens with a braille display via a BRF-capable app (open question: which app) |
| S13 | Share a `.docx` to Play; start a full-band transcription with the companion offline | error messages announced (see README) | |
| S14 | Larger Accessibility Text to max (AX5); Bold Text; Reduce Motion; Increase Contrast; Differentiate Without Colour; Voice Control "Tap Play" | no truncation; cursor jumps; theme switches; "?" badge on uncertain notes; Voice Control hits Play by its visible label (2.5.3) | |

**Platform checks**
- Pinch-zoom has +/- buttons. Swiping between parts has a part picker (2.5.1).
- Touch targets are ≥ 44 pt. Check with Accessibility Inspector "hit region" or Xcode audit `.hitRegion`.
- Recording uses AVAudioEngine: the level meter carries `.accessibilityValue`.
- Sound from other apps is only captured through a user-started ReplayKit broadcast, which is explained in text.
