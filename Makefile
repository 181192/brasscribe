# Verification tiers (docs/dev/verify.md). AREAS= picks areas; by default the ones this branch touches.
#   make setup          scripts/worktree-setup.sh: links data/, models/, Verovio; prebuilt core
#   make check-fast     tier 1, the inner loop
#   make check          tier 2, before handing off: the full suites
#   make check-all      tier 2 for every area
AREAS ?=

.PHONY: setup check-fast check check-all

setup:
	scripts/worktree-setup.sh >/dev/null

check-fast:
	scripts/check.sh fast $(AREAS)

check:
	scripts/check.sh full $(AREAS)

check-all:
	scripts/check.sh full all
