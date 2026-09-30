<!-- Title: a Conventional Commit, e.g. `fix(android): keep the stand page when rotating`.
     `feat` and `fix` titles become release notes: write them for the people who use the apps. -->

## What and why

<!-- What changes for the user or the code, and why. Link the issue: "Fixes #123". -->

## Areas touched

<!-- The areas of `scripts/check.sh` (run it without arguments for the list), e.g. `android`, `core`. -->

## Verification

<!-- What you ran and the result: paste the summary (the timing table of `make check`).
     Say what skipped (tests without `data/` or models skip themselves) and what you did not run. -->

- [ ] `make check` for the areas above (paths outside its areas: the tests their README names)
- [ ] Tier 3 (devices, simulators, VMs) if it changes a screen, audio or a device behaviour; screenshots below
- [ ] Docs updated where this change made them wrong

## AI assistance

<!-- Brasscribe welcomes AI-assisted work; say how it was used so reviewers know where to look. -->

- [ ] None
- [ ] Some: AI suggested parts; I wrote or rewrote the rest
- [ ] Mostly: an agent wrote most of it; I reviewed every line and ran the verification myself

Tool and what it did (optional):

## Screenshots

<!-- For UI changes: before and after, light and dark. Use public-domain music (e.g. Old Hundredth). -->

## Checklist

- [ ] No personal data, machine paths, secrets or copyrighted music (see AGENTS.md, "This repository is public")
- [ ] Goldens and reference outputs changed only on purpose, with the reason in the commit
