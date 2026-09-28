#!/usr/bin/env bash
# One-time setup of a fresh checkout or git worktree for building and testing. Idempotent.
#
#   eval "$(scripts/worktree-setup.sh)"          set up, then export the environment
#   scripts/worktree-setup.sh --print-env        only print the environment
#   scripts/worktree-setup.sh --no-core          skip the prebuilt core artifacts
#   scripts/worktree-setup.sh --core host,apple  only these core components (default: all installed toolchains)
#
# 1. Links data/, models/ and apps/apple/Frameworks (Verovio) from the main checkout, found through
#    BRASSCRIBE_REPO or `git worktree list`. Nothing is linked in the main checkout itself.
# 2. Copies in the prebuilt Rust core (scripts/core-artifacts.sh ensure): the host library, the
#    Apple xcframework and the Android jniLibs, built once per core change and shared by all worktrees.
# 3. Prints the environment to export on stdout (progress goes to stderr), and writes it to
#    .brasscribe-env for `source .brasscribe-env` in later shells.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
print_only=0 core=1 comps=""
while [ $# -gt 0 ]; do
  case "$1" in
    --print-env) print_only=1 ;;
    --no-core) core=0 ;;
    --core) comps="${2//,/ }"; shift ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
log() { printf 'worktree-setup: %s\n' "$*" >&2; }

main_checkout() {
  if [ -n "${BRASSCRIBE_REPO:-}" ] && [ -d "$BRASSCRIBE_REPO" ]; then (cd "$BRASSCRIBE_REPO" && pwd); return; fi
  # The first entry of `git worktree list` is the main working tree.
  git -C "$ROOT" worktree list --porcelain | sed -n '1s/^worktree //p'
}
MAIN="$(main_checkout)"
[ -n "$MAIN" ] || { log "cannot find the main checkout; set BRASSCRIBE_REPO"; exit 1; }

ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
env_lines() {
  local path="/opt/homebrew/opt/rustup/bin:$HOME/.cargo/bin"
  [ -d "$ANDROID_HOME/platform-tools" ] && path="$path:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator"
  echo "export BRASSCRIBE_REPO='$MAIN'"
  echo "export BRASSCRIBE_FFI_PATH='$ROOT/core/target/release/libbrasscribe_ffi.$([ "$(uname -s)" = Darwin ] && echo dylib || echo so)'"
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

# 3. Environment
env_lines > "$ROOT/.brasscribe-env"
log "environment written to .brasscribe-env (source it in new shells)"
env_lines
