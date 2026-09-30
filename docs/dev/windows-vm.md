# Windows builds, tests and screenshots in a virtual machine

Brasscribe Play for Windows (`apps/windows`) and Bandroom for Windows (`apps/bandroom/windows`) are
WinUI 3 apps. Their XAML compiler, PRI generation and the apps themselves run only on Windows. The
Windows VM lets you build, test and screenshot them on this Mac:

- Windows 11 ARM64 runs in QEMU with Apple's Hypervisor.framework (HVF), at near-native speed.
- The VM is headless (`-display none`). It has no window on the host and never touches the host's
  mouse or keyboard.
- Everything runs over SSH, on 127.0.0.1 only. UI work runs in the VM's own logged-on session, through
  a scheduled task.

```sh
scripts/win-vm.sh provision          # once: the ISO, unattended Windows setup, the toolchain (resumable)
scripts/win-vm.sh build [--x64]      # sync this checkout in; the core DLL, Play (ARM64, + x64) and Bandroom
scripts/win-vm.sh test               # build, the .NET tests, the smoke tests and the Axe.Windows scans
scripts/win-vm.sh shots [SCENES]     # Play screenshots: en/nb × light/dark/Pink/Pink dark
scripts/win-vm.sh checklist          # the automatable steps of windows-checklist.md, with 200 % text shots
scripts/win-vm.sh release            # the self-contained Play zips, x64 and ARM64
scripts/win-vm.sh ssh [command]      # a shell (PowerShell), or one cmd.exe command
scripts/win-vm.sh screen [file.png]  # the VM's screen, as a PNG
scripts/win-vm.sh down [--reset]     # shut down; --reset also drops the overlay disk
scripts/win-vm.sh status             # state, disks, free space, the last timings
```

Results land in `build/win-vm/<command>-<time>/`:

- `build.log`, and the MSBuild binlogs (`play-arm64.binlog`, …). Open them with the MSBuild
  Structured Log Viewer. They hold every XAML compiler message with its file and line.
- `test-results/*.trx`.
- `*.png`.
- `shots.log`, which is the transcript of the in-session part.

Runs from different worktrees queue on a host-wide lock (`~/.brasscribe-vm/windows.lock`). A
command refuses to start the VM when the host has less than 15 GB free (`WIN_VM_MIN_FREE_GB`).

## When to use it

It is tier 3 in [verify.md](verify.md): use it for a release and for changes that touch the Windows
apps' XAML, their native interop or their packaging. `tools/check-macos.sh` (tier 2) still covers the
C# of both apps without the VM.

## Install

```sh
brew install qemu                                   # qemu-system-aarch64 and the EDK2 UEFI firmware
brew install aria2 cabextract wimlib cdrtools       # only to make the install ISO from Microsoft's update files
```

The ISO step also needs `chntpw`, which Homebrew does not have. Build it once from its source (about
10 s). It needs no OpenSSL for the registry editing the converter does:

```sh
curl -fsSLO http://pogostick.net/~pnh/ntpasswd/chntpw-source-140201.zip && unzip -q chntpw-source-140201.zip
make -C chntpw-140201 chntpw CFLAGS="-g -I. -w" LIBS=
mkdir -p ~/.brasscribe-vm/bin && cp chntpw-140201/chntpw ~/.brasscribe-vm/bin/   # on PATH for `iso`
```

No `sudo` is needed anywhere.

## The Windows image and the licence

The VM runs **Windows 11 Pro ARM64, unactivated**:

- Setup uses Microsoft's generic Pro setup key. That key selects the edition and does not activate.
- An unactivated Windows works fully for development and testing. It shows an "Activate Windows"
  watermark, and some personalisation settings are locked. The screenshots crop to the app's window,
  so the watermark never shows in them.
- For a longer-lived setup, activate it with a Windows 11 Pro licence you own.

There are two sources for the install ISO. Both give Microsoft's own files.

1. **Microsoft's download page, in a browser.** Open
   <https://www.microsoft.com/en-us/software-download/windows11arm64>, choose "Windows 11
   (multi-edition ISO for Arm64)", English, and save the ISO to `~/Downloads`. `iso` picks up
   `~/Downloads/Win11*Arm64*.iso`, or set `WIN_VM_ISO=path`.
   - A script can't use this page. Its download API answers every automated request with
     "Sentinel marked this request as rejected".
2. **Microsoft's update servers (the default when there's no downloaded ISO).**
   - `iso` fetches the file list for one Windows 11 build from uupdump.net: `WIN_VM_UUP_ID`, by
     default 25H2 26200.9550 arm64, Pro, en-US.
   - It downloads the files from Microsoft's Windows Update CDN, with their SHA-1 checked.
   - It converts them into an ISO with uupdump's converter (wimlib), including the latest cumulative
     update.
   - It takes about 8 GB of download. The download folder is deleted afterwards.

Either way the ISO is written again with the EFI boot image that does not wait for "Press any key to
boot from CD or DVD". A headless VM has no one to press it.

## What `provision` does

Every step is skipped when it is already done, so a failed run is resumed by running `provision`
again. The timings go to `~/.brasscribe-vm/windows/timings.log`.

1. **The ISO** (see above): `~/.brasscribe-vm/windows/iso/win11-arm64.iso`.
2. **A setup CD.** `setup.iso` holds:
   - [`autounattend.xml`](../../scripts/win-vm/autounattend.xml) and
     [`firstlogon.ps1`](../../scripts/win-vm/firstlogon.ps1)
   - the ARM64 virtio network driver, from the Fedora `virtio-win` ISO
   - the Win32-OpenSSH ARM64 MSI
   - the host's public key, `~/.brasscribe-vm/windows/id_ed25519.pub`
3. **Unattended Windows setup** into `base.qcow2`: a 64 GB thin disk on an emulated NVMe drive.
   - The VM has no TPM and no Secure Boot keys, so setup's hardware checks are bypassed
     (`LabConfig`).
   - Setup wipes the disk and installs Pro, then skips OOBE (no Microsoft account, no network
     needed).
   - It creates the local administrator **`brass`** (password `brass`) and turns on auto-logon.
   - At the first logon, `firstlogon.ps1`:
     - installs the network driver and OpenSSH Server, with key-only access for the host
     - keeps auto-logon on every boot, and turns off the lock screen, sleep and hibernation
     - pauses Windows Update, and turns off reserved storage
     - enables long paths, and adds Defender exclusions for the build folders
   - The VM's SSH port is forwarded to `127.0.0.1:52222` on the host only (`WIN_VM_SSH_PORT`), so the
     password never matters outside the VM.
4. **The toolchain**, over SSH ([`provision.ps1`](../../scripts/win-vm/provision.ps1)):
   - Visual Studio 2022 Build Tools, with MSVC for ARM64 and x64 and the Windows 11 SDK 26100
   - .NET SDK 10 (ARM64), plus the x64 .NET 10 runtimes for x64 builds under emulation
   - Git for Windows (ARM64)
   - Rust stable (`aarch64-pc-windows-msvc`, plus the `x86_64-pc-windows-msvc` target)

   The Windows App SDK, WinUI's XAML compiler and the SDK build tools come from NuGet with the
   projects, so no Visual Studio workload is needed for them.
5. **Trim and compact.** TRIM, a shutdown, and `qemu-img convert` so the base holds only used blocks.

The base is never booted again. `up` puts an overlay (`vm.qcow2`) on it and boots that. The overlay
keeps the NuGet cache, cargo's target dir and the build output between runs, which is what makes
builds warm. `down --reset` throws the overlay away. After that, the next `up` starts from the clean
base in about a minute.

## What the commands do

`build` streams this checkout into `C:\b\r` as a tar over SSH. That covers tracked files, and
untracked files that aren't ignored. Unchanged files keep their times, so cargo and MSBuild stay
incremental. Files deleted on the host stay in the VM until `down --reset`. The band SoundFonts are
copied once, when their size changes. Then
[`build.ps1`](../../scripts/win-vm/build.ps1) builds:

- `brasscribe_ffi.dll`, the Rust core's C ABI: ARM64 always, and x64 with `--x64`
- Brasscribe Play: ARM64 always (native in the VM), and x64 with `--x64`. That is the build CI and the
  release ship.
- Bandroom for Windows: x64 only (its projects list only x64). It runs under Windows' x64 emulation.

`test` runs [`test.ps1`](../../scripts/win-vm/test.ps1) with the ARM64 native core:

- Play's core tests
- the core's .NET binding tests
- Bandroom's core tests

It then runs the same smoke tests as CI, in the logged-on session: each app starts and shows its
window, and no crash log is written. It also runs the Axe.Windows scans of both apps and Bandroom's
screenshot script.

`shots` starts Play once per screen with `--show SCENE --theme … --lang …`, with a fresh
`settings.json` each time (`"Appearance": "pink"` for Pink). It captures the window with
`PrintWindow`, in [`shots.ps1`](../../scripts/win-vm/shots.ps1). Files are named
`<scene>-<en|nb>-<light|dark|pink|pink-dark>.png`.

- `SCENES` can be `default` (home, what-do-you-play, score, stand, settings, choose-output), `all`
  (every `PreviewScenes` name), or a comma-separated list.
- The window is 1920 × 1080 at 100 % scale (`WIN_VM_SCREEN`).

`checklist` runs `test`, then `shots default`, then the checklist's 200 % text scenes, all into one
run folder. The 200 % text size is `HKCU\Software\Microsoft\Accessibility\TextScaleFactor`, the
value Settings › Accessibility › Text size writes, and it is reset to 100 % afterwards.

What it covers of [windows-checklist.md](windows-checklist.md):

| Section | Automated here | Left for a person |
|---|---|---|
| 0 Build | 1 (with the binlogs), 2 (tests, smoke, Axe), 3 (fresh profile for every launch) | |
| 1 My instrument | the "What do you play?" screen in en/nb | picking seats, a real take: it needs a paired engine |
| 2 Music stand | the stand's first view | page keys, pedal, Narrator |
| 3 Appearance and Pink | Settings and every scene in Light, Dark, Pink, Pink dark | the five-tap unlock, the contrast themes, restart |
| 4 Quiet recording | | all of it: audio |
| 5 Narrator | | all of it: Narrator can't be driven from a script |
| 6 200 % text | shots of each listed screen at 200 % | judging that nothing is clipped, from the shots |

`release` makes the release job's self-contained Play build for x64 and ARM64. See
[release.md](release.md#5a-windows-built-not-shipped-yet).

## Resources and timings

| | |
|---|---|
| VM | 8 vCPUs (`WIN_VM_CPUS`), 8 GB (`WIN_VM_MEMORY_MB`), NVMe disk, virtio network, virtio-gpu 1920 × 1080 (the firmware framebuffer, no guest driver) |
| Disk on the host | ISO ~6 GB; base TIMING_BASE_GB GB after compaction; the overlay grows with builds (TIMING_OVERLAY_GB GB after a build and test) |
| Cold provision | TIMING_PROVISION (ISO TIMING_ISO, Windows setup to SSH TIMING_SETUP, toolchain TIMING_TOOLCHAIN) |
| `up` from off | TIMING_UP |
| Cold build (fresh overlay) | TIMING_COLD_BUILD |
| Warm build (no change) | TIMING_WARM_BUILD |
| Warm test run | TIMING_WARM_TEST |
| `shots default` (48 shots) | TIMING_SHOTS |

## Troubleshooting

- **Where is setup?** `scripts/win-vm.sh screen` saves the VM's display as a PNG. It works headless,
  at any point, Windows setup included.
- **No SSH after setup.** Look at the screen first. If Windows is at the desktop, `C:\firstlogon.log`
  in the VM says what failed. The usual causes are:
  - the network driver did not install (no network, so no OpenSSH either)
  - `administrators_authorized_keys` has the wrong ACL (sshd then ignores it without a word)

  Reprovision with `rm ~/.brasscribe-vm/windows/base.qcow2 && scripts/win-vm.sh provision`. The ISO
  and the downloads are kept.
- **The ISO boots to a UEFI shell or recovery.** Either the ISO lacks `efisys_noprompt.bin`, or the
  converter's registry edit (`chntpw`) failed. Check with
  `wimlib-imagex extract …/boot.wim 1 /Windows/System32/config/SOFTWARE`, then
  `chntpw -e SOFTWARE` and `cat` of `Microsoft\Windows NT\CurrentVersion\WinPE\InstRoot`.
- **A black screenshot.** The session is locked, or the display went to sleep. `firstlogon.ps1`
  turns both off. Run it again from `D:\` (the setup CD, attached only while provisioning), or set
  the values by hand.
- **"VM busy".** Another worktree holds the lock. If its process is gone, the lock is taken over.
- **The host is short of disk.** `down --reset` frees the overlay. The ISO can be deleted once the
  base is provisioned, since only a new `provision` needs it.
- **x64 apps.** They run under emulation (Prism) and start more slowly than the ARM64 build. The
  smoke test allows 90 s for a window.
