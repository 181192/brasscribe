"""Playback loudness: the output stage every Play app shares, and its test vectors.

    uv run --project sounds python sounds/playback_levels.py --vectors   # rewrite output-stage-vectors.json
    python3 sounds/playback_levels.py --check                            # CI: stdlib only

sounds/playback-levels.json holds the limiter curve, the band's loudness target and each app's
make-up gain, the rule for the original recording's target (the arrangement's estimated band
loudness) and the metronome's click level.
sounds/output-stage-vectors.json holds what the Apple, Android and Windows tests assert against:
limiter input -> output pairs, recording loudness -> gain pairs (for the fallback target and for
given targets), band estimate cases (pitched notes -> estimated band LUFS -> the recording's
target), two scores whose notes each app takes from its own score model, and loudness cases
(signals described by parameters, the expected integrated LUFS from pyloudnorm) for each app's meter.

    uv run --project sounds python sounds/playback_levels.py --calibrate   # the band estimate against its measurements

--check recomputes the limiter and gain vectors with the standard library and fails when the
vectors file is out of date with playback-levels.json.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEVELS = HERE / "playback-levels.json"
VECTORS = HERE / "output-stage-vectors.json"

LIMITER_INPUTS = [0.0, 0.1, -0.25, 0.5, 0.79, 0.8, -0.8, 0.81, 0.85, -0.9, 0.95, 1.0, -1.0, 1.2, 1.5, -2.0, 4.0, 50.0]
RECORDING_LUFS = [-40.0, -30.0, -28.0, -22.0, -16.0, -14.9, -10.0, -4.6, 5.0, None]
# (measured, target) -> gain, for an arrangement's target: the +12 dB cap and the -30 dB cut included.
RECORDING_FOR_TARGET = [(-40.0, -10.0), (-30.0, -12.0), (-22.0, -12.0), (-22.0, -20.0), (-14.9, -11.8), (-8.0, -16.0),
                        (5.0, -20.0), (None, -12.0)]
# Band estimate cases: pitched notes as [start, end, velocity] in quarter notes.
BAND_ESTIMATE_CASES = [
    {"name": "no notes", "notes": []},
    {"name": "one note at f", "notes": [[0, 4, 95]]},
    {"name": "one note at f, twice as long", "notes": [[0, 8, 95]]},
    {"name": "two parts in unison at f (+3 dB)", "notes": [[0, 4, 95], [0, 4, 95]]},
    {"name": "eighteen parts at f", "notes": [[0, 4, 95]] * 18},
    {"name": "eighteen parts at fff (clamped to the highest target)", "notes": [[0, 4, 127]] * 18},
    {"name": "eighteen parts at pp (clamped to the lowest target)", "notes": [[0, 4, 31]] * 18},
    {"name": "between knots (velocities 55 and 103)", "notes": [[0, 2, 55], [0, 2, 103]]},
    {"name": "below the lowest knot (velocity 5)", "notes": [[0, 1, 5]] * 18},
    {"name": "a gap is not counted", "notes": [[0, 2, 79], [10, 12, 79]]},
    {"name": "overlapping and nested notes", "notes": [[0, 3, 63], [1, 2, 111], [2.5, 6, 95], [7, 7.5, 47]]},
    {"name": "zero-length notes are left out", "notes": [[0, 4, 95], [2, 2, 127]]},
    {"name": "eight parts at ff", "notes": [[0, 4, 111]] * 8},
    {"name": "twelve parts at mf, then six more join at ff", "notes": [[0, 8, 79]] * 12 + [[4, 8, 111]] * 6},
]
# Scores (paths from the repository root) whose notes each app takes from its own score model.
BAND_ESTIMATE_SCORES = ["sounds/band-estimate-score.musicxml", "apps/fixtures/old-hundredth/brass-band.musicxml"]

# Loudness cases: sum of sines per channel, `segments` of (seconds, amplitude scale).
LOUDNESS_CASES = [
    {"name": "1 kHz stereo -20 dBFS 48 kHz", "rate": 48000, "channels": 2, "tones": [[1000.0, 0.1]], "segments": [[5.0, 1.0]]},
    {"name": "1 kHz stereo -20 dBFS 44.1 kHz", "rate": 44100, "channels": 2, "tones": [[1000.0, 0.1]], "segments": [[5.0, 1.0]]},
    {"name": "1 kHz mono -20 dBFS 22.05 kHz", "rate": 22050, "channels": 1, "tones": [[1000.0, 0.1]], "segments": [[5.0, 1.0]]},
    {"name": "100 Hz + 3 kHz stereo 44.1 kHz", "rate": 44100, "channels": 2, "tones": [[100.0, 0.3], [3000.0, 0.05]], "segments": [[4.0, 1.0]]},
    {"name": "loud then 40 dB down (relative gate)", "rate": 44100, "channels": 2, "tones": [[440.0, 0.5]],
     "segments": [[4.0, 1.0], [4.0, 0.01]]},
    {"name": "silence", "rate": 44100, "channels": 2, "tones": [[1000.0, 0.0]], "segments": [[2.0, 1.0]]},
]


def load_levels() -> dict:
    return json.loads(LEVELS.read_text())


def limit(x: float, threshold: float, ceiling: float) -> float:
    a = abs(x)
    if a <= threshold:
        return x
    knee = ceiling - threshold
    y = threshold + knee * math.tanh((a - threshold) / knee)
    return -y if x < 0 else y


def recording_gain_db(measured: float | None, rec: dict, target: float | None = None) -> float:
    """Gain that brings a recording measured at `measured` to `target` (default: the fallback target)."""
    if measured is None or not math.isfinite(measured):
        return 0.0
    t = rec["fallback_lufs"] if target is None else target
    return max(-rec["max_cut_db"], min(rec["max_boost_db"], t - measured))


def velocity_lufs(v: float, levels: dict) -> float:
    """L(v) of recording.band_estimate: the alphatab_lufs table, linear between its knots."""
    knots = sorted((int(k), float(x)) for k, x in levels["dynamics"]["sampler_velocity"]["alphatab_lufs"].items())
    if v <= knots[0][0]:
        return knots[0][1] + 20 * math.log10(max(v, 1e-9) / knots[0][0])
    for (v0, l0), (v1, l1) in zip(knots, knots[1:]):
        if v <= v1:
            return l0 + (l1 - l0) * (v - v0) / (v1 - v0)
    return knots[-1][1]


def band_estimate_lufs(notes, levels: dict) -> float | None:
    """Estimated band loudness of an arrangement from its pitched notes (start, end, velocity); None without notes."""
    ns = [(float(a), float(b), float(v)) for a, b, v in notes if b > a]
    if not ns:
        return None
    energy = sum((b - a) * 10 ** (velocity_lufs(v, levels) / 10) for a, b, v in ns)
    union, end = 0.0, -math.inf
    for a, b in sorted((a, b) for a, b, _ in ns):
        if b > end:
            union += b - max(a, end)
            end = b
    return levels["recording"]["band_estimate"]["offset_db"] + 10 * math.log10(energy / union)


def recording_target_lufs(estimate: float | None, rec: dict) -> float:
    """The recording's target for an arrangement's band estimate; the fallback when there is none."""
    if estimate is None or not math.isfinite(estimate):
        return rec["fallback_lufs"]
    return max(rec["min_target_lufs"], min(rec["max_target_lufs"], estimate))


def musicxml_notes(path: Path, levels: dict) -> list[tuple[float, float, int]]:
    """The pitched notes of a MusicXML score as (start, end, velocity) in quarter notes, by the dynamics
    rules: a mark holds in document order from where it is read, a part starts at the default, accents
    add steps. Percussion parts (any unpitched note), grace notes and rests are left out."""
    import xml.etree.ElementTree as ET
    dyn = levels["dynamics"]
    table = dyn["velocity"]
    out: list[tuple[float, float, int]] = []
    for part in ET.parse(path).getroot().findall("part"):
        vel, pos, onset, div = table[dyn["default"]], 0.0, 0.0, 1
        notes, percussion = [], False
        for measure in part.findall("measure"):
            for el in measure:
                marks = []
                if el.tag == "attributes" and el.find("divisions") is not None:
                    div = int(el.find("divisions").text)
                elif el.tag == "direction":
                    marks = el.findall("direction-type/dynamics")
                elif el.tag in ("backup", "forward"):
                    pos += (-1 if el.tag == "backup" else 1) * int(el.find("duration").text) / div
                elif el.tag == "note" and el.find("grace") is None:
                    marks = el.findall("notations/dynamics")
                for d in marks:
                    if len(d) and d[0].tag in table:
                        vel = table[d[0].tag]
                if el.tag != "note" or el.find("grace") is not None:
                    continue
                dur = int(el.find("duration").text) / div
                if el.find("chord") is None:
                    onset, pos = pos, pos + dur
                percussion |= el.find("unpitched") is not None
                if el.find("rest") is None and dur > 0:
                    accents = sum(n for a, n in dyn["accent_steps"].items() if el.find(f"notations/articulations/{a}") is not None)
                    notes.append((onset, onset + dur, max(1, min(127, vel + dyn["step"] * accents))))
        if not percussion:
            out += notes
    return out


def estimate_fields(notes, levels: dict) -> dict:
    e = band_estimate_lufs(notes, levels)
    return {"pitched_notes": sum(1 for a, b, _ in notes if b > a), "estimate_lufs": None if e is None else round(e, 6),
            "target_lufs": round(recording_target_lufs(e, levels["recording"]), 6)}


def stdlib_vectors(levels: dict) -> dict:
    lim = levels["limiter"]
    rec = levels["recording"]
    return {
        "limiter": [{"in": x, "out": round(limit(x, lim["threshold"], lim["ceiling"]), 9)} for x in LIMITER_INPUTS],
        "recording_gain": [{"lufs": v, "gain_db": round(recording_gain_db(v, rec), 6)} for v in RECORDING_LUFS],
        "recording_gain_for_target": [{"lufs": v, "target_lufs": t, "gain_db": round(recording_gain_db(v, rec, t), 6)}
                                      for v, t in RECORDING_FOR_TARGET],
        "band_estimate": [{**c, **estimate_fields(c["notes"], levels)} for c in BAND_ESTIMATE_CASES],
        "band_estimate_scores": [{"path": p, **estimate_fields(musicxml_notes(HERE.parent / p, levels), levels)}
                                 for p in BAND_ESTIMATE_SCORES],
    }


def render_case(case: dict):
    import numpy as np
    parts = []
    t0 = 0
    for secs, scale in case["segments"]:
        n = int(round(secs * case["rate"]))
        t = (np.arange(n) + t0) / case["rate"]
        x = sum(a * np.sin(2 * np.pi * f * t) for f, a in case["tones"]) * scale
        parts.append(x)
        t0 += n
    x = np.concatenate(parts).astype(np.float32).astype(np.float64)
    return np.stack([x] * case["channels"], axis=1)


def loudness_vectors() -> list[dict]:
    import pyloudnorm
    out = []
    for case in LOUDNESS_CASES:
        y = render_case(case)
        v = pyloudnorm.Meter(case["rate"]).integrated_loudness(y if case["channels"] > 1 else y[:, 0])
        out.append({**case, "lufs": round(float(v), 3) if math.isfinite(v) else None})
    return out


def check() -> list[str]:
    errors = []
    levels = load_levels()
    lim = levels["limiter"]
    if not 0 < lim["threshold"] < lim["ceiling"] < 1:
        errors.append("limiter: need 0 < threshold < ceiling < 1")
    if not VECTORS.exists():
        return errors + ["sounds/output-stage-vectors.json is missing: run sounds/playback_levels.py --vectors"]
    vec = json.loads(VECTORS.read_text())
    want = stdlib_vectors(levels)
    rec = levels["recording"]
    if not rec["min_target_lufs"] <= rec["fallback_lufs"] <= rec["max_target_lufs"]:
        errors.append("recording: need min_target_lufs <= fallback_lufs <= max_target_lufs")
    if any(vec.get(k) != v for k, v in want.items()) or vec.get("levels") != levels or [c["name"] for c in vec.get("loudness", [])] != [c["name"] for c in LOUDNESS_CASES]:
        errors.append("sounds/output-stage-vectors.json is out of date: run sounds/playback_levels.py --vectors")
    return errors


def calibrate() -> None:
    """The band estimate against what the apps measured: the golden arrangement (data/golden, when present)
    with its dynamics and at one velocity, and the full-band phrase (sounds/phrases.py)."""
    levels = load_levels()
    rows = []
    golden = HERE.parent / "data/golden/mikkel-arranged-band/brass-band.musicxml"
    if golden.exists():
        g = musicxml_notes(golden, levels)
        rows.append(("golden, its dynamics (Windows)", levels["band"]["arrangement_lufs"], g))
        rows.append(("golden, all at velocity 80 (Apple)", -15.95, [(a, b, 80) for a, b, _ in g]))
    sys.path.insert(0, str(HERE))
    from phrases import band_phrase  # needs mido and music/src
    mapping = json.loads((HERE / "mapping.json").read_text())
    band, _ = band_phrase(mapping)
    phrase = [(2 * a, 2 * b, v) for name, ns in band.items() if mapping["parts"][name]["instrument"] != "drum-kit" for a, b, _, v in ns]
    rows.append(("full-band phrase", levels["band"]["phrase_lufs"], phrase))
    for name, measured, notes in rows:
        e = band_estimate_lufs(notes, levels)
        print(f"{name}: {len(notes)} pitched notes, measured {measured:.2f}, estimate {e:.2f} ({e - measured:+.2f} LU)")


def main() -> None:
    if sys.argv[1:] == ["--calibrate"]:
        calibrate()
        return
    if sys.argv[1:] == ["--check"]:
        errors = check()
        for e in errors:
            print(e)
        sys.exit(1 if errors else 0)
    if sys.argv[1:] == ["--vectors"]:
        levels = load_levels()
        doc = {"about": "Generated by sounds/playback_levels.py --vectors from sounds/playback-levels.json. limiter: in -> out "
                        "(tolerance 1e-6); recording_gain: measured integrated LUFS (null: silent) -> gain dB for the "
                        "fallback target; recording_gain_for_target: the same for a given target; band_estimate: pitched "
                        "notes [start, end, velocity] in quarter notes -> the estimated band LUFS (null: no notes) and the "
                        "recording's target (tolerance 1e-6); band_estimate_scores: the same from a score's own notes, "
                        "taken by each app's score model (tolerance 0.01 LU); loudness: "
                        "sum of sines per channel (tones [Hz, amplitude]) over segments [seconds, amplitude scale], expected "
                        "integrated LUFS from pyloudnorm (tolerance 0.1 LU; null: -inf).",
               "levels": levels, **stdlib_vectors(levels), "loudness": loudness_vectors()}
        VECTORS.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {VECTORS}")
        return
    print(__doc__)


if __name__ == "__main__":
    main()
