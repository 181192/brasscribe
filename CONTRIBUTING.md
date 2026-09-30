# Contributing to Brasscribe

Thanks for helping. Bug reports, ideas, fixes and translations are all welcome, and so is work done
with AI coding tools, as long as you've checked it.

## Reporting

- **Bugs and ideas:** open an issue from a template; the fields are what's needed to act on it.
- **Security problems:** report them privately (see [SECURITY.md](SECURITY.md)), not as an issue.
- **Recordings and scores:** don't attach copyrighted music. Describe the passage, or reproduce the
  problem with a public-domain piece.

## Making a change

1. Fork, then branch from `main` (`fix/…`, `feat/…`, `docs/…`).
2. Set up once: `eval "$(scripts/worktree-setup.sh)"`. Each app's README lists its toolchain.
3. Work in small steps and run `make check-fast`; run `make check` before opening the pull request.
   [docs/dev/verify.md](docs/dev/verify.md) explains the tiers and when device or UI checks are needed.
4. Commit with [Conventional Commits](https://www.conventionalcommits.org): `type(scope): summary`.
5. Open a pull request and fill in the template, including what you verified and how AI was used.
   Pull requests are squash-merged: the title becomes the commit on `main` and an entry in the
   [release notes](CHANGELOG.md) (`cliff.toml` says how). Give it a Conventional Commit title, and
   write `feat` and `fix` titles for the people who use the apps.

## Using AI coding agents

[AGENTS.md](AGENTS.md) is the guide for agents (Claude Code reads it through `CLAUDE.md`), and
`.claude/skills/` holds procedures for verifying a change, cutting a release and triaging an issue.
They point to the scripts and docs rather than repeating them, so they stay true as the code
changes. You are responsible for what you submit: read the diff, run the checks yourself, and say in
the pull request what the agent did.

## Licence

By contributing you agree that your contribution is dual-licensed under Apache 2.0 and MIT, like the
rest of Brasscribe ([LICENSE](LICENSE)).
