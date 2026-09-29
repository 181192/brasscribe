#!/usr/bin/env bash
# The macOS UI tests (they drive a real pointer and keyboard) run in a headless Tart VM, never on
# the desktop of the Mac you are working on. See docs/dev/macos-vm.md.
#
#   scripts/mac-vm.sh up                 start (or resume) the VM headless and wait for SSH (provisions it the first time)
#   scripts/mac-vm.sh test-ui [ONLY]     build for testing on the host, copy the products into the VMs, run the
#                                        Brasscribe Play macOS UI tests there (test-without-building, spread over
#                                        MAC_VM_PARALLEL VMs), copy results and screenshots back to build/mac-vm/<run>/
#                                        ONLY: comma-separated classes or Class/test, e.g. WindowSizeUITests,PlayUITests/testKeyboardShortcuts
#                                        MAC_VM_SHOTS=1 turns on the screenshot tests (SiteScreenshotUITests)
#   scripts/mac-vm.sh test-ui-bandroom   Brasscribe Bandroom in the VM (its UI test scheme when there is one)
#   scripts/mac-vm.sh ssh [command]      a shell (or one command) in the VM
#   scripts/mac-vm.sh down [--stop|--reset]  suspend the VMs (resume in seconds); --stop shuts them down,
#                                        --reset also deletes the clones (the next up reclones them)
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
DOCK_TILE="${MAC_VM_DOCK_TILE:-36}"   # the Dock's icon size in the VM: small enough that the Dock never fills the width
HOST_XCODE="${MAC_VM_XCODE:-/Applications/Xcode.app}"
KEY="$HOME/.tart/brasscribe-ui_ed25519"
PROVISIONED="$HOME/.tart/$BASE.provisioned"   # written when provisioning finished
MIN_FREE_GB="${MAC_VM_MIN_FREE_GB:-15}"
PARALLEL="${MAC_VM_PARALLEL:-2}"   # VMs a test-ui run spreads the tests over (macOS allows 2 macOS guests at once)
SHARD_MEMORY_MB="${MAC_VM_SHARD_MEMORY_MB:-6144}" # memory of the extra VMs
OUT="$ROOT/build/mac-vm"
HOST_DERIVED="$ROOT/apps/apple/build/DerivedData-vm"   # the host build the VMs run
REMOTE="brasscribe"   # the checkout in the VM: ~admin/brasscribe
export DEVELOPER_DIR="${DEVELOPER_DIR:-$HOST_XCODE/Contents/Developer}"

TART="$(command -v tart || true)"
[ -n "$TART" ] || { [ -x "$HOME/.local/bin/tart" ] && TART="$HOME/.local/bin/tart"; }
[ -n "$TART" ] || { echo "error: tart not found (see docs/dev/macos-vm.md, Install)" >&2; exit 1; }

log() { printf '[mac-vm] %s\n' "$*" >&2; }
SSH_OPTS=(-i "$KEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR
          -o ConnectTimeout=5 -o ServerAliveInterval=30 -o IdentitiesOnly=yes)

exists() { "$TART" list --source local --quiet 2>/dev/null | grep -qx "$1"; }
state() { "$TART" list --format json 2>/dev/null | python3 -c 'import json,sys; n=sys.argv[1]; print(next((v.get("State", "") for v in json.load(sys.stdin) if v.get("Name") == n), ""))' "$1"; }
running() { [ "$(state "$1")" = running ]; }
ip_of() { "$TART" ip --wait 120 "$1"; }

# Start <vm> headless in the background; extra arguments go to `tart run` (e.g. --dir=…).
start() {
  local vm="$1"; shift
  if running "$vm"; then return; fi
  mkdir -p "$OUT"
  log "starting $vm headless (no window, no host input)"
  nohup "$TART" run --no-graphics --no-audio --no-clipboard --suspendable "$@" "$vm" >"$OUT/$vm.log" 2>&1 &
  disown || true
  # a suspended state saved by another process can fail to restore ("permission denied"); boot cold instead
  sleep 3
  if grep -q "failed to restore" "$OUT/$vm.log" 2>/dev/null; then
    log "$vm: saved state won't restore; discarding it and booting cold"
    rm -f "$HOME/.tart/vms/$vm/state.vzvmsave"
    nohup "$TART" run --no-graphics --no-audio --no-clipboard --suspendable "$@" "$vm" >"$OUT/$vm.log" 2>&1 &
    disown || true
  fi
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

# Start (or resume) <vm>, cloning it from the base first; prints its IP once SSH answers.
up_vm() {
  local vm="$1"
  { [ -f "$PROVISIONED" ] && exists "$BASE"; } || provision >&2
  check_disk
  if ! exists "$vm"; then
    if running "$BASE"; then "$TART" stop "$BASE" >&2; fi
    log "cloning $BASE into $vm (copy-on-write, no extra disk until it diverges)"
    "$TART" clone "$BASE" "$vm" >&2
    [ "$vm" = "$VM" ] || "$TART" set "$vm" --memory "$SHARD_MEMORY_MB" >&2
  fi
  start "$vm"
  local ip; ip="$(wait_ssh "$vm")"
  # every boot comes back in the image's saved 1024 x 768 mode, whatever tart's --display is;
  # switch to the configured size (a no-op when it already is)
  vssh "$ip" "cat > /tmp/mac-vm-display.swift && swift /tmp/mac-vm-display.swift ${DISPLAY_SIZE%pt}" \
    <"$ROOT/scripts/mac-vm-display.swift" >/dev/null
  # A Dock as wide as the screen shrinks its icons, and so its height, each time an app's icon comes
  # or goes: the visible frame changed by a few points while a test ran, and the test runner (which
  # reads it once) and the app disagreed about where the Dock begins. Small tiles keep the Dock
  # narrower than the screen, so its height never changes.
  vssh "$ip" '[ "$(defaults read com.apple.dock tilesize 2>/dev/null)" = '"$DOCK_TILE"' ] || {
    defaults write com.apple.dock tilesize -int '"$DOCK_TILE"'; defaults write com.apple.dock magnification -bool false; killall Dock; sleep 2; }' >&2
  log "$vm is up at $ip"
  echo "$ip"
}
up() { up_vm "$VM"; }

# The VMs a parallel run uses: brasscribe-ui, brasscribe-ui-2, …
vm_names() { local i; echo "$VM"; for i in $(seq 2 "$PARALLEL"); do echo "$VM-$i"; done; }
all_vms() { "$TART" list --source local --quiet 2>/dev/null | grep -E "^$VM(-[0-9]+)?\$" || true; }

# Suspend the VMs (the next up resumes them in seconds); --stop shuts them down, --reset also
# deletes the clones so the next up reclones them from the base.
down() {
  local vm
  for vm in $(all_vms); do
    running "$vm" || continue
    if [ -z "${1:-}" ] && "$TART" suspend "$vm" >/dev/null 2>&1; then
      # the suspend finishes after the command returns (the VM's memory is saved to disk)
      local i; for i in $(seq 1 60); do [ "$(state "$vm")" = suspended ] && break; sleep 1; done
      log "suspended $vm"; continue
    fi
    log "stopping $vm"; "$TART" stop "$vm" >/dev/null
  done
  if [ "${1:-}" = --reset ]; then
    for vm in $(all_vms); do log "deleting $vm"; "$TART" delete "$vm"; done
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
  # exported in the VM: a failing test's screen recording stays there (hundreds of MB), and only
  # its last frame, the screen at the failure, comes back as <id>-last.png
  local out; out="$(dirname "$remote")/export"
  vssh "$ip" "rm -rf $out && mkdir -p $out && cat > /tmp/mac-vm-lastframe.swift \
    && xcrun xcresulttool export attachments --path $remote --output-path $out/attachments >/dev/null \
    && xcrun xcresulttool get test-results summary --path $remote --compact > $out/summary.json \
    && xcrun xcresulttool get test-results tests --path $remote --compact > $out/tests.json \
    && { ls $out/attachments/*.mp4 >/dev/null 2>&1 || exit 0; swift /tmp/mac-vm-lastframe.swift $out/attachments/*.mp4; }" \
    <"$ROOT/scripts/mac-vm-lastframe.swift" || log "could not export the results in the VM"
  rsync -a --exclude '*.mp4' -e "ssh ${SSH_OPTS[*]}" "admin@$ip:$out/" "$dest/"
  # the whole bundle (with the recordings) only on request
  [ -z "${MAC_VM_FETCH_BUNDLE:-}" ] || rsync -a -e "ssh ${SSH_OPTS[*]}" "admin@$ip:$remote" "$dest/"
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

# Build the app and its UI tests on the host (build-for-testing: no input, nothing on screen), so
# nothing compiles in the VM. The VM has the same Xcode (provision copies the host's).
build_host() {
  host_prereqs
  # the band sounds are bundled at build time from data/sounds/band; a worktree borrows the main checkout's
  if [ ! -e "$ROOT/data/sounds/band" ] && [ -n "$BAND" ]; then mkdir -p "$ROOT/data/sounds"; ln -s "$BAND" "$ROOT/data/sounds/band"; fi
  log "building for testing on the host"
  local blog="$OUT/host-build.log"; mkdir -p "$OUT"
  # a failed build must stop the run: the VMs would otherwise test the previous build's products
  if ! (cd "$ROOT/apps/apple" && xcodegen generate >/dev/null \
    && xcodebuild -project BrasscribePlay.xcodeproj -derivedDataPath "$HOST_DERIVED" -scheme BrasscribePlay-macOS-UITests \
         -destination platform=macOS build-for-testing -quiet >"$blog" 2>&1); then
    grep -E "error:|FAILED" "$blog" >&2 || tail -20 "$blog" >&2
    echo "error: build-for-testing failed (log: ${blog#$ROOT/})" >&2; exit 1
  fi
  XCTESTRUN="$(ls -t "$HOST_DERIVED"/Build/Products/*.xctestrun 2>/dev/null | head -1)"
  [ -n "$XCTESTRUN" ] || { echo "error: build-for-testing produced no .xctestrun" >&2; exit 1; }
}

# Only what the tests need: the products (incrementally), the fixture score and the band's mapping.
sync_products() {
  local ip="$1"
  vssh "$ip" "mkdir -p $REMOTE/apps products"
  rsync -a --delete -e "ssh ${SSH_OPTS[*]}" "$HOST_DERIVED/Build/Products/" "admin@$ip:products/"
  rsync -a --delete -e "ssh ${SSH_OPTS[*]}" "$ROOT/apps/fixtures" "admin@$ip:$REMOTE/apps/"
  rsync -a --delete -e "ssh ${SSH_OPTS[*]}" "$ROOT/sounds" "admin@$ip:$REMOTE/"
}

# Run <ids> (Class/test …) on <vm> and fetch its results into $OUT/<run>/<vm>.
run_shard() {
  local vm="$1" ip="$2" run="$3" ids="$4" args="" t rc=0
  for t in $ids; do args="$args -only-testing:BrasscribePlayUITests_macOS/$t"; done
  local result="results/$run.xcresult"
  vssh "$ip" "pkill -x xcodebuild; pkill -x BrasscribePlay; rm -rf results; mkdir -p results; \
    TEST_RUNNER_BRASSCRIBE_FIXTURES=\$HOME/$REMOTE/apps/fixtures/old-hundredth TEST_RUNNER_BRASSCRIBE_SHOTS=${MAC_VM_SHOTS:-} \
    xcodebuild test-without-building -xctestrun products/$(basename "$XCTESTRUN") -destination platform=macOS \
      -resultBundlePath $result $args" >"$OUT/$run/$vm.log" 2>&1 || rc=$?
  fetch_results "$ip" "$result" "$OUT/$run/$vm" >"$OUT/$run/$vm.summary" 2>&1
  return "$rc"
}

test_ui() {
  local only="${1:-}" run t status=0 vm i k line
  run="play-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$OUT/$run"
  t=$SECONDS
  build_host; log "time: host build $((SECONDS - t)) s"; t=$SECONDS
  # every test (or ONLY's), spread over the VMs by the durations of earlier runs
  local shards=() vms=() ips=() pids=()
  while IFS= read -r line; do shards+=("$line"); done \
    < <(python3 "$ROOT/scripts/mac-vm-plan.py" "$PARALLEL" "$only" "$OUT/durations.json" "$ROOT/apps/apple/AppUITests")
  i=0
  for vm in $(vm_names); do
    if [ -n "${shards[$i]:-}" ]; then
      vms+=("$vm"); ips+=("$(up_vm "$vm")")
      [ -n "${ips[${#ips[@]} - 1]}" ] || { echo "error: $vm did not come up" >&2; exit 1; }
    fi
    i=$((i + 1))
  done
  log "time: VMs up $((SECONDS - t)) s"; t=$SECONDS
  for i in "${!ips[@]}"; do sync_products "${ips[$i]}" & done
  wait
  log "time: sync $((SECONDS - t)) s"; t=$SECONDS
  k=0
  for i in "${!shards[@]}"; do
    [ -n "${shards[$i]}" ] || continue
    log "${vms[$k]}: $(echo "${shards[$i]}" | wc -w | tr -d ' ') tests"
    run_shard "${vms[$k]}" "${ips[$k]}" "$run" "${shards[$i]}" &
    pids+=($!)
    k=$((k + 1))
  done
  for i in "${pids[@]}"; do wait "$i" || status=1; done
  log "time: tests and results $((SECONDS - t)) s"
  cat "$OUT/$run"/*.summary
  record_durations "$OUT/$run"
  log "results in ${OUT#$ROOT/}/$run (xcodebuild logs: <vm>.log)"
  return "$status"
}

# Test durations of a run's result bundles, for the next run's plan (build/mac-vm/durations.json).
record_durations() {
  python3 - "$1" "$OUT/durations.json" <<'EOF' || true
import json, pathlib, sys
p = pathlib.Path(sys.argv[2])
known = json.loads(p.read_text()) if p.exists() else {}
def walk(n):
    if n.get("nodeType") == "Test Case" and "durationInSeconds" in n:
        known[n["nodeIdentifier"].removesuffix("()")] = round(n["durationInSeconds"], 1)
    for c in n.get("children", []):
        walk(c)
for f in pathlib.Path(sys.argv[1]).glob("*/tests.json"):
    for n in json.loads(f.read_text()).get("testNodes", []):
        walk(n)
p.write_text(json.dumps(known, indent=1, sort_keys=True))
EOF
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

# One VM user at a time across all worktrees and agents: runs queue on a host-wide lock instead of
# fighting over the two guests. A full test-ui run (no ONLY) needs MAC_VM_FULL=1; everything else
# runs named classes or tests only (docs/dev/macos-vm.md, "When to use the VM").
LOCK="$HOME/.tart/brasscribe-ui.lock"
take_lock() {
  local waited=0
  until mkdir "$LOCK" 2>/dev/null; do
    local pid; pid="$(cat "$LOCK/pid" 2>/dev/null || true)"
    if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then rm -rf "$LOCK"; continue; fi
    [ "$waited" -eq 0 ] && log "VM busy (pid ${pid:-?}: $(cat "$LOCK/what" 2>/dev/null || echo '?')); waiting"
    waited=$((waited + 5)); sleep 5
  done
  echo $$ >"$LOCK/pid"; echo "$*" >"$LOCK/what"
  trap 'rm -rf "$LOCK"' EXIT
}

cmd="${1:-}"; shift || true
case "$cmd" in
  test-ui)
    if [ -z "${1:-}" ] && [ "${MAC_VM_FULL:-}" != 1 ]; then
      echo "error: the full suite runs once before a release (MAC_VM_FULL=1). Name the classes or tests: test-ui PlayUITests/testX,WindowSizeUITests" >&2; exit 2
    fi
    take_lock "test-ui ${1:-all} from $ROOT" ;;
  test-ui-bandroom|up|down|provision) take_lock "$cmd from $ROOT" ;;
esac
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
    for vm in $(all_vms); do echo "$vm: $(state "$vm")"; done ;;
  *) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
