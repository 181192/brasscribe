# Keyboard-only script and shortcut list: Play (macOS, Windows, iPad) and Studio

This is an acceptance script for apps that are not built yet. Run it with **no pointer and no screen reader**, then repeat it with VoiceOver or NVDA on to check that the shortcuts don't conflict.

## Shortcut list

This list is published in Help (EN 301 549 12.1) and in the app's shortcut sheet: Cmd+/ on macOS, F1 → "Keyboard shortcuts" on Windows and Studio.

### Global (always active; always with a modifier)

| Action | macOS | Windows | Studio (browser) |
|---|---|---|---|
| Import file | Cmd+O | Ctrl+O | Ctrl/Cmd+O (in-page handler) |
| Record / stop recording | Cmd+Shift+R | Ctrl+Shift+R | – |
| Play / pause (from anywhere) | Cmd+Shift+Space, or the media Play/Pause key | Ctrl+Shift+Space, or the media key | Ctrl/Cmd+Shift+Space |
| Export | Cmd+E | Ctrl+E | Ctrl/Cmd+E |
| Go to bar | Cmd+G | Ctrl+G | Ctrl/Cmd+G |
| Switch to talking score / notation | Cmd+T | Ctrl+T (in-app; not a browser tab) | Alt+T (Ctrl+T opens a browser tab) |
| Settings | Cmd+, | Ctrl+, | – |
| Shortcut sheet | Cmd+/ | F1 | F1 or ? outside text fields |
| Close dialog / leave score | Esc | Esc | Esc |

### Score and player (only while the score view has focus)

| Action | macOS | Windows / Studio |
|---|---|---|
| Play / pause | Space | Space |
| Next / previous note | → / ← | → / ← |
| Next / previous beat | Option+→ / ← | Ctrl+→ / ← |
| Next / previous bar | Option+↓ / ↑ | Ctrl+↓ / ↑ (Studio: Alt+↓ / ↑) |
| Next / previous part | Option+Shift+↓ / ↑ | Ctrl+Shift+↓ / ↑ |
| First / last bar | Home / End (or Cmd+↑ / ↓) | Home / End |
| Next / previous uncertain note | U / Shift+U | U / Shift+U |
| Mark as checked | C | C |
| Read bar | R | R |
| Play this bar / play from here | P / Shift+P | P / Shift+P |
| Where am I (full verbosity) | W | W |
| Loop start / end at the current bar | [ / ] | [ / ] |
| Loop on/off | L | L |
| Speed −5% / +5% / reset | - / = / 0 | - / = / 0 |
| Mute / solo the current part | M / S | M / S |
| Count-in / metronome on/off | K / T | K / T |
| Zoom out / in / reset | Cmd+- / Cmd+= / Cmd+0 | Ctrl+- / Ctrl+= / Ctrl+0 |
| Leave the score | Tab / Shift+Tab / Esc | Tab / Shift+Tab / Esc |

**Rules** (2.1.4, 11.6.2)
- Single-character keys work **only while the score view has focus**.
- Settings → Keyboard can turn them off or remap them.
- Space on a focused button activates that button, as the platform does. It doesn't play.
- macOS Ctrl+arrows are Mission Control/Spaces, so macOS uses Option.
- No shortcut uses the VO keys (Ctrl+Option), the NVDA key (Insert/Caps Lock) or the Narrator key.
- In Studio, the score widget switches NVDA/JAWS to focus mode. Outside it, browse-mode quick keys stay with the screen reader.
- **Open question:** check Cmd+Shift+Space against Spotlight or input-source settings on the test Macs. Ctrl+Space is the input-source default, which is why it isn't used.

## Script

| ID | Do (keyboard only) | Pass if |
|---|---|---|
| K-1 | Launch. Press Tab repeatedly through the start screen | visible focus ring on every stop (2.4.7); the order is title → Import → Record → recent songs → Settings (2.4.3) |
| K-2 | Cmd/Ctrl+O, choose a file with the keyboard in the system picker | the file imports; focus goes to the "What is this?" heading |
| K-3 | Arrows in the "What is this?" radio group, Space/Enter, then Tab to Continue, Enter | selection works; Continue is enabled only after a choice |
| K-4 | During transcription: Tab to Cancel, Enter; confirmation dialog: Esc keeps going, Enter on "Stop" stops | focus returns to the Cancel button after Esc (2.4.3) |
| K-5 | After completion, focus is on the result heading. Tab to "Review" | |
| K-6 | U, U, Shift+U through the uncertain notes; C marks one as checked | the counter updates visually ("229 left") |
| K-7 | Output choices: Tab through the lineup, difficulty and key pop-ups; change them with arrows; Apply | |
| K-8 | Parts list: arrows, Enter opens the part; toggle concert pitch with Space on the switch | |
| K-9 | In the score, with the player bar visible, Tab and arrow to the last system on screen | the focused note is **never hidden** behind the player bar (2.4.11) |
| K-10 | Space play, Space pause; `-` ×5 → 75%; Cmd/Ctrl+G 12, [ ; Cmd/Ctrl+G 16, ] ; L | loop 12–16 is set with no mouse (2.5.7); the loop edge markers are visible |
| K-11 | M, S on the current part; K; T | toggle states visible in the mixer |
| K-12 | Tab out of the score; Shift+Tab back in | focus leaves and returns (2.1.2); the position is kept |
| K-13 | Play along: Tab to "Play along", Enter; Esc stops | count-in visible as numerals, no flashing |
| K-14 | Cmd/Ctrl+T to the talking score; arrows, Option/Ctrl+arrows | the text view shows the same strings as the vectors, one line per event; the focused line is highlighted |
| K-15 | Cmd/Ctrl+E → the format list with arrows → Braille BRF → Solo Cornet → the save dialog | the file is saved; a success message is visible and focus returns to the Export button |
| K-16 | Open a `.docx` | error text visible next to the Import button; focus goes to the error text or stays on Import, with the error announced |
| K-17 | Cmd/Ctrl+= to 400% notation zoom | the single-part view scrolls in one direction; the focus ring is still visible |
| K-18 | Settings → Keyboard: turn off single-key shortcuts; press U in the score | nothing happens; arrows still work |
| K-19 | Cmd+/ or F1 | the shortcut sheet opens; Esc closes it; focus returns |
| K-20 | Type "u" and "l" in the "Go to bar" field and in the loop fields | text is entered; no shortcut fires (2.1.4) |

### iPad with a hardware keyboard

- Run K-1 to K-20 with **Full Keyboard Access** off. The app's own focus system (`.focusable()`) and `.keyboardShortcut` handle it.
- Then run K-1, K-8, K-10 and K-15 with Full Keyboard Access **on**, so Tab/arrows move the system focus.
- Cmd-hold must show the shortcut overlay with every global shortcut.

### Android with a hardware keyboard or Chromebook

- Run K-1, K-3, K-8, K-10, K-12 and K-15. Compose `onKeyEvent` must handle arrows and Space in the score, and Tab must leave it.
- Ctrl+/ (Android keyboard shortcuts helper) lists the global shortcuts, published with `onProvideKeyboardShortcuts`.
