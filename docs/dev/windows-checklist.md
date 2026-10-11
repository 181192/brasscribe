# Windows Play: manual check of the Windows parity work

One run on a Windows 11 PC, with the engine paired (Bandroom or `engine` on another computer). The
work came from `feat/windows-parity` and was merged before any Windows run, so run this on `main`. It
covers the music stand, the Appearance setting with Pink, "What do you play?" with the trumpet and
percussion, the quiet-recording boost and the other parity fixes. Tick each line. If a step fails,
note the step number and what you saw, and stop at the first crash.

## 0. Build

1. In `apps/windows`, build the Rust core as the Windows CI job does, then run
   `dotnet build src/Brasscribe.Play -c Debug -p:Platform=x64 -p:RuntimeIdentifier=win-x64 "-p:ScribeFfiDll=<path to scribe_ffi.dll>"`.
   It must compile with no XAML errors. The XAML compiler runs only on Windows, and these files have
   never been compiled there:
   - `Views/ChooseOutputPage.xaml`: "Who played this?", the "Your part" lines and the tune choice
   - `Views/WhatIsThisPage.xaml`: the refused One instrument card and the percussion note
   - `Views/ReviewPage.xaml`: the empty or arranged title is bound
   - `Views/ScoreScreen.xaml`, `Views/MusicStandLayer.xaml`, `Views/MusicStandBand.xaml`: the stand
   - `Views/SeatPickerView.xaml`, `Views/WhatDoYouPlayPage.xaml`: the seat picker
   - `Dialogs/SettingsDialog.xaml`: Appearance, the instrument row and the About version button
   - `Dialogs/ExportDialog.xaml`, `Themes/Styles.xaml`
   - `design/dist/windows/BrasscribePinkTheme.xaml`: the Pink palette, linked as a Page
2. `dotnet test tests/Brasscribe.Play.Core.Tests` passes with the native core, and so do the CI job's
   smoke test and screen catalogue (`tools/Screenshots/catalogue.ps1`, with Axe.Windows through `tools/ScreenCheck play`).
3. Start the app with a fresh profile: delete `%LOCALAPPDATA%\Brasscribe\Play\settings.json` first.

## 1. My instrument, trumpet and percussion

1. The first run asks "What do you play?". The tiles run Cornet, **Trumpet** («Trompet», "in B♭" /
   «i B»), Soprano, … Percussion. Narrator reads the Trumpet tile as "Trumpet, in B flat".
2. Choose Trumpet. There is no "Which part?" and no "You read", and Continue saves it.
3. Record or import a band take (Brass band). On "Choose what to make", each lineup card says
   "Your part: Trumpet". "Who plays the tune?" is **not** shown.
4. Show the score. It opens on the Trumpet part, and the notice reads "The small band has no trumpet
   part. You get the Solo Cornet part, written for trumpet." The full band gives the "full brass
   band" form. In Norwegian it reads «Det lille bandet har ingen stemme for trompet. …».
5. Quartet: the part is 1st Cornet, with the same-key notice.
6. **Older engine** (a Bandroom or engine build from before the trumpet seat, if you have one): the
   take still succeeds. The output screen says "Brasscribe on your computer is too old to write for
   your instrument…", and the score opens on Solo Cornet with the same-key notice.
7. Settings › Your instrument › Change… › Euphonium. Take an Orchestra-with-soloist recording.
   "Who plays the tune?" appears, and choosing "You: Euphonium" puts the tune on the Euphonium part.
8. Settings › Your instrument › Percussion. Import a file and reach "What is this?". One instrument
   shows "Not for percussion yet", looks dimmed but can still be focused, and Continue stays off for
   it. The note under the cards explains why. **Change what I play** opens Settings. Choose
   Euphonium there and close: the refusal is gone at once. Brass band still works for percussion.
9. Empty part: with Percussion chosen, make a band score from a recording **without** drums. The
   Percussion part's source label says "Nothing to play in this arrangement", with the parts icon.
   Review opens on "Your part is empty", which Narrator reads once.

## 2. Music stand and the page-turn pedal

1. Open a multi-page score and press F (or F11): the stand opens full screen with two pages side by
   side on a landscape screen.
2. Press → / Page Down / ↓, then ← / Page Up / ↑, then Home and End. Each press turns the page
   (first/last with Home/End). The **controls do not appear**, and Narrator says "Page 3 of 6, bars
   17 to 32." (and "First page." / "Last page." at the ends).
3. Play. Press only page keys for 10 s: the controls stay hidden, and the page turns follow the music.
4. Press **Space**: the music pauses and the controls appear. Press Space again: it plays, and the
   controls **stay** (Tab or Space keep them until the next touch). Click the music once: they hide,
   and after the next click they hide by themselves 4 s later while playing.
5. Press **Tab**: the controls appear and focus moves to Leave, then through the layer. Shift+Tab
   goes back. Focus never gets stuck, and Esc leaves the stand.
6. Pedal: a Bluetooth page turner in arrow or page mode behaves like step 2. In Space mode it starts
   and stops the music (that is by design; Help says so).
7. Mouse wheel turns pages. A click on the music toggles the controls, and the first auto-hide shows
   the hint once.

## 3. Appearance and Pink

1. Settings › Appearance: Match system, Light, Dark. Each applies at once to the main window, the
   Settings dialog and the caption buttons, and focus stays on the combo box.
2. About: activate the version button five times quickly (click, then Space or Enter, then Narrator's
   activate). On the fifth, "🎺 Pink unlocked" shows for a few seconds and Narrator says it once.
   Appearance does **not** change by itself.
3. Pause 2 s between presses on a fresh profile: nothing unlocks.
4. Appearance now lists **Pink light** and **Pink dark** last. Choose Pink light: the chrome turns
   blush with plum text and a raspberry primary, and the caption glyphs are plum. The notation stays
   ink on paper, and the ? marks, the loop and the cursor keep their colours.
5. Choose Pink dark: the app turns Pink dark (bubblegum primary, coral errors) at once, whatever
   Windows' mode (Settings › Personalisation › Colours). Switching Windows' mode changes neither.
6. Turn on a Windows contrast theme (Aquatic, Desert): the app uses the system colours at once, and
   the contrast note shows. Turn it off: Pink comes back.
7. Quit with Pink dark chosen and start the app again: it opens in Pink dark, caption buttons
   included. A settings.json from an earlier version with `"Appearance": "pink"` opens in Pink light
   or Pink dark to match Windows' mode, and is rewritten.
8. Choose Light: Pink leaves every surface, including open flyouts, with no leftover pink brushes.
   Restart the app: Pink light and Pink dark are still listed.
9. Check Home, the score, the stand, Review, "Choose what to make", Share or print and Settings in
   Pink light and Pink dark. Look for unreadable text and for surfaces left in the old palette.
   Radio buttons, checks and toggles keep the ink accent; that is expected.

## 4. A quiet recording

1. Record a quiet take (a soft passage, or the microphone far away), or import a quiet audio file,
   and make a loud band score from it (Brass band, As played).
2. Switch between the band and the recording (Listen): the recording is about as loud as the band,
   not much softer, and never distorts or clips on its loudest notes.
3. Pause, change the lineup or difficulty so the score is re-arranged, and listen again: the recording
   still matches the band. Nothing jumps in level while it plays.
4. Slow the recording to 75 % and loop two bars: speed, position and loop behave as before the boost.
5. Do the same with a quiet **video**: the picture plays with the boosted sound, in sync, and seeking,
   speed and picture-in-picture still work. If the video plays at its own (quiet) level instead, the
   composition failed: note it.
6. A loud recording is still turned down to the band's level.

## 5. Narrator

Use `qa/screen-reader-scripts/narrator-windows.md` for the full script. For this branch:

1. "What do you play?": each tile has a name and its key line. Continue's hint is read when nothing
   is chosen.
2. "Choose what to make": "Who played this?" is a named combo box. The dimmed Full band card on a band
   take reads its reason, and so does the Quartet card on a solo take.
3. "What is this?" with Percussion: One instrument reads "Not for percussion yet" before its
   description.
4. The stand: page turns are announced. Entering and leaving are announced. Tab reaches the layer.
5. The About version is a button named "Version x.y.z", and the unlock is announced once.

## 6. 200 % text size

Settings › Accessibility › Text size 200 %, then restart the app.

1. "What do you play?": the tiles wrap and nothing is clipped, the Trumpet line included.
2. "Choose what to make": the cards grow, and the "Your part" lines and the tune choice wrap.
3. "What is this?": the refused card and the percussion note wrap. **Change what I play** is fully
   visible.
4. The stand: the controls card wraps upwards without clipping (design/music-stand.md §4.1), and the
   band's position text stays readable.
5. Settings: the Appearance box, the instrument row and the About version button stay inside the
   dialog.
6. Review: the "Your part is empty" and "Your part is arranged" cards wrap.

## Sign-off

- [ ] All sections pass. File anything that fails as a fix against `main`, with the step number.
