# Brasscribe Play for Windows' screen catalogue (tests/Brasscribe.Play.Catalogue): every screen in Light, Dark, Pink
# light, Pink dark, bokmål, a Windows contrast theme and 200 % text, with its checks, and what changed against the
# merge base. Windows only; meant for CI, since the contrast theme and the text size are this user's Windows settings
# for the length of their run.
#
#   catalogue.ps1 record  -Exe EXE -Out DIR                 take them, with the checks
#   catalogue.ps1 compare -Exe EXE -Out DIR [-Base COMMIT]  take them at COMMIT (default: the merge base with origin/main) without
#                                                  the checks, then here with them, and compare
#
# DIR gets the screenshots (shots\, unsteady\, scans\), findings.md and, for compare, report\ (index.html,
# summary.md, result.json) with the base's screenshots in before\. Exit codes as for the other apps' catalogues:
# 0 nothing changed, 1 a screen changed, appeared or went away, 2 the catalogue's checks found something, 3 the
# screenshots could not be taken (here or at the base; nothing was compared).
# EXE is the app's own build (BrasscribePlay.exe): Axe.Windows and the walk with Tab run on it, one start per screen.
# -FfiDll is the Rust core for this checkout (brasscribe_ffi.dll); the base builds its own when its core differs.
param(
    [Parameter(Mandatory, Position = 0)] [ValidateSet("record", "compare")] [string] $Mode,
    [Parameter(Mandatory)] [string] $Out,
    [string] $Base,
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

function Log($text) { Write-Host "catalogue: $text" }

# The catalogue build of the app in the checkout whose apps\windows is $dir: its exe.
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
function Invoke-Run($exe, $shots, $run, $variants, $score, [bool] $checks) {
    $env:BRASSCRIBE_CATALOGUE_OUT = $shots
    $env:BRASSCRIBE_CATALOGUE_RUN = $run
    $env:BRASSCRIBE_CATALOGUE_VARIANTS = $variants
    $env:BRASSCRIBE_CATALOGUE_CHECKS = if ($checks) { "1" } else { "0" }
    $env:BRASSCRIBE_CATALOGUE_SCORE = $score
    $appArgs = @()
    if ($run -eq "nb") { $appArgs += @("--lang", "nb-NO") }
    $appArgs += @("--results-directory", (Join-Path $shots "results"), "--report-trx", "--report-trx-filename", "catalogue-$run.trx")
    $started = Get-Date
    & $exe @appArgs | Out-Host
    $code = $LASTEXITCODE
    Log ("{0} took {1:n0} s (test platform exit {2})" -f $run, ((Get-Date) - $started).TotalSeconds, $code)
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

# Every run of the catalogue on one checkout. False when one could not run.
function Invoke-Catalogue($exe, $shots, $score, [bool] $checks) {
    if (Test-Path $shots) { Remove-Item -Recurse -Force $shots }
    New-Item -ItemType Directory -Force -Path $shots | Out-Null
    $ok = Invoke-Run $exe $shots "en" "light,dark,pink-light,pink-dark" $score $checks
    $ok = (Invoke-Run $exe $shots "nb" "light,dark" $score $checks) -and $ok
    # A contrast theme wins over every choice: the run shows each, and they must all look the same.
    System-State @("--contrast", "on")
    try { $ok = (Invoke-Run $exe $shots "contrast" "system,light,dark,pink-dark" $score $checks) -and $ok }
    finally { System-State @("--contrast", "off") }
    System-State @("--text-scale", "200")
    try { $ok = (Invoke-Run $exe $shots "text200" "light" $score $checks) -and $ok }
    finally { System-State @("--text-scale", "off") }
    if ($checks) {
        & $script:screenCheck play --exe $script:appExe --score $score --out $shots | Out-Host
        $ok = ($LASTEXITCODE -eq 0) -and $ok
    }
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
        if (Test-Path (Join-Path $tree "apps/windows/tests/Brasscribe.Play.Catalogue")) {
            Log "taking them at $($Base.Substring(0, 12))"
            $baseFfi = $FfiDll
            git -C $repo diff --quiet $Base HEAD -- core
            if ($LASTEXITCODE -ne 0 -or -not $FfiDll) {
                Log "the core differs at the base: building it there"
                Push-Location (Join-Path $tree "core")
                try { cargo build --release --locked -p brasscribe-ffi | Out-Host } finally { Pop-Location }
                if ($LASTEXITCODE -ne 0) { & $noBase "its core did not build" }
                $baseFfi = Join-Path $tree "core/target/release/brasscribe_ffi.dll"
            }
            try { $baseExe = Build-Catalogue (Join-Path $tree "apps/windows") $baseFfi } catch { & $noBase $_.Exception.Message }
            $baseScore = Join-Path $tree "apps/fixtures/old-hundredth/brass-band.musicxml"
            if (-not (Invoke-Catalogue $baseExe $before $baseScore $false)) { & $noBase "a run of its catalogue failed" }
        }
        else { Log "$($Base.Substring(0, 12)) has no screen catalogue: every screen is new" }
    }
    finally {
        git -C $repo worktree remove --force $tree 2>$null | Out-Null
    }
}

Log "taking them here, with the checks"
$exe = Build-Catalogue $windows $FfiDll
$taken = Invoke-Catalogue $exe $shots $score $true
& $script:screenCheck verdict --dir $shots --known (Join-Path $windows "tests/Brasscribe.Play.Catalogue/known-findings.json") `
    --title "Play for Windows: screen catalogue" --summary (Join-Path $Out "findings.md") | Out-Host
$checks = $LASTEXITCODE
if (-not $taken -and $checks -ne 3) { $checks = 3 }

if ($Mode -eq "compare") {
    & $script:screenCheck compare --before $before --after $shots --report $report | Out-Host
    $changed = $LASTEXITCODE
    if (-not (Test-Path (Join-Path $report "result.json"))) { Log "the screenshots could not be compared"; exit 3 }
    if ($checks -ne 0) { exit $checks }
    exit $changed
}
exit $checks
