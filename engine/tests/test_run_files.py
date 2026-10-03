"""A finished run's files: how they are listed and what renaming a run changes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brasscribe_engine.api import create_app


def finished_run(settings, run_id: str, files: dict[str, str], title: str = "Old") -> None:
    d = settings.runs_dir / run_id
    (d / "outputs").mkdir(parents=True)
    for name, text in files.items():
        (d / "outputs" / name).parent.mkdir(parents=True, exist_ok=True)
        (d / "outputs" / name).write_text(text)
    manifest = {"run_id": run_id, "profile": "test", "title": title, "status": "succeeded",
                "created": "2026-01-02T03:04:05+00:00", "input": {"path": str(settings.uploads_dir / "a.wav")},
                "stages": []}
    (d / "manifest.json").write_text(json.dumps(manifest))


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def test_artifacts_are_listed_with_the_type_they_are_served_with(settings, client):
    finished_run(settings, "run-a", {"brass-band.pdf": "%PDF", "brass-band.brf": "x", "talking-score.html": "<p>",
                                     "talking-score.txt": "x", "parts/01-solo-cornet.pdf": "%PDF"})
    listed = {a["name"]: a["media_type"] for a in client.get("/v1/jobs/run-a/artifacts").json()}
    assert listed["brass-band.pdf"] == listed["parts/01-solo-cornet.pdf"] == "application/pdf"
    for name, media in listed.items():
        served = client.get(f"/v1/jobs/run-a/artifacts/{name}").headers["content-type"]
        assert served.split(";")[0] == media.split(";")[0], name


def test_rename_replaces_outputs_that_are_read_only_links_into_the_cache(settings, client, monkeypatch):
    import os
    import stat

    from brasscribe_engine import jobs
    from brasscribe_engine.cache import _read_only

    finished_run(settings, "run-a", {})
    cached = settings.cache_dir / "composition.json"
    cached.write_text(json.dumps({"title": "Old"}))
    _read_only(cached)
    os.link(cached, settings.runs_dir / "run-a" / "outputs" / "composition.json")
    replace = os.replace

    def like_windows(src, dst):  # Windows refuses to replace a read-only file
        if os.path.exists(dst) and not os.stat(dst).st_mode & stat.S_IWUSR:
            raise PermissionError(13, "Access is denied", str(dst))
        replace(src, dst)

    monkeypatch.setattr(jobs.os, "replace", like_windows)
    r = client.patch("/v1/runs/run-a", json={"title": "New"})
    assert r.status_code == 200
    assert client.get("/v1/jobs/run-a/composition").json()["title"] == "New"
    assert json.loads(cached.read_text()) == {"title": "Old"}


def test_rename_retitles_the_parts_and_the_talking_score(settings, client):
    from brasscribe_engine import talking_score

    doc = {"version": 1, "title": "Old", "total_bars": 0, "parts": []}
    finished_run(settings, "run-a", {
        "parts/01-solo-cornet.musicxml": "<score-partwise><work><work-title>Old</work-title></work></score-partwise>",
        "talking-score.json": json.dumps(doc), "talking-score.html": talking_score.to_html(doc),
        "talking-score.txt": talking_score.to_text(doc), "brass-band.brf": "OLD"})
    assert client.patch("/v1/runs/run-a", json={"title": "Psalm <100>"}).status_code == 200
    out = settings.runs_dir / "run-a" / "outputs"
    assert "<work-title>Psalm &lt;100&gt;</work-title>" in (out / "parts" / "01-solo-cornet.musicxml").read_text()
    assert json.loads((out / "talking-score.json").read_text())["title"] == "Psalm <100>"
    assert "<h1>Psalm &lt;100&gt;</h1>" in (out / "talking-score.html").read_text()
    assert (out / "talking-score.txt").read_text().startswith("Psalm <100>")
    assert "<h1>Psalm &lt;100&gt;</h1>" in client.get("/v1/jobs/run-a/talking-score").text
    assert (out / "brass-band.brf").read_text() == "OLD"  # no score MusicXML to make it again from


SCORE = "<score-partwise><work><work-title>Old</work-title></work></score-partwise>"


@pytest.fixture
def jobs(settings):
    from brasscribe_engine.jobs import JobManager

    manager = JobManager(settings)
    yield manager
    manager.shutdown()


def drain(jobs) -> None:
    """Wait for the renders queued so far (the render queue has one worker)."""
    jobs.render_pool.submit(lambda: None).result(timeout=10)


@pytest.fixture
def mscore(monkeypatch):
    """A MuseScore that writes the work title of what it renders, and records the style of each launch."""
    import re

    from brasscribe_music import musescore

    styles: list = []

    def convert_many(pairs, style=None, cancel=None):
        styles.append(style)
        for src, outs in pairs:
            title = re.search(r"<work-title>(.*?)</work-title>", Path(src).read_text()).group(1)
            for dst in [outs] if isinstance(outs, (str, Path)) else outs:
                Path(dst).parent.mkdir(parents=True, exist_ok=True)
                Path(dst).write_text(f"rendered {title}")
        return []

    monkeypatch.setattr(musescore, "binary", lambda: "mscore")
    monkeypatch.setattr(musescore, "convert_many", convert_many)
    return styles


def fake_braille(monkeypatch):
    from brasscribe_engine import braille

    monkeypatch.setattr(braille, "translate", lambda src: type("R", (), {"brf": "BRF " + Path(src).read_text()[-60:]})())


def test_rename_makes_the_pdfs_midi_and_braille_again_with_the_new_title(settings, jobs, mscore, monkeypatch):
    fake_braille(monkeypatch)
    finished_run(settings, "run-a", {"brass-band.musicxml": SCORE, "brass-band.pdf": "old", "brass-band.mid": "old",
                                     "brass-band.mp3": "old", "brass-band.brf": "old",
                                     "parts/01-solo-cornet.musicxml": SCORE, "parts/01-solo-cornet.pdf": "old",
                                     "parts/01-solo-cornet.brf": "old", "parts/02-flugel.musicxml": SCORE})
    assert jobs.rename("run-a", "New") == "renamed"
    drain(jobs)
    out = settings.runs_dir / "run-a" / "outputs"
    for name in ("brass-band.pdf", "brass-band.mid", "parts/01-solo-cornet.pdf"):
        assert (out / name).read_text() == "rendered New", name
    assert "New" in (out / "brass-band.brf").read_text() and "New" in (out / "parts" / "01-solo-cornet.brf").read_text()
    assert (out / "brass-band.mp3").read_text() == "old"  # the audio has no title
    assert not (out / "parts" / "02-flugel.pdf").exists()  # only what the run had
    assert mscore[0] is None and mscore[-1] is not None  # parts with the part style, as the export stage
    assert not list(out.rglob("*.tmp"))
    assert sorted(jobs.render_again("run-a", "New")) == [
        "brass-band.brf", "brass-band.mid", "brass-band.pdf", "parts/01-solo-cornet.brf", "parts/01-solo-cornet.pdf"]


def test_quick_renames_in_a_row_launch_musescore_once(settings, jobs, mscore):
    import threading

    finished_run(settings, "run-a", {"brass-band.musicxml": SCORE, "brass-band.pdf": "old"})
    hold = threading.Event()
    jobs.render_pool.submit(hold.wait, 10)  # the render queue is busy while the player types
    for i in range(6):
        assert jobs.rename("run-a", f"Title {i}") == "renamed"
    hold.set()
    drain(jobs)
    assert len(mscore) == 1
    assert (settings.runs_dir / "run-a" / "outputs" / "brass-band.pdf").read_text() == "rendered Title 5"


def test_a_render_for_a_title_the_run_no_longer_has_is_thrown_away(settings, jobs, mscore, monkeypatch):
    from brasscribe_music import musescore

    finished_run(settings, "run-a", {"brass-band.musicxml": SCORE, "brass-band.pdf": "old"})
    convert = musescore.convert_many

    def renamed_meanwhile(pairs, style=None, cancel=None):  # the next rename lands while MuseScore runs
        convert(pairs, style, cancel)
        monkeypatch.setattr(musescore, "convert_many", convert)
        assert jobs.rename("run-a", "Newer") == "renamed"
        return []

    monkeypatch.setattr(musescore, "convert_many", renamed_meanwhile)
    assert jobs.render_again("run-a", "Old") == []  # thrown away, not swapped in
    drain(jobs)  # the later rename's own render
    assert (settings.runs_dir / "run-a" / "outputs" / "brass-band.pdf").read_text() == "rendered Newer"


def test_a_run_deleted_while_it_renders_stays_deleted(settings, jobs, mscore, monkeypatch):
    from brasscribe_music import musescore

    finished_run(settings, "run-a", {"brass-band.musicxml": SCORE, "brass-band.pdf": "old"})
    convert = musescore.convert_many

    def deleted_meanwhile(pairs, style=None, cancel=None):
        convert(pairs, style, cancel)
        assert jobs.delete("run-a") == "deleted"
        return []

    monkeypatch.setattr(musescore, "convert_many", deleted_meanwhile)
    assert jobs.rename("run-a", "New") == "renamed"
    drain(jobs)
    assert not (settings.runs_dir / "run-a").exists()


def test_a_swap_that_fails_leaves_no_partial_file_and_none_is_listed(settings, jobs, mscore, monkeypatch):
    from brasscribe_engine import jobs as J

    finished_run(settings, "run-a", {"brass-band.musicxml": SCORE, "brass-band.pdf": "old", "brass-band.mid": "old"})
    replace = J.os.replace

    def disk_full(src, dst):
        if str(dst).endswith(".mid"):
            raise OSError(28, "No space left on device")
        replace(src, dst)

    monkeypatch.setattr(J.os, "replace", disk_full)
    assert jobs.render_again("run-a", "Old") == []
    out = settings.runs_dir / "run-a" / "outputs"
    assert not list(out.rglob("*.tmp")) and (out / "brass-band.mid").read_text() == "old"
    (out / "brass-band.pdf.tmp").write_text("half")  # a replacement being written
    assert "brass-band.pdf.tmp" not in jobs.outputs(jobs.get("run-a"))


def test_shutdown_stops_a_running_render_and_drops_the_queued_ones(settings, monkeypatch):
    import threading
    import time

    from brasscribe_engine.jobs import JobManager
    from brasscribe_music import musescore

    started, launches = threading.Event(), []

    def slow(pairs, style=None, cancel=None):  # a MuseScore that would take its whole timeout
        launches.append(1)
        started.set()
        if cancel.wait(30):
            raise musescore.Cancelled("killed")
        return []

    monkeypatch.setattr(musescore, "binary", lambda: "mscore")
    monkeypatch.setattr(musescore, "convert_many", slow)
    jobs = JobManager(settings)
    for run in ("run-a", "run-b"):
        finished_run(settings, run, {"brass-band.musicxml": SCORE, "brass-band.pdf": "old"})
        jobs.rename(run, "New")
    assert started.wait(10)
    begun = time.monotonic()
    jobs.shutdown()
    assert time.monotonic() - begun < 5 and launches == [1]
    assert (settings.runs_dir / "run-a" / "outputs" / "brass-band.pdf").read_text() == "old"


def test_a_renamed_tab_is_rendered_again_with_its_page_title(settings, jobs, mscore):
    from brasscribe_engine import bass_tab

    finished_run(settings, "run-t", {"tab.musicxml": SCORE, "tab.pdf": "old", "tab.mid": "old"})
    title = "A very long title " * 10
    assert jobs.rename("run-t", title) == "renamed"
    drain(jobs)
    assert (settings.runs_dir / "run-t" / "outputs" / "tab.pdf").read_text() == f"rendered {bass_tab.page_title(title).strip()}"
    assert sorted(jobs.render_again("run-t", title)) == ["tab.mid", "tab.pdf"]


def test_without_musescore_a_rename_keeps_the_pdf_and_still_makes_the_braille(settings, jobs, monkeypatch):
    from brasscribe_music import musescore

    monkeypatch.setattr(musescore, "binary", lambda: None)
    fake_braille(monkeypatch)
    finished_run(settings, "run-a", {"brass-band.musicxml": SCORE, "brass-band.pdf": "old", "brass-band.brf": "old"})
    assert jobs.rename("run-a", "New") == "renamed"
    drain(jobs)
    out = settings.runs_dir / "run-a" / "outputs"
    assert (out / "brass-band.pdf").read_text() == "old" and "New" in (out / "brass-band.brf").read_text()


def test_a_run_without_rendered_files_queues_no_render(settings, jobs, monkeypatch):
    queued = []
    monkeypatch.setattr(jobs, "render_again", lambda *a: queued.append(a))
    finished_run(settings, "run-a", {"brass-band.musicxml": SCORE})
    assert jobs.rename("run-a", "New") == "renamed"
    drain(jobs)
    assert queued == []
