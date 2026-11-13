#!/usr/bin/env bash
# Build the GitHub Pages site into site/_site: every product in site/ (a folder with a product.toml), from the
# shared layout and the design system's generated assets. site/README.md says how the site is put together.
# Usage: site/build.sh && python3 -m http.server -d site/_site 8000
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# The site and the READMEs link to the latest release and never name a version, so nothing goes stale.
# (The research papers and their reference list are left out: a dataset or a model is cited with its version.)
pinned=$(cd "$ROOT" && git grep -n -I -E 'releases/tag/|releases/download/|(Brasscribe|Fretscribe|Bandroom) [0-9]+\.[0-9]+\.[0-9]|[Vv]ersjon [0-9]+\.[0-9]+|[Vv]ersion [0-9]+\.[0-9]+\.[0-9]|[Rr]elease v[0-9]|-v[0-9]+\.[0-9]+\.[0-9]' \
  -- 'site/*.html' 'site/*.toml' 'README.md' '*/README.md' ':!site/*/pages/*/research.html' ':!site/shared/research/references.toml' || true)
if [ -n "$pinned" ]; then
  echo "error: link to releases/latest (in site/: {{file <name>}} and {{releases}}) instead of naming a version:" >&2; echo "$pinned" >&2; exit 1
fi
python3 "$ROOT/site/build.py"
