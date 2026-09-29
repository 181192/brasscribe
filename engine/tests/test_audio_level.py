"""The engine's MP3 leveller: its loudness meter against the shared pyloudnorm vectors, and the limiter's ceiling."""

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from brasscribe_engine import audio_level

REPO = Path(__file__).resolve().parents[2]
VECTORS = REPO / "sounds" / "output-stage-vectors.json"


def _cases():
    sys.path.insert(0, str(REPO / "sounds"))
    import playback_levels  # stdlib only
    return playback_levels


@pytest.mark.skipif(not VECTORS.exists(), reason="sounds/output-stage-vectors.json not found")
def test_meter_matches_the_shared_loudness_vectors():
    pl = _cases()
    for case in json.loads(VECTORS.read_text())["loudness"]:
        got = audio_level.integrated_lufs(pl.render_case(case), case["rate"])
        if case["lufs"] is None:
            assert not math.isfinite(got), case["name"]
        else:
            assert abs(got - case["lufs"]) < 0.1, (case["name"], got, case["lufs"])


def test_limiter_matches_the_shared_curve():
    pl = _cases()
    levels = json.loads((REPO / "sounds" / "playback-levels.json").read_text())["limiter"]
    xs = np.array([0.0, 0.5, 0.8, 0.9, -1.2, 4.0])
    got = audio_level.limit(xs, levels["threshold"], levels["ceiling"])
    want = [pl.limit(float(x), levels["threshold"], levels["ceiling"]) for x in xs]
    assert np.allclose(got, want, atol=1e-12)


def test_a_hot_mp3_lands_on_the_target_under_the_ceiling(tmp_path):
    sf = pytest.importorskip("soundfile")
    if "MP3" not in sf.available_formats():
        pytest.skip("libsndfile without MP3")
    rate = 44100
    t = np.arange(rate * 6) / rate
    x = 0.99 * np.sign(np.sin(2 * np.pi * 220 * t)) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t)) ** 2
    mp3 = tmp_path / "brass-band.mp3"
    sf.write(str(mp3), np.stack([x, x], axis=1).astype(np.float32), rate, format="MP3")
    levels = audio_level.levels_path()
    info = audio_level.level_mp3(mp3, tmp_path / "missing.musicxml", levels)
    ceiling = json.loads(levels.read_text())["limiter"]["ceiling"]
    assert info["target_lufs"] == json.loads(levels.read_text())["band"]["phrase_lufs"]
    assert abs(info["lufs_after"] - info["target_lufs"]) < 1.0, info
    assert info["peak_dbfs_after"] <= 20 * math.log10(ceiling) + 1e-6, info
