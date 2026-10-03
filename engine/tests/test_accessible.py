"""Braille (BRF) export, arrangement options and the braille / talking-score API."""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brasscribe_engine import braille, profiles
from brasscribe_engine.api import create_app

from .test_api import wait
from .test_talking_score import SMALL


def _scale_xml() -> str:
    def notes(pitches):
        return "".join(f"<note><pitch><step>{s}</step><octave>{o}</octave></pitch><duration>1</duration><voice>1</voice>"
                       f"<type>quarter</type></note>" for s, o in pitches)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><work><work-title>Scale — test</work-title></work>
<part-list><score-part id="P1"><part-name>E♭ Bass</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths></key>
<time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
{notes([("C", 4), ("D", 4), ("E", 4), ("F", 4)])}</measure>
<measure number="2">{notes([("G", 4), ("A", 4), ("B", 4), ("C", 5)])}</measure></part></score-partwise>"""


def test_brf_ascii_table():
    assert len(braille.BRF_ASCII) == 64 and len(set(braille.BRF_ASCII)) == 64
    # dots 1456 = quarter C, dots 3456 = number sign, dot 6 = capital, all six dots = "="
    assert braille.unicode_to_brf("⠹⠼⠠⠿⠀") == "?#,= "
    assert braille.brf_to_unicode("?#,= ") == "⠹⠼⠠⠿⠀"
    with pytest.raises(ValueError):
        braille.unicode_to_brf("x")


def test_two_bars_of_a_scale(tmp_path):
    p = tmp_path / "scale.musicxml"
    p.write_text(_scale_xml())
    r = braille.translate(p)
    # 4/4, bar 1: octave-4 mark, quarter C D E F; bar 2: quarter G A B C (no octave mark needed for the step to C5)
    assert "⠼⠙⠲" in r.unicode
    assert "⠐⠹⠱⠫⠻⠀⠳⠪⠺⠹" in r.unicode
    assert '"?:$] \\[W?' in r.brf
    assert r.brf.isascii() and all(len(line) <= braille.LINE_CELLS for line in r.brf.split("\r\n"))
    assert ",TITLE3 ,SCALE" in r.brf and "TEST" in r.brf and "MUSICXML" not in r.brf  # ASCII title, no file name
    back = braille.brf_to_unicode(r.brf).split("\n")
    assert [ln.rstrip("⠀") for ln in back if ln] == [ln.rstrip("⠀") for ln in r.unicode.split("\n")]


def test_trill_sign_before_its_note(tmp_path):
    p = tmp_path / "scale.musicxml"
    xml = _scale_xml()
    # a trill on the first note (plain) and on the second (its auxiliary sharpened)
    xml = xml.replace("</type>", "</type><notations><ornaments><trill-mark placement=\"above\"/></ornaments></notations>", 1)
    at = xml.index("</type>", xml.index("<notations>") + 1)
    xml = xml[:at] + ("</type><notations><ornaments><trill-mark placement=\"above\"/>"
                      "<accidental-mark placement=\"above\">sharp</accidental-mark></ornaments></notations>") + xml[at + 7:]
    p.write_text(xml)
    r = braille.translate(p)
    # the trill sign (dots 2-3-5) before C, and sharp + trill sign before D
    assert "⠖⠐⠹⠩⠖⠱" in r.unicode


def test_pagination_breaks_every_25_lines():
    brf = braille.paginate("\n".join(f"#{i}" for i in range(30)))
    pages = brf.split("\f")
    assert len(pages) == 2 and pages[0].count("\r\n") == 25 and pages[1].count("\r\n") == 5


def test_arrangement_options_only_non_defaults():
    assert profiles.arrangement_options({"lineup": "full", "difficulty": "faithful", "key": None}) == {}
    assert profiles.arrangement_options({"lineup": "minimal", "transpose": "-2"}) == {"lineup": "minimal", "transpose": -2}
    assert profiles.arrangement_options({"lineup": "quartet"}) == {"lineup": "quartet"}
    assert profiles.job_options("brass-band", {"lineup": "quartet"}) == {"lineup": "quartet"}
    with pytest.raises(ValueError, match="whole group"):
        profiles.job_options("solo", {"lineup": "quartet"})
    with pytest.raises(ValueError, match="whole group"):
        profiles.build("solo", Path("a.wav"), params={"lineup": "quartet"})
    assert profiles.arrangement_options({"transpose": 0}) == {}
    for bad in ({"key": "Bb", "transpose": 2}, {"lineup": "huge"}, {"difficulty": "hard"}, {"transpose": 13}):
        with pytest.raises(ValueError):
            profiles.arrangement_options(bad)
    default = profiles.build("orchestra-with-soloist", "m.wav").stage("arrange").params
    easier = profiles.build("orchestra-with-soloist", "m.wav", params={"difficulty": "easier"}).stage("arrange").params
    assert "arrangement" not in default and easier["arrangement"] == {"difficulty": "easier"}


def test_difficulty_is_a_cache_key_pass_through(settings, audio):
    from brasscribe_engine import runner, stages

    ran = []

    def arrange(ctx):
        ran.append(stages._arrangement_flags(ctx, "json.tool"))  # a module without arrangement flags
        (ctx.out / "composition.json").write_text("{}")
        (ctx.out / "brass-band.musicxml").write_text("<score-partwise/>")

    from .conftest import fake_pipeline

    def pipeline(title, params):
        p = fake_pipeline(title, params)
        a = p.stage("arrange")
        a.run, a.params = arrange, profiles._arrange_params(title, params)
        return p

    profiles.PROFILES["test"] = profiles.Profile("test", "test", "", False, pipeline)
    m1 = runner.run(settings, audio, "test")
    m2 = runner.run(settings, audio, "test", params={"difficulty": "easier"})
    k = {m["run_id"]: {s["stage"]: s for s in m["stages"]}["arrange"] for m in (m1, m2)}
    a1, a2 = k[m1["run_id"]], k[m2["run_id"]]
    assert a1["key"] != a2["key"] and a2["status"] == "ran" and ran == [[], []]
    m3 = runner.run(settings, audio, "test", params={"lineup": "minimal"})
    assert m3["status"] == "failed" and "does not support --lineup" in m3["error"]


def test_braille_and_talking_score_endpoints(settings, audio, tmp_path):
    with TestClient(create_app(settings)) as c:
        r = c.post("/v1/jobs/upload", files={"file": ("song.wav", audio.read_bytes())}, data={"profile": "test"})
        job = wait(c, r.json()["id"])
        out = settings.runs_dir / job["id"] / "outputs"
        # what the export stage writes for a real profile
        (out / "parts").mkdir()
        (out / "parts" / "02-Solo-Cornet.musicxml").write_text(SMALL)
        (out / "brass-band.musicxml").write_text(SMALL)
        from brasscribe_engine import talking_score as T
        from brasscribe_engine.stages import accessible_exports

        class Ctx:
            out = tmp_path / "export"

            @staticmethod
            def log(msg):
                pass

        Ctx.out.mkdir()
        info = accessible_exports(out, Ctx)
        assert info["braille_failed"] == {} and "parts/02-Solo-Cornet.brf" in info["written"]
        for f in ("brass-band.brf", "talking-score.json"):
            shutil.copy(Ctx.out / f, out / f)
        shutil.copy(Ctx.out / "parts" / "02-Solo-Cornet.brf", out / "parts" / "02-Solo-Cornet.brf")

        score = c.get(f"/v1/jobs/{job['id']}/braille")
        assert score.status_code == 200 and score.text.isascii() and score.text.endswith("\r\n")
        for part in ("2", "02", "Solo Cornet", "solo-cornet"):
            assert c.get(f"/v1/jobs/{job['id']}/braille", params={"part": part}).status_code == 200
        assert c.get(f"/v1/jobs/{job['id']}/braille", params={"part": "Tuba"}).status_code == 404

        html = c.get(f"/v1/jobs/{job['id']}/talking-score")
        assert html.headers["content-type"].startswith("text/html") and "<h2>Solo Cornet</h2>" in html.text
        text = c.get(f"/v1/jobs/{job['id']}/talking-score",
                     params={"format": "text", "lang": "nb", "part": "1"}).text
        assert "takt 1, tempo 120, slag 1: B 4, åttendedelsnote" in text  # one part: written pitch
        concert = c.get(f"/v1/jobs/{job['id']}/talking-score", params={"format": "text"}).text
        assert "beat 1: A-flat 4, eighth note" in concert  # whole score: concert pitch
        doc = c.get(f"/v1/jobs/{job['id']}/talking-score", params={"format": "json"}).json()
        assert doc["version"] == 1 and doc["parts"][0]["name"] == "Solo Cornet"
        assert json.loads((out / "talking-score.json").read_text()) == doc
        assert c.get(f"/v1/jobs/{job['id']}/talking-score", params={"part": "9"}).status_code == 404
        assert T.to_text(doc)


def test_job_options_validated_by_the_api(settings, audio):
    with TestClient(create_app(settings)) as c:
        ref = c.post("/v1/audio", files={"file": ("a.wav", audio.read_bytes())}).json()
        bad = c.post("/v1/jobs", json={"audio_id": ref["audio_id"], "profile": "test", "key": "Bb", "transpose": 2})
        assert bad.status_code == 422
        assert c.post("/v1/jobs", json={"audio_id": ref["audio_id"], "profile": "test", "lineup": "huge"}).status_code == 422
        solo = c.post("/v1/jobs", json={"audio_id": ref["audio_id"], "profile": "solo", "lineup": "quartet"})
        assert solo.status_code == 422 and "whole group" in solo.json()["detail"]
        ok = c.post("/v1/jobs", json={"audio_id": ref["audio_id"], "profile": "test", "difficulty": "easier"})
        assert ok.status_code == 202


def test_long_title_lines_wrap_at_words():
    line = ",MOVEMENT ,NAME3 ,MIKKEL 0 SOLO CORNET AND BRASS BAND 7DRAFT7 0 ,SOPRANO ,CORNET"
    out = braille.wrap_line(line)
    assert len(out) > 1 and all(len(x) <= braille.LINE_CELLS for x in out)
    assert all(x.startswith("  ") and not x.startswith("   ") for x in out[1:])  # runover indent of two cells
    assert " ".join(x.strip() for x in out) == line  # nothing lost, words intact
    assert braille.wrap_line("#A \"?:$]") == ["#A \"?:$]"]
    long_word = "X" * 90
    assert all(len(x) <= braille.LINE_CELLS for x in braille.wrap_line(long_word))


def _lines_ok(brf: str) -> bool:
    return all(len(line) <= braille.LINE_CELLS for page in brf.split("\f") for line in page.split("\r\n"))


def test_every_brf_line_fits_the_page(tmp_path):
    p = tmp_path / "scale.musicxml"
    p.write_text(_scale_xml().replace("Scale — test", "A very long title that no braille line of forty cells can hold"))
    r = braille.translate(p)
    assert _lines_ok(r.brf)


GOLDEN = braille.Path(__file__).resolve().parents[2] / "data" / "golden" / "mikkel-arranged-band"


@pytest.mark.skipif(not (GOLDEN / "brass-band.musicxml").exists(), reason="golden output not available")
@pytest.mark.slow
def test_every_line_of_the_golden_score_and_parts_fits_the_page():
    for xml in [GOLDEN / "brass-band.musicxml", *sorted((GOLDEN / "parts").glob("*.musicxml"))]:
        assert _lines_ok(braille.translate(xml).brf), xml.name


def test_a_bar_of_32nds_with_review_marks_still_translates(tmp_path):
    """A measure longer than a braille line (a bar of 32nds, a "?" on it) cannot be broken by music21: it is
    translated on a longer line and wrapped at the page width."""
    steps = [("C", 5), ("D", 5), ("E", 5), ("F", 5), ("G", 5), ("A", 5), ("B", 5), ("C", 6)] * 4
    notes = "".join(f"<note><pitch><step>{s}</step><octave>{o}</octave></pitch><duration>1</duration><voice>1</voice>"
                    f"<type>32nd</type></note>" for s, o in steps)
    mark = '<direction placement="above"><direction-type><words>?</words></direction-type></direction>'
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><work><work-title>Run</work-title></work>
<part-list><score-part id="P1"><part-name>Solo Cornet</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>8</divisions><key><fifths>0</fifths></key>
<time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
{mark}{notes}</measure></part></score-partwise>"""
    src = tmp_path / "run.musicxml"
    src.write_text(xml)
    r = braille.translate(src)
    assert all(len(line) <= braille.LINE_CELLS for page in r.brf.split("\f") for line in page.split("\r\n"))
    assert len(r.brf.replace("\r\n", "").replace(" ", "")) > 32


def test_the_band_export_is_keyed_on_the_musescore_that_would_render_it(tmp_path, monkeypatch):
    from brasscribe_music import musescore

    def key(profile: str) -> dict:
        return profiles.build(profile, Path("song.wav"), "T").stage("export").params

    band = [name for name in profiles.PROFILES if not profiles.tab.is_tab(name)]
    monkeypatch.setattr(musescore, "binary", lambda: None)
    assert band and all(key(p)["musescore"] is None for p in band)
    exe = tmp_path / "mscore"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.setattr(musescore, "binary", lambda: str(exe))
    installed = key("brass-band")["musescore"]
    assert installed and all(key(p)["musescore"] == installed for p in band)
    exe.write_text("#!/bin/sh\n# an update\n")
    assert key("brass-band")["musescore"] not in (None, installed)
    for p in band:  # only the export
        assert all("musescore" not in s.params for s in profiles.build(p, Path("song.wav"), "T").stages if s.name != "export")


def test_a_band_run_made_without_musescore_is_rendered_once_it_is_installed(settings, audio, tmp_path, monkeypatch):
    from brasscribe_engine import runner
    from brasscribe_engine import stages as S
    from brasscribe_music import musescore

    from .conftest import fake_pipeline

    def pipeline(title, params):
        p = fake_pipeline(title, params)
        p.stages.append(profiles._export("arrange", False))
        p.outputs.update({"brass-band.pdf": ("export", "brass-band.pdf"), "brass-band.mid": ("export", "brass-band.mid")})
        return p

    monkeypatch.setitem(profiles.PROFILES, "test", profiles.Profile("test", "test", "", False, pipeline))
    monkeypatch.setattr(S, "accessible_exports", lambda score, ctx: {"written": []})
    monkeypatch.setattr(musescore, "binary", lambda: None)
    without = runner.run(settings, audio, "test")
    assert without["status"] == "succeeded" and "brass-band.pdf" not in without["outputs"]

    exe = tmp_path / "mscore"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.setattr(musescore, "binary", lambda: str(exe))
    monkeypatch.setattr(musescore, "convert_many",
                        lambda jobs, style=None: [Path(d).write_bytes(b"rendered") for _, ds in jobs for d in ds] and [])
    installed = runner.run(settings, audio, "test")
    statuses = {s["stage"]: s["status"] for s in installed["stages"]}
    assert statuses.pop("export") == "ran" and set(statuses.values()) == {"cached"}
    assert {"brass-band.pdf", "brass-band.mid"} <= set(installed["outputs"])
    again = runner.run(settings, audio, "test")
    assert again["stages"][-1]["status"] == "cached" and "brass-band.pdf" in again["outputs"]


def test_the_band_export_renders_only_with_the_musescore_it_was_keyed_on(tmp_path, monkeypatch):
    """A MuseScore installed between keying and running is not used: the stored export would say otherwise
    than its key."""
    from types import SimpleNamespace

    from brasscribe_engine import stages as S
    from brasscribe_music import musescore

    (tmp_path / "score").mkdir()
    (tmp_path / "score" / "brass-band.musicxml").write_text("<score-partwise/>")
    monkeypatch.setattr(S, "accessible_exports", lambda score, ctx: {"written": []})
    monkeypatch.setattr(musescore, "binary", lambda: "mscore")
    launched = []
    monkeypatch.setattr(musescore, "convert_many", lambda jobs, style=None: launched.append(jobs) or [])
    ctx = SimpleNamespace(out=tmp_path, inputs={"score": tmp_path / "score"}, log=lambda m: None,
                          stage=SimpleNamespace(name="export"), params={"audio": False, "musescore": None})
    S.export(ctx)
    assert launched == [] and json.loads((tmp_path / "export.json").read_text())["skipped"] == ["pdf", "mid"]
    ctx.params = {"audio": False, "musescore": "0123456789abcdef"}
    S.export(ctx)
    assert launched and json.loads((tmp_path / "export.json").read_text())["musescore"] == "mscore"
