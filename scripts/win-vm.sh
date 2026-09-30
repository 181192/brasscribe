#!/usr/bin/env bash
# The Windows builds, tests and screenshots run in a headless Windows 11 ARM64 VM (QEMU with HVF) on
# this Mac. See docs/dev/windows-vm.md.
#
#   scripts/win-vm.sh iso                make the install ISO (from Microsoft's update servers, or WIN_VM_ISO=<the ARM64 ISO>)
#   scripts/win-vm.sh provision          install Windows unattended and the toolchain into the base disk (resumable)
#   scripts/win-vm.sh up                 start the VM (an overlay on the base) headless and wait for SSH
#   scripts/win-vm.sh down [--reset]     shut the VM down; --reset also deletes the overlay (the next up starts from the base)
#   scripts/win-vm.sh status             the VM, its disks and the host's free space
#   scripts/win-vm.sh ssh [command]      a shell (or one cmd.exe command) in the VM
#   scripts/win-vm.sh build [--x64]      sync this checkout in, build the core DLL (ARM64, and x64 with --x64),
#                                        Brasscribe Play and Bandroom for Windows; logs in build/win-vm/<run>/
#   scripts/win-vm.sh test               build, then the .NET tests (Play core, Bandroom core), the smoke tests and Axe.Windows
#   scripts/win-vm.sh shots [SCENES]     build, then screenshots of Play in en/nb, light/dark/Pink into build/win-vm/<run>/
#   scripts/win-vm.sh checklist          the automatable steps of docs/dev/windows-checklist.md, with 200 % text shots
#   scripts/win-vm.sh release            the self-contained x64 and ARM64 zips of Play into build/win-vm/<run>/
#   scripts/win-vm.sh screen [file.png]  a screendump of the VM's display (QMP), e.g. while Setup runs
#
# The VM has no window on the host (-display none) and never touches the host's mouse or keyboard.
# Everything runs over SSH; UI work runs in the VM's auto-logged-on session through a scheduled task.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HERE="$ROOT/scripts/win-vm"
DIR="${WIN_VM_DIR:-$HOME/.brasscribe-vm/windows}"
CPUS="${WIN_VM_CPUS:-8}"
MEMORY_MB="${WIN_VM_MEMORY_MB:-8192}"
DISK_GB="${WIN_VM_DISK_GB:-64}"          # virtual size; qcow2 grows only as Windows writes
SCREEN="${WIN_VM_SCREEN:-1920x1080}"
PORT="${WIN_VM_SSH_PORT:-52222}"         # 127.0.0.1 only
MIN_FREE_GB="${WIN_VM_MIN_FREE_GB:-15}"
UUP_ID="${WIN_VM_UUP_ID:-8c5f8bc1-bb0a-4f87-b444-0942d610a4dd}"   # Windows 11 25H2 26200.9550 arm64 (uupdump.net)
OPENSSH_MSI="${WIN_VM_OPENSSH_MSI:-https://github.com/PowerShell/Win32-OpenSSH/releases/download/10.0.0.0p2-Preview/OpenSSH-ARM64-v10.0.0.0.msi}"
VIRTIO_ISO_URL="https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso"

ISO="$DIR/iso/win11-arm64.iso"       # the install ISO, remastered to boot without "Press any key"
VIRTIO="$DIR/iso/virtio-win.iso"
LANG_FILE="$DIR/iso/language"        # the install ISO's language (en-US, en-GB, …): Setup's UI language must be it
SETUP_ISO="$DIR/setup.iso"           # autounattend.xml, firstlogon.ps1, drivers, OpenSSH, the host's key
BASE="$DIR/base.qcow2"               # the provisioned base; never booted once an overlay exists
BASE_VARS="$DIR/base-vars.fd"
PROVISIONED="$DIR/base.provisioned"
DISK="$DIR/vm.qcow2"                 # the VM's overlay on the base: keeps NuGet, cargo and build caches warm
VARS="$DIR/vm-vars.fd"
KEY="$DIR/id_ed25519"
QMP="$DIR/qmp.sock"
PIDFILE="$DIR/qemu.pid"
TIMINGS="$DIR/timings.log"
FW="$(brew --prefix 2>/dev/null || echo /opt/homebrew)/share/qemu"
OUT="$ROOT/build/win-vm"
REMOTE='C:\b\r'                      # the checkout in the VM (short: WinAppSDK and NuGet paths are long)

QEMU="$(command -v qemu-system-aarch64 || true)"
[ -n "$QEMU" ] || { echo "error: qemu-system-aarch64 not found (brew install qemu; see docs/dev/windows-vm.md)" >&2; exit 1; }

log() { printf '[win-vm] %s\n' "$*" >&2; }
timing() { printf '%s %-28s %5d s\n' "$(date +%Y-%m-%dT%H:%M:%S)" "$1" "$2" >>"$TIMINGS"; log "time: $1 $2 s"; }
COMMON_OPTS=(-i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR
             -o ConnectTimeout=5 -o ServerAliveInterval=30 -o IdentitiesOnly=yes -o BatchMode=yes)
SSH_OPTS=(-p "$PORT" "${COMMON_OPTS[@]}")
SCP_OPTS=(-P "$PORT" "${COMMON_OPTS[@]}")
vssh() { ssh "${SSH_OPTS[@]}" brass@127.0.0.1 "$@"; }
# A PowerShell script from the host, run in the VM with arguments: vps <script.ps1> [args…]
vps() {
  local script="$1"; shift
  scp -q "${SCP_OPTS[@]}" "$HERE"/*.ps1 "brass@127.0.0.1:C:/b/"
  vssh "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\b\\$(basename "$script") $*"
}

running() { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }
ssh_ok() { [ -f "$KEY" ] && vssh "exit 0" </dev/null >/dev/null 2>&1; }

# Refuse to start when the host's disk is nearly full: the VM's disk grows into it.
check_disk() {
  local free; free="$(df -g "$HOME" | awk 'NR==2 {print $4}')"
  if [ "$free" -lt "$MIN_FREE_GB" ]; then
    echo "error: only $free GB free on the host (WIN_VM_MIN_FREE_GB=$MIN_FREE_GB); not starting the VM" >&2; exit 1
  fi
}

# Tiny QMP client: qmp '{"execute": …}' prints the reply.
qmp() {
  python3 - "$QMP" "$@" <<'EOF'
import json, socket, sys
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); f = s.makefile("rw")
f.readline()
def cmd(c):
    f.write(json.dumps(c) + "\n"); f.flush()
    while True:
        r = json.loads(f.readline())
        if "return" in r or "error" in r: return r
cmd({"execute": "qmp_capabilities"})
for a in sys.argv[2:]:
    print(json.dumps(cmd(json.loads(a))))
EOF
}

# The VM's display as a PNG (works headless: QEMU keeps the framebuffer).
screen() {
  local file="${1:-$OUT/screen-$(date +%H%M%S).png}"
  mkdir -p "$(dirname "$file")"
  running || { echo "error: the VM is not running" >&2; exit 1; }
  qmp "{\"execute\": \"screendump\", \"arguments\": {\"filename\": \"$file\", \"format\": \"png\"}}" >/dev/null
  echo "$file"
}

# Start QEMU headless on <disk> <vars> [install]: with "install", the install ISO and the setup ISO are attached.
start() {
  local disk="$1" vars="$2" install="${3:-}"
  running && return
  check_disk
  mkdir -p "$OUT"
  # The install boots the ISO only while the disk is still empty: the disk comes first in the boot
  # order, so Setup's reboot starts Windows from the disk instead of Setup again. Setup's display is
  # ramfb (a plain framebuffer Windows can draw on without a driver); afterwards it is virtio-gpu,
  # driven by viogpudo from firstlogon.ps1, at $SCREEN.
  local media=() display=(-device "virtio-gpu-pci,xres=${SCREEN%x*},yres=${SCREEN#*x}")
  if [ -n "$install" ]; then
    media=(-drive "if=none,id=cd0,media=cdrom,readonly=on,file=$ISO" -device "usb-storage,drive=cd0,removable=on,bootindex=1"
           -drive "if=none,id=cd1,media=cdrom,readonly=on,file=$SETUP_ISO" -device "usb-storage,drive=cd1,removable=on")
    display=(-device ramfb)
  fi
  rm -f "$QMP"
  log "starting the VM headless ($CPUS CPUs, $MEMORY_MB MB, no window, no host input)"
  "$QEMU" -name brasscribe-win \
    -machine virt,highmem=on,gic-version=3 -accel hvf -cpu host -smp "$CPUS" -m "$MEMORY_MB" \
    -drive "if=pflash,format=raw,readonly=on,file=$FW/edk2-aarch64-code.fd" -drive "if=pflash,format=raw,file=$vars" \
    "${display[@]}" \
    -device qemu-xhci,id=xhci -device usb-kbd -device usb-tablet \
    -drive "if=none,id=disk,file=$disk,format=qcow2,discard=unmap,detect-zeroes=unmap,cache=writeback" \
    -device nvme,drive=disk,serial=brasscribe,bootindex=0 \
    -netdev "user,id=net0,hostfwd=tcp:127.0.0.1:$PORT-:22" -device virtio-net-pci,netdev=net0 \
    ${media[@]+"${media[@]}"} \
    -rtc base=localtime -display none -monitor none -serial none \
    -qmp "unix:$QMP,server=on,wait=off" -pidfile "$PIDFILE" -daemonize \
    >>"$DIR/qemu.log" 2>&1
}

wait_ssh() {  # [minutes]
  local deadline=$((SECONDS + ${1:-5} * 60))
  until ssh_ok; do
    running || { echo "error: the VM stopped (log: $DIR/qemu.log)" >&2; exit 1; }
    [ "$SECONDS" -lt "$deadline" ] || { echo "error: no SSH after ${1:-5} min; see scripts/win-vm.sh screen" >&2; exit 1; }
    sleep 5
  done
}

# Shut the guest down cleanly (and wait); kill QEMU if it does not stop.
stop() {
  running || return 0
  log "shutting the VM down"
  vssh "shutdown /s /t 0" </dev/null >/dev/null 2>&1 || qmp '{"execute": "system_powerdown"}' >/dev/null 2>&1 || true
  local i; for i in $(seq 1 120); do running || break; sleep 1; done
  if running; then log "the VM did not stop in 2 min; killing QEMU"; kill "$(cat "$PIDFILE")"; sleep 2; fi
  rm -f "$PIDFILE" "$QMP"
}

# --- the install ISO ---------------------------------------------------------------------------------

# Remaster <source dir> into $ISO with the EFI boot image that does not wait for a key press.
remaster() {
  local src="$1" label="${2:-CCCOMA_A64FRE_EN-US_DV9}"
  [ -f "$src/efi/microsoft/boot/efisys_noprompt.bin" ] || { echo "error: $src has no efisys_noprompt.bin" >&2; exit 1; }
  mkdir -p "$(dirname "$ISO")"
  log "writing $ISO (UDF, EFI boot without the key prompt)"
  mkisofs -quiet -b efi/microsoft/boot/efisys_noprompt.bin -no-emul-boot -udf -iso-level 3 -hide '*' \
    -V "$label" -o "$ISO.tmp" "$src"
  mv "$ISO.tmp" "$ISO"
}

# From Microsoft's Windows Update servers through uupdump.net's scripts (only the file list comes from
# uupdump.net; the files are Microsoft's and are checked against their SHA-1). Needs aria2, cabextract,
# wimlib, cdrtools and chntpw (built from source: docs/dev/windows-vm.md).
iso_from_uup() {
  local work="$DIR/uup"
  export PATH="$HOME/.brasscribe-vm/bin:$PATH"   # chntpw, built from source
  for t in aria2c cabextract wimlib-imagex mkisofs chntpw; do
    command -v "$t" >/dev/null || { echo "error: $t not found (see docs/dev/windows-vm.md, The install ISO)" >&2; exit 1; }
  done
  mkdir -p "$work" && cd "$work"
  if [ ! -f files/convert.sh ]; then
    curl -fsSL -o uup.zip -X POST -d 'autodl=2&updates=1&cleanup=1' \
      "https://uupdump.net/get.php?id=$UUP_ID&pack=en-us&edition=professional"
    unzip -o -q uup.zip
    aria2c --no-conf --console-log-level=warn -x16 -s16 -j2 --allow-overwrite=true --auto-file-renaming=false -d files -i files/converter_multi
  fi
  log "downloading Windows 11 Pro ARM64 (en-US) from Microsoft's update servers, ~5 GB"
  aria2c --no-conf --console-log-level=warn -o aria2_script.txt --allow-overwrite=true --auto-file-renaming=false \
    "https://uupdump.net/get.php?id=$UUP_ID&pack=en-us&edition=professional&aria2=2"
  if grep -q '#UUPDUMP_ERROR:' aria2_script.txt; then echo "error: $(grep '#UUPDUMP_ERROR:' aria2_script.txt)" >&2; exit 1; fi
  aria2c --no-conf --console-log-level=warn --summary-interval=0 -x16 -s16 -j5 -c -R -d UUPs -i aria2_script.txt
  # boot without "Press any key to boot from CD": the converter's mkisofs takes the no-prompt EFI image
  sed -i '' 's#efi/microsoft/boot/efisys.bin#efi/microsoft/boot/efisys_noprompt.bin#g' files/convert.sh
  log "converting (wimlib), ~20 min"
  chmod +x files/convert.sh
  files/convert.sh wim UUPs 0
  local built; built="$(ls -t ./*.ISO ./*.iso 2>/dev/null | head -1)"
  [ -n "$built" ] || { echo "error: the converter wrote no ISO" >&2; exit 1; }
  mkdir -p "$(dirname "$ISO")"; mv "$built" "$ISO"
  echo en-US >"$LANG_FILE"
  cd "$ROOT"
  rm -rf "$work/UUPs" "$work/ISODIR"
}

# From Microsoft's download page (a browser download: the scripted API refuses automated requests).
iso_from_download() {
  local src="$1" mnt
  mnt="$(hdiutil attach -readonly -nobrowse -noverify "$src" | awk -F'\t' '/\/Volumes\//{print $NF}' | tail -1)"
  [ -n "$mnt" ] || { echo "error: could not attach $src" >&2; exit 1; }
  remaster "$mnt" "$(basename "$mnt")" || { hdiutil detach -quiet "$mnt"; exit 1; }
  hdiutil detach -quiet "$mnt"
  # Setup's language is the ISO's own (the label ends in _EN-GB_DV9 for an en-GB ISO)
  basename "$mnt" | sed -E 's/.*_([A-Z]{2})-([A-Z]{2})_.*/\1-\2/' | awk -F- '{print tolower($1) "-" $2}' >"$LANG_FILE"
}

iso() {
  local t=$SECONDS src="${WIN_VM_ISO:-}"
  [ -n "$src" ] || src="$(ls -t "$HOME"/Downloads/Win*11*[Aa][Rr][Mm]64*.iso 2>/dev/null | head -1 || true)"
  if [ -f "$ISO" ] && [ -z "${WIN_VM_ISO:-}" ]; then log "install ISO: $ISO"; return; fi
  if [ -n "$src" ]; then iso_from_download "$src"; else iso_from_uup; fi
  timing "iso" $((SECONDS - t))
}

# --- provisioning ------------------------------------------------------------------------------------

# The second CD of the install: the answer file, the first-logon script, the ARM64 virtio drivers
# (network, and display: the firmware's virtio-gpu GOP is blit-only, so Windows needs viogpudo to draw
# at 1920 × 1080), OpenSSH Server and the host's public key.
setup_iso() {
  [ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N '' -C brasscribe-win -f "$KEY"
  [ -f "$VIRTIO" ] || { log "downloading the virtio-win drivers"; curl -fsSL -o "$VIRTIO.tmp" "$VIRTIO_ISO_URL"; mv "$VIRTIO.tmp" "$VIRTIO"; }
  local msi="$DIR/iso/$(basename "$OPENSSH_MSI")"
  [ -f "$msi" ] || { log "downloading OpenSSH for Windows (ARM64)"; curl -fsSL -o "$msi.tmp" "$OPENSSH_MSI"; mv "$msi.tmp" "$msi"; }
  local stage; stage="$(mktemp -d)"
  cp "$HERE/firstlogon.ps1" "$msi" "$stage/"
  sed "s#<UILanguage>en-US</UILanguage>#<UILanguage>$(cat "$LANG_FILE" 2>/dev/null || echo en-US)</UILanguage>#g" \
    "$HERE/autounattend.xml" >"$stage/autounattend.xml"
  cp "$KEY.pub" "$stage/authorized_keys"
  local mnt; mnt="$(hdiutil attach -readonly -nobrowse -noverify "$VIRTIO" | awk -F'\t' '/\/Volumes\//{print $NF}' | tail -1)"
  mkdir -p "$stage/drivers"
  local d; for d in NetKVM viogpudo; do
    [ -d "$mnt/$d/w11/ARM64" ] && cp -R "$mnt/$d/w11/ARM64" "$stage/drivers/$d"
  done
  hdiutil detach -quiet "$mnt"
  [ -n "$(ls "$stage/drivers")" ] || { echo "error: no ARM64 drivers in $VIRTIO" >&2; exit 1; }
  rm -f "$SETUP_ISO"
  hdiutil makehybrid -quiet -iso -joliet -default-volume-name BCSETUP -o "$SETUP_ISO" "$stage"
  chmod -R u+w "$stage"; rm -rf "$stage"   # the drivers come read-only off the CD
}

# Install Windows into the base disk, then the toolchain. Each stage is skipped when it is done.
provision() {
  check_disk
  mkdir -p "$DIR" "$OUT"
  local t0=$SECONDS t
  if [ -f "$DISK" ]; then
    echo "error: an overlay (vm.qcow2) sits on the base; 'down --reset' first, provisioning changes the base" >&2; exit 1
  fi
  running && stop
  iso
  rm -f "$PROVISIONED"
  if [ ! -f "$BASE" ]; then
    setup_iso
    qemu-img create -q -f qcow2 "$BASE" "${DISK_GB}G"
    cp "$FW/edk2-arm-vars.fd" "$BASE_VARS"
    # the pflash vars must be as large as the code image
    truncate -s "$(stat -f %z "$FW/edk2-aarch64-code.fd")" "$BASE_VARS"
    t=$SECONDS
    start "$BASE" "$BASE_VARS" install
    log "installing Windows unattended (~25 min): scripts/win-vm.sh screen shows where it is"
    wait_ssh 90
    timing "windows setup to ssh" $((SECONDS - t))
  else
    start "$BASE" "$BASE_VARS"
    wait_ssh 10
  fi
  trap 'stop; rm -rf "$LOCK"' EXIT
  vssh "if not exist C:\\firstlogon.done exit 1" </dev/null || { echo "error: firstlogon.ps1 did not finish (C:\\firstlogon.log in the VM)" >&2; exit 1; }
  t=$SECONDS
  log "installing the toolchain (Build Tools, .NET 10, Git, Rust), ~30 min"
  vps "$HERE/provision.ps1"
  timing "toolchain" $((SECONDS - t))
  t=$SECONDS
  log "trimming the disk"
  vssh 'powershell -NoProfile -Command "Remove-Item -Recurse -Force $env:TEMP\* -ErrorAction SilentlyContinue; Optimize-Volume -DriveLetter C -ReTrim"' </dev/null || true
  stop
  trap 'rm -rf "$LOCK"' EXIT
  log "compacting the base disk"
  qemu-img convert -O qcow2 "$BASE" "$BASE.compact" && mv "$BASE.compact" "$BASE"
  timing "trim and compact" $((SECONDS - t))
  touch "$PROVISIONED"
  timing "provision total" $((SECONDS - t0))
  du -h "$BASE" | sed 's/^/[win-vm] base disk: /' >&2
}

# --- the VM ------------------------------------------------------------------------------------------

up() {
  [ -f "$PROVISIONED" ] || { log "no provisioned base yet"; provision; }
  if [ ! -f "$DISK" ]; then
    log "creating the overlay on the base"
    qemu-img create -q -f qcow2 -F qcow2 -b "$BASE" "$DISK"
    cp "$BASE_VARS" "$VARS"
  fi
  local t=$SECONDS
  if ! running; then start "$DISK" "$VARS"; fi
  wait_ssh 5
  [ $((SECONDS - t)) -lt 2 ] || timing "up" $((SECONDS - t))
}

down() {
  stop
  if [ "${1:-}" = --reset ]; then log "deleting the overlay"; rm -f "$DISK" "$VARS"; fi
}

status() {
  if running; then echo "VM: running (pid $(cat "$PIDFILE")), SSH on 127.0.0.1:$PORT$(ssh_ok && echo ', answering' || echo ', not answering')"; else echo "VM: stopped"; fi
  [ -f "$PROVISIONED" ] && echo "base: provisioned $(date -r "$PROVISIONED" '+%Y-%m-%d %H:%M')" || echo "base: not provisioned"
  local f; for f in "$ISO" "$BASE" "$DISK"; do [ -f "$f" ] && echo "$(du -h "$f" | cut -f1)  $f (on disk)"; done
  echo "host free: $(df -g "$HOME" | awk 'NR==2 {print $4}') GB"
  [ -f "$TIMINGS" ] && { echo "last timings:"; tail -8 "$TIMINGS"; }
  return 0
}

# --- sync, build, test, shots ------------------------------------------------------------------------

# This checkout's files (tracked, and untracked but not ignored) into C:\b\r, as a tar stream. Unchanged
# files keep their times, so cargo and MSBuild stay incremental. Files deleted on the host stay in the VM
# until 'down --reset'. The band SoundFonts (not in git) are copied once.
sync_repo() {
  local t=$SECONDS
  log "syncing the checkout into $REMOTE"
  vssh "if not exist $REMOTE mkdir $REMOTE" </dev/null
  (cd "$ROOT" && git ls-files -co --exclude-standard -z | while IFS= read -r -d '' f; do [ -f "$f" ] && printf '%s\0' "$f"; done \
    | COPYFILE_DISABLE=1 tar -c --null -T - -f -) | vssh "tar -xf - -C $REMOTE"
  local sf band
  for sf in brasscribe-band-16bit.sf2 brasscribe-band-mobile.sf2; do
    band="$(cd "$ROOT" && readlink -f data/sounds/band/$sf 2>/dev/null || true)"
    [ -f "$band" ] || continue
    if ! vssh "powershell -NoProfile -Command \"if ((Get-Item $REMOTE\\data\\sounds\\band\\$sf -ErrorAction SilentlyContinue).Length -ne $(stat -f %z "$band")) { exit 1 }\"" </dev/null; then
      log "copying $sf"
      vssh "if not exist $REMOTE\\data\\sounds\\band mkdir $REMOTE\\data\\sounds\\band" </dev/null
      scp -q "${SCP_OPTS[@]}" "$band" "brass@127.0.0.1:C:/b/r/data/sounds/band/$sf"
    fi
  done
  timing "sync" $((SECONDS - t))
}

new_run() { RUN="$1-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$OUT/$RUN"; }

# Copy C:\b\out\<run> back into build/win-vm/<run>.
fetch() {
  (vssh "tar -c -f - -C C:\\b\\out $RUN" </dev/null | tar -x -f - -C "$OUT") || log "nothing to fetch from C:\\b\\out\\$RUN"
}

build() {
  local x64=""; [ "${1:-}" = --x64 ] && x64=1
  sync_repo
  local t=$SECONDS rc=0
  vps "$HERE/build.ps1" -Run "$RUN" ${x64:+-X64} </dev/null 2>&1 | tee "$OUT/$RUN/build.log" || rc=$?
  timing "build${x64:+ x64}" $((SECONDS - t))
  return "$rc"
}

test_all() {
  local t=$SECONDS rc=0
  vps "$HERE/test.ps1" -Run "$RUN" </dev/null 2>&1 | tee "$OUT/$RUN/test.log" || rc=$?
  timing "test" $((SECONDS - t))
  fetch
  return "$rc"
}

# Runs shots.ps1 in the logged-on session (a scheduled task as brass, interactive), where the app's
# windows are drawn, and waits for it.
interactive() {
  local args="$*" t=$SECONDS
  vssh "if not exist C:\\b\\out\\$RUN mkdir C:\\b\\out\\$RUN" </dev/null
  scp -q "${SCP_OPTS[@]}" "$HERE"/*.ps1 "brass@127.0.0.1:C:/b/"
  vssh "schtasks /create /f /tn brasscribe-shots /sc once /st 23:59 /ru brass /rp brass /it /rl highest /tr \"powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\\b\\shots.ps1 -Run $RUN $args\" >nul && schtasks /run /tn brasscribe-shots >nul" </dev/null
  until vssh "if not exist C:\\b\\out\\$RUN\\shots.done exit 1" </dev/null >/dev/null 2>&1; do
    [ $((SECONDS - t)) -lt 1800 ] || { log "the screenshots did not finish in 30 min"; break; }
    sleep 5
  done
  vssh "type C:\\b\\out\\$RUN\\shots.log" </dev/null || true
  timing "shots" $((SECONDS - t))
  fetch
}

release() {
  local t=$SECONDS rc=0
  vps "$HERE/build.ps1" -Run "$RUN" -X64 -Release </dev/null 2>&1 | tee "$OUT/$RUN/release.log" || rc=$?
  timing "release" $((SECONDS - t))
  fetch
  return "$rc"
}

# One VM user at a time across all worktrees and agents.
LOCK="$HOME/.brasscribe-vm/windows.lock"
take_lock() {
  local waited=0
  mkdir -p "$(dirname "$LOCK")"
  until mkdir "$LOCK" 2>/dev/null; do
    local pid; pid="$(cat "$LOCK/pid" 2>/dev/null || true)"
    if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then rm -rf "$LOCK"; continue; fi
    [ "$waited" -eq 0 ] && log "VM busy (pid ${pid:-?}: $(cat "$LOCK/what" 2>/dev/null || echo '?')); waiting"
    waited=$((waited + 5)); sleep 5
  done
  echo $$ >"$LOCK/pid"; echo "$*" >"$LOCK/what"
  trap 'rm -rf "$LOCK"' EXIT
}

mkdir -p "$DIR"
cmd="${1:-}"; shift || true
case "$cmd" in
  iso|provision|up|down|build|test|shots|checklist|release) take_lock "$cmd from $ROOT" ;;
esac
SECONDS=0
case "$cmd" in
  iso) iso ;;
  provision) provision ;;
  up) up ;;
  down) down "${1:-}" ;;
  status) status ;;
  screen) screen "${1:-}" ;;
  ssh) up >/dev/null; if [ $# -gt 0 ]; then vssh "$@"; else ssh -t "${SSH_OPTS[@]}" brass@127.0.0.1 powershell -NoLogo; fi ;;
  build) up; new_run build; rc=0; build "${1:-}" || rc=$?; fetch; log "logs in ${OUT#$ROOT/}/$RUN"; exit "$rc" ;;
  test) up; new_run test; rc=0; build --x64 || rc=$?; test_all || rc=$?; interactive -Smoke
        [ ! -s "$OUT/$RUN/shots.done" ] || rc=1
        log "results in ${OUT#$ROOT/}/$RUN"; exit "$rc" ;;
  shots) up; new_run shots; build --x64; interactive -Scenes "${1:-default}"; log "screenshots in ${OUT#$ROOT/}/$RUN" ;;
  checklist) up; new_run checklist; build --x64; test_all || true; interactive -Checklist; log "checklist results in ${OUT#$ROOT/}/$RUN" ;;
  release) up; new_run release; sync_repo; release; log "release zips in ${OUT#$ROOT/}/$RUN" ;;
  *) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
[ "$SECONDS" -lt 5 ] || log "took $((SECONDS / 60)) min $((SECONDS % 60)) s"
