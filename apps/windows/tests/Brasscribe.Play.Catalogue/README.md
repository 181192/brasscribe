# Screen catalogue (Play for Windows, and Bandroom for Windows)

Every screen of Brasscribe Play for Windows with sample content, in every appearance, with its checks, and a
screenshot of each to look at. Bandroom for Windows has the same catalogue over its views (below).
Windows only: CI runs both on every pull request that reaches the apps (`.github/workflows/windows.yml`).

## How it runs

The catalogue is the app itself, built as its own test host: `-p:BrasscribeCatalogue=true` adds the tests in this
folder, MSTest and the Microsoft Testing Platform to `src/Brasscribe.Play` and builds into `bin/catalogue` and
`obj/catalogue`, apart from the app's own build. `App.OnLaunched` hands the start to `CatalogueHost.cs`, which runs
the test platform in the app's process; each `[UITestMethod]` runs on the app's UI thread. Nothing of this is in the
app's own build (`App.RunCatalogue` is a partial method without a body there).

For each screen (the scenes of `PreviewScenes`, and Settings) a test composes the app's window as a start does
(`App.Compose`), with settings kept in memory, shows the screen, and then for each Appearance choice of the run sets
it in the settings, as a person does in Settings › Appearance, waits until the screen is the one asked for and keeps
still (below) and takes:

- a screenshot of the window's client area as it is on screen (`PrintWindow`; `RenderTargetBitmap` drew an open
  dialog half transparent, as at the start of its opening animation, and without the dimming behind it);
- the contrast of every text and icon on it, measured on the screenshot: 4.5:1 for body text, 3:1 for large text and
  icons (`tools/ScreenCheck.Core/Contrast.cs`), and text cut off (`TextBlock.IsTextTrimmed`, so only text whose
  trimming is set: text clipped by its container without trimming is not seen);
- an exception the app did not catch while the screen was open (its `crash.log`; the app then says "Something went
  wrong").

Then the Axe.Windows rules and a walk with Tab (the focus lands on something shown, it comes back round, and every
button, box, link and slider in the window is reached, or only in an open modal dialog when every stop was inside it;
Tab caught in one pane is reported, not taken as the scope; list, tab and menu items and radio buttons are left out,
since the arrow keys reach them inside their group) run on each screen in Light, from another process (`tools/ScreenCheck
play`), on the app's own build with one start per screen (`--show SCENE`): the app built as the test host ended with an
access violation while Axe.Windows read it, which the app's own build does not.

### When a screenshot is taken

A picture of a window that keeps still is not yet a picture of the screen asked for: a window before its first frame,
or a screen whose dialog has not opened, keeps perfectly still. So each take (250 ms apart, after two rendered
frames) counts only when all of this holds, read off the app before and after the picture, with the same answer
both times (`ScreenCatalogue.Read`, `tools/ScreenCheck.Core/SteadyShot.cs`):

- the screen's window is the app's window, shown, in front, and its content has loaded at the window's size;
- the frame shows the page of the step asked for, and exactly the dialog asked for is open and has opened (its
  `Opened` event), or none at all;
- the window and the dialog have the theme of the Appearance choice, with the Pink palette merged or not as the choice
  says, and every score has its notation drawn;
- the text is where it was before the picture, and it is drawn in the picture (at least half of the texts have ink
  where the app says they are: a window that has presented nothing is one flat colour);
- a dialog's picture is not the picture of the screen taken just before the dialog was opened.

The screenshot is the last of six such takes in a row with the same pixels. A screen that does not get there in 30 s
is **not taken**: the run says which condition it was waiting for (`screen not taken: …`), its last picture goes to
`not-taken\` to look at, and the catalogue fails with 3 instead of comparing a picture of something else. The run's
`takes-<run>.log` (also in the job log) says how long each screen took and what it waited for.

Windows' animation effects are off for every run (`tools/ScreenCheck system --animations off`, the switch in
Settings › Accessibility › Visual effects), so dialogs, pages and theme changes are on screen at once; the app checks
that the setting reached it, as it does for the contrast theme and the text size.

Dialogs (Settings, Share or print) are opened again in each choice, so they show it, and the next one is opened only
when the one before has gone. The run in bokmål sets the
language through `BRASSCRIBE_CATALOGUE_LANG` (the test platform runs the tests in a process of its own, with its own
arguments), and checks that the app's strings are in bokmål; `tools/ScreenCheck play` checks the same of the app's own
build started with `--lang nb-NO`.

`tools/Screenshots/catalogue.ps1` runs the catalogue once per language, contrast theme and text size, which Windows
settles when an app starts:

| Run | Appearance choices | Screenshot names |
|---|---|---|
| English | Light and Dark; Pink light and Pink dark on First run, Home, the score, Check the notes, Share or print and Settings | `home--light`, `home--pink-dark` |
| Bokmål (`nb-NO`) | Light | `home--nb-light` |
| A contrast theme on in Windows | Match system, and also Pink dark, which must look the same (the contrast theme wins); one screenshot is kept | `home--contrast` |
| Text size 200 % (Settings › Accessibility › Text size) | Light | `home--text200-light` |

The contrast theme, the text size and animation effects are this user's Windows settings (`tools/ScreenCheck system`):
the contrast theme is turned off after its run, and the text size and animation effects are put back to what they
were. Run the script on a CI runner or a Windows VM, not on a PC you use.

`tools/ScreenCheck play` also starts the app's own build with `--theme pink-light` and `--theme pink-dark` on Home and
compares it with the catalogue's Home after Pink was chosen in Settings: a palette chosen while the app runs must reach
every part of the window (finding `theme-at-start`).

## What it answers

```powershell
tools/Screenshots/catalogue.ps1 -Exe <BrasscribePlay.exe> -Out out -FfiDll <brasscribe_ffi.dll>
```

`out\` gets `shots\` and `findings.md`. Exit codes: 0 every check passed; 2 a check found something new; 3 the
screenshots could not be taken (a screen that was not taken counts: one that was not the screen asked for, or did not
keep still).

The screenshots are the `windows-screenshots` and `bandroom-windows-screenshots` artefacts of a pull request's run, to
look at; no check waits for them, and none is kept in git. After a merge, CI compares the pictures on `main` with those
of the `main` before it and lists changed screens in an issue
([docs/dev/verify.md](../../../../docs/dev/verify.md#screenshots)).

`known-findings.json` lists findings that are accepted for now, each with the issue that tracks it and why (`check`,
`shot` and `what` are regular expressions over a finding); an entry without its issue is refused, and one that
matches nothing any more is listed in `findings.md` to be removed.

## Bandroom for Windows

`apps/bandroom/windows/tools/Screenshots/catalogue.ps1` does the same for Bandroom with one start of the app per view
(`tools/ScreenCheck bandroom`: `--show VIEW [--state STATE] --theme --lang`, sample content, no engine): English in
Light and Dark, bokmål, a contrast theme and 200 % text, each in Light; then Axe.Windows and Tab in Light, after every
screenshot, since once a Tab has been pressed Windows draws keyboard focus rectangles in the windows started later.
Where its text is comes from UI Automation, so icons (which UI Automation does not list) are not measured, and cut-off
text is not checked. A view is taken from outside its process (`tools/ScreenCheck/WindowShot.cs`), with the same rule
as above over what can be read from there: the process runs, the window is shown with the same place and size before
and after each take, its text is drawn in the picture, and six takes in a row are the same; otherwise the view is not
taken (3).
Its accepted findings are in `apps/bandroom/windows/tools/Screenshots/known-findings.json`.

## Off Windows

`tools/check-macos.sh` type-checks the catalogue build (`tools/CodeBehindCheck -p:BrasscribeCatalogue=true`), builds
`tools/ScreenCheck` and runs `tools/ScreenCheck.Tests`: the checks on pictures, the rule for when a screenshot is
taken, the comparison and the verdict, each shown failing on a picture made for it.
