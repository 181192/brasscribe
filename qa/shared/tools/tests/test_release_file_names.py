"""The file an app links to when it needs an update is a file the release workflows make: a renamed file in a
workflow, or a new name in an app, fails here and not as a broken link in a released app."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WORKFLOWS = ROOT / ".github/workflows"


def names(pattern: str, *files: str) -> set[str]:
    found = {n for f in files for n in re.findall(pattern, (ROOT / f).read_text(encoding="utf-8"))}
    assert found, f"no file name found in {', '.join(files)}: the test no longer reads where the names are"
    return found


def test_the_android_apps_link_to_the_apks_the_workflow_signs():
    workflow = (WORKFLOWS / "android.yml").read_text(encoding="utf-8")
    link = (ROOT / "apps/android/features/play/src/main/kotlin/no/kalli/scribe/play/ui/GetBandroom.kt").read_text(encoding="utf-8")
    stems = names(r'releaseFile = "([^"]+)"',
                  "apps/android/products/brasscribe/src/main/kotlin/no/kalli/brasscribe/Brasscribe.kt",
                  "apps/android/products/fretscribe/src/main/kotlin/no/kalli/fretscribe/Fretscribe.kt")
    assert len(stems) == 2
    for stem in stems:
        assert f'out="$RUNNER_TEMP/out/{stem}-$a.apk"' in workflow, stem
    # The two kinds the link chooses between are the two the workflow builds.
    assert "for a in arm64-v8a universal; do" in workflow
    assert '"arm64-v8a" else "universal"}.apk' in link


def test_the_mac_apps_and_bandroom_link_to_the_archives_the_workflow_makes():
    workflow = (WORKFLOWS / "apple.yml").read_text(encoding="utf-8")
    linked = names(r"[a-z-]+-macos-arm64\.zip", "apps/apple/products/brasscribe/App/AppModel.swift",
                   "apps/apple/products/fretscribe/App/FretscribeModel.swift",
                   "apps/bandroom/macos/Packages/BandroomKit/Sources/BandroomKit/Wire.swift")
    assert len(linked) == 3
    for name in linked:
        assert f'"$RUNNER_TEMP/out/{name}"' in workflow, name


def test_the_windows_apps_and_bandroom_link_to_the_archives_the_workflow_makes():
    workflow = (WORKFLOWS / "windows.yml").read_text(encoding="utf-8")
    linked = names(r"[a-z-]+-windows-x64\.zip", "apps/windows/products/brasscribe/Kalli.Brasscribe/Product.cs",
                   "apps/windows/products/fretscribe/Kalli.Fretscribe/Product.cs",
                   "apps/bandroom/windows/src/Brasscribe.Bandroom.Core/Engine/Wire.cs")
    assert len(linked) == 3
    for name in linked:
        assert f'/out/{name}"' in workflow, name
