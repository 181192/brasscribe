# TalkBack on Android: Play acceptance script

This is an acceptance script for an app that is not built yet. Step IDs, expected strings and pass/fail rules are in [README.md](README.md).

**Setup**
- TalkBack on (Settings → Accessibility → TalkBack), current Android Accessibility Suite. Note the TalkBack version in the record.
- Run on a phone and a tablet.
- Gestures:
  - swipe right/left: next/previous item
  - double-tap: activate
  - TalkBack menu: three-finger tap, or the "swipe down then right" gesture, depending on version and settings
  - **reading controls**: swipe up/down; change the control with three-finger swipe up/down, or swipe up then down
  - custom actions: Actions in the TalkBack menu, or the "Actions" reading control
- First run Accessibility Scanner (Google) on every screen. It reports touch target, contrast, labels and clickable items. Also run `AccessibilityChecks.enable()` in Espresso/Compose UI tests in CI.
- No emulator or device is available on the dev machine, so this needs a device run.

| ID | Do | Expect | Pass if |
|---|---|---|---|
| S1 | Launch | "Brasscribe Play"; "Import audio or video, Button" | |
| S2 | Double-tap Import → system picker (Storage Access Framework) → choose; also Share → Play from Files | "Imported old-hundredth.wav, 4 minutes 6 seconds"; focus on the "What is this?" heading (`paneTitle` / heading) | |
| S3 | Record → grant the RECORD_AUDIO permission dialog → Stop | "Recording started" (live region polite); level meter: "Input level, good" (`stateDescription`); "Recording stopped, …" | |
| S4 | Swipe through the radio group | "Not selected, Solo instrument, Radio button, 1 of 4" (`collectionItemInfo`); "Continue, Button, disabled" | positions heard |
| S5 | Continue; wait; Cancel → Stop; restart; wait | progress through `progressBarRangeInfo` plus a polite live region, throttled; "Transcription cancelled"; completion moves accessibility focus to the result heading | foreground-service notification text is readable too |
| S6 | Actions → "Next uncertain note"; Actions → "Listen to this bar"; "Mark as checked" | the vector string; "Playing bar 2, original"; "Checked. 229 left" | custom actions present (`CustomAccessibilityAction`) |
| S7 | Lineup dropdown → Minimal band → Apply | "Lineup, Full band, Dropdown menu" (Role.DropdownList); "Arrangement ready" | |
| S8 | Parts list → "Solo Cornet, 2 of 18"; open; Concert pitch switch | "Solo Cornet part. Written pitch, Cornet in B-flat"; "On, Concert pitch, Switch" | |
| S9 | Play; Pause; Speed slider: swipe up/down with the "adjust" reading control, or volume keys while focused; loop fields; Set loop; Mute toggle | "Speed, 100 percent, Slider" → "95 percent" (`setProgress`); "Loop set, bars 12 to 16"; "On, Mute Solo Cornet, Toggle" | no drag |
| S10 | Play along; count-in; Stop | as README | |
| S11 | Swipe right through the score list (one node per event, `traversalIndex` in time order). Actions → "Next bar", "Next beat", "Next part", "Go to bar" → 82, "Read bar", "Play this bar" | vector strings; "bars 82 to 88: rest, 7 bars" | swipe past the last event leaves the score |
| S12 | Export → Braille BRF → Solo Cornet → Save (SAF create document) | "Exported Solo Cornet as braille…" | file saved; opens in a BRF-capable reader (open question) |
| S13 | Share a .docx; companion offline; try capturing a streaming app that opts out of AudioPlaybackCapture | error texts announced; for opt-out apps: "This app blocks recording. Import a file instead." (not silent recording) | |
| S14 | Font size and display size at max; Remove animations; high-contrast text / contrast level (Android 14+); Switch Access run of S2–S9; Voice Access "Tap Play" | no truncation (`sp`, no fixed heights); cursor jumps; theme follows `UiModeManager.getContrast()`; Switch Access reaches every control; Voice Access matches visible labels | |

**Platform checks**
- Touch targets are ≥ 48 dp (`minimumInteractiveComponentSize`).
- No `clearAndSetSemantics` that drops the note value.
- Merged semantics for part rows: name + mute + solo read as one item with custom actions, or as separate focusable toggles. Pick one design and keep it consistent.
- Check TalkBack's nb voice (Google TTS nb-NO) for "Ess 5", "Ass 4", "H 4" (spec open question 5).
