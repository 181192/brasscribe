# Working on Brasscribe (for coding agents)

This file says **how to work** here and **where the facts live**. It deliberately holds no facts that
change (versions, file lists, test counts, commands' options, benchmark numbers): those live in the
code, the scripts and the docs linked below, and a copy here would go stale. When this file and the
repository disagree, the repository wins. Read the source you are about to change instead of relying
on memory or on this file.

## Where to look first

| Question | Source of truth |
|---|---|
| What the project is, the apps, the layout | [README.md](README.md) |
| How to set up a checkout or worktree | `scripts/worktree-setup.sh` and [docs/dev/verify.md](docs/dev/verify.md) |
| Which checks to run, and the areas | `scripts/check.sh` (run it without arguments for its help) and [docs/dev/verify.md](docs/dev/verify.md) |
| How a release is made | `scripts/release.sh` and [docs/dev/release.md](docs/dev/release.md) |
| What CI runs | `.github/workflows/` |
| Design rules and tokens | [design/README.md](design/README.md) and `design/tokens/` |
| Why the architecture is as it is | [docs/research/00-summary.md](docs/research/00-summary.md) |
| Per-app build and toolchain | the README in each `apps/*` directory |
| Licences of what is bundled | [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) |

## How to work

- **Verify before you claim.** Run the tier the change needs (`make check-fast` while working,
  `make check` before handing off). Report what you ran and its result; if you skipped a check,
  say so. Never describe a test as passing that you did not run.
- **Change one thing per branch**, on a branch or worktree, never directly on `main` unless told to.
- **Follow the surrounding code.** Each part has its own language and idioms (Python, Rust, Swift,
  Kotlin, C#, TypeScript); match the file you are in, its naming and its comment density.
- **The Python reference is the spec.** Music rules are written once in Python (`music/`) and ported
  to the Rust core; the conformance suite checks they agree. Change the reference first, then the port.
- **Goldens change deliberately.** Reference outputs are promoted on purpose with a reason in the
  commit, never regenerated just to make a test pass.
- **Keep docs true.** If your change makes a doc wrong, fix the doc in the same branch. Don't add
  numbers or lists to docs that a script can print instead.

## Commits and pull requests

- [Conventional Commits](https://www.conventionalcommits.org): `type(scope): summary`. The scope is
  the app or part (`android`, `apple`, `windows`, `bandroom-mac`, `studio`, `engine`, `core`, …).
- **Commit messages become the release notes** (`cliff.toml`): `feat` and `fix` are listed for users,
  so write the summary for someone who uses the app, in plain words. `docs`, `test`, `ci`, `build`,
  `refactor` and `chore` are folded away.
- Don't mention agents, sessions, task ids or tools in commits, code comments or docs. Describe what
  the change does.
- Fill in the pull request template, including the verification and the AI-assistance section.

## This repository is public

Never commit:

- personal or machine details: email addresses other than the author's public one, absolute paths
  (`/Users/...`, `C:\Users\...`), host names, IP addresses, device serials;
- secrets: keys, keystores, tokens, `.env` files (the Android release key lives only in the
  `release` environment's secrets);
- copyrighted music: recordings, scores or renders of real pieces. Use the public-domain fixtures
  (e.g. *Old Hundredth*) for tests, screenshots and docs;
- references to anyone's employer or internal systems (internal package registries, hostnames).

`data/`, `models/` and the band SoundFonts are not in git on purpose; tests that need them skip
themselves when they are missing.

## Repo skills

`.claude/skills/` holds step-by-step procedures (verify a change, cut a release, triage an issue).
They point to the scripts and docs above rather than repeating them.
