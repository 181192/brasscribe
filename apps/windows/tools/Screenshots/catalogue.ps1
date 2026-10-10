# Brasscribe Play for Windows' screen catalogue (tests/Brasscribe.Play.Catalogue): every screen in Light, Dark, Pink
# light, Pink dark, bokmål, a Windows contrast theme and 200 % text, with its checks (contrast measured from the
# picture, cut-off text, Axe.Windows, Tab), and a screenshot of each. Windows only; meant for CI, since the contrast
# theme, the text size and animation effects (off for every run) are this user's Windows settings for the length of
# their run.
#
#   catalogue.ps1 -Exe EXE -Out DIR
#
# DIR gets the screenshots (shots\, with not-taken\ and scans\ in it) and findings.md. Exit codes: 0 every check
# passed, 2 the catalogue's checks found something, 3 the screenshots could not be taken (a screen that was not the
# screen asked for, or did not keep still, is not taken). The screenshots are to look at; nothing here compares
# them. After a merge, CI compares main's with those of the main before it (.github/workflows/screens.yml), and
# that blocks nothing.
# EXE is the app's own build (BrasscribePlay.exe): Axe.Windows and the walk with Tab run on it, one start per screen.
# -FfiDll is the Rust core for this checkout (brasscribe_ffi.dll).
param(
    [Parameter(Mandatory)] [string] $Out,
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

# The catalogue build of the app: its exe.
function Build-Catalogue($dir, $ffi) {
    $props = @("-c", $Configuration, "-p:Platform=x64", "-p:RuntimeIdentifier=win-x64", "-p:BrasscribeCatalogue=true")
    if ($ffi) { $props += "-p:BrasscribeFfiDll=$ffi" }
    dotnet build (Join-Path $dir "src/Brasscribe.Play") @props | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "the catalogue build failed in $dir" }
    $exe = Get-ChildItem -Recurse -Filter BrasscribePlay.exe (Join-Path $dir "src/Brasscribe.Play/bin/catalogue") | Select-Object -First 1
    if (-not $exe) { throw "the catalogue build left no BrasscribePlay.exe in $dir" }
    $exe.FullName
}

# One run of the catalogue exe: $run is en, nb, contrast or text200. Returns false when it could not run.
function Invoke-Run($exe, $shots, $run, $variants, $score) {
    $env:BRASSCRIBE_CATALOGUE_OUT = $shots
    $env:BRASSCRIBE_CATALOGUE_RUN = $run
    $env:BRASSCRIBE_CATALOGUE_VARIANTS = $variants
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

# Every run of the catalogue. False when one could not run. Pink on the screens with most of its colours; bokmål in
# Light; under a contrast theme Match system and Pink dark, which must look the same (the contrast theme wins).
function Invoke-Catalogue($exe, $shots, $score) {
    if (Test-Path $shots) { Remove-Item -Recurse -Force $shots }
    New-Item -ItemType Directory -Force -Path $shots | Out-Null
    $env:BRASSCRIBE_CATALOGUE_PINK_SCENES = "first-run,home,score,review,export,settings"
    # No animation effects while the screens are taken (Settings > Accessibility > Visual effects): a dialog, a page or
    # a theme change is on screen at once instead of fading or sliding in. The app reads it when it starts.
    System-State @("--animations", "off", "--keep", $script:animationsKeep)
    try {
        $ok = Invoke-Run $exe $shots "en" "light,dark,pink-light,pink-dark" $score
        $ok = (Invoke-Run $exe $shots "nb" "light" $score) -and $ok
        System-State @("--contrast", "on")
        try { $ok = (Invoke-Run $exe $shots "contrast" "system,pink-dark" $score) -and $ok }
        finally { System-State @("--contrast", "off") }
        System-State @("--text-scale", "200", "--keep", $script:textScaleKeep)
        try { $ok = (Invoke-Run $exe $shots "text200" "light" $score) -and $ok }
        finally { System-State @("--text-scale", "restore", "--keep", $script:textScaleKeep) }
        & $script:screenCheck play --exe $script:appExe --score $score --out $shots --shots $shots | Out-Host
        $ok = ($LASTEXITCODE -eq 0) -and $ok
    }
    finally { System-State @("--animations", "restore", "--keep", $script:animationsKeep) }
    return $ok
}

# ScreenCheck from this checkout: the scan, the system settings and the verdict.
dotnet build (Join-Path $windows "tools/ScreenCheck") -c $Configuration | Out-Host
if ($LASTEXITCODE -ne 0) { throw "ScreenCheck did not build" }
$script:screenCheck = (Get-ChildItem -Recurse -Filter ScreenCheck.exe (Join-Path $windows "tools/ScreenCheck/bin/$Configuration") | Select-Object -First 1).FullName
$score = Join-Path $repo "apps/fixtures/old-hundredth/brass-band.musicxml"
$script:appExe = (Resolve-Path $Exe).Path
$shots = Join-Path $Out "shots"

Log "taking them, with the checks"
$exe = Build-Catalogue $windows $FfiDll
$taken = Invoke-Catalogue $exe $shots $score
& $script:screenCheck verdict --dir $shots --known (Join-Path $windows "tests/Brasscribe.Play.Catalogue/known-findings.json") `
    --title "Play for Windows: screen catalogue" --summary (Join-Path $Out "findings.md") | Out-Host
$checks = $LASTEXITCODE
if (-not $taken -and $checks -ne 3) { $checks = 3 }
exit $checks
