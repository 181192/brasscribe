# First logon of the build VM (autounattend.xml runs it from the setup drive, as the user "brass").
# Installs the virtio network driver and OpenSSH Server with the host's key, and sets what a headless
# build and screenshot VM needs: auto-logon on every boot, no lock screen, no sleep, no hibernation,
# Windows Update paused, long paths. Idempotent. The host waits for SSH, then carries on over it.
param([string] $Drive = "D:")
$ErrorActionPreference = "Continue"
Start-Transcript -Path C:\firstlogon-transcript.log -Append | Out-Null
function Step($m) { Write-Host "[firstlogon] $(Get-Date -Format HH:mm:ss) $m" }

Step "network and display drivers (virtio NetKVM and viogpudo, ARM64)"
# trust the drivers' publisher first, so installing them never waits on a "Would you like to install" prompt
Get-ChildItem "$Drive\drivers" -Recurse -Filter *.cat | ForEach-Object {
    $signer = (Get-AuthenticodeSignature $_.FullName).SignerCertificate
    if ($signer) {
        $store = New-Object System.Security.Cryptography.X509Certificates.X509Store "TrustedPublisher", "LocalMachine"
        $store.Open("ReadWrite"); $store.Add($signer); $store.Close()
    }
}
pnputil /add-driver "$Drive\drivers\*.inf" /subdirs /install

Step "OpenSSH Server"
$msi = Get-ChildItem "$Drive\OpenSSH-*.msi" | Select-Object -First 1
if ($msi) { Start-Process msiexec.exe -Wait -ArgumentList "/i `"$($msi.FullName)`" /qn ADDLOCAL=Server" }
if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {
    Step "no MSI or it failed: the Windows capability (needs Windows Update)"
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
}
$keys = "C:\ProgramData\ssh\administrators_authorized_keys"
New-Item -ItemType Directory -Force -Path C:\ProgramData\ssh | Out-Null
Copy-Item "$Drive\authorized_keys" $keys -Force
# sshd ignores the file unless only Administrators and SYSTEM can read it
icacls $keys /inheritance:r /grant "*S-1-5-32-544:F" /grant "*S-1-5-18:F" | Out-Null
Set-Service sshd -StartupType Automatic
Start-Service sshd
if (-not (Get-NetFirewallRule -Name brasscribe-sshd -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name brasscribe-sshd -DisplayName "OpenSSH Server (brasscribe VM)" -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow | Out-Null
}

Step "auto-logon on every boot, no lock screen, no sleep"
$wl = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
Set-ItemProperty $wl AutoAdminLogon "1"
Set-ItemProperty $wl DefaultUserName "brass"
Set-ItemProperty $wl DefaultPassword "brass"
Set-ItemProperty $wl DefaultDomainName $env:COMPUTERNAME
Remove-ItemProperty $wl AutoLogonCount -ErrorAction SilentlyContinue
New-Item -Force "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization" | Out-Null
Set-ItemProperty "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization" NoLockScreen 1 -Type DWord
Set-ItemProperty "HKCU:\Control Panel\Desktop" ScreenSaveActive "0"
powercfg /change monitor-timeout-ac 0
powercfg /change standby-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /h off
# no password prompt after the display would have gone off
powercfg /setacvalueindex SCHEME_CURRENT SUB_NONE CONSOLELOCK 0

Step "Windows Update paused, no reboots with a user logged on, no consumer apps"
$au = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
New-Item -Force $au | Out-Null
Set-ItemProperty $au NoAutoUpdate 1 -Type DWord
Set-ItemProperty $au NoAutoRebootWithLoggedOnUsers 1 -Type DWord
$cc = "HKLM:\SOFTWARE\Policies\Microsoft\Windows\CloudContent"
New-Item -Force $cc | Out-Null
Set-ItemProperty $cc DisableWindowsConsumerFeatures 1 -Type DWord
Set-ItemProperty $cc DisableCloudOptimizedContent 1 -Type DWord

Step "disk: no reserved storage, long paths, a small pagefile"
DISM /Online /Set-ReservedStorageState /State:Disabled /NoRestart | Out-Null
Set-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" LongPathsEnabled 1 -Type DWord
$cs = Get-CimInstance Win32_ComputerSystem
if ($cs.AutomaticManagedPagefile) {
    Set-CimInstance -InputObject $cs -Property @{ AutomaticManagedPagefile = $false }
    Get-CimInstance Win32_PageFileSetting | Remove-CimInstance -ErrorAction SilentlyContinue
    New-CimInstance -ClassName Win32_PageFileSetting -Property @{ Name = "C:\pagefile.sys"; InitialSize = [uint32]2048; MaximumSize = [uint32]4096 } | Out-Null
}

Step "Defender: skip the build folders"
New-Item -ItemType Directory -Force -Path C:\b | Out-Null
Add-MpPreference -ExclusionPath "C:\b", "$env:USERPROFILE\.nuget", "$env:USERPROFILE\.cargo", "$env:USERPROFILE\.rustup", "C:\Program Files\dotnet" -ErrorAction SilentlyContinue

Step "done"
Set-Content C:\firstlogon.done (Get-Date -Format o)
Stop-Transcript | Out-Null
