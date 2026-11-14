# Cutting a release

Releases are built by CI, one product at a time. Each product has its own version, tags and changelog:

| Product | Tag | What its release holds |
|---|---|---|
| `brasscribe` | `brasscribe-vX.Y.Z` | Brasscribe Play for Android, Mac, iPhone and iPad, and Windows |
| `fretscribe` | `fretscribe-vX.Y.Z` | Fretscribe for Android, Mac, iPhone and iPad, and Windows |
| `bandroom` | `bandroom-vX.Y.Z` | Bandroom for Mac and for Windows, with the engine inside (the engine has no version of its own) |
| `scribe-core` | `scribe-core-vX.Y.Z` | the `scribe-core` command-line tool, per system |

`main` takes changes only through pull requests, so a release takes two steps, both in `scripts/release.sh`
(on an up-to-date `main`):

```sh
scripts/release.sh --preview PRODUCT      # the notes the product's next release would get
scripts/release.sh PRODUCT X.Y.Z          # bump its versions, add to changelogs/PRODUCT.md, open the release pull request
scripts/release.sh --tag PRODUCT X.Y.Z    # once it is merged and pulled: tag the release commit and push the tag
```

The script bumps the product's version and build number (the files are in the script's `product` table) and adds the
release to the product's changelog with git-cliff (`cliff.toml`). The notes list the changes that reach the
product: its own code and the shared layers it is built from (the paths are in the same table). Pick the version
from the preview: a `feat` since the product's last release means a minor bump, only fixes a patch bump.
Pre-releases (`PRODUCT-vX.Y.Z-beta.N`) are tagged by hand on `main`; the script makes only `X.Y.Z`. If a run stops
halfway, `git switch main`, delete the local `release/PRODUCT-vX.Y.Z` branch, and start again.

A product's first release under its own tag takes a version above 0.14.0, the last release of everything together
(`v0.14.0`), and its notes count from there. Android needs it: an app installs only over a lower `versionCode`, and
both apps had 20 in that release. `CHANGELOG.md` is the history up to that release; `changelogs/PRODUCT.md` goes on
from it. App and engine must still match (the interface version): a change that raises the number is released for
Bandroom and for every app it breaks, one release each.

The script runs in the main checkout (a worktree cannot be on `main`). The pushed tag starts `.github/workflows/release.yml`: the checks, the product's builds, then a GitHub release
named after the product with its files, `SHA256SUMS` and notes generated from the commits since the product's
previous release (new features and fixes sorted and labelled by scope, the rest folded away, first-time
contributors named). Pull requests are squash-merged, so each pull request's title is one entry in
the notes: write them for the people who use the apps. If a tag push does not start the workflow, start it on the
tag: `gh workflow run release.yml --ref PRODUCT-vX.Y.Z`.

After a full release the workflow puts the same files in the release `PRODUCT-latest` (`scripts/latest-release.sh`),
so a link never names a version: a product's page is `releases/tag/PRODUCT-latest` and a file is
`releases/download/PRODUCT-latest/<file>`. That release is changed in place, never deleted, and only a product's
highest full release is put there (a pre-release, or a run started again for an older tag, leaves it alone). The
site, the READMEs and the apps' own update links all use these two addresses. The repository's one "latest" release
(`releases/latest`) is Bandroom's highest full release, by the same rule: apps from before the products had releases of their own send people there
for Bandroom, and every release's notes name the newest of each app.

Once, before the first release of each product: `scripts/latest-release.sh --seed v0.14.0` makes the four
`PRODUCT-latest` releases from the files of the last release of everything together, so the links work from the day
they are merged.

The file names are part of the links: `scripts/release.sh --files PRODUCT` lists a product's, and the workflow
publishes exactly those (a file that was not built stops the release before anything is published).

The Android APKs are signed in CI with the release key, held in the secrets of the `release`
environment (`ANDROID_KEYSTORE_B64`, `ANDROID_KEYSTORE_PASSWORD`), which only the release tags may use (its
deployment tag rule is the repository owner's to set: `brasscribe-v*` and `fretscribe-v*`); the
job checks the certificate
against the one every earlier release used. Fretscribe's APKs are signed in the same job with a key
of their own, shared with other prototype apps (`PROTOTYPES_KEYSTORE_B64`,
`PROTOTYPES_KEYSTORE_PASSWORD`, alias `prototypes`), and the job fails if an APK carries the other
app's certificate. The Mac apps are re-signed ad hoc (there is no Apple
Developer ID), and the Windows builds are not signed. The sections below are the local build, kept
for when CI cannot be used; v0.1.0 to v0.3.0 were made that way.

What the releases ship, each file in its product's release:

| Asset | What |
|---|---|
| `brasscribe-play-android-arm64-v8a.apk` | Play for Android, most devices |
| `brasscribe-play-android-universal.apk` | Play for Android, all CPU types |
| `fretscribe-android-arm64-v8a.apk` | Fretscribe for Android, most devices |
| `fretscribe-android-universal.apk` | Fretscribe for Android, all CPU types |
| `brasscribe-play-macos-arm64.zip` | Play for Mac (Apple silicon), ad-hoc signed |
| `brasscribe-play-ios-unsigned.ipa` | Play for iPhone and iPad, unsigned: a tester signs it with their own Apple account |
| `fretscribe-macos-arm64.zip` | Fretscribe for Mac (Apple silicon), ad-hoc signed |
| `fretscribe-ios-unsigned.ipa` | Fretscribe for iPhone and iPad, unsigned, as Play's |
| `brasscribe-bandroom-macos-arm64.zip` | Bandroom for Mac, ad-hoc signed, with `pixi` and `scribe-core` inside |
| `brasscribe-bandroom-windows-x64.zip` | Bandroom for Windows, self-contained, with `pixi` and `scribe-core` inside |
| `brasscribe-play-windows-x64.zip` | Play for Windows, self-contained (preview) |
| `fretscribe-windows-x64.zip` | Fretscribe for Windows, self-contained (preview). Built in a job of its own: if it fails, the release goes out without it |
| `scribe-core-*` | the `scribe-core` command-line tool, per OS |
| `SHA256SUMS` | checksums of the files above |

Bandroom is how the engine is installed: it bundles the engine workspace and `pixi`, and the first run
sets up the engine. The iPhone and iPad app cannot be signed for others without an Apple Developer
account, so it ships unsigned (`apps/apple/scripts/make-ipa.sh`, job `ios` in apple.yml): see
[apps/apple/README.md](../../../apps/apple/README.md#iphone-and-ipad-test-build). To build only the Apple
assets from a branch, without a release: `gh workflow run apple.yml -f release=true --ref <branch>`.

Below, `$S` is a scratch directory (DerivedData, staging) and `$OUT` the directory of finished assets.
Disk is tight on the build Mac: keep DerivedData in `$S`, and delete staging directories and unshipped
APKs once the assets are uploaded.

## 1. A clean worktree and the version bump

Build from a fresh worktree of `origin/main`, never from the main checkout. Gitignored leftovers there
get staged into the app (a stray band SoundFont under `engine/src/scribe_engine/static/assets/band`
once grew Bandroom from 118 MB to 181 MB).

```sh
git worktree add --detach .claude/worktrees/release-X.Y.Z origin/main
cd .claude/worktrees/release-X.Y.Z
eval "$(scripts/worktree-setup.sh)"        # links data/ (band sounds), models/, Verovio; installs the core
python3 sounds/tools/band_sounds.py verify # the pinned band pack is in data/sounds/band
python3 convert/models_pack.py fetch       # the pinned on-device models are in models/converted (§9b)
```

Bump the product's version in its own commit and push it to main **before** building, because Bandroom's
workspace stamp records the commit it was built from. Each product's version is in its own files:

- Brasscribe Play: `apps/android/products/brasscribe/build.gradle.kts` (`versionCode` + 1, `versionName`, the ones in `defaultConfig`), `apps/apple/products/brasscribe/project.yml` (`MARKETING_VERSION`, `CURRENT_PROJECT_VERSION` + 1), `apps/windows/products/brasscribe/Kalli.Brasscribe/Kalli.Brasscribe.csproj` (`<Version>`)
- Fretscribe: the same three under `products/fretscribe`
- Bandroom: `apps/bandroom/macos/project.yml` and `apps/bandroom/windows/Directory.Build.props`
- scribe-core: none. Leave the core's Cargo version alone: the fixtures embed `scribe-core 0.1.0` in their MusicXML. Its tag is its version.

Commit as `chore(release): PRODUCT X.Y.Z` and merge it through a pull request (`scripts/release.sh PRODUCT X.Y.Z` does this part).

Recommended before building: tier 2 (`make check-all`, [verify.md](verify.md)) and, once per release, the
full macOS UI suite in the VM: `MAC_VM_FULL=1 scripts/mac-vm.sh test-ui` ([macos-vm.md](macos-vm.md)).

## 2. Android

```sh
cd apps/android && ./gradlew assembleRelease assembleDebug -q   # the debug APK is for the phone (§7)
```

This writes `products/brasscribe/build/outputs/apk/release/brasscribe-{arm64-v8a,universal,x86_64}-release-unsigned.apk`
(one APK per ABI plus a universal one; the x86_64 one is not shipped). A release build stops when the
on-device models in `models/converted` are missing or not the pinned ones (`verifyModelAssets`; fetch them as in §1;
`-Pbrasscribe.allowNoModels` builds one without them, for a try-out only; refused when `CI` is set). Signing is not in Gradle. It is
done by hand with the build tools and the key in `~/.brasscribe/release-keys`
(`brasscribe-release.jks`, alias `brasscribe`, and `keystore-password.txt`). **Every release must use
this key**, or it will not install over the previous one. Keep a backup of both files. Never print the
password, and pass it as `file:`, not `pass:`, so it stays out of the process list.

```sh
BT=$(ls -d "$ANDROID_HOME"/build-tools/* | tail -1); K=~/.brasscribe/release-keys
for a in arm64-v8a universal; do
  "$BT/zipalign" -f -p 4 "products/brasscribe/build/outputs/apk/release/brasscribe-$a-release-unsigned.apk" "$S/tmp.apk"
  "$BT/apksigner" sign --ks "$K/brasscribe-release.jks" --ks-pass "file:$K/keystore-password.txt" \
    --out "$OUT/brasscribe-play-android-$a.apk" "$S/tmp.apk"
  "$BT/apksigner" verify "$OUT/brasscribe-play-android-$a.apk"
done
rm -f "$S/tmp.apk" "$OUT"/*.idsig
```

Check each APK: `apksigner verify --print-certs` shows the same certificate SHA-256 as the previous
release's APK, `aapt2 dump badging` shows the new `versionCode`/`versionName`, and `unzip -l` lists
`brasscribe-band-mobile.sf2` beside `assets/models/swift-f0-window.onnx`, `nmp-b1.onnx`, `beat-this-small0.onnx` and
`NOTICE.md`. `.github/scripts/release-models.py "$OUT"` checks the models of every file (§6).

`assembleRelease` also writes Fretscribe's APKs, to `products/fretscribe/build/outputs/apk/release/`
(`fretscribe-{arm64-v8a,universal,x86_64}-release-unsigned.apk`). They are signed the same way with
the prototypes key (alias `prototypes`), never with Brasscribe's, and are named
`fretscribe-android-{arm64-v8a,universal}.apk`. `.github/workflows/android.yml` has the certificate
digest of each key and what a Fretscribe APK must not carry (the band SoundFont, the models, sfizz).

## 3. Play for Mac

```sh
cd apps/apple/products/brasscribe && xcodegen generate
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
`swift test --no-parallel --filter 'engineBuildsInASandboxedProcess|OutputStageTests'` in `apps/apple/services`
(it starts the playback engine in a sandboxed process), then opening the app and looking for a new
`BrasscribePlay-*.ips` in `~/Library/Logs/DiagnosticReports`.

## 4. Bandroom for Mac

```sh
(cd core && MACOSX_DEPLOYMENT_TARGET=26.0 cargo build --release --locked -p scribe-cli)   # staged into the app below
cd apps/bandroom/macos && xcodegen generate
xcodebuild -project BrasscribeBandroom.xcodeproj -scheme BrasscribeBandroom -configuration Release \
  -destination 'generic/platform=macOS' -derivedDataPath "$S/dd-band" build
```

The build's post-build scripts stage what the first run installs from:

- `scripts/stage-band-sounds.sh` copies `data/sounds/band/brasscribe-band-mobile.sf2` into
  `Resources/band/brasscribe-band.sf2`. A Release build fails without it.
- `scripts/stage-core-cli.sh` copies the core's command line, `core/target/release/scribe-core`
  (the build above, for macOS 26 as Bandroom itself), into `Resources/bin/scribe-core`. Bandroom
  passes it to the installed engine as `SCRIBE_CORE_CLI`: the `bass-tab` profile runs it. A Release
  build fails without it.
- `scripts/stage-workspace.sh` copies the engine workspace (`pixi.toml`, `pixi.lock`, `engine`, `music`,
  the benchmark package, `ml/adapters` and the pinned MSST code, fetched once into `build/cache`, which
  needs the network) into `Resources/workspace`. Last, it writes the **workspace stamp**,
  `.scribe-workspace.json`: a hash of every staged file, a hash of `pixi.lock`, the short commit,
  the version and the build. On launch Bandroom compares it with the installed copy in
  `~/Library/Application Support/Brasscribe/envs`, swaps the workspace when they differ, and runs
  `pixi install` again only when the lock hash changed. Check that the stamp's commit is the release
  commit before shipping.

The pixi version CI installs, and so the one both Bandroom builds bundle, is pinned once, in
`.pixi-version` (read by `.github/actions/pixi` and `engine/Dockerfile`). `requires-pixi` in `pixi.toml` stays
the requirement; `check-bundled-pixi.sh` fails when the pin or a bundled pixi doesn't meet it, so raise the pin
first when the requirement goes up.

The app bundles `pixi`, so a Mac without it can install the engine. Bandroom takes `SCRIBE_PIXI` when set,
then the bundled `Contents/Resources/bin/pixi`, then `~/.pixi/bin` and Homebrew. Copy it in,
then re-sign **pixi and `scribe-core` first, then the app**:

```sh
B="$S/stage/Brasscribe Bandroom.app"
ditto "$S/dd-band/Build/Products/Release/Brasscribe Bandroom.app" "$B"
mkdir -p "$B/Contents/Resources/bin"
cp -L "$(command -v pixi)" "$B/Contents/Resources/bin/pixi" && chmod 755 "$B/Contents/Resources/bin/pixi"
scripts/check-bundled-pixi.sh "$B/Contents/Resources/bin/pixi"   # stops unless it and .pixi-version (what CI bundles) meet requires-pixi in pixi.toml
codesign -d --entitlements - --xml "$B" > "$S/band.entitlements"
"$B/Contents/Resources/bin/scribe-core" version    # staged by the build
codesign --force --sign - "$B/Contents/Resources/bin/pixi"
codesign --force --sign - "$B/Contents/Resources/bin/scribe-core"
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
cd core && cargo build --release --locked -p scribe-cli
tar -czf "$OUT/scribe-core-macos-arm64.tar.gz" -C target/release scribe-core
```

## 6. Checksums and the GitHub release

```sh
.github/scripts/release-models.py --require 'brasscribe-play-android-*.apk' "$OUT"   # exit 1 when an app lacks its models
(cd "$OUT" && shasum -a 256 -- * > SHA256SUMS)
```

`release-models.py` prints a table with a row for every file: the models inside and whether that is the set its app
must carry (the rules are in the script, the files' names and sha256 come from `convert/on-device-models.json`). Play
for Android must carry the three pinned ONNX files byte for byte and `NOTICE.md` (`convert/on-device-models-NOTICE.md`,
byte for byte); Play for Mac, iPhone and iPad the three Core ML models, compiled, and the same `NOTICE.md`;
Fretscribe and Play for Windows none. An APK or IPA that no rule names fails, and so does a missing
file named with `--require`. The release workflow
runs it on the downloaded files before it publishes. Never publish over a failure: a Play without its models sends
every solo to the computer.

Just before publishing, check that `git rev-parse origin/main` is still the commit you built. If main
has moved, pass the built commit's **full** 40-character SHA as the target (a short SHA fails):

```sh
gh release create PRODUCT-vX.Y.Z "$OUT"/* --target main --latest=false --title "<Product> X.Y.Z" --notes-file notes.md
gh release view PRODUCT-vX.Y.Z --json assets     # every asset "uploaded", digests matching SHA256SUMS
```

This creates the tag on GitHub. Don't push tags or dispatch workflows yourself. Release notes follow
the site's rules: plain words, no internal names, no model names outside the research page (the band
writer's CC BY-NC 4.0 notice stays), and the install notes (Android: allow installs, it updates in place;
Mac: System Settings › Privacy & Security › Open Anyway (right-click › Open does not bypass Gatekeeper), the one-time keychain prompt, Bandroom's first run of about 10 GB and its
Hugging Face key). See `gh release view v0.2.0` for the shape.

## 7. Installing on the owner's devices

- **Mac.** Quit both apps (`osascript -e 'quit app "BrasscribePlay"'`, `… "Brasscribe Bandroom"`), wait
  until they are gone and Bandroom's port is free, replace `/Applications/Brasscribe Play.app` and
  `/Applications/Brasscribe Bandroom.app` with the staged ones (`ditto`), and open Bandroom. Take a file
  listing of `~/Library/Containers/no.kalli.brasscribe` and `~/Library/Application Support/Brasscribe`
  (without `envs/` and `logs/`) before and after, to show the user's data is untouched.
- **The phone.** It carries the **debug**-signed app, so it gets the debug APK
  (`adb install -r products/brasscribe/build/outputs/apk/debug/brasscribe-debug.apk`; Fretscribe's is
  `products/fretscribe/build/outputs/apk/debug/fretscribe-debug.apk`). A release APK would need an
  uninstall first. **Never uninstall the app**: that deletes the user's scores. The apps' ids are `no.kalli.brasscribe`
  and `no.kalli.fretscribe`: a phone that still has an app under its old id (`no.brasscribe.play`, `no.fretscribe.play`)
  gets the new one installed beside it, not over it, and the old one keeps its scores until it is uninstalled.

## 8. The site

`.github/workflows/pages.yml` builds `site/` and deploys it with GitHub Pages (source: GitHub
Actions, at kalli.no/brasscribe) on every push to main that touches the site; start it by hand with
`gh workflow run pages.yml`. The site and the READMEs never name a version: they link to a product's
`PRODUCT-latest` release (`releases/tag/PRODUCT-latest`, `releases/download/PRODUCT-latest/<file>`), so a release
needs no text changes there.
Keep the asset file names stable (no version in them) for those links to keep working.
`site/build.sh` fails if a pinned release link or version number creeps back in.

## 9. The band sounds: a separate pre-release

The band SoundFonts are not in git and not in the app releases. They are a pre-release of their own,
pinned in `sounds/band-sounds.json` ([sounds/README.md](../../../sounds/README.md)):

1. Build the pack into `data/sounds/band`: `uv run --project sounds python sounds/band.py --bits 16
   -o data/sounds/band/brasscribe-band-16bit.sf2`, then
   `uv run --project sounds python apps/android/scripts/mobile_soundfont.py` for
   `brasscribe-band-mobile.sf2`. Run the sound checks in [sounds/README.md](../../../sounds/README.md) first.
2. `python3 sounds/tools/band_sounds.py pin --version sounds-YYYY.MM.DD` rewrites the pin and
   `SHA256SUMS` (`--dir DIR` for a pack built elsewhere).
3. `gh release create sounds-YYYY.MM.DD --prerelease data/sounds/band/brasscribe-band-16bit.sf2 data/sounds/band/brasscribe-band-mobile.sf2 data/sounds/band/SHA256SUMS`.
   A `sounds-*` tag starts no workflow (only the products' release tags do).
4. Commit the pin, with the sources and licences in [sounds/LICENSES.md](../../../sounds/LICENSES.md).
   Every checkout then runs `pixi run fetch-sounds` (or `band_sounds.py fetch`) to get the new pack.

The current pack is the `version` in `sounds/band-sounds.json`. An app release bundles whatever pack is
pinned on the commit it is built from.

## 9b. The on-device models: a separate pre-release

The models Play runs on the device (SwiftF0, Basic Pitch, Beat This small: Core ML packages for Mac,
iPhone and iPad, ONNX for Android) are not in git either. They are a pre-release of their own, pinned
in `convert/on-device-models.json`; a build that bundles them fetches them first
(`.github/actions/on-device-models` in CI, `python3 convert/models_pack.py fetch` by hand), and the
release builds of Play for Mac, iPhone and iPad stop without them:

1. Convert the models into `models/converted` and pass their parity gates ([convert/README.md](../../../convert/README.md)).
2. `python3 convert/models_pack.py pack --version models-YYYY.MM.DD` writes the pack's files,
   `SHA256SUMS` and `NOTICE.md` (each model's source and licence, from
   `convert/on-device-models-NOTICE.md`: keep it true) into `models/pack` and rewrites the pin.
   The pack's `NOTICE.md` is not pinned: the apps bundle the repository's file, not the release's copy.
   A Core ML package is a folder, so it is packed as a `.zip` that depends only on the folder's files.
3. `gh release create models-YYYY.MM.DD --prerelease models/pack/*`. A `models-*` tag starts no
   workflow (only `v*` tags do).
4. Commit the pin. A checkout runs `python3 convert/models_pack.py fetch` to get the pack, and
   `verify` to check `models/converted` against the pin.

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
