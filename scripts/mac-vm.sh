#!/usr/bin/env bash
# The macOS UI tests (they drive a real pointer and keyboard) run in a headless Tart VM, never on
# the desktop of the Mac you are working on. See docs/dev/macos-vm.md.
#
#   scripts/mac-vm.sh up                 start the VM headless and wait for SSH (provisions it the first time)
#   scripts/mac-vm.sh test-ui [ONLY]     sync the repo in, run the Brasscribe Play macOS UI tests, copy the
#                                        .xcresult and screenshots back to build/mac-vm/<time>/
#                                        ONLY: an -only-testing value, e.g. BrasscribePlayUITests_macOS/WindowSizeUITests
#   scripts/mac-vm.sh test-ui-bandroom   the same for Brasscribe Bandroom (its UI test scheme when there is one)
#   scripts/mac-vm.sh ssh [command]      a shell (or one command) in the VM
#   scripts/mac-vm.sh down [--reset]     stop the VM; --reset also reclones it from the provisioned base
#   scripts/mac-vm.sh provision          set up (or finish setting up) the base VM from the Cirrus Labs image
#   scripts/mac-vm.sh status             VMs, disk use, IP
#
# The VM runs with --no-graphics: it has no window on the host and never touches the host's mouse
# or keyboard. The UI tests drive the VM's own virtual display.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VM="${MAC_VM_NAME:-brasscribe-ui}"
BASE="${MAC_VM_BASE:-brasscribe-ui-base}"
IMAGE="${MAC_VM_IMAGE:-ghcr.io/cirruslabs/macos-tahoe-base:latest}"
CPUS="${MAC_VM_CPUS:-6}"
MEMORY_MB="${MAC_VM_MEMORY_MB:-10240}"
DISPLAY_SIZE="${MAC_VM_DISPLAY:-1440x900}"
DISK_GB="${MAC_VM_DISK_GB:-72}"
HOST_XCODE="${MAC_VM_XCODE:-/Applications/Xcode.app}"
KEY="$HOME/.tart/brasscribe-ui_ed25519"
PROVISIONED="$HOME/.tart/$BASE.provisioned"   # written when provisioning finished
MIN_FREE_GB="${MAC_VM_MIN_FREE_GB:-15}"
OUT="$ROOT/build/mac-vm"
REMOTE="brasscribe"   # the checkout in the VM: ~admin/brasscribe
export DEVELOPER_DIR="${DEVELOPER_DIR:-$HOST_XCODE/Contents/Developer}"

TART="$(command -v tart || true)"
[ -n "$TART" ] || { [ -x "$HOME/.local/bin/tart" ] && TART="$HOME/.local/bin/tart"; }
[ -n "$TART" ] || { echo "error: tart not found (see docs/dev/macos-vm.md, Install)" >&2; exit 1; }

log() { printf '[mac-vm] %s\n' "$*" >&2; }
SSH_OPTS=(-i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR
          -o ConnectTimeout=5 -o ServerAliveInterval=30 -o IdentitiesOnly=yes)

exists() { "$TART" list --source local --quiet 2>/dev/null | grep -qx "$1"; }
running() { "$TART" list --format json 2>/dev/null | python3 -c 'import json,sys; n=sys.argv[1]; print(any(v.get("Name")==n and v.get("State")=="running" for v in json.load(sys.stdin)))' "$1" | grep -q True; }
ip_of() { "$TART" ip --wait 120 "$1"; }

# Start <vm> headless in the background; extra arguments go to `tart run` (e.g. --dir=…).
start() {
  local vm="$1"; shift
  if running "$vm"; then return; fi
  mkdir -p "$OUT"
  log "starting $vm headless (no window, no host input)"
  nohup "$TART" run --no-graphics --no-audio --no-clipboard "$@" "$vm" >"$OUT/$vm.log" 2>&1 &
  disown || true
}

wait_ssh() {  # <vm> [password-ok]
  local vm="$1" ip i
  ip="$(ip_of "$vm")"
  for i in $(seq 1 90); do
    if [ -f "$KEY" ] && ssh -n "${SSH_OPTS[@]}" -o BatchMode=yes "admin@$ip" true 2>/dev/null; then echo "$ip"; return; fi
    if [ "${2:-}" = password-ok ] && nc -z -G 2 "$ip" 22 2>/dev/null; then echo "$ip"; return; fi
    sleep 2
  done
  echo "error: no SSH on $vm ($ip) after 3 minutes; see $OUT/$vm.log" >&2; exit 1
}

# The Cirrus Labs images log in as admin/admin; swap the password for a key once, in the base VM.
push_key() {
  local ip="$1"
  [ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N '' -C brasscribe-ui -f "$KEY"
  PUB="$(cat "$KEY.pub")" IP="$ip" expect -f - <<'EOF' >/dev/null
set timeout 60
spawn ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PubkeyAuthentication=no -o LogLevel=ERROR admin@$env(IP) "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$env(PUB)' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
expect {
  -re "assword:" { send "admin\r"; exp_continue }
  eof
}
EOF
}

vssh() { local ip="$1"; shift; ssh "${SSH_OPTS[@]}" "admin@$ip" "$@"; }

# Refuse to start when the host's disk is nearly full: the VM's disk grows into it.
check_disk() {
  local free; free="$(df -g "$HOME" | awk 'NR==2 {print $4}')"
  if [ "$free" -lt "$MIN_FREE_GB" ]; then
    echo "error: only $free GB free on the host (MAC_VM_MIN_FREE_GB=$MIN_FREE_GB); not starting the VM" >&2; exit 1
  fi
}

# The provisioned base: the image, the host's Xcode, and what XCUITest needs. Each step is skipped
# when already done, so a failed run is resumed with `provision` rather than started over.
provision() {
  [ -d "$HOST_XCODE" ] || { echo "error: $HOST_XCODE not found (MAC_VM_XCODE=…)" >&2; exit 1; }
  check_disk
  if exists "$VM" && running "$VM"; then "$TART" stop "$VM"; fi
  if ! exists "$BASE"; then
    log "cloning $IMAGE into $BASE (pulls the image the first time: ~27 GB download, ~33 GB on disk)"
    "$TART" clone "$IMAGE" "$BASE"
    "$TART" set "$BASE" --cpu "$CPUS" --memory "$MEMORY_MB" --display "$DISPLAY_SIZE" --disk-size "$DISK_GB"
  fi
  rm -f "$PROVISIONED"
  start "$BASE"
  trap '"$TART" stop "$BASE" >/dev/null 2>&1 || true' EXIT
  local ip; ip="$(wait_ssh "$BASE" password-ok)"
  if ! ssh -n "${SSH_OPTS[@]}" -o BatchMode=yes "admin@$ip" true 2>/dev/null; then sleep 5; push_key "$ip"; fi
  ip="$(wait_ssh "$BASE")"
  log "provisioning $BASE at $ip"
  # grow the APFS container into the enlarged disk
  vssh "$ip" 'yes | sudo diskutil repairDisk disk0 >/dev/null 2>&1; sudo diskutil apfs resizeContainer disk0s2 0 >/dev/null 2>&1; true'
  local want have
  want="$(xcodebuild -version | tr '\n' ' ')"
  have="$(vssh "$ip" '/Applications/Xcode.app/Contents/Developer/usr/bin/xcodebuild -version 2>/dev/null | tr "\n" " "' || true)"
  if [ "$want" != "$have" ]; then
    # streamed over SSH (a shared folder is slow and breaks the frameworks' symlinks), and kept
    # compressed in the guest as it is on the host
    log "copying $HOST_XCODE ($want) into the VM"
    vssh "$ip" 'sudo rm -rf /Applications/Xcode.app'
    ditto -c "$HOST_XCODE" - | vssh "$ip" 'sudo ditto -x --hfsCompression - /Applications/Xcode.app'
  fi
  # xcodegen: the host's, so the project is generated by the same version (and no network is needed)
  if ! vssh "$ip" 'test -x /opt/homebrew/bin/xcodegen'; then
    local keg; keg="$(cd "$(dirname "$(readlink -f "$(command -v xcodegen)")")/.." && pwd)"
    log "copying xcodegen ($(basename "$keg")) into the VM"
    ditto -c "$keg" - | vssh "$ip" "mkdir -p /opt/homebrew/Cellar/xcodegen && ditto -x - /opt/homebrew/Cellar/xcodegen/$(basename "$keg") \
      && ln -sf ../Cellar/xcodegen/$(basename "$keg")/bin/xcodegen /opt/homebrew/bin/xcodegen"
  fi
  vssh "$ip" 'bash -s' <<'EOF'
set -euo pipefail
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
sudo DevToolsSecurity -enable >/dev/null
# XCUITest may take over input without an authentication prompt
sudo automationmodetool enable-automationmode-without-authentication
# the display never sleeps and no screensaver covers the app
sudo pmset -a sleep 0 displaysleep 0 disksleep 0
defaults -currentHost write com.apple.screensaver idleTime -int 0
# no "reopen windows" and no state restoration between test launches
defaults write -g NSQuitAlwaysKeepsWindows -bool false
xcodebuild -version | head -1
sw_vers -productVersion
df -h / | tail -1
EOF
  log "stopping $BASE; clones of it start ready"
  "$TART" stop "$BASE"
  trap - EXIT
  touch "$PROVISIONED"
}

up() {
  { [ -f "$PROVISIONED" ] && exists "$BASE"; } || provision >&2
  check_disk
  if ! exists "$VM"; then
    if running "$BASE"; then "$TART" stop "$BASE" >&2; fi
    log "cloning $BASE into $VM (copy-on-write, no extra disk until it diverges)"
    "$TART" clone "$BASE" "$VM" >&2
  fi
  start "$VM"
  local ip; ip="$(wait_ssh "$VM")"
  # every boot comes back in the image's saved 1024 x 768 mode, whatever tart's --display is;
  # switch to the configured size (a no-op when it already is)
  vssh "$ip" "cat > /tmp/mac-vm-display.swift && swift /tmp/mac-vm-display.swift ${DISPLAY_SIZE%pt}" \
    <"$ROOT/scripts/mac-vm-display.swift" >&2
  log "$VM is up at $ip"
  echo "$ip"
}

down() {
  running "$VM" && { log "stopping $VM"; "$TART" stop "$VM"; }
  if [ "${1:-}" = --reset ] && exists "$VM"; then
    log "deleting $VM; the next up reclones it from $BASE"
    "$TART" delete "$VM"
  fi
}

# The main checkout, when this is a git worktree (prerequisites built there are reused).
main_checkout() {
  local common; common="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  [ -n "$common" ] && dirname "$common"
}

# Pick <relative path> from this checkout, else from the main checkout; empty when neither has it.
prereq() {
  local rel="$1" main
  if [ -e "$ROOT/$rel" ]; then echo "$ROOT/$rel"; return; fi
  main="$(main_checkout)"
  if [ -n "$main" ] && [ -e "$main/$rel" ]; then echo "$main/$rel"; fi
}

# Everything the Apple builds need that is not in git, built or found on the host.
host_prereqs() {
  local xcf="$ROOT/core/swift/BrasscribeCore/BrasscribeFFI.xcframework"
  # the core is always this checkout's: a framework from another core version fails like an app bug
  if [ ! -d "$xcf" ] || [ -n "$(find "$ROOT/core" -path "$ROOT/core/target" -prune -o \( -name '*.rs' -o -name '*.udl' -o -name 'Cargo.toml' \) -newer "$xcf" -print -quit)" ]; then
    log "building the Rust core xcframework on the host (apps/apple/scripts/build-core.sh)"
    "$ROOT/apps/apple/scripts/build-core.sh"
  fi
  VEROVIO="$(prereq apps/apple/Frameworks/Verovio.xcframework)"
  if [ -z "$VEROVIO" ]; then
    log "building Verovio on the host (make verovio, ~2 min)"
    make -C "$ROOT/apps/apple" verovio
    VEROVIO="$ROOT/apps/apple/Frameworks/Verovio.xcframework"
  fi
  VEROVIO="$(dirname "$VEROVIO")"
  BAND="$(prereq data/sounds/band)"
  [ -n "$BAND" ] || log "warning: no data/sounds/band (pixi run fetch-sounds); the app plays the basic tier"
  SOUNDFONT="$(prereq data/soundfonts/MuseScore_General.sf2)"
}

sync_repo() {
  local ip="$1"
  host_prereqs
  log "syncing the repo into the VM (~/$REMOTE)"
  rsync -a --delete \
    --exclude .git --exclude .claude/ --exclude node_modules/ --exclude '/build/' --exclude 'build/' \
    --exclude DerivedData/ --exclude .build/ --exclude .gradle/ --exclude .pixi/ --exclude .venv/ \
    --exclude __pycache__/ --exclude '/data/' --exclude '/models/' --exclude 'core/target/' --exclude 'core/dist/' \
    --exclude 'bin/' --exclude 'obj/' --exclude '*.xcodeproj/' --exclude 'apps/apple/Sounds/' \
    --exclude 'apps/apple/Frameworks/Verovio.xcframework/' --exclude 'apps/apple/Frameworks/VerovioResources/' \
    --exclude 'site/_site/' --exclude '.DS_Store' \
    -e "ssh ${SSH_OPTS[*]}" "$ROOT/" "admin@$ip:$REMOTE/"
  rsync -a --delete -e "ssh ${SSH_OPTS[*]}" "$VEROVIO/" "admin@$ip:$REMOTE/apps/apple/Frameworks/"
  vssh "$ip" "mkdir -p $REMOTE/data/sounds $REMOTE/data/soundfonts"
  [ -z "$BAND" ] || rsync -a --delete -e "ssh ${SSH_OPTS[*]}" "$BAND/" "admin@$ip:$REMOTE/data/sounds/band/"
  [ -z "$SOUNDFONT" ] || rsync -a -e "ssh ${SSH_OPTS[*]}" "$SOUNDFONT" "admin@$ip:$REMOTE/data/soundfonts/"
}

# Copy <remote .xcresult> back into <local dir> and export its screenshots and a summary.
fetch_results() {
  local ip="$1" remote="$2" dest="$3"
  mkdir -p "$dest"
  if ! vssh "$ip" "test -d $remote"; then log "no result bundle at $remote"; return; fi
  rsync -a -e "ssh ${SSH_OPTS[*]}" "admin@$ip:$remote" "$dest/"
  local bundle="$dest/$(basename "$remote")"
  xcrun xcresulttool export attachments --path "$bundle" --output-path "$dest/attachments" >/dev/null 2>&1 \
    || log "could not export attachments from $bundle"
  # a failing test gets a screen recording; its last frame is the screen at the failure
  if command -v ffmpeg >/dev/null; then
    local m d
    for m in "$dest"/attachments/*.mp4; do
      [ -f "$m" ] || continue
      d="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$m" 2>/dev/null || echo 0)"
      ffmpeg -y -loglevel error -ss "$(python3 -c "print(max(0, float('${d:-0}') - 0.3))")" -i "$m" -frames:v 1 "${m%.mp4}-last.png" || true
    done
  fi
  xcrun xcresulttool get test-results summary --path "$bundle" --compact >"$dest/summary.json" 2>/dev/null || true
  xcrun xcresulttool get test-results tests --path "$bundle" --compact >"$dest/tests.json" 2>/dev/null || true
  python3 - "$dest" <<'EOF' || true
import json, sys, pathlib
d = pathlib.Path(sys.argv[1])
try:
    s = json.loads((d / "summary.json").read_text())
except Exception:
    sys.exit()
print(f"[mac-vm] {s.get('result')}: {s.get('passedTests', 0)} passed, {s.get('failedTests', 0)} failed, {s.get('skippedTests', 0)} skipped")
for f in s.get("testFailures", []):
    print(f"[mac-vm]   FAIL {f.get('testIdentifierString')}: {f.get('failureText', '').strip()[:300]}")
EOF
  log "results in ${dest#$ROOT/}"
}

test_ui() {
  local only="${1:-}" ip stamp status=0
  ip="$(up)"
  sync_repo "$ip"
  stamp="$(date +%Y%m%d-%H%M%S)"
  local result="build/mac-vm/play-$stamp.xcresult"
  log "running make test-mac-ui in the VM${only:+ (only $only)}"
  set +e
  vssh "$ip" "export PATH=/opt/homebrew/bin:\$PATH; cd $REMOTE/apps/apple && rm -rf $result && make test-mac-ui \
      TEST_ARGS='-resultBundlePath $result ${only:+-only-testing:$only}'" 2>&1 | tee "$OUT/play-$stamp.log" \
    | grep --line-buffered -E '^(Test Suite|Test Case|.*error:|\*\* TEST)'
  status="${PIPESTATUS[0]}"
  set -e
  fetch_results "$ip" "$REMOTE/apps/apple/$result" "$OUT/play-$stamp"
  return "$status"
}

test_ui_bandroom() {
  local ip stamp result status=0
  ip="$(up)"
  sync_repo "$ip"
  stamp="$(date +%Y%m%d-%H%M%S)"
  result="build/mac-vm/bandroom-$stamp.xcresult"
  log "Brasscribe Bandroom in the VM"
  vssh "$ip" "bash -s" <<EOF 2>&1 | tee "$OUT/bandroom-$stamp.log" || status=$?
set -euo pipefail
export PATH=/opt/homebrew/bin:\$PATH
cd $REMOTE/apps/bandroom/macos
make project
scheme=\$(xcodebuild -project BrasscribeBandroom.xcodeproj -list -json | python3 -c 'import json,sys; s=[n for n in json.load(sys.stdin)["project"]["schemes"] if "UITest" in n]; print(s[0] if s else "")')
if [ -n "\$scheme" ]; then
  xcodebuild -project BrasscribeBandroom.xcodeproj -derivedDataPath build/DerivedData -scheme "\$scheme" \
    -destination platform=macOS -resultBundlePath $result test
else
  echo "Bandroom has no UI test scheme yet: building the app and running its unit tests"
  make build
  make test
fi
EOF
  fetch_results "$ip" "$REMOTE/apps/bandroom/macos/$result" "$OUT/bandroom-$stamp"
  return "$status"
}

cmd="${1:-}"; shift || true
case "$cmd" in
  up) up >/dev/null ;;
  down) down "${1:-}" ;;
  provision) provision >&2 ;;
  test-ui) SECONDS=0; rc=0; test_ui "${1:-}" || rc=$?; log "took $((SECONDS / 60)) min $((SECONDS % 60)) s"; exit "$rc" ;;
  test-ui-bandroom) SECONDS=0; rc=0; test_ui_bandroom || rc=$?; log "took $((SECONDS / 60)) min $((SECONDS % 60)) s"; exit "$rc" ;;
  ssh) ip="$(up)"; if [ $# -gt 0 ]; then vssh "$ip" "$@"; else vssh "$ip"; fi ;;
  status)
    "$TART" list
    du -sh "$HOME/.tart/vms/"* "$HOME/.tart/cache" 2>/dev/null || true
    running "$VM" && echo "$VM: $("$TART" ip "$VM")" || echo "$VM: stopped" ;;
  *) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
