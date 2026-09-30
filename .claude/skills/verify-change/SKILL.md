---
name: verify-change
description: Pick and run the right checks for a change in Brasscribe, and report the result honestly. Use after editing code, before committing, and before saying a change works.
---

# Verify a change

The tiers, the areas and what each runs are defined by `scripts/check.sh` and
[docs/dev/verify.md](../../../docs/dev/verify.md). Read them; don't rely on a remembered list.

1. **Set up once per checkout:** `eval "$(scripts/worktree-setup.sh)"` (later shells: `source .brasscribe-env`).
2. **While working:** `make check-fast`. It runs the areas the branch touches. To name areas:
   `AREAS="engine core" make check-fast`. Run `scripts/check.sh` without arguments to see the areas.
3. **Before handing off:** `make check` (the full suites, as CI runs them).
4. **Device, audio or UI changes:** tier 3 in docs/dev/verify.md (emulators, simulators, VMs). Never
   drive UI tests on the host desktop; the docs say where they run.
5. **Report:** say which commands you ran and paste the summary lines (the timing table at the end).
   Tests that skip because `data/` or models are missing are expected; say they skipped, don't
   count them as passing. If a check failed and you didn't fix it, say so plainly.

If a test fails for a reason unrelated to your change, check whether it also fails on `origin/main`
before touching it, and mention it rather than "fixing" it silently.
