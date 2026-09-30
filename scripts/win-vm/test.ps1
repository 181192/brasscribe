# The .NET tests in the VM (scripts/win-vm.sh test), after build.ps1: Brasscribe Play's core tests with
# the native core (ARM64 brasscribe_ffi.dll), the core's .NET binding tests, and Bandroom's core tests.
# TRX files go to C:\b\out\<Run>\test-results. The smoke tests and Axe.Windows need the logged-on
# session and run from shots.ps1 -Smoke.
param([Parameter(Mandatory)] [string] $Run, [string] $Filter = "")
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\env.ps1"
$out = "C:\b\out\$Run"
$results = "$out\test-results"
New-Item -ItemType Directory -Force -Path $results | Out-Null
$ffi = "$Repo\core\target\release\brasscribe_ffi.dll"
if (Test-Path $ffi) { $env:BRASSCRIBE_FFI_PATH = $ffi } else { Write-Host "[test] no native core at ${ffi}: its tests will skip" }
$failed = @()
$filterArgs = if ($Filter) { @("--filter", $Filter) } else { @() }

$suites = [ordered]@{
    "play-core"     = "$Repo\apps\windows\tests\Brasscribe.Play.Core.Tests"
    "core-dotnet"   = "$Repo\core\dotnet\Brasscribe.Core.Tests"
    "bandroom-core" = "$Repo\apps\bandroom\windows\tests\Brasscribe.Bandroom.Core.Tests"
}
foreach ($name in $suites.Keys) {
    if (-not (Test-Path $suites[$name])) { Write-Host "[test] ${name}: not in this checkout"; continue }
    $t = Get-Date
    Write-Host "[test] $name"
    dotnet test $suites[$name] -c Release @filterArgs --logger "trx;LogFileName=$name.trx" --logger "console;verbosity=minimal" --results-directory $results 2>&1 | Out-Host
    $ok = $LASTEXITCODE -eq 0
    Write-Host ("[test] {0}: {1} in {2} s" -f $name, ($(if ($ok) { "passed" } else { "FAILED" })), [int]((Get-Date) - $t).TotalSeconds)
    if (-not $ok) { $failed += $name }
}

# the counts from the TRX files, one line per suite
Get-ChildItem $results -Filter *.trx | ForEach-Object {
    [xml] $x = Get-Content $_.FullName
    $c = $x.TestRun.ResultSummary.Counters
    Write-Host ("[test] {0}: {1} passed, {2} failed, {3} skipped of {4}" -f $_.BaseName, $c.passed, $c.failed, ([int]$c.total - [int]$c.executed), $c.total)
}
if ($failed.Count -gt 0) { Write-Host "[test] FAILED: $($failed -join ', ')"; exit 1 }
Write-Host "[test] all passed"
