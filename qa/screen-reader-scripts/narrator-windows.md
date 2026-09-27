# Narrator on Windows: Play acceptance script

This is an acceptance script for an app that is not built yet. Step IDs, expected strings and pass/fail rules are in [README.md](README.md).

**Setup**
- Narrator on (Win+Ctrl+Enter). The Narrator key is Caps Lock or Insert.
- Keys:
  - Tab / Shift+Tab: focus
  - Narrator+→/←: next/previous item in scan mode (Narrator+Space toggles scan mode)
  - Narrator+Enter: primary action
  - Narrator+0: report the current item
- Windows 11, current build. Narrator voice English, then "Microsoft Jon"-class nb voice (Microsoft nb-NO voice) for the nb run.
- First run **Accessibility Insights for Windows**:
  - FastPass: automated checks plus tab stops
  - Live Inspect: check each custom control's patterns
- In CI, Axe.Windows runs in the UI tests.

| ID | Do | Expect | Pass if |
|---|---|---|---|
| S1 | Launch | "Brasscribe Play, window"; Tab → "Import audio or video, button" | `AppWindow.Title` set |
| S2 | Enter on Import → FileOpenPicker → choose | "Imported old-hundredth.wav, 4 minutes 6 seconds" through a UIA notification (`RaiseNotificationEvent`); focus on the "What is this?" heading | |
| S3 | Record (microphone privacy prompt) → Stop | "Recording started"; meter "Input level, good" (`IRangeValueProvider` or `IValueProvider`); "Recording stopped…" | |
| S4 | Arrows in the radio group | "Solo instrument, radio button, not selected, 1 of 4"; "Continue, button, unavailable" | |
| S5 | Continue; wait; Cancel → Stop; restart; wait | progress notifications with `AutomationNotificationProcessing.MostRecent` (throttled); "Transcription cancelled"; completion moves focus to the result heading | |
| S6 | Score focused: U (next uncertain note); Shift+F10 (context menu) → "Listen to this bar", "Mark as checked" | the vector string (the peer's Value changes, plus a notification); "Checked. 229 left" | context menu reachable by keyboard |
| S7 | Lineup ComboBox (Alt+↓) → Minimal band → Apply | "Lineup, combo box, Full band, collapsed"; "Arrangement ready" | `IExpandCollapseProvider` |
| S8 | Parts ListView → Solo Cornet → Enter; Concert pitch ToggleSwitch | "Solo Cornet part. Written pitch, Cornet in B-flat"; "Concert pitch, toggle switch, on" | |
| S9 | Ctrl+Shift+Space play/pause (global); Speed slider with arrows; loop NumberBoxes 12/16 + "Set loop"; Mute ToggleButton | "Speed, slider, 95 percent" (`SmallChange` = 5); "Loop set, bars 12 to 16"; "Mute Solo Cornet, toggle button, pressed" | |
| S10 | Play along; Stop | as README | |
| S11 | Tab into the score. →/← note, Ctrl+→/← beat, Ctrl+↓/↑ bar, Ctrl+Shift+↓/↑ part, Ctrl+G 82, R read bar, P play bar | vector strings; Tab leaves the score (2.1.2) | Narrator doesn't swallow the arrows. **Open question:** Narrator scan mode must be off inside the score; confirm the peer's control type (custom/list) lets Narrator pass arrow keys through |
| S12 | Ctrl+E → Braille BRF → Solo Cornet → FileSavePicker | "Exported Solo Cornet as braille…" | file saved |
| S13 | Open a .docx; companion off (not relevant on desktop, where the local engine runs; instead stop the engine process); try WASAPI loopback of a DRM stream | error announcements | |
| S14 | Settings → Accessibility: text size 225%, contrast theme "Night sky" and "Desert", Animation effects off; Windows Voice Access "Click Play"; Magnifier at 400% following keyboard focus | no clipping; system colours used (`SystemColorWindowTextColor` etc.); cursor jumps; Magnifier follows the focused note (the peer returns `BoundingRectangle`) | |

**Platform checks**
- The score is a custom `FrameworkElement`. Its `OnCreateAutomationPeer` returns a peer:
  - `AutomationControlType.List` (or `Custom`), with children peers per visible event (`ListItem`)
  - `IValueProvider.Value` = the current announcement
  - `IScrollProvider`
- Mixer rows: `IToggleProvider` for mute/solo.
- Speed: a `Slider` (built-in `IRangeValueProvider`).
- No `AccessibilityView="Raw"` on anything interactive.
- Focus visuals: `UseSystemFocusVisuals`, High Visibility.
