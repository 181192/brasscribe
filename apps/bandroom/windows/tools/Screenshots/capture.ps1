# Screenshots of Brasscribe Bandroom's views, light and dark, to compare with design/mockups/png/server-*.
# Starts the app once per scene with --show NAME (sample content, see DemoEngine), finds its visible
# windows (the flyout is a tool window), waits for it to settle and captures each with PrintWindow.
#
# Usage: capture.ps1 -Exe BrasscribeBandroom.exe -Out screenshots
param(
    [Parameter(Mandatory)] [string] $Exe,
    [Parameter(Mandatory)] [string] $Out,
    [string[]] $Scenes = @("flyout", "flyout:busy", "flyout:attention", "flyout:stopped", "flyout:error", "devices", "confirm-stop", "window", "pair", "allow", "settings"),
    [string[]] $Themes = @("light", "dark"),
    [string[]] $Languages = @("en", "nb"),
    [int] $Settle = 5
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class Win {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    public delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
    public static List<IntPtr> Visible(int pid) {
        var list = new List<IntPtr>();
        EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p); if (p == pid && IsWindowVisible(h)) list.Add(h); return true; }, IntPtr.Zero);
        return list;
    }
}
"@

$failed = 0
foreach ($lang in $Languages) {
foreach ($theme in $Themes) {
    foreach ($entry in $Scenes) {
        # nb only for the main flyout and the pair window (the copy check); en for everything.
        if ($lang -ne "en" -and $entry -notin @("flyout", "pair", "flyout:busy")) { continue }
        $scene, $state = $entry.Split(":")
        $appArgs = @("--show", $scene, "--theme", $theme, "--lang", $lang)
        if ($state) { $appArgs += @("--state", $state) }
        $name = ($entry -replace ":", "-")
        $suffix = if ($lang -eq "en") { "" } else { "-$lang" }
        $p = Start-Process -FilePath $Exe -ArgumentList $appArgs -PassThru
        try {
            $deadline = (Get-Date).AddSeconds(90)
            while (([Win]::Visible($p.Id)).Count -eq 0 -and -not $p.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
            if ($p.HasExited -or ([Win]::Visible($p.Id)).Count -eq 0) { Write-Warning "${name}/${theme}: no window"; $failed++; continue }
            Start-Sleep -Seconds $Settle
            $i = 0
            foreach ($h in [Win]::Visible($p.Id)) {
                $r = New-Object Win+RECT
                [Win]::GetWindowRect($h, [ref] $r) | Out-Null
                $w = $r.Right - $r.Left; $hgt = $r.Bottom - $r.Top
                if ($w -lt 50 -or $hgt -lt 50) { continue }
                $bmp = New-Object System.Drawing.Bitmap $w, $hgt
                $g = [System.Drawing.Graphics]::FromImage($bmp)
                $hdc = $g.GetHdc()
                [Win]::PrintWindow($h, $hdc, 2) | Out-Null  # PW_RENDERFULLCONTENT
                $g.ReleaseHdc($hdc); $g.Dispose()
                $tag = if ($i -eq 0) { "" } else { "-$i" }
                $file = Join-Path $Out "server-win-$name$tag$suffix-desktop-$theme.png"
                $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
                Write-Host "captured $file ($w x $hgt)"
                $i++
            }
        }
        finally {
            if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
        }
    }
}
}
if ($failed -gt 0) { throw "$failed views could not be captured" }
