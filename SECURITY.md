# Security

## Reporting a vulnerability

Please report it privately through GitHub:
[Report a vulnerability](https://github.com/181192/brasscribe/security/advisories/new). Don't open a
public issue. Say what's affected (app, platform, version), how to reproduce it and what an attacker
could do.

## What is in scope

- The apps (Brasscribe Play, Bandroom), the engine and its HTTP API, pairing between devices,
  Studio, `brasscribe-core`, and the release files on GitHub.
- The build and release workflows in `.github/workflows/`.

The latest release is the one that gets fixes.

## How the project checks itself

- CodeQL analyses the code and the workflows on every push to `main`, weekly, and on pull requests
  for the languages the pull request changes (`security.yml`). Pushes to other branches are not scanned
  until they are in a pull request.
- Dependabot opens updates for vulnerable and outdated dependencies (`.github/dependabot.yml`), and
  pull requests that add a dependency with a known high-severity vulnerability fail.
- GitHub secret scanning with push protection blocks committed keys and tokens.
- Release files have SHA-256 checksums in `SHA256SUMS`; the Android APKs are signed with the same key
  every release.
