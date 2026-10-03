#!/usr/bin/env bash
# Test tiers per area (docs/dev/verify.md).
#
#   scripts/check.sh fast [area...]   tier 1, the inner loop: each area well under a minute warm
#   scripts/check.sh full [area...]   tier 2, before handing off: the full suites, as CI runs them
#
# Areas: engine core conformance studio apple android windows core-dotnet bandroom-mac.
# Without areas, the ones the branch touches (against the merge base with origin/main, plus
# uncommitted and untracked files); `all` for every area. Prints a timing table at the end and
# exits non-zero if any area failed.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
[ -f .brasscribe-env ] && . ./.brasscribe-env
export PATH="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin:$PATH"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
export DOTNET_ROOT="${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1

tier="${1:-}"; shift || true
case "$tier" in fast|full) ;; *) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;; esac

ALL="engine core conformance studio apple android windows core-dotnet bandroom-mac"

changed_areas() {
  local base files
  base=$(git merge-base HEAD origin/main 2>/dev/null || echo HEAD)
  files=$( { git diff --name-only "$base"; git ls-files -o --exclude-standard; } | sort -u)
  local a=""
  add() { case " $a " in *" $1 "*) ;; *) a="$a $1" ;; esac; }
  while read -r f; do
    case "$f" in
      engine/*|pixi.toml|pixi.lock) add engine ;;
      # music/ and eval/ are also the Python side of conformance.
      music/*|eval/*) add engine; { [ "$tier" = full ] || [ -d core/target/conformance/mikkel ]; } && add conformance ;;
      core/dotnet/*) add core-dotnet ;;
      core/conformance/*) add conformance ;;
      # The C ABI and the generated bindings: the .NET wrapper calls them too.
      core/brasscribe-ffi/*|core/bindings/*) add core; add core-dotnet
                         { [ "$tier" = full ] || [ -d core/target/conformance/mikkel ]; } && add conformance ;;
      core/*) add core; { [ "$tier" = full ] || [ -d core/target/conformance/mikkel ]; } && add conformance ;;
      studio/*) add studio ;;
      apps/apple/*|capture/*) add apple ;;
      apps/bandroom/macos/*|.pixi-version) add bandroom-mac ;;
      apps/android/*) add android ;;
      apps/windows/*) add windows ;;
    esac
  done <<< "$files"
  echo "$a"
}

# A hash of the Python reference sources (committed, uncommitted and untracked): the fast
# conformance tier reuses the Python outputs of an earlier run only while this is unchanged.
PY_REF_PATHS=(music/src eval/brasscribe_eval core/conformance/brasscribe_conformance)
py_ref_stamp() {
  { git ls-files -s -- "${PY_REF_PATHS[@]}"; git diff HEAD -- "${PY_REF_PATHS[@]}"
    git ls-files -o --exclude-standard -z -- "${PY_REF_PATHS[@]}" | xargs -0 shasum 2>/dev/null; } | shasum | cut -d' ' -f1
}
PY_REF_STAMP=core/target/conformance/.python-reference-stamp

free_port() { python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])'; }

need_node_modules() { [ -d studio/node_modules ] || (cd studio && npm ci --no-audit --no-fund); }

run_area() {
  local area="$1"
  # The apps test against the prebuilt core: refresh it first (about a second when nothing changed).
  case "$area" in
    windows|core-dotnet) scripts/core-artifacts.sh ensure host || return 1 ;;
    android) scripts/core-artifacts.sh ensure host android || return 1 ;;
    apple) scripts/core-artifacts.sh ensure apple || return 1 ;;
  esac
  case "$tier:$area" in
    fast:engine) pixi run test-fast ;;
    full:engine) pixi run test ;;
    fast:core) (cd core && cargo test --profile fast -q) ;;
    full:core) (cd core && cargo test --release) ;;
    # The Python reference and the extras take minutes; the fast tier compares the Rust side of the
    # Mikkel cases against reference outputs of an earlier run in this worktree, as long as the
    # Python sources are the ones that run used (else, or with none yet, all of Mikkel), then the
    # checked-in talking-score fixtures (under a second, no data/ needed).
    fast:conformance) stamp=$(py_ref_stamp)
                      if [ -d core/target/conformance/mikkel ] && [ "$(cat "$PY_REF_STAMP" 2>/dev/null)" = "$stamp" ]; then
                        conf=(--skip-python --no-extras); else conf=(); fi
                      (cd core/conformance && uv run python -m unittest discover -s tests -q \
                         && uv run python -m brasscribe_conformance.run --only mikkel ${conf[@]+"${conf[@]}"} \
                         --work "$ROOT/core/target/conformance") && echo "$stamp" > "$PY_REF_STAMP" \
                      && (cd core/conformance && uv run python -m brasscribe_conformance.run --only talking/ \
                         --work "$ROOT/core/target/conformance-talking") ;;
    full:conformance) stamp=$(py_ref_stamp)
                      (cd core/conformance && uv run python -m unittest discover -s tests -q \
                         && uv run python -m brasscribe_conformance.run --work "$ROOT/core/target/conformance") \
                        && echo "$stamp" > "$PY_REF_STAMP" ;;
    fast:studio) need_node_modules && (cd studio && npx vitest run) ;;
    full:studio) need_node_modules && (cd studio && npx vitest run && npm run build \
                   && STUDIO_STATIC_PORT="$(free_port)" npm run test:browser) ;;
    fast:apple) make -C apps/apple package-test-fast ;;
    full:apple) (cd apps/apple/Packages/BrasscribeKit && swift test --no-parallel) \
                && (cd apps/apple/Packages/NotationKit && swift test --no-parallel) \
                && (cd capture && swift test --no-parallel) \
                && make -C apps/apple build-for-testing-mac test-mac-unit ;;
    fast:android) (cd apps/android && ./gradlew testDebugUnitTest -Pbrasscribe.fast --console=plain -q) ;;
    full:android) (cd apps/android && ./gradlew testDebugUnitTest lint assembleDebug --console=plain) ;;
    fast:windows) (cd apps/windows && dotnet test tests/Brasscribe.Play.Core.Tests --filter 'Category!=Slow') ;;
    full:windows) apps/windows/tools/check-macos.sh ;;
    *:core-dotnet) (cd core/dotnet/Brasscribe.Core.Tests && dotnet test) ;;
    fast:bandroom-mac) (cd apps/bandroom/macos && scripts/test-pixi-spec.sh && scripts/test-kit.sh) ;;
    full:bandroom-mac) (cd apps/bandroom/macos && scripts/test-pixi-spec.sh && scripts/test-kit.sh && make build) ;;
    *) echo "unknown area: $area ($ALL)" >&2; return 2 ;;
  esac
}

areas="$*"
[ "$areas" = all ] && areas="$ALL"
[ -z "$areas" ] && areas="$(changed_areas)"
if [ -z "${areas// }" ]; then echo "nothing changed against origin/main; name the areas ($ALL) or all" >&2; exit 0; fi

summary="" status=0
for area in $areas; do
  printf '\n=== %s %s\n' "$tier" "$area"
  s=$SECONDS
  if run_area "$area"; then r=pass; else r=FAIL; status=1; fi
  summary="$summary$(printf '%-12s %-5s %4d s' "$area" "$r" $((SECONDS - s)))\n"
done
printf '\n%s tier\n%b' "$tier" "$summary"
exit $status
