#!/usr/bin/env bash
# A private Android emulator per agent or shell, so parallel test runs don't share one device.
#
#   serial=$(apps/android/scripts/emulator-pool.sh acquire)   # boots one (or returns yours), prints its serial
#   ANDROID_SERIAL=$serial ./gradlew connectedDebugAndroidTest
#   apps/android/scripts/emulator-pool.sh release [serial]    # stops it and frees the slot
#   apps/android/scripts/emulator-pool.sh list                # leases, owners, expiry
#   apps/android/scripts/emulator-pool.sh reap                # stop emulators whose lease ran out
#
# Options for acquire:
#   --owner NAME   who holds the lease (default: this checkout's directory name)
#   --ttl MIN      lease length in minutes (default 120); acquire again to renew it
#   --phone        hand out the attached phone ($BRASSCRIBE_PHONE_SERIAL) instead, if it is free
#
# Each emulator runs the same AVD ($BRASSCRIBE_AVD, default bc36) with -read-only, headless
# (-no-window -no-audio), on an even console port from 5556 up. emulator-5554 is never touched:
# that is the interactive one. At most $BRASSCRIBE_EMULATORS_MAX (default 4) run at once; each
# takes about 4 GB. Leases live in ~/.cache/brasscribe/emulators/<serial>/ (mkdir is the lock).
# A lease past its expiry, or whose emulator died, is reaped by the next acquire.
#
# The phone: after device tests, install the current debug build again (./gradlew installDebug)
# and never uninstall the app; uninstalling deletes the user's scores.
set -euo pipefail

SDK="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
ADB="$SDK/platform-tools/adb"
EMULATOR="$SDK/emulator/emulator"
AVD="${BRASSCRIBE_AVD:-bc36}"
MAX="${BRASSCRIBE_EMULATORS_MAX:-4}"
PHONE="${BRASSCRIBE_PHONE_SERIAL:-RFCY9141XEF}"
POOL="${BRASSCRIBE_CACHE:-$HOME/.cache/brasscribe}/emulators"
BOOT_TIMEOUT="${BRASSCRIBE_EMULATOR_BOOT_TIMEOUT:-300}"
mkdir -p "$POOL"

log() { printf 'emulator-pool: %s\n' "$*" >&2; }
die() { log "$*"; exit 1; }
now() { date +%s; }
default_owner() { basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"; }
field() { cat "$POOL/$1/$2" 2>/dev/null || true; }

alive() {  # the lease's emulator process still runs
  local pid; pid=$(field "$1" pid)
  [ -z "$pid" ] && return 0            # the phone has no process
  kill -0 "$pid" 2>/dev/null
}

stop() {  # stop the emulator behind a lease and drop the lease
  local s="$1" pid
  pid=$(field "$s" pid)
  if [ -n "$pid" ]; then
    "$ADB" -s "$s" emu kill >/dev/null 2>&1 || true
    for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    kill "$pid" 2>/dev/null || true
  fi
  rm -rf "${POOL:?}/$s"
}

reap() {
  local d s
  for d in "$POOL"/*/; do
    [ -d "$d" ] || continue
    s=$(basename "$d")
    if [ ! -f "$d/expires" ]; then
      # a lease being created; reap it only when its creator is gone
      kill -0 "$(field "$s" creator)" 2>/dev/null || rm -rf "$d"
    elif [ "$(field "$s" expires)" -lt "$(now)" ] || ! alive "$s"; then
      log "reaping $s (owner $(field "$s" owner))"; stop "$s"
    fi
  done
}

port_free() {
  local p="$1"
  ! "$ADB" devices 2>/dev/null | grep -q "^emulator-$p[[:space:]]" \
    && ! lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1 \
    && ! lsof -nP -iTCP:"$((p + 1))" -sTCP:LISTEN >/dev/null 2>&1
}

lease() {  # write the lease fields: lease <serial> <owner> <ttl-min> [pid]
  echo "$2" > "$POOL/$1/owner"
  [ -n "${4:-}" ] && echo "$4" > "$POOL/$1/pid"
  echo $(( $(now) + $3 * 60 )) > "$POOL/$1/expires"
}

acquire() {
  local owner="" ttl=120 phone=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --owner) owner="$2"; shift ;;
      --ttl) ttl="$2"; shift ;;
      --phone) phone=1 ;;
      *) die "unknown option: $1" ;;
    esac
    shift
  done
  owner="${owner:-$(default_owner)}"
  [ -x "$ADB" ] || die "adb not found under $SDK (set ANDROID_HOME)"
  reap

  # the caller's lease, renewed
  local d s
  for d in "$POOL"/*/; do
    [ -d "$d" ] || continue
    s=$(basename "$d")
    if [ "$(field "$s" owner)" = "$owner" ] && [ -f "$d/expires" ] && alive "$s"; then
      if [ $phone = 1 ] && [ "$s" != "$PHONE" ]; then continue; fi
      lease "$s" "$owner" "$ttl"; log "$s is already yours (renewed for $ttl min)"; echo "$s"; return
    fi
  done

  if [ $phone = 1 ]; then
    "$ADB" devices | grep -q "^$PHONE[[:space:]]*device$" || die "phone $PHONE is not attached"
    mkdir "$POOL/$PHONE" 2>/dev/null || die "phone $PHONE is leased by $(field "$PHONE" owner)"
    lease "$PHONE" "$owner" "$ttl"
    log "phone $PHONE is yours for $ttl min: reinstall the debug build when done, never uninstall"
    echo "$PHONE"; return
  fi

  local running; running=$(find "$POOL" -mindepth 1 -maxdepth 1 -type d -name 'emulator-*' | wc -l | tr -d ' ')
  [ "$running" -lt "$MAX" ] || die "all $MAX emulators are leased (list, or raise BRASSCRIBE_EMULATORS_MAX)"
  [ -x "$EMULATOR" ] || die "emulator not found under $SDK"

  local p serial=""
  for p in $(seq 5556 2 5584); do
    port_free "$p" || continue
    if mkdir "$POOL/emulator-$p" 2>/dev/null; then serial="emulator-$p"; break; fi
  done
  [ -n "$serial" ] || die "no free console port between 5556 and 5584"
  echo $$ > "$POOL/$serial/creator"

  log "starting $AVD on $serial for $owner"
  nohup "$EMULATOR" -avd "$AVD" -port "${serial#emulator-}" -read-only -no-window -no-audio \
    -no-boot-anim -no-snapshot-save >"$POOL/$serial/emulator.log" 2>&1 &
  local pid=$!
  echo "$pid" > "$POOL/$serial/pid"

  local t=0
  until [ "$("$ADB" -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; do
    if ! kill -0 "$pid" 2>/dev/null; then
      tail -5 "$POOL/$serial/emulator.log" >&2; rm -rf "${POOL:?}/$serial"; die "the emulator exited"
    fi
    if [ $t -ge "$BOOT_TIMEOUT" ]; then stop "$serial"; die "$serial did not boot in $BOOT_TIMEOUT s"; fi
    sleep 2; t=$((t + 2))
  done
  "$ADB" -s "$serial" shell input keyevent 82 >/dev/null 2>&1 || true   # unlock the screen
  lease "$serial" "$owner" "$ttl" "$pid"
  log "$serial booted in $t s; export ANDROID_SERIAL=$serial"
  echo "$serial"
}

release() {
  local s="${1:-}" owner d
  if [ -z "$s" ]; then
    owner=$(default_owner)
    for d in "$POOL"/*/; do
      [ -d "$d" ] && [ "$(field "$(basename "$d")" owner)" = "$owner" ] && release "$(basename "$d")"
    done
    return 0
  fi
  [ "$s" = emulator-5554 ] && die "emulator-5554 is not a pool emulator"
  [ -d "$POOL/$s" ] || die "$s is not leased"
  if [ "$s" = "$PHONE" ]; then
    rm -rf "${POOL:?}/$s"; log "phone $s released (did you reinstall the debug build?)"
  else
    stop "$s"; log "$s stopped"
  fi
}

list() {
  local d s
  printf '%-16s %-40s %s\n' SERIAL OWNER EXPIRES
  for d in "$POOL"/*/; do
    [ -d "$d" ] || continue
    s=$(basename "$d")
    printf '%-16s %-40s %s\n' "$s" "$(field "$s" owner)" \
      "$(date -r "$(field "$s" expires)" '+%H:%M' 2>/dev/null || echo starting)$(alive "$s" || echo ' (dead)')"
  done
}

cmd="${1:-}"; shift || true
case "$cmd" in
  acquire) acquire "$@" ;;
  release) release "$@" ;;
  list) list ;;
  reap) reap ;;
  *) sed -n '2,23p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
