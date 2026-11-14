#!/usr/bin/env bash
# Build the GitHub Pages site into site/_site: every product in site/ (a folder with a product.toml), from the
# shared layout and the design system's generated assets. site/README.md says how the site is put together.
# Usage: site/build.sh && python3 -m http.server -d site/_site 8000
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# The site and the READMEs link to the latest release and never name a version, so nothing goes stale.
# (The research papers and their reference list are left out: a dataset or a model is cited with its version.)
pinned=$(cd "$ROOT" && git grep -n -I -E 'releases/tag/[A-Za-z0-9._-]*[0-9]|releases/download/[A-Za-z0-9._-]*[0-9][A-Za-z0-9._-]*/|(Brasscribe|Fretscribe|Bandroom) [0-9]+\.[0-9]+\.[0-9]|[Vv]ersjon [0-9]+\.[0-9]+|[Vv]ersion [0-9]+\.[0-9]+\.[0-9]|[Rr]elease v[0-9]|-v[0-9]+\.[0-9]+\.[0-9]' \
  -- 'site/*.html' 'site/*.toml' 'README.md' '*/README.md' ':!site/*/pages/research.html' ':!site/*/pages/research.*.toml' ':!site/shared/research/measure-*.html' \
     ':!site/shared/research/words.*.toml' ':!site/shared/research/references.toml' || true)
if [ -n "$pinned" ]; then
  echo "error: link to a product's latest release (in site/: {{file <name>}} and {{releases}}) instead of naming a version:" >&2; echo "$pinned" >&2; exit 1
fi
# One word for each state, the same everywhere: the apps are "not in the app stores yet" ("ligger ikke i appbutikkene
# ennå"), iPhone and iPad have a "test version", Windows an "early version". The words they replaced are refused.
retired=$(cd "$ROOT" && git grep -n -I -i -E 'early testing|test build|not in any app store|Hent Bandroom|tidlig testing|testbygg|ikke i noen appbutikk' \
  -- 'site/*.html' 'site/*.toml' 'site/*.py' 'site/*.js' || true)
if [ -n "$retired" ]; then
  echo "error: use the site's one word for the state (not in the app stores yet, test version, early version; Last ned Bandroom):" >&2
  echo "$retired" >&2; exit 1
fi
python3 "$ROOT/site/build.py"
