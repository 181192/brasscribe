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
    monkeypatch.setattr(licences, "gradle_modules", lambda: ["androidx.core:core-ktx", "org.example:new-library"])
    monkeypatch.setattr(licences, "nuget_packages", lambda: ["AlphaTab", "New.Package"])
    monkeypatch.setattr(licences, "locked_crates", lambda: sorted([*json.loads((ROOT / "licences/cargo.json").read_text())["crates"], "new-crate"]))
    found = "\n".join(licences.problems())
    assert "org.example:new-library" in found and "New.Package" in found and "new: new-crate" in found
    assert "androidx.core:core-ktx" not in found and "AlphaTab (" not in found
