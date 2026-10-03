#!/usr/bin/env bash
# The instrumented tests that need a device, on one: the emulator or phone in ANDROID_SERIAL.
#
#   apps/android/scripts/device-tests.sh smoke [brasscribe|fretscribe]        each app starts, one flow end to
#                                                                              end, the score or tab has ink, a turn
#   apps/android/scripts/device-tests.sh device-only [brasscribe|fretscribe]  what only a device can run
#                                                                              (sound out, capture, memory, frames...)
#   apps/android/scripts/device-tests.sh class <fully.qualified.Class> [brasscribe|fretscribe]
#
# Without an app, both. Everything else is checked on the JVM (scripts/check.sh fast|full android). For
# an emulator of your own:
#
#   serial=$(apps/android/scripts/emulator-pool.sh acquire)
#   ANDROID_SERIAL=$serial apps/android/scripts/device-tests.sh smoke
#   apps/android/scripts/emulator-pool.sh release "$serial"
set -euo pipefail

android="$(cd "$(dirname "$0")/.." && pwd)"
what="${1:-}"; shift || true
case "$what" in
  smoke) filter=("-Pandroid.testInstrumentationRunnerArguments.annotation=no.brasscribe.play.test.Smoke") ;;
  device-only) filter=("-Pandroid.testInstrumentationRunnerArguments.annotation=no.brasscribe.play.test.DeviceOnly") ;;
  class) filter=("-Pandroid.testInstrumentationRunnerArguments.class=${1:?a class}"); shift ;;
  *) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
[ -n "${ANDROID_SERIAL:-}" ] || { echo "device-tests: set ANDROID_SERIAL (apps/android/scripts/emulator-pool.sh acquire)" >&2; exit 2; }

apps="${1:-brasscribe fretscribe}"
tasks=()
for app in $apps; do
  case "$app" in
    brasscribe) tasks+=(":app:connectedBrasscribeDebugAndroidTest") ;;
    fretscribe) tasks+=(":app:connectedFretscribeDebugAndroidTest") ;;
    *) echo "device-tests: no app $app (brasscribe, fretscribe)" >&2; exit 2 ;;
  esac
done
# The realistic sound's own test is in the audio module; it is a device's too.
[ "$what" = device-only ] && tasks+=(":audio:connectedDebugAndroidTest")
cd "$android"
exec ./gradlew "${tasks[@]}" "${filter[@]}" --console=plain
