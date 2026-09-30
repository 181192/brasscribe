# Builds the Windows artifacts in the VM from C:\b\r (scripts/win-vm.sh build|test|shots|release).
#   the Rust core's C ABI DLL, brasscribe_ffi.dll: ARM64 (native), and x64 with -X64
#   Brasscribe Play (WinUI 3): ARM64, and x64 with -X64
#   Brasscribe Bandroom for Windows (WinUI 3, x64 only; it runs under emulation here)
# With -Release: the self-contained Play zips for x64 and ARM64 instead, as the release job makes them.
# Writes C:\b\out\<Run>\artifacts.json (the exe and DLL paths) for test.ps1 and shots.ps1.
param([Parameter(Mandatory)] [string] $Run, [switch] $X64, [switch] $Release)
$ErrorActionPreference = "Continue"   # native tools write progress to stderr
. "$PSScriptRoot\env.ps1"
$out = "C:\b\out\$Run"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$failed = @()
$artifacts = [ordered]@{}

function Invoke-Step([string] $name, [scriptblock] $body) {
    $t = Get-Date
    Write-Host "[build] $name"
    & $body | Out-Host
    $ok = $LASTEXITCODE -eq 0
    $s = [int]((Get-Date) - $t).TotalSeconds
    Write-Host ("[build] {0}: {1} in {2} s" -f $name, ($(if ($ok) { "ok" } else { "FAILED ($LASTEXITCODE)" })), $s)
    if (-not $ok) { $script:failed += $name }
    $ok
}

$core = "$Repo\core"
$ffi = @{ arm64 = "$core\target\release\brasscribe_ffi.dll"; x64 = "$core\target\x86_64-pc-windows-msvc\release\brasscribe_ffi.dll" }
Push-Location $core
Invoke-Step "core DLL arm64" { cargo build --release --locked -p brasscribe-ffi } | Out-Null
if ($X64 -or $Release) {
    Invoke-Step "core DLL x64" { cargo build --release --locked -p brasscribe-ffi --target x86_64-pc-windows-msvc } | Out-Null
}
Pop-Location
foreach ($a in $ffi.Keys) { if (Test-Path $ffi[$a]) { $artifacts["ffi-$a"] = $ffi[$a] } }

$play = "$Repo\apps\windows"
$archs = @("arm64") + $(if ($X64 -or $Release) { @("x64") } else { @() })
Push-Location $play
foreach ($a in $archs) {
    $platform = @{ arm64 = "ARM64"; x64 = "x64" }[$a]
    if ($Release) {
        $pub = "$out\publish\BrasscribePlay-$a"
        if (Invoke-Step "Play publish $a" { dotnet publish src/Brasscribe.Play -c Release "-p:Platform=$platform" -r "win-$a" --self-contained "-p:BrasscribeFfiDll=$($ffi[$a])" -o $pub -bl:"$out\play-publish-$a.binlog" }) {
            foreach ($f in "BrasscribePlay.exe", "brasscribe_ffi.dll", "SoundFonts\brasscribe-band.sf2") {
                if (-not (Test-Path "$pub\$f")) { Write-Host "[build] MISSING in the $a publish: $f"; $failed += "publish $a has no $f" }
            }
            Compress-Archive -Force -Path $pub -DestinationPath "$out\brasscribe-play-windows-$a.zip"
            Remove-Item -Recurse -Force $pub
            $artifacts["zip-$a"] = "$out\brasscribe-play-windows-$a.zip"
        }
        continue
    }
    if (Invoke-Step "Play build $a" { dotnet build src/Brasscribe.Play -c Release "-p:Platform=$platform" "-p:RuntimeIdentifier=win-$a" "-p:BrasscribeFfiDll=$($ffi[$a])" -bl:"$out\play-$a.binlog" }) {
        $exe = Get-ChildItem -Recurse -Filter BrasscribePlay.exe "src\Brasscribe.Play\bin" | Where-Object { $_.DirectoryName -like "*win-$a*" } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($exe) { $artifacts["play-$a"] = $exe.FullName }
    }
}
Pop-Location

if (-not $Release) {
    Push-Location "$Repo\apps\bandroom\windows"
    if (Invoke-Step "Bandroom build x64" { dotnet build src/Brasscribe.Bandroom -c Release -p:Platform=x64 -p:RuntimeIdentifier=win-x64 -p:BandroomBundleWorkspace=true -bl:"$out\bandroom-x64.binlog" }) {
        $exe = Get-ChildItem -Recurse -Filter BrasscribeBandroom.exe "src\Brasscribe.Bandroom\bin" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($exe) { $artifacts["bandroom-x64"] = $exe.FullName }
    }
    Pop-Location
}

$artifacts | ConvertTo-Json | Set-Content "$out\artifacts.json"
$artifacts.GetEnumerator() | ForEach-Object { Write-Host ("[build] {0}: {1}" -f $_.Key, $_.Value) }
if ($failed.Count -gt 0) { Write-Host "[build] FAILED: $($failed -join ', ')"; exit 1 }
Write-Host "[build] all ok"
