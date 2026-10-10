#!/usr/bin/env bash
# One-time setup of a fresh checkout or git worktree for building and testing. Idempotent.
#
#   eval "$(scripts/worktree-setup.sh)"          set up, then export the environment
#   scripts/worktree-setup.sh --print-env        only print the environment
#   scripts/worktree-setup.sh --no-core          skip the prebuilt core artifacts
#   scripts/worktree-setup.sh --core host,apple  only these core components (default: all installed toolchains)
#
# 1. Links data/, models/ and apps/apple/Frameworks (Verovio) from the main checkout, found through
#    `git worktree list` (or BRASSCRIBE_MAIN). Nothing is linked in the main checkout itself.
# 2. Copies in the prebuilt Rust core (scripts/core-artifacts.sh ensure): the host library and
#    command line, the Apple xcframework and the Android jniLibs, built once per core change and
#    shared by all worktrees.
# 3. Prints the environment to export on stdout (progress goes to stderr), and writes it to
#    .scribe-env for `source .scribe-env` in later shells.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
print_only=0 core=1 comps=""
while [ $# -gt 0 ]; do
  case "$1" in
    --print-env) print_only=1 ;;
    --no-core) core=0 ;;
    --core) comps="${2//,/ }"; shift ;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
log() { printf 'worktree-setup: %s\n' "$*" >&2; }

main_checkout() {
  # The first entry of `git worktree list` is the main working tree; BRASSCRIBE_MAIN overrides it.
  if [ -n "${BRASSCRIBE_MAIN:-}" ] && [ -d "$BRASSCRIBE_MAIN" ]; then (cd "$BRASSCRIBE_MAIN" && pwd); return; fi
  git -C "$ROOT" worktree list --porcelain | sed -n '1s/^worktree //p'
}
MAIN="$(main_checkout)"
[ -n "$MAIN" ] || { log "cannot find the main checkout; set BRASSCRIBE_MAIN"; exit 1; }

ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
env_lines() {
  local path="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin"
  [ -d "$ANDROID_HOME/platform-tools" ] && path="$path:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator"
  # This checkout, not the main one: tests also look up tracked files (sounds/, design/) through
  # it, and data/ and models/ are linked in.
  echo "export BRASSCRIBE_REPO='$ROOT'"
  echo "export SCRIBE_FFI_PATH='$ROOT/core/target/release/libscribe_ffi.$([ "$(uname -s)" = Darwin ] && echo dylib || echo so)'"
  # The core's command line, for the engine's bass-tab profile and the tests that need it.
  [ -x "$ROOT/core/target/release/scribe-core" ] && echo "export SCRIBE_CORE_CLI='$ROOT/core/target/release/scribe-core'"
  # The data is here, so a Rust golden test that cannot find it fails instead of skipping.
  [ -e "$MAIN/data/mikkel/repro/mix.beats" ] && echo "export BRASSCRIBE_REQUIRE_DATA=1"
  echo "export ANDROID_HOME='$ANDROID_HOME'"
  [ -d "$ANDROID_HOME/ndk/28.2.13676358" ] && echo "export ANDROID_NDK_HOME='$ANDROID_HOME/ndk/28.2.13676358'"
  [ -d /Applications/Xcode.app ] && echo "export DEVELOPER_DIR='${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}'"
  [ -d /opt/homebrew/opt/dotnet/libexec ] && echo "export DOTNET_ROOT='${DOTNET_ROOT:-/opt/homebrew/opt/dotnet/libexec}'"
  echo "export PATH='$path':\"\$PATH\""
}
if [ $print_only = 1 ]; then env_lines; exit 0; fi

# 1. Links from the main checkout
link() {
  local rel="$1" src="$MAIN/$1" dst="$ROOT/$1"
  if [ "$ROOT" = "$MAIN" ]; then return; fi
  if [ -L "$dst" ]; then
    [ "$(readlink "$dst")" = "$src" ] && return
    rm "$dst"
  elif [ -e "$dst" ]; then
    log "$rel exists and is not a link; leaving it"; return
  fi
  if [ ! -e "$src" ]; then log "$rel is missing in $MAIN too; tests that need it will be skipped"; return; fi
  ln -s "$src" "$dst"
  log "linked $rel -> $src"
}
link data
link models
link apps/apple/Frameworks
[ -e "$ROOT/apps/apple/Frameworks/Verovio.xcframework" ] || log "no Verovio.xcframework: run make verovio in apps/apple (in $MAIN, then run this again)"
for f in data/golden/mikkel-arranged-band/composition.json data/mikkel/repro/layers/solo-sw.mid data/sounds/band; do
  [ -e "$ROOT/$f" ] || log "missing $f: golden tests that need it will be reported as skipped"
done

# 2. Prebuilt core
if [ $core = 1 ]; then
  # shellcheck disable=SC2086
  "$ROOT/scripts/core-artifacts.sh" ensure $comps >&2 || log "core artifacts failed; build them with scripts/core-artifacts.sh ensure"
fi

# Studio's node_modules, cloned from the main checkout when both lock files match (npm ci otherwise)
if [ "$ROOT" != "$MAIN" ] && [ ! -d "$ROOT/studio/node_modules" ] && [ -d "$MAIN/studio/node_modules" ] \
   && cmp -s "$ROOT/studio/package-lock.json" "$MAIN/studio/package-lock.json" \
   && [ "$MAIN/studio/node_modules" -nt "$MAIN/studio/package-lock.json" ]; then
  cp -cR "$MAIN/studio/node_modules" "$ROOT/studio/node_modules" 2>/dev/null \
    && log "cloned studio/node_modules from $MAIN" || rm -rf "$ROOT/studio/node_modules"
fi

# 3. Environment
env_lines > "$ROOT/.scribe-env"
log "environment written to .scribe-env (source it in new shells)"
env_lines
