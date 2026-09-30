# Runs in the VM's logged-on session (win-vm.sh starts it as a scheduled task), where the apps' windows
# are drawn. Writes into C:\b\out\<Run>: PNGs, shots.log and shots.done at the end.
#   -Scenes default|all|a,b,c   Brasscribe Play screens (PreviewScenes, --show) in en and nb, light, dark, Pink and Pink dark
#   -Smoke                      the CI smoke tests of Play and Bandroom, and their Axe.Windows scans
#   -Checklist                  -Smoke, the default scenes, and the scenes again at 200 % text size
#                               (docs/dev/windows-checklist.md §0 and §6)
# Each launch starts from a fresh profile: settings.json is written anew (Pink: "Appearance": "pink").
param(
    [Parameter(Mandatory)] [string] $Run,
    [string] $Scenes = "",
    [switch] $Smoke,
    [switch] $Checklist,
    [int] $Settle = 6
)
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\env.ps1"
$out = "C:\b\out\$Run"
New-Item -ItemType Directory -Force -Path $out | Out-Null
Start-Transcript -Path "$out\shots.log" -Force | Out-Null
$artifacts = Get-Content (Get-ChildItem C:\b\out\*\artifacts.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName | ConvertFrom-Json
$playExe = $artifacts.'play-arm64'
$bandroomExe = $artifacts.'bandroom-x64'
$score = "$Repo\apps\fixtures\old-hundredth\brass-band.musicxml"
$profileDir = Join-Path $env:LOCALAPPDATA "Brasscribe\Play"
$failures = @()

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@

function Save-Window([IntPtr] $hwnd, [string] $file) {
    $r = New-Object Win+RECT
    [Win]::GetWindowRect($hwnd, [ref] $r) | Out-Null
    $w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc()
    [Win]::PrintWindow($hwnd, $hdc, 2) | Out-Null  # PW_RENDERFULLCONTENT: WinUI's composition too
    $g.ReleaseHdc($hdc); $g.Dispose()
    $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    Write-Host "captured $(Split-Path -Leaf $file) ($w x $h)"
}

function Reset-Profile([string] $appearance) {
    New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
    Remove-Item "$profileDir\settings.json", "$profileDir\crash.log" -ErrorAction SilentlyContinue
    if ($appearance -eq "pink") { '{"Appearance":"pink","PinkUnlocked":true}' | Set-Content "$profileDir\settings.json" -Encoding ascii }
}

# Starts Play on <scene>, captures its window into <file>; false when it shows no window.
function Shoot([string] $scene, [string] $lang, [string] $theme, [string] $file) {
    $appearance = if ($theme -like "pink*") { "pink" } else { $theme }
    $rootTheme = if ($theme -eq "pink") { "light" } elseif ($theme -eq "pink-dark") { "dark" } else { $theme }
    Reset-Profile $appearance
    $p = Start-Process -FilePath $playExe -ArgumentList @("--show", $scene, "--theme", $rootTheme, "--lang", $lang, "--score", $score) -PassThru
    try {
        $deadline = (Get-Date).AddSeconds(90)
        while ($p.MainWindowHandle -eq 0 -and -not $p.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500; $p.Refresh() }
        if ($p.HasExited -or $p.MainWindowHandle -eq 0) {
            Write-Warning "${scene} ${lang} ${theme}: no window (exit $(if ($p.HasExited) { $p.ExitCode }))"
            if (Test-Path "$profileDir\crash.log") { Get-Content "$profileDir\crash.log" | Select-Object -Last 30 | Write-Host }
            return $false
        }
        [Win]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
        Start-Sleep -Seconds $Settle
        if ($scene -in "stand", "settings", "export") { Start-Sleep -Seconds 3 }  # opened 1.5 s after the window, then animated
        $p.Refresh()
        Save-Window $p.MainWindowHandle $file
        return $true
    }
    finally { if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force } }
}

function Shoot-All([string[]] $names, [string] $suffix) {
    foreach ($lang in "en-US", "nb-NO") {
        foreach ($theme in "light", "dark", "pink", "pink-dark") {
            foreach ($scene in $names) {
                $file = Join-Path $out ("{0}-{1}-{2}{3}.png" -f $scene, $lang.Substring(0, 2), $theme, $suffix)
                if (-not (Shoot $scene $lang $theme $file)) { $script:failures += "shot $scene $lang $theme$suffix" }
            }
        }
    }
}

# The CI smoke test: the app starts and shows its window (Play), and keeps running with its tray icon (Bandroom).
function Smoke-Tests {
    Reset-Profile "system"
    foreach ($exe in @($playExe, $artifacts.'play-x64', $bandroomExe) | Where-Object { $_ }) {
        $p = Start-Process -FilePath $exe -PassThru
        $deadline = (Get-Date).AddSeconds(90)
        while ($p.MainWindowHandle -eq 0 -and -not $p.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500; $p.Refresh() }
        Start-Sleep -Seconds 5
        $name = Split-Path -Leaf (Split-Path -Parent $exe)
        if ($p.HasExited) { Write-Host "SMOKE FAIL $exe exited with $($p.ExitCode)"; $script:failures += "smoke $exe" }
        elseif ($p.MainWindowHandle -eq 0 -and $exe -notlike "*Bandroom*") { Write-Host "SMOKE FAIL $exe no window"; $script:failures += "smoke $exe" }
        else {
            Write-Host "SMOKE OK $exe ($($p.MainWindowTitle))"
            if ($p.MainWindowHandle -ne 0) { Save-Window $p.MainWindowHandle (Join-Path $out ("smoke-{0}.png" -f [IO.Path]::GetFileNameWithoutExtension($exe) + "-" + $name)) }
        }
        if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
    }
    foreach ($log in "$profileDir\crash.log", (Join-Path $env:LOCALAPPDATA "Brasscribe\logs\bandroom-crash.log")) {
        if (Test-Path $log) { Write-Host "crash log ${log}:"; Get-Content $log | Select-Object -Last 40 | Write-Host; $script:failures += "crash log $log" }
    }
    Write-Host "Axe.Windows: Play"
    Push-Location "$Repo\apps\windows"
    dotnet run --project tools/AxeScan -c Release -- $playExe "$out\axe-play" tests/Brasscribe.Play.Core.Tests/Fixtures/two-parts.musicxml 2>&1 | Write-Host
    if ($LASTEXITCODE -ne 0) { $script:failures += "axe play" }
    Pop-Location
    if ($bandroomExe) {
        Write-Host "Axe.Windows: Bandroom"
        Push-Location "$Repo\apps\bandroom\windows"
        dotnet run --project tools/AxeScan -c Release -- $bandroomExe "$out\axe-bandroom" flyout devices confirm-stop window pair allow 2>&1 | Write-Host
        if ($LASTEXITCODE -ne 0) { $script:failures += "axe bandroom" }
        Write-Host "Bandroom screenshots"
        & ./tools/Screenshots/capture.ps1 -Exe $bandroomExe -Out "$out\bandroom" 2>&1 | Write-Host
        Pop-Location
    }
}

# Settings › Accessibility › Text size, as the Settings app writes it (100–225 %); applies at the next launch.
function Set-TextScale([int] $percent) {
    Set-ItemProperty "HKCU:\Software\Microsoft\Accessibility" TextScaleFactor $percent -Type DWord
}

$sets = @{
    default = @("home", "what-do-you-play", "score", "stand", "settings", "choose-output")
}
if ($Smoke -or $Checklist) { Smoke-Tests }
if ($Checklist) {
    Shoot-All $sets.default ""
    Set-TextScale 200
    try { Shoot-All @("what-do-you-play", "choose-output", "what-is-this", "stand", "settings", "review") "-text200" }
    finally { Set-TextScale 100 }
}
elseif ($Scenes) {
    $names = if ($Scenes -eq "default") { $sets.default } elseif ($Scenes -eq "all") {
        @("first-run", "what-do-you-play", "home", "home-offline", "settings", "what-is-this", "transcribing", "review", "review-listening", "choose-output", "score", "part", "stand", "export", "error")
    } else { $Scenes -split "," }
    Shoot-All $names ""
}

if ($failures.Count -gt 0) { Write-Host "FAILED: $($failures -join '; ')" } else { Write-Host "all ok" }
Stop-Transcript | Out-Null
Set-Content -NoNewline "$out\shots.done" ($failures -join "`n")
