#!/usr/bin/env bash
# Runs the iPhone screen catalogue (PhoneScreensTests, README "Screen catalogue (iPhone)") in English and in bokmål, into
# build/catalogue/iphone. Called by `make test-iphone-catalogue` after build-for-testing-ios, with XCB (the xcodebuild
# command) and SCRIBE_FIXTURES in the environment.
#
#   scripts/iphone-catalogue.sh                 two phones of its own, made for the run and deleted after it: the
#                                               smallest iPhone of the newest iOS and an iPhone SE, run at once
#   scripts/iphone-catalogue.sh <destination>   that one simulator (CI, where the job has one), shut down after
#
# CATALOGUE_LANGUAGES picks the languages (default "en nb"): a pull request that cannot change the bokmål screens
# runs English alone (.github/workflows/ci.yml, filter apple_play_nb).
#
# Its own phones have names of their own (catalogue-smallest-<pid>, catalogue-shortest-<pid>), so a run never starts,
# stops or tests on a simulator another run is using.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${XCB:?XCB (the xcodebuild command) is not set}"

out=$PWD/build/catalogue/iphone
dests=() sims=() own=()
cleanup() {
  # (The macOS bash takes an empty array for an unset one under set -u, hence ${a[@]+...}.)
  for s in ${sims[@]+"${sims[@]}"}; do xcrun simctl shutdown "$s" 2>/dev/null || true; done
  for s in ${own[@]+"${own[@]}"}; do xcrun simctl delete "$s" 2>/dev/null || true; done
}
trap cleanup EXIT

if [ -n "${1:-}" ]; then
  dests=("$1")
  sims=("${1##*id=}")
else
  for phone in smallest shortest; do
    dest=$(scripts/smallest-iphone.sh "$phone" "catalogue-$phone-$$")
    dests+=("$dest")
    sims+=("${dest##*id=}")
    own+=("${dest##*id=}")
  done
fi

for sim in "${sims[@]}"; do scripts/boot-simulator.sh "$sim"; done

args=()
for d in "${dests[@]}"; do args+=(-destination "$d"); done
rm -rf "$out"
for lang in ${CATALOGUE_LANGUAGES:-en nb}; do
  TEST_RUNNER_CATALOGUE_OUT=$out TEST_RUNNER_CATALOGUE_LANGUAGE=$lang \
    $XCB -scheme BrasscribePlay-iOS "${args[@]}" -maximum-concurrent-test-simulator-destinations 2 -testLanguage "$lang" \
    -only-testing:BrasscribePlayTests_iOS/PhoneScreensTests test-without-building
done
