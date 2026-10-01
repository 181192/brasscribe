"""Retune before transcribing: the tuning estimate, the resampling and the cache keys."""

from pathlib import Path

import numpy as np
import pretty_midi
import pytest
import soundfile as sf

from brasscribe_engine import profiles, runner, tuning
from brasscribe_engine.dag import SOURCE, Input, Stage

from .conftest import fake_pipeline
from .test_dag import run

SR = 44100
NOTES = (46, 53, 58, 62, 65, 70, 74)  # B♭2 to D5, the brass band's middle


def tones(cents: float, partials=lambda k: 1 / k, seconds: float = 1.0, notes=NOTES) -> np.ndarray:
    """Harmonic tones `cents` off A = 440, one after another, with a little noise."""
    t = np.arange(int(SR * seconds)) / SR
    out = []
    for m in notes:
        f0 = 440 * 2 ** ((m - 69) / 12) * 2 ** (cents / 1200)
        out.append(sum(partials(k) * np.sin(2 * np.pi * k * f0 * t) for k in range(1, 11) if k * f0 < SR / 2))
    x = np.concatenate(out)
    return (0.1 * x / np.abs(x).max() + 1e-4 * np.random.default_rng(0).standard_normal(len(x))).astype(np.float32)


@pytest.mark.parametrize("cents", [-30, -10, 0, 10, 30])
def test_estimate_finds_the_offset(cents):
    est, concentration = tuning.estimate(tones(cents), SR)
    assert est == pytest.approx(cents, abs=1.5)
    assert concentration > 0.8


def test_estimate_of_tones_with_strong_upper_partials_stays_below_the_threshold():
    # Equal partials 1-10: the 5th and 7th sit 14 and 31 cents flat of the grid and pull the estimate.
    est, _ = tuning.estimate(tones(0, partials=lambda k: 1.0), SR)
    assert abs(est) < tuning.THRESHOLD_CENTS


def test_noise_has_no_tuning():
    x = np.random.default_rng(1).standard_normal(SR * 3).astype(np.float32)
    _, concentration = tuning.estimate(x, SR)
    assert concentration < tuning.MIN_CONCENTRATION
    assert tuning.estimate(np.zeros(SR), SR) == (0.0, 0.0)


def test_decide():
    assert tuning.decide(3.9, 0.9) == 0
    assert tuning.decide(13.4, 0.9) == -13
    assert tuning.decide(-30.6, 0.9) == 31
    assert tuning.decide(30.0, 0.1) == 0


@pytest.mark.parametrize("cents", [-30, 10, 30])
def test_shift_audio_retunes_and_rescale_restores_the_timeline(tmp_path, cents):
    src = tmp_path / "in.wav"
    sf.write(src, tones(cents, seconds=0.5), SR)
    dst = tmp_path / "out.wav"
    q = tuning.shift_audio(src, dst, tuning.decide(cents, 1.0))
    y, sr = sf.read(dst)
    assert sr == SR
    assert tuning.estimate(y, sr)[0] == pytest.approx(0, abs=1.5)
    n = len(tones(cents, seconds=0.5))
    assert len(y) * float(q) == pytest.approx(n, abs=2)
    # A note at the end of the retuned audio lands at the end of the original after rescaling.
    mid = tmp_path / "t.mid"
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(0)
    inst.notes.append(pretty_midi.Note(80, 60, 1.0, len(y) / sr))
    pm.instruments.append(inst)
    pm.write(str(mid))
    tuning.rescale_midi(mid, float(q))
    note = pretty_midi.PrettyMIDI(str(mid)).instruments[0].notes[0]
    assert note.end == pytest.approx(n / SR, abs=0.003)
    assert note.start == pytest.approx(float(q), abs=0.003)


def test_ratio_is_exact_enough():
    for c in (-50, -13, 7, 45):
        assert 1200 * np.log2(float(tuning.ratio(c))) == pytest.approx(c, abs=0.01)


def test_derive_leaves_an_in_tune_input_alone(tmp_path):
    wav = tmp_path / "a.wav"
    sf.write(wav, tones(2), SR)
    params, facts = tuning.derive({"audio": wav})
    assert params == {} and facts["retuned"] is False and facts["tuning_cents"] == pytest.approx(2, abs=1.5)
    sf.write(wav, tones(-20), SR)
    params, facts = tuning.derive({"audio": wav})
    assert params["retune"]["shift_cents"] in (19, 20, 21) and facts["retuned"] is True
    params, facts = tuning.derive({"audio": tmp_path / "missing.wav"})
    assert params == {} and "tuning_error" in facts


def _with_derive(derive):
    """The test pipeline with a derive on the Basic Pitch stage."""
    p = fake_pipeline("T", {})
    s = p.stage("transcribe.mix.basic-pitch")
    s.derive = derive
    return p


def test_empty_derived_params_keep_the_key(settings, audio, tmp_path):
    plain, _ = run(settings, audio, tmp_path, "r0")
    r, _ = run(settings, audio, tmp_path, "r1", pipeline=_with_derive(lambda inputs: ({}, {"tuning_cents": 1.0})))
    assert {k: v.key for k, v in r.items()} == {k: v.key for k, v in plain.items()}
    assert r["transcribe.mix.basic-pitch"].status == "cached"
    assert r["transcribe.mix.basic-pitch"].record()["derived"] == {"tuning_cents": 1.0}


def test_derived_params_change_the_key_skip_reuse_and_reach_the_stage(settings, audio, tmp_path):
    reuse = tmp_path / "old-run"
    (reuse / "layers").mkdir(parents=True)
    (reuse / "layers" / "mix-sw.mid").write_bytes(b"precomputed sw")
    (reuse / "layers" / "mix-bp.mid").write_bytes(b"precomputed bp")
    seen = {}

    def run_stage(ctx):
        seen.update(ctx.params)
        (ctx.out / "mix-bp.mid").write_bytes(b"retuned")

    p = _with_derive(lambda inputs: ({"retune": {"shift_cents": -12}}, {"tuning_cents": 12.0, "retuned": True}))
    p.stage("transcribe.mix.basic-pitch").run = run_stage
    plain, _ = run(settings, audio, tmp_path, "r0")
    r, _ = run(settings, audio, tmp_path, "r1", pipeline=p, reuse_dir=reuse)
    assert r["transcribe.mix.swift-f0"].status == "cached"
    bp = r["transcribe.mix.basic-pitch"]
    assert bp.key != plain["transcribe.mix.basic-pitch"].key and bp.status == "ran"
    assert seen == {"output": "mix-bp.mid", "retune": {"shift_cents": -12}}


def test_manifest_records_the_tuning(settings, audio, monkeypatch):
    p = _with_derive(lambda inputs: ({}, {"tuning_cents": 4.2, "retuned": False}))
    monkeypatch.setitem(profiles.PROFILES, "test", profiles.Profile("test", "test", "", False, lambda title, params: p))
    m = runner.run(settings, audio, "test")
    assert m["tuning"] == {"transcribe.mix.basic-pitch": {"tuning_cents": 4.2, "retuned": False}}


def test_only_basic_pitch_on_the_brass_band_recording_is_retuned():
    audio = Path("take.wav")
    retuned = [(name, s.name) for name in profiles.PROFILES if name != "test"
               for s in profiles.build(name, audio).stages if s.derive is not None]
    assert retuned == [("brass-band", "transcribe.mix.basic-pitch")]


def test_transcribe_retunes_then_rescales(tmp_path):
    """tuning.transcribe on a sharp input: the adapter hears A = 440, the notes land on the original timeline."""
    src = tmp_path / "take.wav"
    x = tones(25, seconds=0.5)
    sf.write(src, x, SR)
    heard = {}

    class Ctx:
        out = tmp_path / "out"
        inputs = {"audio": src}
        params = {"output": "mix-bp.mid", "retune": {"shift_cents": -25}}
        stage = Stage("transcribe.mix.basic-pitch", "transcribe", {"audio": Input(SOURCE)}, tuning.transcribe,
                      adapter="basic-pitch")

        def log(self, message):
            pass

        def adapter(self, name, audio, dst, env=None):
            y, sr = sf.read(audio)
            heard["cents"] = tuning.estimate(y, sr)[0]
            pm = pretty_midi.PrettyMIDI()
            inst = pretty_midi.Instrument(0)
            inst.notes.append(pretty_midi.Note(80, 60, 0.0, len(y) / sr))
            pm.instruments.append(inst)
            pm.write(str(dst))

    Ctx.out.mkdir()
    tuning.transcribe(Ctx())
    assert heard["cents"] == pytest.approx(0, abs=1.5)
    note = pretty_midi.PrettyMIDI(str(Ctx.out / "mix-bp.mid")).instruments[0].notes[0]
    assert note.end == pytest.approx(len(x) / SR, abs=0.003)
    assert [p.name for p in Ctx.out.iterdir()] == ["mix-bp.mid"]



def test_estimate_file_reads_the_same_windows(tmp_path):
    x = np.stack([tones(12), tones(12)], axis=1)
    wav = tmp_path / "stereo.wav"
    sf.write(wav, x, SR, subtype="FLOAT")
    assert tuning.estimate_file(wav) == pytest.approx(tuning.estimate(x, SR), abs=1e-6)


def test_a_derive_that_raises_fails_its_stage(settings, audio, tmp_path):
    from brasscribe_engine.dag import StageFailed

    def boom(inputs):
        raise ValueError("unreadable")

    with pytest.raises(StageFailed, match="unreadable"):
        run(settings, audio, tmp_path, "r1", pipeline=_with_derive(boom))
