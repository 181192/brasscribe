# Bandroom for Windows' screen catalogue: every view (--show VIEW [--state STATE], sample content, no engine) in Light,
# Dark, bokmål, a Windows contrast theme and 200 % text, with its checks, and what changed against the merge base.
# One start of the app per view (apps/windows/tools/ScreenCheck, bandroom). Windows only; meant for CI, since the
# contrast theme and the text size are this user's Windows settings for the length of their run.
#
#   catalogue.ps1 record  -Exe EXE -Out DIR                 take them, with the checks
#   catalogue.ps1 compare -Exe EXE -Out DIR [-Base COMMIT]  take them with Bandroom built at COMMIT (default: the merge
#                                                           base with origin/main) without the checks, then with EXE
#                                                           with them, and compare
#
# Writes and exits as apps/windows/tools/Screenshots/catalogue.ps1: DIR\shots, DIR\findings.md, DIR\report; 0 nothing
# changed, 1 a view changed, appeared or went away, 2 the checks found something, 3 the screenshots could not be taken.
param(
    [Parameter(Mandatory, Position = 0)] [ValidateSet("record", "compare")] [string] $Mode,
    [Parameter(Mandatory)] [string] $Exe,
    [Parameter(Mandatory)] [string] $Out,
    [string] $Base,
    [string] $Configuration = "Release"
)
$ErrorActionPreference = "Stop"
$bandroom = Resolve-Path (Join-Path $PSScriptRoot "../..")
$repo = Resolve-Path (Join-Path $bandroom "../../..")
$windows = Join-Path $repo "apps/windows"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$Out = Resolve-Path $Out
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
    $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "en", "--themes", "light,dark", "--checks", $c)) -eq 0) -and $ok
    $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "nb", "--themes", "light", "--checks", $c)) -eq 0) -and $ok
    if ((Invoke-ScreenCheck @("system", "--contrast", "on")) -ne 0) { throw "the contrast theme could not be turned on" }
    try { $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "contrast", "--themes", "light", "--checks", $c)) -eq 0) -and $ok }
    finally { Invoke-ScreenCheck @("system", "--contrast", "off") | Out-Null }
    if ((Invoke-ScreenCheck @("system", "--text-scale", "200")) -ne 0) { throw "the text size could not be set" }
    try { $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "text200", "--themes", "light", "--checks", $c)) -eq 0) -and $ok }
    finally { Invoke-ScreenCheck @("system", "--text-scale", "off") | Out-Null }
    # Axe.Windows and Tab last: after a Tab, Windows draws focus rectangles in the windows of later starts.
    if ($checks) { $ok = ((Invoke-ScreenCheck @("bandroom", "--exe", $exe, "--out", $shots, "--run", "scan", "--themes", "light")) -eq 0) -and $ok }
    Log ("the runs took {0:n0} s" -f ((Get-Date) - $started).TotalSeconds)
    return $ok
}

dotnet build (Join-Path $windows "tools/ScreenCheck") -c $Configuration | Out-Host
if ($LASTEXITCODE -ne 0) { throw "ScreenCheck did not build" }
$script:screenCheck = (Get-ChildItem -Recurse -Filter ScreenCheck.exe (Join-Path $windows "tools/ScreenCheck/bin/$Configuration") | Select-Object -First 1).FullName
$shots = Join-Path $Out "shots"
$report = Join-Path $Out "report"
$before = Join-Path $report "before"

if ($Mode -eq "compare") {
    if (Test-Path $report) { Remove-Item -Recurse -Force $report }
    New-Item -ItemType Directory -Force -Path $report | Out-Null
    $noBase = {
        param($why)
        Log "the screenshots could not be taken at the base: $why"
        "# Screenshots`n`nThe screenshots could not be taken at the base, $Base, so nothing was compared ($why).`n" | Set-Content (Join-Path $report "summary.md")
        exit 3
    }
    if (-not $Base) { $Base = git -C $repo merge-base HEAD origin/main }
    $Base = git -C $repo rev-parse --verify --quiet "$Base^{commit}"
    if (-not $Base) { & $noBase "no such commit" }
    $tree = Join-Path ([IO.Path]::GetTempPath()) "brasscribe-base-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
    git -C $repo worktree add --detach $tree $Base | Out-Host
    if ($LASTEXITCODE -ne 0) { & $noBase "git worktree add failed" }
    try {
        Log "building Bandroom at $($Base.Substring(0, 12))"
        $app = Join-Path $tree "apps/bandroom/windows/src/Brasscribe.Bandroom"
        dotnet build $app -c $Configuration -p:Platform=x64 -p:RuntimeIdentifier=win-x64 | Out-Host
        if ($LASTEXITCODE -ne 0) { & $noBase "Bandroom did not build there" }
        $baseExe = (Get-ChildItem -Recurse -Filter BrasscribeBandroom.exe (Join-Path $app "bin") | Select-Object -First 1).FullName
        if (-not $baseExe) { & $noBase "the build left no BrasscribeBandroom.exe" }
        if (-not (Invoke-Catalogue $baseExe $before $false)) { & $noBase "a run of the catalogue failed there" }
    }
    finally {
        Get-Process BrasscribeBandroom -ErrorAction SilentlyContinue | Stop-Process -Force
        git -C $repo worktree remove --force $tree 2>$null | Out-Null
    }
}

Log "taking them with this build, with the checks"
$taken = Invoke-Catalogue $Exe $shots $true
Invoke-ScreenCheck @("verdict", "--dir", $shots, "--known", (Join-Path $bandroom "tools/Screenshots/known-findings.json"),
    "--title", "Bandroom for Windows: screen catalogue", "--summary", (Join-Path $Out "findings.md")) | Out-Null
$checks = $LASTEXITCODE
if (-not $taken -and $checks -ne 3) { $checks = 3 }

if ($Mode -eq "compare") {
    Invoke-ScreenCheck @("compare", "--before", $before, "--after", $shots, "--report", $report) | Out-Null
    $changed = $LASTEXITCODE
    if (-not (Test-Path (Join-Path $report "result.json"))) { Log "the screenshots could not be compared"; exit 3 }
    if ($checks -ne 0) { exit $checks }
    exit $changed
}
exit $checks
