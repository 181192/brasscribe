"""Talking score: every conformance vector in both languages, plus export from real MusicXML."""

import json
from pathlib import Path

import pytest

from brasscribe_engine import talking_score as T

ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads((ROOT / "docs" / "accessibility" / "talking-score-vectors.json").read_text())["cases"]


def _vector_call(c: dict, lang: str) -> str:
    """Same reading of a case as the Windows app's vector test: B-flat cornet, written key 2 sharps unless stated."""
    s = c.get("settings", {})
    settings = T.Settings(lang=lang, pitch_mode=s.get("pitch_mode", "written"), verbosity=s.get("verbosity", "standard"))
    cx = c.get("context", {})
    ctx = T.Context(cx.get("part"), cx.get("bar"), cx.get("pitch_mode"))
    pn = c.get("part")
    part = T.Part(name=(pn or {}).get("name") or ctx.part or "Solo Cornet", name_nb=(pn or {}).get("name_nb"),
                  instrument=(pn or {}).get("instrument") or "Cornet in B♭",
                  instrument_nb=(pn or {}).get("instrument_nb") or ("kornett i B" if pn is None else None),
                  transpose={"chromatic": -2, "diatonic": -1})
    b = c.get("bar") or {}
    region = None
    if b.get("free_region"):
        fr = b["free_region"]
        region = {k: fr[k] for k in ("start_bar", "end_bar", "start_s", "end_s")}
    key = b.get("key_fifths")
    bar = T.Bar(b.get("number") or ctx.bar or 1, 2 if key is None else key, key_changed=False,
                tempo_marked=b.get("tempo_bpm"), free_region=region,
                entering_region=bool((b.get("free_region") or {}).get("entering")), a_tempo=b.get("a_tempo", False),
                total_bars=128)
    return T.announce(part, bar, c["event"], ctx, settings)


@pytest.mark.parametrize("lang", ["en", "nb"])
@pytest.mark.parametrize("case", VECTORS, ids=[c["id"] for c in VECTORS])
def test_conformance_vector(case, lang):
    assert _vector_call(case, lang) == case["expected"][lang]


@pytest.mark.parametrize("written,chromatic,concert", [(2, -2, 0), (0, 3, -3), (3, -9, 0), (0, 0, 0)])
def test_concert_key_follows_transposition(written, chromatic, concert):
    assert T.concert_key(written, {"chromatic": chromatic}) == concert


def test_rounding_is_half_up_not_bankers():
    assert T.round_half_up(31.5) == 32 and T.round_half_up(0.5) == 1 and T.round_half_up(2.5) == 3
    assert T.round_half(2.6) == 2.5 and T.round_half(3.25) == 3.5


SMALL = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <work><work-title>Test tune</work-title></work>
  <part-list>
    <score-part id="P1"><part-name>Solo Cornet</part-name>
      <score-instrument id="I1"><instrument-name>Cornet in B♭</instrument-name></score-instrument></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>2</divisions><key><fifths>2</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time>
        <transpose><diatonic>-1</diatonic><chromatic>-2</chromatic></transpose></attributes>
      <direction><sound tempo="120"/></direction>
      <note><pitch><step>B</step><alter>-1</alter><octave>4</octave></pitch><duration>1</duration><voice>1</voice><type>eighth</type></note>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>eighth</type></note>
      <note><rest/><duration>2</duration><voice>1</voice><type>quarter</type></note>
      <note><pitch><step>G</step><octave>5</octave></pitch><duration>4</duration><voice>1</voice><type>half</type>
        <tie type="start"/><notations><tied type="start"/></notations></note>
    </measure>
    <measure number="2">
      <note><pitch><step>G</step><octave>5</octave></pitch><duration>8</duration><voice>1</voice><type>whole</type>
        <tie type="stop"/><notations><tied type="stop"/></notations></note>
    </measure>
    <measure number="3">
      <note><rest measure="yes"/><duration>8</duration><voice>1</voice></note>
    </measure>
    <measure number="4">
      <note><rest measure="yes"/><duration>8</duration><voice>1</voice></note>
    </measure>
  </part>
</score-partwise>
"""


def test_build_and_export_small_score():
    comp = {"ticks_per_beat": 24, "first_downbeat": 0, "beat_times": [0.0, 0.5, 1.0, 1.5, 2.0],
            "voices": [{"id": "solo", "role": "melody", "layer": "solo",
                        "notes": [{"pitch": 68, "start": 0, "dur": 12, "confidence": 0.55, "sources": ["swiftf0"]}]}],
            "free_regions": []}
    doc = T.build(SMALL, comp)
    assert doc["title"] == "Test tune" and doc["total_bars"] == 4
    ev = doc["parts"][0]["bars"][0]["events"][0]
    assert ev["concert"] == {"step": "A", "alter": -1, "octave": 4} and ev["confidence"] == 0.55
    lines = T.part_lines(doc, 0, T.Settings())
    assert lines[0] == ("Bar 1", ["bar 1, tempo 120, beat 1: B-flat 4, eighth note, uncertain",
                                  "beat 1 and: C-natural 5, eighth note",
                                  "beat 2: quarter rest",
                                  "beat 3: G 5, half note, tied to whole note in bar 2"])
    assert lines[1] == ("Bar 2", ["bar 2, beat 1: G 5 held, from bar 1 beat 3"])
    assert lines[2] == ("Bars 3–4", ["bars 3 to 4: rest, 2 bars"])
    nb = T.part_lines(doc, 0, T.Settings(lang="nb"))
    assert nb[0][1][0] == "takt 1, tempo 120, slag 1: B 4, åttendedelsnote, usikker"
    page = T.to_html(doc, T.Settings())
    assert page.startswith('<!DOCTYPE html>\n<html lang="en">') and "<h2>Solo Cornet</h2>" in page and "<h3>Bar 1</h3>" in page
    text = T.to_text(doc, T.Settings(lang="nb"))
    assert "Solokornett\n===========" in text and "  takt 3 til 4: pause, 2 takter" in text


GOLDEN = ROOT / "data" / "golden" / "mikkel-arranged-band"


@pytest.mark.skipif(not (GOLDEN / "brass-band.musicxml").exists(), reason="golden output not available")
def test_golden_score_builds_every_part():
    comp = json.loads((GOLDEN / "composition.json").read_text())
    doc = T.build(GOLDEN / "brass-band.musicxml", comp)
    assert len(doc["parts"]) == 18
    text = T.to_text(doc, T.Settings())
    assert "Solo Cornet" in text and "Percussion" in text
    lines = [x for _, ls in T.part_lines(doc, 1, T.Settings()) for x in ls]
    assert lines and all(x for x in lines)


COMPOUND_BARS = """<measure number="1">
      <attributes><divisions>2</divisions><key><fifths>2</fifths></key><time><beats>6</beats><beat-type>8</beat-type></time>
        <transpose><diatonic>-1</diatonic><chromatic>-2</chromatic></transpose></attributes>
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>eighth</type></note>
      <note><pitch><step>E</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>eighth</type></note>
      <note><pitch><step>F</step><alter>1</alter><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>eighth</type></note>
      <note><pitch><step>G</step><octave>5</octave></pitch><duration>2</duration><voice>1</voice><type>quarter</type></note>
      <note><pitch><step>A</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>eighth</type>
        <tie type="start"/><notations><tied type="start"/></notations></note>
    </measure>
    <measure number="2">
      <note><pitch><step>A</step><octave>5</octave></pitch><duration>6</duration><voice>1</voice><type>half</type><dot/>
        <tie type="stop"/><notations><tied type="stop"/></notations></note>
    </measure>
  """


def test_compound_time_names_eighths_not_triplets():
    # In 6/8 the beat is a dotted quarter: its eighths are named within the beat, not as triplets,
    # and the position a tie is held from keeps that naming.
    start, end = SMALL.index('<measure number="1">'), SMALL.index("</part>")
    doc = T.build(SMALL[:start] + COMPOUND_BARS + SMALL[end:], None)
    pos = [e["pos"] for e in doc["parts"][0]["bars"][0]["events"]]
    assert pos[1] == {"beat": 1, "num": 1, "den": 3, "compound": True}
    lines = T.part_lines(doc, 0, T.Settings())
    assert lines[0][1] == ["bar 1, beat 1: D 5, eighth note",
                           "beat 1, eighth 2: E 5, eighth note",
                           "beat 1, eighth 3: F-sharp 5, eighth note",
                           "beat 2: G 5, quarter note",
                           "beat 2, eighth 3: A 5, eighth note, tied to dotted half note in bar 2"]
    assert lines[1][1] == ["bar 2, beat 1: A 5 held, from bar 1 beat 2, eighth 3"]
    nb = T.part_lines(doc, 0, T.Settings(lang="nb"))
    assert nb[0][1][1] == "slag 1, 2. åttendedel: E 5, åttendedelsnote"
    assert nb[1][1] == ["takt 2, slag 1: A 5 holdes, fra takt 1 slag 2, 3. åttendedel"]
