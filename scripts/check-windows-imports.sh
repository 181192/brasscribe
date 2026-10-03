#!/usr/bin/env bash
# Checks that Windows binaries start on a PC without the Visual C++ runtime installed (CI, Windows runners).
#
#   scripts/check-windows-imports.sh --static FILE...   no C runtime DLL at all: our own Rust builds,
#                                                       linked with -C target-feature=+crt-static
#   scripts/check-windows-imports.sh --shipped DIR      every Visual C++ runtime DLL that an .exe or .dll
#                                                       in DIR imports is shipped in DIR (app-local)
#
# Prints each binary's imported DLLs (from the import and delay-import tables, read with llvm-readobj
# from rustup's llvm-tools). The Universal CRT (api-ms-win-crt-*, ucrtbase.dll) is part of Windows 10
# and later, so --shipped allows it; --static does not.
set -euo pipefail

mode="${1:-}"; shift || true
[ "$mode" = --static ] || [ "$mode" = --shipped ] || { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
[ $# -gt 0 ] || { echo "no files or directory given" >&2; exit 2; }

rustup component add llvm-tools >/dev/null 2>&1
host="$(rustc -vV | sed -n 's/^host: //p')"
readobj="$(rustc --print sysroot)/lib/rustlib/$host/bin/llvm-readobj"
[ -x "$readobj" ] || readobj="$readobj.exe"

imports() {
  { "$readobj" --coff-imports "$1" 2>/dev/null || true; } | sed -n 's/^ *Name: //p' | tr -d '\r' | sort -fu
}

fail=0
if [ "$mode" = --static ]; then
  for f in "$@"; do
    dlls="$(imports "$f")"
    echo "$(basename "$f") imports:"; sed 's/^/  /' <<<"$dlls"
    grep -qi '^kernel32\.dll$' <<<"$dlls" || { echo "::error::no imports read from $f"; fail=1; continue; }
    if bad="$(grep -iE '^(vcruntime|msvcp|concrt|vccorlib|ucrtbase|api-ms-win-crt-)' <<<"$dlls")"; then
      echo "::error::$(basename "$f") needs a C runtime DLL ($(tr '\n' ' ' <<<"$bad")); build it with -C target-feature=+crt-static"
      fail=1
    fi
  done
  exit $fail
fi

dir="$1"
shipped="$(find "$dir" -type f -iname '*.dll' -exec basename {} \; | tr '[:upper:]' '[:lower:]' | sort -u)"
while IFS= read -r f; do
  dlls="$(imports "$f")"
  vc="$(grep -iE '^(vcruntime|msvcp|concrt|vccorlib)' <<<"$dlls" || true)"
  [ -n "$vc" ] || continue
  rel="${f#"$dir"/}"
  for d in $vc; do
    if grep -qx "$(tr '[:upper:]' '[:lower:]' <<<"$d")" <<<"$shipped"; then
      echo "$rel: $d (shipped)"
    else
      echo "::error::$rel imports $d, which is not shipped in $(basename "$dir")"
      fail=1
    fi
  done
done < <(find "$dir" -type f \( -iname '*.dll' -o -iname '*.exe' \) | sort)
exit $fail
