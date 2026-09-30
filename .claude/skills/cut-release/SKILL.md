---
name: cut-release
description: Cut a Brasscribe release (version bump, changelog, tag, CI build and publish). Use when asked to release, publish a version, or prepare release notes.
---

# Cut a release

The procedure and its reasons are in [docs/dev/release.md](../../../docs/dev/release.md); the
steps are scripted in `scripts/release.sh`. Read both before starting.

1. On `main`, up to date with `origin/main`, with a clean tree.
2. `scripts/release.sh --preview` shows the notes the release would get. Choose the version from
   it: any `feat` since the last release means a minor bump; only fixes, a patch bump. Confirm the
   version with the owner before tagging.
3. If the preview reads badly, the fix is in the commit messages and `cliff.toml`, not in
   hand-edited notes.
4. `scripts/release.sh X.Y.Z --push` bumps the versions, regenerates `CHANGELOG.md`, commits,
   tags and pushes. The tag starts `.github/workflows/release.yml`.
5. Watch it: `gh run list -w release -L 1`, then `gh run watch <id>`. When it finishes, check the
   release page lists every file the site's download table links to (`site/guide/index.html`).
6. If the workflow did not start from the tag, start it: `gh workflow run release.yml --ref vX.Y.Z`.

Never move or delete a published tag, and never publish from a local build unless the doc's
local-build sections say why CI can't be used.
