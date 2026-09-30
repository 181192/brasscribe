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
  for the languages the pull request changes (`security.yml`). Pushes to other branches are not
  scanned until they are in a pull request. Swift is not analysed: CodeQL needs a full Xcode build.
- Dependabot alerts on and updates vulnerable and outdated dependencies (`.github/dependabot.yml`);
  the Android (Gradle) dependencies reach it through `dependencies.yml`, which submits only the
  release runtime classpaths (what ships in the APK and the core's AAR), not the build tooling.
  The model-conversion environments under `convert/` run on developers' machines only and are pinned
  on purpose, so Dependabot opens no pull requests for them. Pull requests that change
  dependencies get a dependency review, which flags any with a known high-severity vulnerability.
  The Python environment (`pixi.lock`) is not covered by Dependabot; it is updated with `pixi update`.
- GitHub secret scanning with push protection blocks committed keys and tokens.
- The Android release key can only be used by release builds from `v*` tags. Release files have
  SHA-256 checksums in `SHA256SUMS`, and the Android APKs are signed with the same key every release.
