#!/usr/bin/env bash
# Checks that Windows binaries start on a PC without the Visual C++ runtime installed (CI, Windows runners).
#
#   scripts/check-windows-imports.sh --static FILE...
#       no C runtime DLL at all: our own Rust builds, linked with -C target-feature=+crt-static
#   scripts/check-windows-imports.sh --shipped DIR [NAME...]
#       every Visual C++ runtime DLL that an .exe or .dll under DIR imports is shipped next to it or in
#       DIR (app-local); the binaries called NAME must have readable imports, which are printed
#
# Imports are read from the import and delay-import tables with llvm-readobj (rustup's llvm-tools). The
# Universal CRT (api-ms-win-crt-*, ucrtbase.dll) is part of Windows 10 and later, so --shipped allows it;
# --static does not.
set -euo pipefail

mode="${1:-}"; shift || true
[ "$mode" = --static ] || [ "$mode" = --shipped ] || { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[ $# -gt 0 ] || { echo "no files or directory given" >&2; exit 2; }

rustup component add llvm-tools >/dev/null 2>&1
host="$(rustc -vV | sed -n 's/^host: //p')"
readobj="$(rustc --print sysroot)/lib/rustlib/$host/bin/llvm-readobj"
[ -x "$readobj" ] || readobj="$readobj.exe"

# The DLLs a binary imports, one per line; empty when its tables cannot be read.
imports() {
  { "$readobj" --coff-imports "$1" 2>/dev/null || true; } | sed -n 's/^ *Name: //p' | tr -d '\r' | sort -fu
}

fail=0
if [ "$mode" = --static ]; then
  for f in "$@"; do
    dlls="$(imports "$f")"
    echo "$(basename "$f") imports:"
    while IFS= read -r d; do echo "  $d"; done <<<"$dlls"
    grep -qi '^kernel32\.dll$' <<<"$dlls" || { echo "::error::no imports read from $f"; fail=1; continue; }
    if bad="$(grep -iE '^(vcruntime|msvcp|concrt|vccorlib|ucrtbase|api-ms-win-crt-)' <<<"$dlls")"; then
      echo "::error::$(basename "$f") needs a C runtime DLL ($(tr '\n' ' ' <<<"$bad")); build it with -C target-feature=+crt-static"
      fail=1
    fi
  done
  exit $fail
fi

dir="$1"; shift
# The loader finds an app-local DLL next to the binary that imports it, or next to the app's exe (DIR).
has() { [ -n "$(find "$1" "$dir" -maxdepth 1 -type f -iname "$2" -print -quit)" ]; }
read_ok=0 total=0
while IFS= read -r f; do
  total=$((total + 1))
  dlls="$(imports "$f")"
  [ -z "$dlls" ] || read_ok=$((read_ok + 1))
  rel="${f#"$dir"/}"
  for name in "$@"; do
    [ "$(basename "$f")" = "$name" ] || continue
    echo "$rel imports:"
    while IFS= read -r d; do echo "  $d"; done <<<"$dlls"
    grep -qi '^kernel32\.dll$' <<<"$dlls" || { echo "::error::no imports read from $rel"; fail=1; }
  done
  vc="$(grep -iE '^(vcruntime|msvcp|concrt|vccorlib)' <<<"$dlls" || true)"
  for d in $vc; do
    if has "$(dirname "$f")" "$d"; then
      echo "$rel: $d (shipped)"
    else
      echo "::error::$rel imports $d, which is not shipped next to it or next to the app"
      fail=1
    fi
  done
done < <(find "$dir" -type f \( -iname '*.dll' -o -iname '*.exe' \) | sort)
echo "import tables read: $read_ok of $total binaries"
[ "$read_ok" -gt 0 ] || { echo "::error::no import table read under $dir"; fail=1; }
exit $fail
