# Brasscribe Play for Windows' screen catalogue (tests/Brasscribe.Play.Catalogue): every screen in Light, Dark, Pink
# light, Pink dark, bokmål, a Windows contrast theme and 200 % text, with its checks, and what changed against the
# base. Windows only; meant for CI, since the contrast theme, the text size and animation effects (off for every run)
# are this user's Windows settings for the length of their run.
#
#   catalogue.ps1 record  -Exe EXE -Out DIR                 take them, with the checks
#   catalogue.ps1 compare -Exe EXE -Out DIR [-Base COMMIT]  take them at COMMIT (default: the merge base with origin/main) without
#                                                  the checks, then here with them, and compare
#
# DIR gets the screenshots (shots\, with not-taken\ and scans\ in it), findings.md and, for compare, report\ (index.html,
# summary.md, result.json) with the base's screenshots in before\. Exit codes as for the other apps' catalogues:
# 0 nothing changed, 1 a screen changed, appeared or went away, 2 the catalogue's checks found something, 3 the
# screenshots could not be taken here. When nothing the screens are made from changed since the base, the base is not
# taken (nothing to compare; 0). When the base's screenshots cannot be taken (a change to the catalogue itself, say),
# that is a warning and nothing is compared (0): this side's checks still decide. A -Base that is not a commit here
# is 3: a comparison that was asked for is never passed over.
# EXE is the app's own build (BrasscribePlay.exe): Axe.Windows and the walk with Tab run on it, one start per screen.
# -FfiDll is the Rust core for this checkout (scribe_ffi.dll); the base builds its own when its core differs.
param(
    [Parameter(Mandatory, Position = 0)] [ValidateSet("record", "compare")] [string] $Mode,
    [Parameter(Mandatory)] [string] $Out,
    [string] $Base,
    # Take the base even when nothing its screens are made from changed (a hand-started comparison, the noise check).
    [switch] $AlwaysBase,
    [string] $FfiDll,
    # The app's own build: Axe.Windows and the walk with Tab run on it, one start per screen.
    [Parameter(Mandatory)] [string] $Exe,
    [string] $Configuration = "Release"
)
$ErrorActionPreference = "Stop"
$windows = Resolve-Path (Join-Path $PSScriptRoot "../..")
$repo = Resolve-Path (Join-Path $windows "../..")
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$Out = Resolve-Path $Out
# The text size this user had before a run at 200 %, put back after it; and whether animation effects were on.
$script:textScaleKeep = Join-Path $Out "text-scale-before.txt"
$script:animationsKeep = Join-Path $Out "animations-before.txt"

function Log($text) { Write-Host "catalogue: $text" }

# The catalogue build of the app in the checkout whose apps\windows is $dir: its exe.
function Build-Catalogue($dir, $ffi) {
    $props = @("-c", $Configuration, "-p:Platform=x64", "-p:RuntimeIdentifier=win-x64", "-p:BrasscribeCatalogue=true")
    if ($ffi) { $props += "-p:ScribeFfiDll=$ffi" }
    dotnet build (Join-Path $dir "src/Brasscribe.Play") @props | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "the catalogue build failed in $dir" }
    $exe = Get-ChildItem -Recurse -Filter BrasscribePlay.exe (Join-Path $dir "src/Brasscribe.Play/bin/catalogue") | Select-Object -First 1
    if (-not $exe) { throw "the catalogue build left no BrasscribePlay.exe in $dir" }
    $exe.FullName
}

# One run of the catalogue exe: $run is en, nb, contrast or text200. Returns false when it could not run.
function Invoke-Run($exe, $shots, $run, $variants, $score, [bool] $checks) {
    $env:BRASSCRIBE_CATALOGUE_OUT = $shots
    $env:BRASSCRIBE_CATALOGUE_RUN = $run
    $env:BRASSCRIBE_CATALOGUE_VARIANTS = $variants
    $env:BRASSCRIBE_CATALOGUE_CHECKS = if ($checks) { "1" } else { "0" }
    $env:BRASSCRIBE_CATALOGUE_SCORE = $score
    $env:BRASSCRIBE_CATALOGUE_LANG = if ($run -eq "nb") { "nb-NO" } else { "" }
    $appArgs = @("--results-directory", (Join-Path $shots "results"), "--report-trx", "--report-trx-filename", "catalogue-$run.trx")
    $started = Get-Date
    & $exe @appArgs | Out-Host
    $code = $LASTEXITCODE
    Log ("{0} took {1:n0} s (test platform exit {2})" -f $run, ((Get-Date) - $started).TotalSeconds, $code)
    # How long each screen took to be the screen asked for, and what it waited for.
    $takes = Join-Path $shots "takes-$run.log"
    if (Test-Path $takes) { Get-Content $takes | Out-Host }
    if ($code -ne 0) {
        # Why the app ended, when it crashed: Windows' own record of it.
        Get-WinEvent -FilterHashtable @{ LogName = "Application"; StartTime = $started } -ErrorAction SilentlyContinue |
            Where-Object { $_.ProviderName -in "Application Error", ".NET Runtime", "Windows Error Reporting" } |
            ForEach-Object { Write-Host "$($_.ProviderName): $($_.Message)" }
    }
    # 0: every screen was taken. 2: a screen failed (the run's file says which). Anything else: the run itself failed
    # (8 is "no tests ran", never a pass).
    return ($code -eq 0 -or $code -eq 2) -and (Test-Path (Join-Path $shots "catalogue-$run.json"))
}

function System-State([string[]] $what) {
    & $script:screenCheck system @what | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "ScreenCheck system $what failed" }
}

# Every run of the catalogue on one checkout. False when one could not run. Pink on the screens with most of its
# colours; bokmål in Light; under a contrast theme the base takes Match system only, and this side also Pink dark,
# which must look the same (the contrast theme wins).
function Invoke-Catalogue($exe, $shots, $score, [bool] $checks) {
    if (Test-Path $shots) { Remove-Item -Recurse -Force $shots }
    New-Item -ItemType Directory -Force -Path $shots | Out-Null
    $env:BRASSCRIBE_CATALOGUE_PINK_SCENES = "first-run,home,score,review,export,settings"
    # No animation effects while the screens are taken (Settings > Accessibility > Visual effects): a dialog, a page or
    # a theme change is on screen at once instead of fading or sliding in. The app reads it when it starts.
    System-State @("--animations", "off", "--keep", $script:animationsKeep)
    try {
        $ok = Invoke-Run $exe $shots "en" "light,dark,pink-light,pink-dark" $score $checks
        $ok = (Invoke-Run $exe $shots "nb" "light" $score $checks) -and $ok
        System-State @("--contrast", "on")
        try { $ok = (Invoke-Run $exe $shots "contrast" ($(if ($checks) { "system,pink-dark" } else { "system" })) $score $checks) -and $ok }
        finally { System-State @("--contrast", "off") }
        System-State @("--text-scale", "200", "--keep", $script:textScaleKeep)
        try { $ok = (Invoke-Run $exe $shots "text200" "light" $score $checks) -and $ok }
        finally { System-State @("--text-scale", "restore", "--keep", $script:textScaleKeep) }
        if ($checks) {
            & $script:screenCheck play --exe $script:appExe --score $score --out $shots --shots $shots | Out-Host
            $ok = ($LASTEXITCODE -eq 0) -and $ok
        }
    }
    finally { System-State @("--animations", "restore", "--keep", $script:animationsKeep) }
    return $ok
}

# ScreenCheck from this checkout: the scan, the system settings, the verdict and the comparison.
dotnet build (Join-Path $windows "tools/ScreenCheck") -c $Configuration | Out-Host
if ($LASTEXITCODE -ne 0) { throw "ScreenCheck did not build" }
$script:screenCheck = (Get-ChildItem -Recurse -Filter ScreenCheck.exe (Join-Path $windows "tools/ScreenCheck/bin/$Configuration") | Select-Object -First 1).FullName
$score = Join-Path $repo "apps/fixtures/old-hundredth/brass-band.musicxml"
$script:appExe = (Resolve-Path $Exe).Path
$shots = Join-Path $Out "shots"
$report = Join-Path $Out "report"
$before = Join-Path $report "before"

# What the screens are made from: when none of it changed since the base, the base is not taken.
$madeFrom = @("apps/windows/src", "apps/windows/tests/Brasscribe.Play.Catalogue", "apps/windows/Directory.Build.props",
    "apps/windows/Directory.Packages.props", "core", "design/tokens", "design/dist/windows", "design/dist/icons/windows", "design/brand", "apps/fixtures", "sounds")
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
        Write-Host "::error::Play for Windows: the base to compare with, '$given', is not a commit in this checkout, so nothing was compared."
        exit 3
    }
    if (-not $Base) { $why = "no merge base with origin/main" }
    else {
        git -C $repo diff --quiet $Base HEAD -- @madeFrom
        if ($LASTEXITCODE -eq 0 -and -not $AlwaysBase) {
            Log "nothing the screens are made from changed since $($Base.Substring(0, 12)): not taken there"
            "# Screenshots`n`nNothing the screens are made from changed since $($Base.Substring(0, 12)), so they were not compared.`n" | Set-Content $summary
        }
        else {
            $tree = Join-Path ([IO.Path]::GetTempPath()) "brasscribe-base-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
            git -C $repo worktree add --detach $tree $Base | Out-Host
            if ($LASTEXITCODE -ne 0) { $why = "git worktree add failed" }
            else {
                try {
                    if (-not (Test-Path (Join-Path $tree "apps/windows/tests/Brasscribe.Play.Catalogue"))) {
                        Log "$($Base.Substring(0, 12)) has no screen catalogue: every screen is new"
                        $compared = $true
                    }
                    else {
                        Log "taking them at $($Base.Substring(0, 12))"
                        $baseFfi = $FfiDll
                        git -C $repo diff --quiet $Base HEAD -- core
                        if ($LASTEXITCODE -ne 0 -or -not $FfiDll) {
                            Log "the core differs at the base: building it there"
                            Push-Location (Join-Path $tree "core")
                            try { cargo build --release --locked -p scribe-ffi | Out-Host } finally { Pop-Location }
                            if ($LASTEXITCODE -ne 0) { $why = "its core did not build" }
                            $baseFfi = Join-Path $tree "core/target/release/scribe_ffi.dll"
                        }
                        if (-not $why) {
                            try {
                                $baseExe = Build-Catalogue (Join-Path $tree "apps/windows") $baseFfi
                                $baseScore = Join-Path $tree "apps/fixtures/old-hundredth/brass-band.musicxml"
                                if (Invoke-Catalogue $baseExe $before $baseScore $false) { $compared = $true }
                                else { $why = "a run of its catalogue failed" }
                            }
                            catch { $why = $_.Exception.Message }
                        }
                    }
                }
                finally { git -C $repo worktree remove --force $tree 2>$null | Out-Null }
            }
        }
    }
    if ($why) {
        # Not this change's failure to judge: a pull request that changes the catalogue itself can make the base's
        # run fail. Say so, compare nothing, and let this side's checks decide.
        Write-Host "::warning::Play for Windows: the screenshots could not be taken at the base ($why), so nothing was compared."
        "# Screenshots`n`nThe screenshots could not be taken at the base, $Base, so nothing was compared ($why).`n" | Set-Content $summary
    }
}

Log "taking them here, with the checks"
$exe = Build-Catalogue $windows $FfiDll
$taken = Invoke-Catalogue $exe $shots $score $true
& $script:screenCheck verdict --dir $shots --known (Join-Path $windows "tests/Brasscribe.Play.Catalogue/known-findings.json") `
    --title "Play for Windows: screen catalogue" --summary (Join-Path $Out "findings.md") | Out-Host
$checks = $LASTEXITCODE
if (-not $taken -and $checks -ne 3) { $checks = 3 }

if ($compared) {
    & $script:screenCheck compare --before $before --after $shots --report $report | Out-Host
    $changed = $LASTEXITCODE
    if (-not (Test-Path (Join-Path $report "result.json"))) { Log "the screenshots could not be compared"; exit 3 }
    if ($checks -ne 0) { exit $checks }
    exit $changed
}
exit $checks
