---
name: triage-issue
description: Triage a Brasscribe GitHub issue — reproduce it, find the area and the code involved, and either fix it or write up findings. Use when given an issue number or link.
---

# Triage an issue

1. Read the issue and its comments: `gh issue view <n> --comments`. The templates in
   `.github/ISSUE_TEMPLATE/` ask for the app, platform, version and steps; note what is missing.
2. Find the area: the app and part it concerns map to the areas of `scripts/check.sh` (run it
   without arguments for the list). Search the code for the screen text, error message or setting
   named in the issue (`git grep`), and read the code there before forming a theory.
3. Reproduce before fixing: a failing test in that area is the best reproduction. If it needs a
   device, recording or model you don't have, say exactly what you'd need.
4. Fix on a branch (`fix/<short-name>`), with the test, then run the checks (see the
   `verify-change` skill) and open a pull request that says `Fixes #<n>`.
5. If you can't fix it, comment on the issue with what you found: the code involved, what you
   tried, and what would confirm the cause. Don't guess a root cause you haven't checked.

Recordings and scores attached to issues may be copyrighted: don't commit them. Rebuild the case
with a public-domain piece instead.
