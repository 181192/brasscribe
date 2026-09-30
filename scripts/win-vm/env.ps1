# The environment of the VM's scripts: an SSH session starts with the PATH sshd had when it started,
# so the toolchain's entries are read back from the registry.
$Repo = "C:\b\r"
$env:Path = @(
    [Environment]::GetEnvironmentVariable("Path", "Machine"),
    [Environment]::GetEnvironmentVariable("Path", "User"),
    "$env:USERPROFILE\.cargo\bin", "C:\Program Files\dotnet", "C:\Program Files\Git\cmd"
) -join ";"
$env:DOTNET_ROOT = "C:\Program Files\dotnet"
$env:DOTNET_ROOT_X64 = "C:\Program Files\dotnet\x64"
$env:DOTNET_CLI_TELEMETRY_OPTOUT = "1"
$env:DOTNET_NOLOGO = "1"
$env:BRASSCRIBE_REPO = $Repo
$ProgressPreference = "SilentlyContinue"
