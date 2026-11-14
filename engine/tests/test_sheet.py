"""Printed music read from pictures: the pages a job takes, the score and the tab made of what was read,
and the upload route. The recogniser itself is not run here: its reading of Old Hundredth, kept with the
benchmark's fixtures, stands in for it."""

import io
import json
import struct
import time
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scribe_engine import bass_tab, config, pages, profiles, sheet
from scribe_engine.api import create_app
from scribe_music import written

FIXTURES = config.REPO_ROOT / "eval" / "fixtures" / "sheet-image"
HYMN = FIXTURES / "old-hundredth-hymn" / "screenshot.homr.musicxml"  # two staves, written chord by chord
TUNE = FIXTURES / "old-hundredth-tune" / "screenshot.homr.musicxml"


def png(width: int = 8, height: int = 8) -> bytes:
    """The start of a PNG that says it is `width` by `height`: all the engine reads of a page."""
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I4sII", 13, b"IHDR", width, height) + b"\x08\x00\x00\x00\x00" + b"\0" * 16


def picture(fmt: str, size: tuple[int, int] = (40, 30), **options) -> bytes:
    """A real picture of `size`, written by Pillow."""
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, fmt, **options)
    return out.getvalue()


PNG = png()
JPEG = picture("JPEG")
PDF = b"%PDF-1.7\n" + b"\0" * 32
HEIC = b"\0\0\0\x18ftypheic" + b"\0" * 32

needs_core = pytest.mark.skipif(not bass_tab.core_cli_path().exists(), reason="scribe-core is not built")


def score(bars: str, attributes: str = "<divisions>2</divisions><time><beats>4</beats><beat-type>4</beat-type></time>") -> str:
    """A one-part score whose bars are given as MusicXML notes, separated by '|'."""
    measures = "".join(f'<measure number="{i}">{f"<attributes>{attributes}</attributes>" if i == 1 else ""}{bar}</measure>'
                       for i, bar in enumerate(bars.split("|"), 1))
    return (f'<score-partwise><part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list>'
            f'<part id="P1">{measures}</part></score-partwise>')


def note(step: str, octave: int, duration: int, extra: str = "") -> str:
    return f"<note><pitch><step>{step}</step><octave>{octave}</octave></pitch><duration>{duration}</duration>{extra}</note>"


def read(tmp_path: Path, xml: str) -> written.WrittenScore:
    path = tmp_path / "score.musicxml"
    path.write_text(xml)
    return written.read(path)


# ---------------------------------------------------------------- pages

def test_a_page_is_known_by_its_first_bytes_not_its_name():
    assert [pages.kind(b) for b in (PNG, JPEG, PDF, HEIC, b"RIFF\0\0\0\0WAVE")] == [".png", ".jpg", ".pdf", None, None]
    assert "HEIC" in pages.seems(HEIC)
    # TIFF and BMP are not taken: no phone sends them, and they are the decoders with the worst record.
    assert pages.kind(b"II*\0" + b"\0" * 28) is None and pages.kind(b"BM" + b"\0" * 30) is None
    assert "TIFF" in pages.seems(b"II*\0") and "BMP" in pages.seems(b"BM\0\0")
    assert pages.is_pages("a.PNG") and pages.is_pages("b.pdf") and pages.is_pages("c.zip") and not pages.is_pages("d.wav")


def test_several_pages_are_one_archive_in_order_and_always_the_same_bytes(tmp_path):
    a, b = tmp_path / "x", tmp_path / "y"
    a.write_bytes(PNG)
    b.write_bytes(JPEG)
    pages.pack([(a, ".png"), (b, ".jpg")], tmp_path / "one.zip")
    time.sleep(0.01)
    pages.pack([(a, ".png"), (b, ".jpg")], tmp_path / "two.zip")
    assert (tmp_path / "one.zip").read_bytes() == (tmp_path / "two.zip").read_bytes()
    out = tmp_path / "out"
    out.mkdir()
    assert pages.unpack(tmp_path / "one.zip", out) == 2
    assert sorted(p.name for p in out.iterdir()) == ["page-001.png", "page-002.jpg"]
    assert (out / "page-002.jpg").read_bytes() == JPEG


@pytest.mark.parametrize("fmt, options", [("PNG", {}), ("JPEG", {}), ("JPEG", {"progressive": True}), ("WEBP", {}),
                                          ("WEBP", {"lossless": True})])
def test_a_pictures_size_is_read_from_its_header(tmp_path, fmt, options):
    path = tmp_path / "page"
    path.write_bytes(picture(fmt, (123, 45), **options))
    assert pages.picture_size(path) == (123, 45)
    assert pages.too_large(path, pages.kind(path.read_bytes()[:16])) is None


def test_a_page_is_too_large_by_its_bytes_or_by_the_pixels_its_header_claims(tmp_path, monkeypatch):
    bomb = tmp_path / "bomb.png"
    bomb.write_bytes(png(12000, 12000))  # a few bytes that would decode to 144 million pixels
    assert "12000 by 12000 pixels" in pages.too_large(bomb, ".png")
    cut = tmp_path / "cut.jpg"
    cut.write_bytes(JPEG[:20])  # no frame header: nothing says how large it is
    assert pages.too_large(cut, ".jpg") == "does not say how large it is"
    monkeypatch.setattr(pages, "MAX_PAGE_BYTES", 100)
    big = tmp_path / "big.pdf"
    big.write_bytes(PDF + b"\0" * 200)
    assert "a page is at most" in pages.too_large(big, ".pdf")
    # An archive whose member says it is larger than a page may be is not unpacked.
    ok = tmp_path / "ok.png"
    ok.write_bytes(png() + b"\0" * 200)
    monkeypatch.setattr(pages, "MAX_PAGE_BYTES", 1000)
    pages.pack([(ok, ".png")], tmp_path / "pages.zip")
    monkeypatch.setattr(pages, "MAX_PAGE_BYTES", 100)
    (tmp_path / "out").mkdir()
    with pytest.raises(ValueError):
        pages.unpack(tmp_path / "pages.zip", tmp_path / "out")
    assert not list((tmp_path / "out").iterdir())


@pytest.mark.parametrize("member", ["../escape.png", "notes.txt", "page-1.png", "sub/page-001.png", "page-001.tif"])
def test_an_archive_with_anything_but_pages_is_refused(tmp_path, member):
    with zipfile.ZipFile(tmp_path / "bad.zip", "w") as z:
        z.writestr(member, PNG)
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(ValueError):
        pages.unpack(tmp_path / "bad.zip", out)
    assert not list(out.iterdir()) and not (tmp_path / "escape.png").exists()


# ---------------------------------------------------------------- what was read

def test_the_recognisers_reading_is_read_staff_by_staff():
    hymn = written.read(HYMN)
    assert [(s.number, s.clef, len(s.bars), s.notes()) for s in hymn.staves] == [(1, "G", 12, 64), (2, "F", 12, 64)]
    assert hymn.title == ""  # the recogniser is not asked for the page's title
    first = hymn.staves[0].bars[0]
    assert [(n.pitch, n.start, n.dur) for n in first.notes] == [
        (62, 0, 2), (67, 0, 2), (62, 2, 1), (67, 2, 1), (62, 3, 1), (66, 3, 1)]
    assert (first.beats, first.beat_unit, first.fifths, first.length) == (4, 4, 1, 4)


def test_a_bar_that_does_not_add_up_is_in_doubt_but_not_a_pickup_or_its_last_bar(tmp_path):
    full = note("C", 4, 8)
    s = read(tmp_path, score(f"{note('G', 4, 2)}|{full}|{note('C', 4, 6)}|{full}|{note('C', 4, 10)}|{note('C', 4, 6)}"))
    staff = s.staves[0]
    assert sheet.doubtful_bars(staff) == [2, 4]  # a quarter short, a quarter long; the pickup and the last bar are not
    # Bars keep the length their time signature gives them, so the misread ones do not move what follows.
    assert sheet.bar_starts(s) == [-1, 0, 4, 8, 12, 16]
    notes = sheet.sounding_notes(staff, sheet.bar_starts(s), set(sheet.doubtful_bars(staff)))
    assert [(n["start"], n["confidence"]) for n in notes] == [(-24, 1.0), (0, 1.0), (96, 0.3), (192, 1.0), (288, 0.3), (384, 1.0)]
    assert all(c < bass_tab.DOUBT for c in (sheet.DOUBTFUL,))


def test_bars_that_agree_against_their_time_signature_are_one_doubt_not_many(tmp_path):
    three, four, five = note("C", 4, 6), note("C", 4, 8), note("C", 4, 10)
    # Read as 4/4, written in three all through: the signature is what is wrong, so the first bar carries the
    # doubt, and a bar that differs from the others is still found.
    s = read(tmp_path, score("|".join([three, three, three, five, three, three, three, three])))
    assert sheet.doubtful_bars(s.staves[0]) == [0, 3]
    # A change to three that was not read, half way: the doubt is where the bars start to agree on three.
    s = read(tmp_path, score("|".join([four] * 6 + [three] * 6)))
    assert sheet.doubtful_bars(s.staves[0]) == [6]
    # Two short bars among full ones are two misread bars.
    s = read(tmp_path, score("|".join([four, four, three, three, four, four, four, four])))
    assert sheet.doubtful_bars(s.staves[0]) == [2, 3]


def test_each_staff_is_counted_by_itself(tmp_path):
    def on(staff: int, *notes: str) -> str:
        return "".join(n.replace("</note>", f"<staff>{staff}</staff></note>") for n in notes)

    back = "<backup><duration>{}</duration></backup>"
    full, short, long = note("C", 4, 8), note("C", 4, 6), note("C", 4, 10)
    xml = score(f"{on(1, full)}{back.format(8)}{on(2, full)}|{on(1, short)}{back.format(6)}{on(2, full)}|"
                f"{on(1, full)}{back.format(8)}{on(2, long)}|{on(1, full)}|{on(1, full)}{back.format(8)}{on(2, full)}")
    upper, lower = read(tmp_path, xml).staves
    assert [float(b.length) for b in upper.bars] == [4, 3, 4, 4, 4] and [float(b.length) for b in lower.bars] == [4, 4, 5, 0, 4]
    # The short bar is the upper staff's alone, the long one the lower's; a bar a staff has nothing in is neither.
    assert (sheet.doubtful_bars(upper), sheet.doubtful_bars(lower)) == ([1], [2])


def test_tied_notes_sound_as_one_and_a_transposing_part_sounds_where_it_plays(tmp_path):
    tie = lambda kind: f'<tie type="{kind}"/>'  # noqa: E731
    xml = score(f"{note('C', 5, 8, tie('start'))}|{note('C', 5, 4, tie('stop'))}{note('D', 5, 4)}",
                "<divisions>2</divisions><time><beats>4</beats><beat-type>4</beat-type></time>"
                "<transpose><diatonic>-1</diatonic><chromatic>-2</chromatic></transpose>")
    s = read(tmp_path, xml)
    notes = sheet.sounding_notes(s.staves[0], sheet.bar_starts(s), set())
    assert [(n["pitch"], n["start"], n["dur"]) for n in notes] == [(70, 0, 144), (72, 144, 48)]


def test_the_score_keeps_what_was_read_under_the_jobs_title_with_each_staff_in_voices(tmp_path):
    read_score = sheet.written_score(HYMN, "Old Hundredth — from the page (draft)", tmp_path)
    out = tmp_path / "brass-band.musicxml"
    root = ET.fromstring(out.read_text())
    assert root.findtext("work/work-title") == "Old Hundredth — from the page (draft)"
    assert [sp.findtext("part-name") for sp in root.iterfind("part-list/score-part")] == ["Part 1"]
    assert root.find("part/measure/sound").get("tempo") == str(sheet.TEMPO_BPM)
    # Not a note is lost or moved by putting each staff's notes one after another.
    again = written.read(out)
    assert [[(n.pitch, n.start, n.dur) for b in s.bars for n in b.notes] for s in again.staves] == \
           [[(n.pitch, n.start, n.dur) for b in s.bars for n in b.notes] for s in read_score.staves]
    first = root.find("part/measure")
    order = [(el.tag, el.findtext("staff")) for el in first if el.tag in ("note", "backup")]
    staves = [staff for tag, staff in order if tag == "note"]
    assert staves == sorted(staves) and [tag for tag, _ in order].count("backup") == 1  # staff 1, one step back, staff 2
    assert {el.findtext("voice") for el in first.iter("note")} == {"1", "5"}


def test_a_doubtful_bar_is_marked_in_the_score_and_listed_for_review(tmp_path):
    xml = score(f"{note('C', 4, 8)}|{note('D', 4, 6)}|{note('E', 4, 8)}")
    (tmp_path / "read.musicxml").write_text(xml)
    s = sheet.written_score(tmp_path / "read.musicxml", "A tune", tmp_path)
    bars = ET.fromstring((tmp_path / "brass-band.musicxml").read_text()).findall("part/measure")
    assert [m.findtext("direction/direction-type/words") for m in bars] == [None, "?", None]
    assert bars[1].find("note").get("color") == sheet.UNCERTAIN_COLOUR and bars[0].find("note").get("color") is None
    comp = sheet.composition(s, "A tune")
    assert [(r.voice, r.start, r.notes) for r in comp.review] == [("part-1", 96, 1)]
    assert [n.confidence for n in comp.voices[0].notes] == [1.0, sheet.DOUBTFUL, 1.0]
    assert sheet.summary(s) == {"recogniser": "homr", "staves": 1, "bars": 3, "notes": 3, "doubtful_bars": [{"staff": 1, "bar": 2}]}


def test_the_composition_has_a_voice_for_each_staff_on_a_steady_beat():
    comp = sheet.composition(written.read(HYMN), "Old Hundredth")
    assert [(v.id, v.role.value, len(v.notes)) for v in comp.voices] == [("part-1-staff-1", "melody", 64), ("part-1-staff-2", "harmony", 64)]
    assert (comp.meters[0].beats, comp.keys[0].fifths, comp.first_downbeat) == (4, 1, 0)
    assert comp.bpm == pytest.approx(sheet.TEMPO_BPM)
    last = max(n.offset_s for v in comp.voices for n in v.notes)
    assert last == pytest.approx(12 * 4 * 60 / sheet.TEMPO_BPM - 2 * 60 / sheet.TEMPO_BPM)  # the last bar ends with a half rest


# ---------------------------------------------------------------- the tab

def test_a_guitars_notation_is_taken_an_octave_down_and_a_ukuleles_is_not():
    tune = written.read(TUNE)  # G4 to D5 on the staff
    guitar, ukulele = sheet.tab_notes(tune, "guitar-6"), sheet.tab_notes(tune, "ukulele")
    assert (guitar["octave_shift"], guitar["octave_source"], ukulele["octave_shift"]) == (-12, "auto", 0)
    assert guitar["notes"][0]["pitch"] == 55 and ukulele["notes"][0]["pitch"] == 67
    assert sheet.tab_notes(tune, "guitar-6", "0")["octave_shift"] == 0  # the player's choice counts from the staff
    assert guitar["meter"] == {"beats": 4, "beat_unit": 4} and guitar["key"] == {"name": "G", "fifths": 1, "mode": "major"}
    assert all(n["start"] >= 0 for n in guitar["notes"])


def test_a_line_outside_the_instrument_is_moved_by_octaves_into_it():
    assert sheet.octave_shift([40, 45, 52], "bass-4", 0) == -12  # written an octave high, as a bass part is
    assert sheet.octave_shift([79, 84], "bass-4", 0) == -24  # a tune high in the treble clef, for a bass
    assert sheet.octave_shift([40, 45], "ukulele", 0) == 24  # below a ukulele's lowest string
    assert sheet.octave_shift([52, 60], "guitar-6", -1) == 0  # the clef's 8 was read: the pitches are already right


def test_a_page_of_tab_alone_says_that_tab_is_not_read(tmp_path):
    tab_clef = "<divisions>2</divisions><clef><sign>TAB</sign><line>5</line></clef>"
    with pytest.raises(ValueError, match="a tab staff is not read"):
        sheet.tab_notes(read(tmp_path, score(note("E", 2, 8), tab_clef)), "guitar-6")
    with pytest.raises(ValueError, match=sheet.NO_MUSIC):
        sheet.tab_notes(read(tmp_path, score("<note><rest/><duration>8</duration></note>")), "guitar-6")


def test_a_pickup_is_a_full_bar_that_starts_with_a_rest_in_the_tab(tmp_path):
    s = read(tmp_path, score(f"{note('G', 4, 2)}|{note('C', 5, 8)}"))
    doc = sheet.tab_notes(s, "ukulele")
    assert [(n["start"], n["dur"]) for n in doc["notes"]] == [(72, 24), (96, 96)]


# ---------------------------------------------------------------- profiles and the route

def test_the_sheet_profiles_read_pages_and_take_only_their_own_options():
    assert {p: profiles.PROFILES[p].input for p in ("sheet", "sheet-tab", "solo", "tab")} == {
        "sheet": "pages", "sheet-tab": "pages", "solo": "audio", "tab": "audio"}
    assert (profiles.PROFILES["sheet"].target.id, profiles.PROFILES["sheet-tab"].target.id) == ("brass", "fretted")
    assert [s.name for s in profiles.PROFILES["sheet"].build("-", {}).stages] == ["read", "arrange", "export"]
    assert [s.name for s in profiles.PROFILES["sheet-tab"].build("-", {}).stages] == ["read", "notes", "arrange", "export"]
    for profile, path in (("sheet", "take.wav"), ("solo", "page.png"), ("tab", "pages.zip"), ("sheet", "scan.tif")):
        with pytest.raises(pages.WrongInput):
            profiles.check_input(profile, Path(path))
    profiles.check_input("sheet-tab", Path("page.PDF"))
    for params in ({"lineup": "quartet"}, {"seat": "solo-cornet"}, {"transpose": 2}, {"instrument": "guitar-6"}):
        with pytest.raises(ValueError):
            sheet.job_options("sheet", params)
    with pytest.raises(ValueError):
        sheet.job_options("sheet-tab", {"recording": "instrument"})
    assert sheet.job_options("sheet-tab", {"instrument": "bass-4", "capo": 2}) == {
        "instrument": "bass-4", "tuning": "standard", "capo": 2, "style": "as-played", "octave": "auto", "layout": "tab"}


FAKE_RECOGNISER = """import os, shutil, sys
# fake run_adapter.py: homr <page or folder> <out>; "reads" every page as Old Hundredth, except a page that
# starts as a WebP, which it fails on as homr does on a page without a staff: a traceback, then the reason
name, src, dst = sys.argv[1:4]
assert name == "homr", name
if open(src, "rb").read(4) == b"RIFF":
    sys.stderr.write('Traceback (most recent call last):\\n  File "/home/someone/engine/ml/adapters/homr/main.py", line 1\\n'
                     'cv2.error: /var/folders/xy/T/tmp123/page-001.webp has no staff\\nscribe-refusal: ' + os.environ.get("FAKE_REFUSAL", "no_music") + '\\n')
    sys.exit(3)
shutil.copyfile({reading!r}, dst)
"""


@pytest.fixture
def client(settings, monkeypatch):
    (settings.adapters_dir / "homr").mkdir()
    (settings.adapters_dir / "homr" / "pyproject.toml").write_text('[project]\nname = "fake-homr"\nversion = "9.9.9"\n')
    (settings.adapters_dir / "run_adapter.py").write_text(FAKE_RECOGNISER.format(reading=str(TUNE)))
    monkeypatch.setenv("SCRIBE_MSCORE", "")  # no MuseScore: the export stage writes what needs none
    monkeypatch.setattr("scribe_music.musescore.binary", lambda: None)
    monkeypatch.setattr(sheet, "reader_installed", lambda adapters_dir: True)
    with TestClient(create_app(settings)) as c:
        yield c


def wait(client, job_id, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/v1/jobs/{job_id}").json()
        if j["status"] in ("succeeded", "failed", "cancelled"):
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_profiles_say_what_they_read(client):
    by_name = {p["name"]: p for p in client.get("/v1/profiles").json()}
    assert (by_name["sheet"]["input"], by_name["sheet-tab"]["input"], by_name["solo"]["input"]) == ("pages", "pages", "audio")


@pytest.mark.slow
def test_a_picture_becomes_a_score_with_parts_and_a_talking_score(client):
    r = client.post("/v1/jobs/pages", files=[("files", ("Old Hundredth.png", PNG, "image/png"))])
    assert r.status_code == 202, r.text
    job = r.json()
    assert (job["profile"], job["target"], job["title"]) == ("sheet", "brass", "Old Hundredth — from the page (draft)")
    done = wait(client, job["id"])
    assert done["status"] == "succeeded", done
    names = {a["name"] for a in client.get(f"/v1/jobs/{job['id']}/artifacts").json()}
    assert {"brass-band.musicxml", "composition.json", "sheet.json", "parts/01-Part-1.musicxml", "talking-score.json",
            "brass-band.brf"} <= names
    assert "<work-title>Old Hundredth — from the page (draft)</work-title>" in client.get(f"/v1/jobs/{job['id']}/musicxml").text
    comp = client.get(f"/v1/jobs/{job['id']}/composition").json()
    assert len(comp["voices"]) == 1 and len(comp["voices"][0]["notes"]) == 32
    summary = client.get(f"/v1/jobs/{job['id']}/artifacts/sheet.json").json()
    assert (summary["bars"], summary["notes"], summary["doubtful_bars"]) == (12, 32, [])
    talking = client.get(f"/v1/jobs/{job['id']}/talking-score?format=json").json()
    assert talking["parts"][0]["name"] == "Part 1" and len(talking["parts"][0]["bars"]) == 12
    # The job can be run again from its stored page, and its input is the picture.
    assert client.get(f"/v1/jobs/{job['id']}/input").content == PNG
    assert client.post(f"/v1/jobs/{job['id']}/rerun").status_code == 202


@needs_core
def test_a_picture_becomes_a_tab_for_the_instrument_asked_for(client):
    r = client.post("/v1/jobs/pages", files=[("files", ("tune.jpg", JPEG, "image/jpeg"))],
                    data={"profile": "sheet-tab", "instrument": "ukulele", "title": "A tune"})
    assert r.status_code == 202, r.text
    done = wait(client, r.json()["id"])
    assert done["status"] == "succeeded", done
    tab = client.get(f"/v1/jobs/{done['id']}/tab").json()
    assert (tab["preset"], tab["octave_shift"], len(tab["notes"]), tab["violations"]) == ("ukulele-high-g", 0, 32, [])
    assert tab["notes"][0]["pitch"] == 67 and (tab["notes"][0]["string"], tab["notes"][0]["fret"]) == (4, 0)
    assert "A tune" in client.get(f"/v1/jobs/{done['id']}/artifacts/tab.txt").text


def test_several_pages_are_stored_as_one_input_in_the_order_given(client, settings):
    r = client.post("/v1/jobs/pages", files=[("files", ("b.png", PNG, "image/png")), ("files", ("a.jpg", JPEG, "image/jpeg")),
                                             ("files", ("c.pdf", PDF, "application/pdf"))])
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["title"] == "B (3 Pages) — from the page (draft)"
    stored = settings.uploads_dir / f"{job['audio_id']}.zip"
    with zipfile.ZipFile(stored) as z:
        assert z.namelist() == ["page-001.png", "page-002.jpg", "page-003.pdf"]
        assert z.read("page-002.jpg") == JPEG
    assert not [p for p in settings.uploads_dir.iterdir() if p.name.startswith(".upload-")]
    # The same pages again are the same upload.
    again = client.post("/v1/jobs/pages", files=[("files", ("b.png", PNG, "image/png")), ("files", ("a.jpg", JPEG, "image/jpeg")),
                                                 ("files", ("c.pdf", PDF, "application/pdf"))])
    assert again.json()["audio_id"] == job["audio_id"]


def test_a_file_that_is_not_a_page_is_refused_and_nothing_is_kept(client, settings):
    r = client.post("/v1/jobs/pages", files=[("files", ("ok.png", PNG, "image/png")), ("files", ("IMG_0001.HEIC", HEIC, "image/heic"))])
    assert r.status_code == 415
    assert r.json()["code"] == "not_a_page" and "IMG_0001.HEIC is a HEIC" in r.json()["detail"]
    assert not list(settings.uploads_dir.iterdir())
    assert client.post("/v1/jobs/pages", files=[("files", ("song.png", b"RIFF-fake-audio", "image/png"))]).status_code == 415
    for name, data in (("scan.tif", b"II*\0" + b"\0" * 40), ("scan.bmp", b"BM" + b"\0" * 40)):
        assert client.post("/v1/jobs/pages", files=[("files", (name, data, "image/x"))]).json()["code"] == "not_a_page"


def test_a_page_too_large_to_read_is_refused_before_anything_opens_it(client, settings, monkeypatch):
    r = client.post("/v1/jobs/pages", files=[("files", ("ok.png", PNG, "image/png")), ("files", ("bomb.png", png(12000, 12000), "image/png"))])
    assert (r.status_code, r.json()["code"]) == (413, "page_too_large")
    assert "bomb.png is 12000 by 12000 pixels" in r.json()["detail"]
    monkeypatch.setattr(pages, "MAX_PAGE_BYTES", 1000)
    r = client.post("/v1/jobs/pages", files=[("files", ("long.pdf", PDF + b"\0" * 2000, "application/pdf"))])
    assert (r.status_code, r.json()["code"]) == (413, "page_too_large")
    assert client.post("/v1/jobs/pages", files=[("files", (f"{i}.png", PNG, "image/png")) for i in range(pages.MAX_PAGES + 1)]).status_code == 422
    assert not list(settings.uploads_dir.iterdir())


@pytest.mark.parametrize("refusal, words", [("no_music", "no notes were found on the page"), ("too_many_pages", "there are more than 40 pages"),
                                            ("page_too_large", "a page is too large to read"), ("something_else", "the pages could not be read")])
def test_a_page_that_cannot_be_read_fails_in_fixed_words_without_the_computers_paths(client, monkeypatch, refusal, words):
    monkeypatch.setenv("FAKE_REFUSAL", refusal)
    blank = picture("WEBP")  # the fake recogniser finds no staff on a WebP
    job = client.post("/v1/jobs/pages", files=[("files", ("blank.webp", blank, "image/webp"))]).json()
    done = wait(client, job["id"])
    assert done["status"] == "failed" and done["error"].endswith(f"read: {words}")  # as every failed stage is worded
    events = client.get(f"/v1/jobs/{job['id']}/events").text
    assert "has no staff" in events  # what the recogniser said is in the log
    assert "/home/" not in events and "/var/folders" not in events and "someone" not in events


def test_the_recogniser_has_minutes_not_hours():
    from scribe_engine.adapters import ADAPTERS, LIGHT_TIMEOUT_S

    assert ADAPTERS["homr"].timeout_s == 900 < LIGHT_TIMEOUT_S
    assert all(f.startswith("homr/") and f.endswith(".zip") for f in ADAPTERS["homr"].model_files)


def test_without_the_recogniser_the_profiles_are_not_offered_and_a_job_is_refused(client, settings, monkeypatch):
    monkeypatch.setattr(sheet, "reader_installed", lambda adapters_dir: False)
    assert not {"sheet", "sheet-tab"} & {p["name"] for p in client.get("/v1/profiles").json()}
    r = client.post("/v1/jobs/pages", files=[("files", ("page.png", PNG, "image/png"))])
    assert (r.status_code, r.json()["code"]) == (503, "reader_missing")
    assert not list(settings.uploads_dir.iterdir())


def test_the_recognisers_environment_is_looked_for_where_its_runner_keeps_it(tmp_path, monkeypatch):
    from scribe_engine import adapters

    root = tmp_path / "repo" / "ml" / "adapters"
    (root / "homr").mkdir(parents=True)
    for runner, made in (("uv", root / "homr" / ".venv"), ("pixi", tmp_path / "repo" / ".pixi" / "envs" / "homr")):
        monkeypatch.setenv("SCRIBE_ADAPTER_RUNNER", runner)
        assert not adapters.environment_installed(root, "homr")
        made.mkdir(parents=True)
        assert adapters.environment_installed(root, "homr")


def test_the_wrong_kind_of_input_is_refused_with_its_code(client, audio, settings):
    # A picture for a profile that listens, and a recording for one that reads.
    r = client.post("/v1/jobs/pages", files=[("files", ("page.png", PNG, "image/png"))], data={"profile": "solo"})
    assert (r.status_code, r.json()["code"]) == (415, "wrong_input")
    assert not list(settings.uploads_dir.iterdir())  # refused before the page was kept
    r = client.post("/v1/jobs/upload", files={"file": ("song.wav", audio.read_bytes())}, data={"profile": "sheet"})
    assert (r.status_code, r.json()["code"]) == (415, "wrong_input")
    r = client.post("/v1/jobs/pages", files=[("files", ("page.png", PNG, "image/png"))], data={"profile": "sheet", "instrument": "guitar-6"})
    assert (r.status_code, r.json()["code"]) == (422, "invalid_options")
    assert client.post("/v1/jobs/pages", files=[("files", ("page.png", PNG, "image/png"))], data={"profile": "nope"}).status_code == 422
