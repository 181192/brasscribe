# Bandroom for Windows' screen catalogue: every view (--show VIEW [--state STATE], sample content, no engine) in Light,
# Dark, bokmål, a Windows contrast theme and 200 % text, with its checks, and what changed against the base.
# One start of the app per view (apps/windows/tools/ScreenCheck, bandroom). Windows only; meant for CI, since the
# contrast theme, the text size and animation effects (off for every run) are this user's Windows settings for the
# length of their run.
#
#   catalogue.ps1 record  -Exe EXE -Out DIR                 take them, with the checks
#   catalogue.ps1 compare -Exe EXE -Out DIR [-Base COMMIT]  take them with Bandroom built at COMMIT (default: the merge
#                                                           base with origin/main) without the checks, then with EXE
#                                                           with them, and compare
#
# Writes and exits as apps/windows/tools/Screenshots/catalogue.ps1: DIR\shots, DIR\findings.md, DIR\report; 0 nothing
# changed, 1 a view changed, appeared or went away, 2 the checks found something, 3 the screenshots could not be taken
# here. The base is skipped when nothing its views are made from changed; a base that fails is a warning (nothing
# compared, 0); a -Base that is not a commit here is 3.
param(
    [Parameter(Mandatory, Position = 0)] [ValidateSet("record", "compare")] [string] $Mode,
    [Parameter(Mandatory)] [string] $Exe,
    [Parameter(Mandatory)] [string] $Out,
    [string] $Base,
    # Take the base even when nothing its screens are made from changed (a hand-started comparison, the noise check).
    [switch] $AlwaysBase,
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
function Invoke-Catalogue($exe, $shots, [bool] $checks) {
    if (Test-Path $shots) { Remove-Item -Recurse -Force $shots }
    $c = if ($checks) { "1" } else { "0" }
    $ok = $true
    $started = Get-Date
    # No animation effects while the views are taken (Settings > Accessibility > Visual effects): a window or a dialog
    # is on screen at once instead of fading or sliding in. The app reads it when it starts.
    if ((Invoke-ScreenCheck @("system", "--animations", "off", "--keep", $script:animationsKeep)) -ne 0) { throw "animation effects could not be turned off" }
    try {
        $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "en", "--themes", "light,dark", "--checks", $c)) -eq 0) -and $ok
        $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "nb", "--themes", "light", "--checks", $c)) -eq 0) -and $ok
        if ((Invoke-ScreenCheck @("system", "--contrast", "on")) -ne 0) { throw "the contrast theme could not be turned on" }
        try { $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "contrast", "--themes", "light", "--checks", $c)) -eq 0) -and $ok }
        finally { if ((Invoke-ScreenCheck @("system", "--contrast", "off")) -ne 0) { throw "the contrast theme could not be turned off" } }
        if ((Invoke-ScreenCheck @("system", "--text-scale", "200", "--keep", $script:textScaleKeep)) -ne 0) { throw "the text size could not be set" }
        try { $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "text200", "--themes", "light", "--checks", $c)) -eq 0) -and $ok }
        finally { if ((Invoke-ScreenCheck @("system", "--text-scale", "restore", "--keep", $script:textScaleKeep)) -ne 0) { throw "the text size could not be put back" } }
        # Axe.Windows and Tab last: after a Tab, Windows draws focus rectangles in the windows of later starts.
        if ($checks) { $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "scan", "--themes", "light")) -eq 0) -and $ok }
    }
    finally { if ((Invoke-ScreenCheck @("system", "--animations", "restore", "--keep", $script:animationsKeep)) -ne 0) { throw "animation effects could not be put back" } }
    Log ("the runs took {0:n0} s" -f ((Get-Date) - $started).TotalSeconds)
    return $ok
}

dotnet build (Join-Path $windows "tools/ScreenCheck") -c $Configuration | Out-Host
if ($LASTEXITCODE -ne 0) { throw "ScreenCheck did not build" }
$script:screenCheck = (Get-ChildItem -Recurse -Filter ScreenCheck.exe (Join-Path $windows "tools/ScreenCheck/bin/$Configuration") | Select-Object -First 1).FullName
$shots = Join-Path $Out "shots"
$report = Join-Path $Out "report"
$before = Join-Path $report "before"

# What its views are made from: when none of it changed since the base, the base is not taken.
$madeFrom = @("apps/bandroom/windows/src", "apps/bandroom/windows/Directory.Build.props", "apps/bandroom/windows/Directory.Packages.props",
    "design/tokens", "design/dist/windows", "design/dist/icons/windows", "design/brand")
$compared = $false
if ($Mode -eq "compare") {
    if (Test-Path $report) { Remove-Item -Recurse -Force $report }
    New-Item -ItemType Directory -Force -Path $report | Out-Null
    $summary = Join-Path $report "summary.md"
    $given = $Base
    if (-not $Base) { $Base = git -C $repo merge-base HEAD origin/main }
    $Base = git -C $repo rev-parse --verify --quiet "$Base^{commit}"
    $why = $null
    if (-not $Base -and $given) {
        # A base that was asked for by name: not finding it is not a comparison passed.
        Write-Host "::error::Bandroom for Windows: the base to compare with, '$given', is not a commit in this checkout, so nothing was compared."
        exit 3
    }
    if (-not $Base) { $why = "no merge base with origin/main" }
    else {
        git -C $repo diff --quiet $Base HEAD -- @madeFrom
        if ($LASTEXITCODE -eq 0 -and -not $AlwaysBase) {
            Log "nothing Bandroom's views are made from changed since $($Base.Substring(0, 12)): not taken there"
            "# Screenshots`n`nNothing Bandroom's views are made from changed since $($Base.Substring(0, 12)), so they were not compared.`n" | Set-Content $summary
        }
        else {
            $tree = Join-Path ([IO.Path]::GetTempPath()) "brasscribe-base-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
            git -C $repo worktree add --detach $tree $Base | Out-Host
            if ($LASTEXITCODE -ne 0) { $why = "git worktree add failed" }
            else {
                try {
                    Log "building Bandroom at $($Base.Substring(0, 12))"
                    $app = Join-Path $tree "apps/bandroom/windows/src/Brasscribe.Bandroom"
                    dotnet build $app -c $Configuration -p:Platform=x64 -p:RuntimeIdentifier=win-x64 | Out-Host
                    if ($LASTEXITCODE -ne 0) { $why = "Bandroom did not build there" }
                    else {
                        $baseExe = (Get-ChildItem -Recurse -Filter BrasscribeBandroom.exe (Join-Path $app "bin") | Select-Object -First 1).FullName
                        if (-not $baseExe) { $why = "the build left no BrasscribeBandroom.exe" }
                        elseif (Invoke-Catalogue $baseExe $before $false) { $compared = $true }
                        else { $why = "a run of the catalogue failed there" }
                    }
                }
                catch { $why = $_.Exception.Message }
                finally {
                    Get-Process BrasscribeBandroom -ErrorAction SilentlyContinue | Stop-Process -Force
                    git -C $repo worktree remove --force $tree 2>$null | Out-Null
                }
            }
        }
    }
    if ($why) {
        # A change to the catalogue itself can make the base's run fail: say so, compare nothing, let this side's checks decide.
        Write-Host "::warning::Bandroom for Windows: the screenshots could not be taken at the base ($why), so nothing was compared."
        "# Screenshots`n`nThe screenshots could not be taken at the base, $Base, so nothing was compared ($why).`n" | Set-Content $summary
    }
}

Log "taking them with this build, with the checks"
$taken = Invoke-Catalogue $Exe $shots $true
Invoke-ScreenCheck @("verdict", "--dir", $shots, "--known", (Join-Path $bandroom "tools/Screenshots/known-findings.json"),
    "--title", "Bandroom for Windows: screen catalogue", "--summary", (Join-Path $Out "findings.md")) | Out-Null
$checks = $LASTEXITCODE
if (-not $taken -and $checks -ne 3) { $checks = 3 }

if ($compared) {
    Invoke-ScreenCheck @("compare", "--before", $before, "--after", $shots, "--report", $report) | Out-Null
    $changed = $LASTEXITCODE
    if (-not (Test-Path (Join-Path $report "result.json"))) { Log "the screenshots could not be compared"; exit 3 }
    if ($checks -ne 0) { exit $checks }
    exit $changed
}
exit $checks
