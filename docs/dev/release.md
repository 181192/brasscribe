# Cutting a release

Releases are built by hand on an Apple silicon Mac and published with `gh`. CI does not build them:
a `v*` tag starts `.github/workflows/release.yml`, but on this account it stops within seconds with
every job skipped (billing), so the tag is harmless. v0.1.0 and v0.2.0 were made this way.

What a release ships:

| Asset | What |
|---|---|
| `brasscribe-play-android-arm64-v8a.apk` | Play for Android, most devices |
| `brasscribe-play-android-universal.apk` | Play for Android, all CPU types |
| `brasscribe-play-macos-arm64.zip` | Play for Mac (Apple silicon), ad-hoc signed |
| `brasscribe-bandroom-macos-arm64.zip` | Bandroom for Mac, ad-hoc signed, with `pixi` inside |
| `brasscribe-core-macos-arm64.zip` | the `brasscribe-core` command-line tool |
| `SHA256SUMS` | checksums of the files above |

No Windows or iPhone/iPad build yet. Windows Play is built and tested in the Windows VM (§5a), but it
does not ship until [the Windows checklist](windows-checklist.md) has passed on a real PC. iOS needs
an Apple Developer account.

Below, `$S` is a scratch directory (DerivedData, staging) and `$OUT` the directory of finished assets.
Disk is tight on the build Mac: keep DerivedData in `$S`, and delete staging directories and unshipped
APKs once the assets are uploaded.

## 1. A clean worktree and the version bump

Build from a fresh worktree of `origin/main`, never from the main checkout. Gitignored leftovers there
get staged into the app (a stray band SoundFont under `engine/src/brasscribe_engine/static/assets/band`
once grew Bandroom from 118 MB to 181 MB).

```sh
git worktree add --detach .claude/worktrees/release-X.Y.Z origin/main
cd .claude/worktrees/release-X.Y.Z
eval "$(scripts/worktree-setup.sh)"        # links data/ (band sounds), models/, Verovio; installs the core
python3 sounds/tools/band_sounds.py verify # the pinned band pack is in data/sounds/band
```

Bump the version in its own commit and push it to main **before** building, because Bandroom's
workspace stamp records the commit it was built from:

- `apps/android/app/build.gradle.kts`: `versionCode` + 1, `versionName`
- `apps/apple/project.yml` and `apps/bandroom/macos/project.yml`: `MARKETING_VERSION`, `CURRENT_PROJECT_VERSION`
- Leave the core's Cargo version alone: the fixtures embed `brasscribe-core 0.1.0` in their MusicXML.

Commit as `chore(release): X.Y.Z` and `git push origin HEAD:main`.

Recommended before building: tier 2 (`make check-all`, [verify.md](verify.md)) and, once per release, the
full macOS UI suite in the VM: `MAC_VM_FULL=1 scripts/mac-vm.sh test-ui` ([macos-vm.md](macos-vm.md)).

## 2. Android

```sh
cd apps/android && ./gradlew assembleRelease assembleDebug -q   # the debug APK is for the phone (§7)
```

This writes `app/build/outputs/apk/release/app-{arm64-v8a,universal,x86_64}-release-unsigned.apk`
(one APK per ABI plus a universal one; the x86_64 one is not shipped). Signing is not in Gradle. It is
done by hand with the build tools and the key in `~/.brasscribe/release-keys`
(`brasscribe-release.jks`, alias `brasscribe`, and `keystore-password.txt`). **Every release must use
this key**, or it will not install over the previous one. Keep a backup of both files. Never print the
password, and pass it as `file:`, not `pass:`, so it stays out of the process list.

```sh
BT=$(ls -d "$ANDROID_HOME"/build-tools/* | tail -1); K=~/.brasscribe/release-keys
for a in arm64-v8a universal; do
  "$BT/zipalign" -f -p 4 "app/build/outputs/apk/release/app-$a-release-unsigned.apk" "$S/tmp.apk"
  "$BT/apksigner" sign --ks "$K/brasscribe-release.jks" --ks-pass "file:$K/keystore-password.txt" \
    --out "$OUT/brasscribe-play-android-$a.apk" "$S/tmp.apk"
  "$BT/apksigner" verify "$OUT/brasscribe-play-android-$a.apk"
done
rm -f "$S/tmp.apk" "$OUT"/*.idsig
```

Check each APK: `apksigner verify --print-certs` shows the same certificate SHA-256 as the previous
release's APK, `aapt2 dump badging` shows the new `versionCode`/`versionName`, and `unzip -l` lists
`brasscribe-band-mobile.sf2`.

## 3. Play for Mac

```sh
cd apps/apple && xcodegen generate
xcodebuild -project BrasscribePlay.xcodeproj -scheme BrasscribePlay-macOS -configuration Release \
  -destination 'generic/platform=macOS' -derivedDataPath "$S/dd-play" build
P="$S/stage/Brasscribe Play.app"
ditto "$S/dd-play/Build/Products/Release/BrasscribePlay.app" "$P"
test -s "$P/Contents/Resources/Sounds/brasscribe-band-16bit.sf2"
```

There is no signing identity, so the app is re-signed ad hoc, without the hardened runtime. An ad-hoc
signature has no Team ID, so under the hardened runtime and library validation the embedded
`Verovio.framework` is rejected and the app crashes at launch. Always re-sign, **inside out: Verovio
first, then the app**, keeping the app's own entitlements (sandbox, audio input, user-selected files,
network client):

```sh
codesign -d --entitlements - --xml "$P" > "$S/play.entitlements"
ls "$P/Contents/Frameworks" "$P/Contents/PlugIns" 2>/dev/null   # anything besides Verovio is signed before the app too
codesign --force --sign - "$P/Contents/Frameworks/Verovio.framework"
codesign --force --sign - --entitlements "$S/play.entitlements" "$P"
codesign --verify --deep --strict "$P"
codesign -d --entitlements - "$P" | grep -q app-sandbox
(cd "$S/stage" && ditto -c -k --keepParent "Brasscribe Play.app" "$OUT/brasscribe-play-macos-arm64.zip")
```

`make -C apps/apple install-mac` does the same build locally (hardened runtime off) and checks that the
installed app stays up. Without UI automation, a quick crash check is
`swift test --no-parallel --filter 'engineBuildsInASandboxedProcess|OutputStageTests'` in `apps/apple/Packages/BrasscribeKit`
(it starts the playback engine in a sandboxed process), then opening the app and looking for a new
`BrasscribePlay-*.ips` in `~/Library/Logs/DiagnosticReports`.

## 4. Bandroom for Mac

```sh
cd apps/bandroom/macos && xcodegen generate
xcodebuild -project BrasscribeBandroom.xcodeproj -scheme BrasscribeBandroom -configuration Release \
  -destination 'generic/platform=macOS' -derivedDataPath "$S/dd-band" build
```

The build's post-build scripts stage what the first run installs from:

- `scripts/stage-band-sounds.sh` copies `data/sounds/band/brasscribe-band-mobile.sf2` into
  `Resources/band/brasscribe-band.sf2`. A Release build fails without it.
- `scripts/stage-workspace.sh` copies the engine workspace (`pixi.toml`, `pixi.lock`, `engine`, `music`,
  the benchmark package, `ml/adapters` and the pinned MSST code, fetched once into `build/cache`, which
  needs the network) into `Resources/workspace`. Last, it writes the **workspace stamp**,
  `.brasscribe-workspace.json`: a hash of every staged file, a hash of `pixi.lock`, the short commit,
  the version and the build. On launch Bandroom compares it with the installed copy in
  `~/Library/Application Support/Brasscribe/envs`, swaps the workspace when they differ, and runs
  `pixi install` again only when the lock hash changed. Check that the stamp's commit is the release
  commit before shipping.

The app bundles `pixi`, so a Mac without it can install the engine. Bandroom takes `BRASSCRIBE_PIXI` when set,
then the bundled `Contents/Resources/bin/pixi`, then `~/.pixi/bin` and Homebrew. Copy it in,
then re-sign **pixi first, then the app**:

```sh
B="$S/stage/Brasscribe Bandroom.app"
ditto "$S/dd-band/Build/Products/Release/Brasscribe Bandroom.app" "$B"
mkdir -p "$B/Contents/Resources/bin"
cp -L "$(command -v pixi)" "$B/Contents/Resources/bin/pixi" && chmod 755 "$B/Contents/Resources/bin/pixi"
codesign -d --entitlements - --xml "$B" > "$S/band.entitlements"
codesign --force --sign - "$B/Contents/Resources/bin/pixi"
codesign --force --sign - --entitlements "$S/band.entitlements" "$B"
codesign --verify --deep --strict "$B"
(cd "$S/stage" && ditto -c -k --keepParent "Brasscribe Bandroom.app" "$OUT/brasscribe-bandroom-macos-arm64.zip")
```

**The keychain prompt.** Each ad-hoc re-sign gives the app a new signature, so on the first launch
after an update macOS asks once whether Bandroom may read its saved Hugging Face key (the Mac password,
then Always Allow). Bandroom reads the key in the background: the engine starts without it and
restarts once the key is read. Keep the line about this prompt in the release notes until the apps
have a real signing identity.

After installing, `curl -s 127.0.0.1:<port>/v1/health` (Bandroom takes the first free port of 8765–8775) reports the running engine's `build`, which should
start with the release commit. Its `version` is the engine API version, not the app's.

## 5. The core command-line tool

```sh
cd core && cargo build --release --locked -p brasscribe-cli
(cd target/release && zip -q "$OUT/brasscribe-core-macos-arm64.zip" brasscribe-core)
```

## 5a. Windows (built, not shipped yet)

The Windows artifacts are built in the headless Windows 11 ARM64 VM on the build Mac
([windows-vm.md](windows-vm.md)), from the same release worktree:

```sh
scripts/win-vm.sh test       # the .NET tests, the smoke tests and the Axe.Windows scans of Play and Bandroom
scripts/win-vm.sh release    # Play, self-contained, for x64 and ARM64, as the CI release job makes it
```

`release` builds `brasscribe_ffi.dll` for both architectures, publishes Play with
`dotnet publish -r win-<arch> --self-contained` (.NET and the Windows App SDK inside, the 16-bit band
SoundFont bundled), and checks that the exe, the DLL and the SoundFont are in it. It writes
`build/win-vm/release-<time>/brasscribe-play-windows-{x64,arm64}.zip`. The zips are unsigned:
SmartScreen warns on first start until the app has a code-signing certificate.

Don't upload them yet. Once the checklist has passed, copy the zips to `$OUT` before §6, so they get
into `SHA256SUMS`, and add the install note for Windows (More info › Run anyway) to the release notes.

## 6. Checksums and the GitHub release

```sh
(cd "$OUT" && shasum -a 256 *.apk *.zip > SHA256SUMS)
```

Just before publishing, check that `git rev-parse origin/main` is still the commit you built. If main
has moved, pass the built commit's **full** 40-character SHA as the target (a short SHA fails):

```sh
gh release create vX.Y.Z "$OUT"/* --target main --title "vX.Y.Z" --notes-file notes.md
gh release view vX.Y.Z --json assets     # every asset "uploaded", digests matching SHA256SUMS
```

This creates the tag on GitHub. Don't push tags or dispatch workflows yourself. Release notes follow
the site's rules: plain words, no internal names, no model names outside the research page (the band
writer's CC BY-NC 4.0 notice stays), and the install notes (Android: allow installs, it updates in place;
Mac: System Settings › Privacy & Security › Open Anyway (right-click › Open no longer bypasses Gatekeeper since macOS 15), the one-time keychain prompt, Bandroom's first run of about 10 GB and its
Hugging Face key). See `gh release view v0.2.0` for the shape.

## 7. Installing on the owner's devices

- **Mac.** Quit both apps (`osascript -e 'quit app "BrasscribePlay"'`, `… "Brasscribe Bandroom"`), wait
  until they are gone and Bandroom's port is free, replace `/Applications/Brasscribe Play.app` and
  `/Applications/Brasscribe Bandroom.app` with the staged ones (`ditto`), and open Bandroom. Take a file
  listing of `~/Library/Containers/no.brasscribe.play` and `~/Library/Application Support/Brasscribe`
  (without `envs/` and `logs/`) before and after, to show the user's data is untouched.
- **The phone.** It carries the **debug**-signed app, so it gets the debug APK
  (`adb install -r app/build/outputs/apk/debug/app-arm64-v8a-debug.apk`). A release APK would need an
  uninstall first. **Never uninstall the app**: that deletes the user's scores.

## 8. The site

The site is served from the `gh-pages` branch (Pages in legacy branch mode, `gh-pages` at `/`, at
kalli.no/brasscribe). `.github/workflows/pages.yml` would deploy it on a push to main, but it stops on
billing like the other workflows, so the site is published by hand:

```sh
bash site/build.sh                                            # site/_site
git clone --depth 1 -b gh-pages https://github.com/181192/brasscribe.git "$S/ghpages"
cd "$S/ghpages" && find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R "$W/site/_site/." . && git add -A
git commit -m "docs(site): …" && git push origin gh-pages     # never force: other site updates land here too
gh api repos/181192/brasscribe/pages/builds/latest
```

`$W` is the release worktree. The site and the READMEs never name a version: they link to
`releases/latest` and to `releases/latest/download/<file>`, so a release needs no text changes there.
Keep the asset file names stable (no version in them) for those links to keep working.
`site/build.sh` fails if a pinned release link or version number creeps back in.

## 9. The band sounds: a separate pre-release

The band SoundFonts are not in git and not in the app releases. They are a pre-release of their own,
pinned in `sounds/band-sounds.json` ([sounds/README.md](../../sounds/README.md)):

1. Build the pack into `data/sounds/band`: `uv run --project sounds python sounds/band.py --bits 16
   -o data/sounds/band/brasscribe-band-16bit.sf2`, then
   `uv run --project sounds python apps/android/scripts/mobile_soundfont.py` for
   `brasscribe-band-mobile.sf2`. Run the sound checks in [sounds/README.md](../../sounds/README.md) first.
2. `python3 sounds/tools/band_sounds.py pin --version sounds-YYYY.MM.DD` rewrites the pin and
   `SHA256SUMS` (`--dir DIR` for a pack built elsewhere).
3. `gh release create sounds-YYYY.MM.DD --prerelease data/sounds/band/brasscribe-band-16bit.sf2 data/sounds/band/brasscribe-band-mobile.sf2 data/sounds/band/SHA256SUMS`.
   A `sounds-*` tag starts no workflow (only `v*` tags do).
4. Commit the pin, with the sources and licences in [sounds/LICENSES.md](../../sounds/LICENSES.md).
   Every checkout then runs `pixi run fetch-sounds` (or `band_sounds.py fetch`) to get the new pack.

The current pack is `sounds-2026.09.30`. An app release bundles whatever pack is pinned on the commit it
is built from.

## 10. Goldens are promoted at merge, never before

`data/` (goldens, runs, band sounds) is one directory, linked into every worktree by
`scripts/worktree-setup.sh`. Re-saving `data/golden/mikkel-arranged-band` from a branch changes it for
main and for every other worktree at once, and their golden checks go red. So a branch that changes
the golden output:

- writes it to a sibling directory (for example `mikkel-arranged-band.fast-notes`), with a manifest of
  the commit that built it, and points its tests at that sibling through one constant per platform;
- at merge, and only then, moves the old golden to `data/golden-backups/before-<change>/`, renames the
  sibling to `mikkel-arranged-band`, and reverts the paths in the same commit
  (`chore: promote the … golden`).
