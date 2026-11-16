"""scripts/licences.py: the licence files the apps ship are what the list gives, and a dependency outside the list is noticed."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("licences", ROOT / "scripts/licences.py")
licences = importlib.util.module_from_spec(spec)
spec.loader.exec_module(licences)


def test_the_committed_files_are_current_and_every_dependency_is_listed():
    assert licences.problems() == []


def test_a_crate_with_a_choice_is_used_under_apache_and_every_and_part_counts():
    assert licences.used_under("MIT OR Apache-2.0") == ["Apache-2.0"]
    assert licences.used_under("MIT/Apache-2.0") == ["Apache-2.0"]
    assert licences.used_under("Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT") == ["Apache-2.0"]
    assert licences.used_under("Unlicense OR MIT") == ["MIT"]
    assert licences.used_under("(MIT OR Apache-2.0) AND Unicode-3.0") == ["Apache-2.0", "Unicode-3.0"]
    assert licences.used_under("Zlib") == ["Zlib"]


def test_a_text_is_reflowed_by_paragraph_and_list_item_without_losing_a_word():
    text = "  TITLE\n   Version 1\n\nOne line that\nruns on.\n\n1. first item\n   goes on\n2. second\n(a) third\n"
    flowed = licences.reflow(text)
    assert flowed == "TITLE Version 1\n\nOne line that runs on.\n\n1. first item goes on\n2. second\n(a) third"
    for name in sorted((ROOT / "licences/texts").glob("*.txt")):
        original = name.read_text(encoding="utf-8")
        assert licences.reflow(original).split() == original.split(), name.name


def test_every_app_file_carries_the_text_of_each_licence_it_names():
    m = licences.manifest()
    for path, text in licences.build().items():
        app = path.stem
        for c in m["components"]:
            if app in c["apps"]:
                assert f"\n{c['name']}\n{c['url']}\n" in text, (app, c["id"])
                for t in c["texts"]:
                    assert f"\nLicence text: {t}\n" in text, (app, c["id"], t)


def test_a_new_dependency_that_is_in_neither_list_is_reported(monkeypatch):
    monkeypatch.setattr(licences, "gradle_modules", lambda: {"androidx.core:core-ktx": "catalogue", "org.example:new-library": "catalogue"})
    monkeypatch.setattr(licences, "nuget_packages", lambda: {"AlphaTab": "apps/windows", "New.Package": "apps/bandroom/windows/Directory.Packages.props"})
    monkeypatch.setattr(licences, "locked_crates", lambda: sorted([*json.loads((ROOT / "licences/cargo.json").read_text())["crates"], "new-crate"]))
    found = "\n".join(licences.problems())
    assert "org.example:new-library" in found and "New.Package" in found and "new: new-crate" in found
    assert "androidx.core:core-ktx" not in found and "AlphaTab (" not in found
    assert "New.Package (apps/bandroom/windows/Directory.Packages.props)" in found


def test_a_published_notice_file_follows_the_version_the_build_names(monkeypatch, tmp_path):
    m = licences.manifest()
    text = licences.build()[licences.DIST / "brasscribe-android.txt"]
    (_, path), = licences.upstream_files("brasscribe-android", m)
    assert path.exists() and "\nNotices published with ONNX Runtime\n" in text
    assert licences.upstream_files("fretscribe-android", m) == []
    # A new version in the build asks for that version's file.
    pin = tmp_path / "libs.versions.toml"
    pin.write_text('onnxruntime = "9.9.9"\n')
    monkeypatch.setattr(licences, "ROOT", tmp_path)
    for c in m["components"]:
        for u in c.get("upstream", []):
            u["version_in"] = "libs.versions.toml"
            u["version_is"] = '^onnxruntime = "([^"]+)"'
    (_, path), = licences.upstream_files("brasscribe-android", m)
    assert path.name == "onnxruntime-9.9.9-ThirdPartyNotices.txt"


def assets(tmp_path, app, *packages):
    """A restore's project.assets.json that resolved these packages (and a project of the app's own)."""
    libraries = {f"{p}/1.0.0": {"type": "package"} for p in packages} | {"Kalli.Scribe.Services/1.0.0": {"type": "project"}}
    path = tmp_path / app / "project.assets.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"libraries": libraries}), encoding="utf-8-sig")  # NuGet writes it with a BOM
    return path


def test_a_package_that_comes_along_with_another_is_checked_for_the_app_that_takes_it(monkeypatch, tmp_path):
    monkeypatch.setattr(licences, "NUGET_RESTORED", {
        # Windows ML and WebView2 come with the Windows App SDK; System.Text.Brand.New with nothing listed
        "brasscribe-windows": assets(tmp_path, "play", "Microsoft.WindowsAppSDK", "Microsoft.WindowsAppSDK.WinUI",
                                     "Microsoft.Windows.AI.MachineLearning", "Microsoft.Web.WebView2",
                                     "Microsoft.Windows.SDK.BuildTools.MSIX", "System.Text.Brand.New"),
        # DirectML's own package is listed for Play for Windows only
        "fretscribe-windows": assets(tmp_path, "fretscribe", "Microsoft.WindowsAppSDK", "Microsoft.AI.DirectML"),
        "bandroom-windows": tmp_path / "not-restored" / "project.assets.json",
    })
    found = "\n".join(licences.problems(["brasscribe-windows", "fretscribe-windows"]))
    assert "System.Text.Brand.New (taken by brasscribe-windows" in found
    assert "Microsoft.AI.DirectML (taken by fretscribe-windows" in found and "add fretscribe-windows to the apps of directml" in found
    for covered in ("Microsoft.WindowsAppSDK.WinUI", "Microsoft.Windows.AI.MachineLearning", "Microsoft.Web.WebView2",
                    "Microsoft.Windows.SDK.BuildTools.MSIX", "Kalli.Scribe.Services"):
        assert covered not in found
    # Without --restored the restores are not read; an app named whose restore is not there is said, not skipped.
    assert "System.Text.Brand.New" not in "\n".join(licences.problems())
    assert "restore bandroom-windows first" in "\n".join(licences.problems(["bandroom-windows"]))


def test_check_takes_restored_apps_and_nothing_else(monkeypatch):
    seen = []
    monkeypatch.setattr(licences, "problems", lambda restored=None: seen.append(restored) or [])
    assert licences.main(["licences.py", "check"]) == 0
    assert licences.main(["licences.py", "check", "--restored", "brasscribe-windows", "bandroom-windows"]) == 0
    assert licences.main(["licences.py", "check", "brasscribe-windows"]) == 2
    assert seen == [None, ["brasscribe-windows", "bandroom-windows"]]
