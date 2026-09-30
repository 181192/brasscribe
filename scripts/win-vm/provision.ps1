# The build toolchain of the Windows VM (scripts/win-vm.sh provision runs it over SSH). Each step is
# skipped when it is already there, so a failed run is resumed by running it again.
#   Visual Studio 2022 Build Tools: MSVC for ARM64 and x64 (the Rust core's linker), the Windows 11 SDK
#   .NET SDK 10 (ARM64): the WinUI 3 builds bring the Windows App SDK and its XAML compiler from NuGet
#   Git for Windows (ARM64), Rust with aarch64-pc-windows-msvc and x86_64-pc-windows-msvc
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest is many times slower with the progress bar
$dl = "C:\b\downloads"
New-Item -ItemType Directory -Force -Path $dl | Out-Null
function Step($m) { Write-Host "[provision] $(Get-Date -Format HH:mm:ss) $m" }
function Fetch($url, $file) {
    $path = Join-Path $dl $file
    if (-not (Test-Path $path)) { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $path }
    $path
}

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vsComponents = @(
    "Microsoft.VisualStudio.Component.VC.Tools.ARM64",
    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
    "Microsoft.VisualStudio.Component.Windows11SDK.26100"
)
$haveVs = (Test-Path $vswhere) -and (& $vswhere -products * -requires $vsComponents -property installationPath)
if (-not $haveVs) {
    Step "Visual Studio 2022 Build Tools (MSVC ARM64 and x64, Windows 11 SDK): about 15 minutes"
    $exe = Fetch "https://aka.ms/vs/17/release/vs_BuildTools.exe" "vs_BuildTools.exe"
    $vsArgs = @("--quiet", "--wait", "--norestart", "--nocache") + ($vsComponents | ForEach-Object { "--add", $_ })
    $p = Start-Process $exe -ArgumentList $vsArgs -Wait -PassThru
    # 3010: installed, a reboot is pending (it is not needed for building)
    if ($p.ExitCode -notin 0, 3010) { throw "vs_BuildTools exited with $($p.ExitCode)" }
} else { Step "Build Tools: installed" }

$dotnet = "C:\Program Files\dotnet\dotnet.exe"
if (-not ((Test-Path $dotnet) -and ((& $dotnet --list-sdks) -match "^10\."))) {
    Step ".NET SDK 10 (ARM64)"
    $script = Fetch "https://dot.net/v1/dotnet-install.ps1" "dotnet-install.ps1"
    & $script -Channel 10.0 -Architecture arm64 -InstallDir "C:\Program Files\dotnet" -NoPath
    [Environment]::SetEnvironmentVariable("DOTNET_ROOT", "C:\Program Files\dotnet", "Machine")
    [Environment]::SetEnvironmentVariable("DOTNET_CLI_TELEMETRY_OPTOUT", "1", "Machine")
    [Environment]::SetEnvironmentVariable("DOTNET_NOLOGO", "1", "Machine")
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    if ($machinePath -notlike "*C:\Program Files\dotnet*") {
        [Environment]::SetEnvironmentVariable("Path", "$machinePath;C:\Program Files\dotnet", "Machine")
    }
} else { Step ".NET SDK 10: installed" }

# x64 builds (Bandroom, the Play release) run under emulation and need the x64 runtimes, which
# Windows on ARM keeps in dotnet\x64 (found through DOTNET_ROOT_X64)
$dotnetX64 = "C:\Program Files\dotnet\x64"
if (-not ((Test-Path "$dotnetX64\dotnet.exe") -and ((& "$dotnetX64\dotnet.exe" --list-runtimes) -match "WindowsDesktop.App 10\."))) {
    Step ".NET 10 runtimes (x64, for x64 builds under emulation)"
    $script = Fetch "https://dot.net/v1/dotnet-install.ps1" "dotnet-install.ps1"
    & $script -Channel 10.0 -Architecture x64 -Runtime dotnet -InstallDir $dotnetX64 -NoPath
    & $script -Channel 10.0 -Architecture x64 -Runtime windowsdesktop -InstallDir $dotnetX64 -NoPath
    [Environment]::SetEnvironmentVariable("DOTNET_ROOT_X64", $dotnetX64, "Machine")
} else { Step ".NET 10 x64 runtimes: installed" }

if (-not (Test-Path "C:\Program Files\Git\cmd\git.exe")) {
    Step "Git for Windows (ARM64)"
    $rel = Invoke-RestMethod -UseBasicParsing "https://api.github.com/repos/git-for-windows/git/releases/latest"
    $asset = $rel.assets | Where-Object { $_.name -match "^Git-[\d.]+-arm64\.exe$" } | Select-Object -First 1
    if (-not $asset) { throw "no ARM64 Git installer in $($rel.tag_name)" }
    $exe = Fetch $asset.browser_download_url $asset.name
    Start-Process $exe -ArgumentList "/VERYSILENT", "/NORESTART", "/NOCANCEL", "/SP-", "/SUPPRESSMSGBOXES" -Wait
} else { Step "Git: installed" }

$cargo = "$env:USERPROFILE\.cargo\bin\cargo.exe"
if (-not (Test-Path $cargo)) {
    Step "Rust (stable, aarch64-pc-windows-msvc)"
    $exe = Fetch "https://static.rust-lang.org/rustup/dist/aarch64-pc-windows-msvc/rustup-init.exe" "rustup-init.exe"
    & $exe -y --profile minimal --default-toolchain stable --no-modify-path
    if ($LASTEXITCODE -ne 0) { throw "rustup-init exited with $LASTEXITCODE" }
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*\.cargo\bin*") {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$env:USERPROFILE\.cargo\bin", "User")
    }
} else { Step "Rust: installed" }
& "$env:USERPROFILE\.cargo\bin\rustup.exe" target add x86_64-pc-windows-msvc

Step "versions"
& $vswhere -products * -property catalog_productDisplayVersion
& $dotnet --list-sdks
& "C:\Program Files\Git\cmd\git.exe" --version
& "$env:USERPROFILE\.cargo\bin\rustc.exe" -vV | Select-String "release|host"
Get-PSDrive C | ForEach-Object { "C: {0:N1} GB used, {1:N1} GB free" -f ($_.Used / 1GB), ($_.Free / 1GB) }
Remove-Item -Recurse -Force $dl -ErrorAction SilentlyContinue
