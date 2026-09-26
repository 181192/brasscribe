# Screenshots of every screen of Brasscribe Play, light and dark, to compare with design/mockups/png.
# Starts the app once per screen with --show NAME (sample content, see PreviewScenes), waits for the
# window to settle and captures it with PrintWindow (the whole window, even when partly off screen).
#
# Usage: capture.ps1 -Exe BrasscribePlay.exe -Score two-parts.musicxml -Out screenshots
param(
    [Parameter(Mandatory)] [string] $Exe,
    [Parameter(Mandatory)] [string] $Score,
    [Parameter(Mandatory)] [string] $Out,
    [string[]] $Scenes = @("first-run", "home", "what-is-this", "transcribing", "review", "choose-output", "score", "part", "export", "error"),
    [string[]] $Themes = @("light", "dark"),
    [int] $Settle = 6
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
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

$failed = 0
foreach ($theme in $Themes) {
    foreach ($scene in $Scenes) {
        $appArgs = @("--show", $scene, "--theme", $theme, "--score", (Resolve-Path $Score).Path)
        $p = Start-Process -FilePath $Exe -ArgumentList $appArgs -PassThru
        try {
            $deadline = (Get-Date).AddSeconds(90)
            while ($p.MainWindowHandle -eq 0 -and -not $p.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500; $p.Refresh() }
            if ($p.HasExited -or $p.MainWindowHandle -eq 0) { Write-Warning "${scene}/${theme}: no window"; $failed++; continue }
            [Win]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
            Start-Sleep -Seconds $Settle
            $r = New-Object Win+RECT
            [Win]::GetWindowRect($p.MainWindowHandle, [ref] $r) | Out-Null
            $w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
            $bmp = New-Object System.Drawing.Bitmap $w, $h
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            $hdc = $g.GetHdc()
            [Win]::PrintWindow($p.MainWindowHandle, $hdc, 2) | Out-Null  # PW_RENDERFULLCONTENT
            $g.ReleaseHdc($hdc); $g.Dispose()
            $file = Join-Path $Out "$scene-desktop-$theme.png"
            $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
            Write-Host "captured $file ($w x $h)"
        }
        finally {
            if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
        }
    }
}
if ($failed -gt 0) { throw "$failed screens could not be captured" }
