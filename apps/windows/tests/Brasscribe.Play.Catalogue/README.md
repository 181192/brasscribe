# Screen catalogue (Play for Windows, and Bandroom for Windows)

Every screen of Brasscribe Play for Windows with sample content, in every appearance, with its checks, and
screenshots compared with the merge base. Bandroom for Windows has the same catalogue over its views (below).
Windows only: CI runs both on every pull request that reaches the apps (`.github/workflows/windows.yml`).

## How it runs

The catalogue is the app itself, built as its own test host: `-p:BrasscribeCatalogue=true` adds the tests in this
folder, MSTest and the Microsoft Testing Platform to `src/Brasscribe.Play` and builds into `bin/catalogue` and
`obj/catalogue`, apart from the app's own build. `App.OnLaunched` hands the start to `CatalogueHost.cs`, which runs
the test platform in the app's process; each `[UITestMethod]` runs on the app's UI thread. Nothing of this is in the
app's own build (`App.RunCatalogue` is a partial method without a body there).

For each screen (the scenes of `PreviewScenes`, and Settings) a test composes the app's window as a start does
(`App.Compose`), with settings kept in memory, shows the screen, and then for each Appearance choice of the run sets
it in the settings, as a person does in Settings › Appearance, waits until the screen keeps still and takes:

- a screenshot (`RenderTargetBitmap` of the window, with an open dialog drawn on top where it is);
- the contrast of every text and icon on it, measured on the screenshot: 4.5:1 for body text, 3:1 for large text and
  icons (`tools/ScreenCheck.Core/Contrast.cs`), and text cut off (`TextBlock.IsTextTrimmed`, so only text whose
  trimming is set: text clipped by its container without trimming is not seen);
- in the first choice of the English run, from another process (`tools/ScreenCheck scan`, so UI Automation never
  calls into its own process): the Axe.Windows rules, and a walk with Tab (the focus lands on something shown, it comes
  back round, and every button, box, link and slider on screen is reached; list, tab and menu items and radio buttons
  are left out, since the arrow keys reach them inside their group).

A screen that does not keep still for 1.5 s within 20 s (something on it moves) is kept in `unsteady\` and not compared.

`tools/Screenshots/catalogue.ps1` runs the catalogue once per language, contrast theme and text size, which Windows
settles when an app starts:

| Run | Appearance choices | Screenshot names |
|---|---|---|
| English | Light, Dark, Pink light, Pink dark | `home--light`, `home--pink-dark` |
| Bokmål (`--lang nb`) | Light, Dark | `home--nb-light` |
| A contrast theme on in Windows | Match system, Light, Dark, Pink dark: all must look the same (the contrast theme wins), and one screenshot is kept | `home--contrast` |
| Text size 200 % (Settings › Accessibility › Text size) | Light | `home--text200-light` |

The contrast theme and the text size are this user's Windows settings (`tools/ScreenCheck system`), turned off again
after their run: run the script on a CI runner or a Windows VM, not on a PC you use.

## What it answers

```powershell
tools/Screenshots/catalogue.ps1 record  -Out out -FfiDll <brasscribe_ffi.dll>
tools/Screenshots/catalogue.ps1 compare -Out out -FfiDll <brasscribe_ffi.dll> [-Base <commit>]
```

`compare` takes the screenshots at the base (the merge base with `origin/main` by default) on the same machine, without
the checks, then here with them. `out\` gets `shots\`, `findings.md` and `report\` (`index.html` with before, the
difference and after for each changed screen, `summary.md`, `result.json`). A pixel counts as changed as in Studio's
catalogue, and a screen with 4 or fewer changed pixels is within the noise floor. Exit codes, as for the other apps'
catalogues: 0 nothing changed; 1 a screen changed, appeared or went away; 2 a check found something new; 3 the
screenshots could not be taken, here or at the base (nothing was compared). A commit without a catalogue has nothing to
compare with: every screen is new and nothing counts as changed.

In CI a changed screen fails the job `screenshots` unless the pull request has the label `screenshots-changed` (read
when that job runs, with retries; adding or removing the label starts CI again). The label never lets 2 or 3 through.
`windows.yml` started by hand takes `screenshots_base` to compare with any commit. The images are in the
`windows-screenshots` and `bandroom-windows-screenshots` artefacts; no screenshot is kept in git.

`known-findings.json` lists findings that are accepted for now, each with why (`check`, `shot` and `what` are regular
expressions over a finding); an entry that matches nothing any more is listed in `findings.md` to be removed.

## Bandroom for Windows

`apps/bandroom/windows/tools/Screenshots/catalogue.ps1` does the same for Bandroom with one start of the app per view
(`tools/ScreenCheck bandroom`: `--show VIEW [--state STATE] --theme --lang`, sample content, no engine): English in
Light and Dark (Axe.Windows and Tab in Light), bokmål, a contrast theme and 200 % text, each in Light. Where its text
is comes from UI Automation, so icons (which UI Automation does not list) are not measured, and cut-off text is not
checked. The base is Bandroom built at the merge base, so its views are compared from the first pull request on.
Its accepted findings are in `apps/bandroom/windows/tools/Screenshots/known-findings.json`.

## Off Windows

`tools/check-macos.sh` type-checks the catalogue build (`tools/CodeBehindCheck -p:BrasscribeCatalogue=true`), builds
`tools/ScreenCheck` and runs `tools/ScreenCheck.Tests`: the checks on pictures, the comparison and the verdict, each
shown failing on a picture made for it.
