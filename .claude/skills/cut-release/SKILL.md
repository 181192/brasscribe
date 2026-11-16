---
name: cut-release
description: Cut a release of one product (Brasscribe Play, Fretscribe, Bandroom or scribe-core): version bump, changelog, tag, CI build and publish. Use when asked to release, publish a version, or prepare release notes.
---

# Cut a release

The procedure and its reasons are in [docs/shared/dev/release.md](../../../docs/shared/dev/release.md); the
steps are scripted in `scripts/release.sh`. Read both before starting.

1. On `main`, up to date with `origin/main`, with a clean tree.
2. Each product is released on its own (`scripts/release.sh --products` lists them). `scripts/release.sh --preview PRODUCT` shows the notes its release would get. Choose the version from
   it: any `feat` since the product's last release means a minor bump; only fixes, a patch bump. Confirm the
   version with the owner before tagging.
3. If the preview reads badly, the fix is in the commit messages and `cliff.toml`, not in
   hand-edited notes.
4. `scripts/release.sh PRODUCT X.Y.Z` bumps the product's versions and `changelogs/PRODUCT.md` on `release/PRODUCT-vX.Y.Z` and opens
   the release pull request (`main` takes changes only through pull requests). Let the owner review
   and merge it.
5. After the merge: `git pull`, then `scripts/release.sh --tag PRODUCT X.Y.Z` tags the release commit and
   pushes the tag, which starts `.github/workflows/release.yml`.
6. Watch it: `gh run list -w release -L 1`, then `gh run watch <id>`. When it finishes, check the
   product's release page (and its `PRODUCT-latest` release) lists every file of the product the site links to (the `[[downloads]]` in `site/shared/site.toml` and in each `site/<product>/product.toml`).
   The run's summary has the table of on-device models per file (step "On-device models in the release files" of
   the `github` job, `.github/scripts/release-models.py`): Play for Android must show the three models and
   `NOTICE.md` as ok. The step fails the release before publishing when an app lacks its models; fix the build,
   never skip it. For files built by hand, run `.github/scripts/release-models.py $(for f in $(scripts/release.sh --files PRODUCT); do printf -- "--require %s " "$f"; done) <folder>` before publishing.
7. If the workflow did not start from the tag, start it: `gh workflow run release.yml --ref PRODUCT-vX.Y.Z`.

Never move or delete a published tag, and never publish from a local build unless the doc's
local-build sections say why CI can't be used.
