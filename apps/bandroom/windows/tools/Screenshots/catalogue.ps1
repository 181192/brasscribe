# Bandroom for Windows' screen catalogue: every view (--show VIEW [--state STATE], sample content, no engine) in Light,
# Dark, bokmål, a Windows contrast theme and 200 % text, with its checks (contrast measured from the picture, Axe.Windows,
# Tab), and a screenshot of each. One start of the app per view (apps/windows/tools/ScreenCheck, bandroom). Windows
# only; meant for CI, since the contrast theme, the text size and animation effects (off for every run) are this user's
# Windows settings for the length of their run.
#
#   catalogue.ps1 -Exe EXE -Out DIR
#
# Writes and exits as apps/windows/tools/Screenshots/catalogue.ps1: DIR\shots and DIR\findings.md; 0 every check passed,
# 2 the checks found something, 3 the screenshots could not be taken. The screenshots are to look at; nothing here
# compares them (.github/workflows/screens.yml does, on main after a merge, and that blocks nothing).
param(
    [Parameter(Mandatory)] [string] $Exe,
    [Parameter(Mandatory)] [string] $Out,
    [string] $Configuration = "Release"
)
$ErrorActionPreference = "Stop"
$bandroom = Resolve-Path (Join-Path $PSScriptRoot "../..")
$repo = Resolve-Path (Join-Path $bandroom "../../..")
$windows = Join-Path $repo "apps/windows"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$Out = Resolve-Path $Out
# The text size this user had before a run at 200 %, put back after it; and whether animation effects were on.
$script:textScaleKeep = Join-Path $Out "text-scale-before.txt"
$script:animationsKeep = Join-Path $Out "animations-before.txt"
$Exe = Resolve-Path $Exe

function Log($text) { Write-Host "catalogue: $text" }

function Invoke-ScreenCheck([string[]] $what) {
    & $script:screenCheck @what | Out-Host
    return $LASTEXITCODE
}

# Every run on one build of Bandroom. False when one could not run.
function Invoke-Catalogue($exe, $shots) {
    if (Test-Path $shots) { Remove-Item -Recurse -Force $shots }
    $ok = $true
    $started = Get-Date
    # No animation effects while the views are taken (Settings > Accessibility > Visual effects): a window or a dialog
    # is on screen at once instead of fading or sliding in. The app reads it when it starts.
    if ((Invoke-ScreenCheck @("system", "--animations", "off", "--keep", $script:animationsKeep)) -ne 0) { throw "animation effects could not be turned off" }
    try {
        $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "en", "--themes", "light,dark")) -eq 0) -and $ok
        $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "nb", "--themes", "light")) -eq 0) -and $ok
        if ((Invoke-ScreenCheck @("system", "--contrast", "on")) -ne 0) { throw "the contrast theme could not be turned on" }
        try { $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "contrast", "--themes", "light")) -eq 0) -and $ok }
        finally { if ((Invoke-ScreenCheck @("system", "--contrast", "off")) -ne 0) { throw "the contrast theme could not be turned off" } }
        if ((Invoke-ScreenCheck @("system", "--text-scale", "200", "--keep", $script:textScaleKeep)) -ne 0) { throw "the text size could not be set" }
        try { $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "text200", "--themes", "light")) -eq 0) -and $ok }
        finally { if ((Invoke-ScreenCheck @("system", "--text-scale", "restore", "--keep", $script:textScaleKeep)) -ne 0) { throw "the text size could not be put back" } }
        # Axe.Windows and Tab last: after a Tab, Windows draws focus rectangles in the windows of later starts.
        $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "scan", "--themes", "light")) -eq 0) -and $ok
    }
    finally { if ((Invoke-ScreenCheck @("system", "--animations", "restore", "--keep", $script:animationsKeep)) -ne 0) { throw "animation effects could not be put back" } }
    Log ("the runs took {0:n0} s" -f ((Get-Date) - $started).TotalSeconds)
    return $ok
}

dotnet build (Join-Path $windows "tools/ScreenCheck") -c $Configuration | Out-Host
if ($LASTEXITCODE -ne 0) { throw "ScreenCheck did not build" }
$script:screenCheck = (Get-ChildItem -Recurse -Filter ScreenCheck.exe (Join-Path $windows "tools/ScreenCheck/bin/$Configuration") | Select-Object -First 1).FullName
$shots = Join-Path $Out "shots"

Log "taking them with this build, with the checks"
$taken = Invoke-Catalogue $Exe $shots
Invoke-ScreenCheck @("verdict", "--dir", $shots, "--known", (Join-Path $bandroom "tools/Screenshots/known-findings.json"),
    "--title", "Bandroom for Windows: screen catalogue", "--summary", (Join-Path $Out "findings.md")) | Out-Null
$checks = $LASTEXITCODE
if (-not $taken -and $checks -ne 3) { $checks = 3 }
exit $checks
