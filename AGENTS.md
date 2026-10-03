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
| Per-app build and toolchain | the README in the app's directory (`apps/<app>/`, `apps/bandroom/<os>/`) |
| Licences of what is bundled | [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) |

## How to work

- **Verify before you claim.** Run the tier the change needs (`make check-fast` while working,
  `make check` before handing off). Report what you ran and its result; if you skipped a check,
  say so. Never describe a test as passing that you did not run.
- **Android: the JVM first.** The app's screens, flows, screenshots and accessibility checks run on the JVM
  in the unit tests; an emulator is for what only a device can do. A new screen comes with its JVM tests and
  an entry in its app's screen catalogue, and a reviewer's probe is a JVM test. The rules and the list of
  device-only cases are in [apps/android/README.md](apps/android/README.md#testing).
- **Studio: the catalogue first.** Studio's views are checked on the built bundle with the API answered from
  committed fixtures, no engine: accessibility, cut-off text, reflow, text spacing, the keyboard and screenshots
  compared with the merge base. A new view comes with an entry in the catalogue and the fixtures it needs; a
  live engine and `data/` are for what only they can show. The rules are in [studio/README.md](studio/README.md#test).
- **Change one thing per branch**, on a branch or worktree, never directly on `main` unless told to.
- **Follow the surrounding code.** Each part has its own language and idioms (Python, Rust, Swift,
  Kotlin, C#, TypeScript); match the file you are in, its naming and its comment density.
- **The Python reference is the spec.** Music rules are written once in Python and ported to the Rust
  core; the conformance suite checks they agree. [core/README.md](core/README.md) says what counts as
  the reference. Change the reference first, then the port.
- **Goldens change deliberately.** Reference outputs are promoted at merge, never from a branch and
  never just to make a test pass: follow [docs/dev/release.md](docs/dev/release.md) §10.
- **Keep docs true.** If your change makes a doc wrong, fix the doc in the same branch. Don't add
  numbers or lists to docs that a script can print instead.

## Commits and pull requests

- [Conventional Commits](https://www.conventionalcommits.org): `type(scope): summary`. The scope is
  the app or part (`android`, `apple`, `windows`, `bandroom-mac`, `studio`, `engine`, `core`, …).
- **Pull request titles become the release notes.** Pull requests are squash-merged, and the title
  becomes the commit on `main` (`cliff.toml` decides what is listed for users and what is folded
  away). Give each pull request a Conventional Commit title, and write `feat` and `fix` titles for
  someone who uses the app, in plain words. One pull request is one entry in the notes.
- Describe what the change does. Don't refer to agents, sessions or task ids in commit messages, code
  comments or docs. A `Co-Authored-By` trailer that credits an AI assistant is fine: it is the
  disclosure the pull request template asks for.
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
