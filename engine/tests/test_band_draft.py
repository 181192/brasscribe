"""brass-band with muscriptor=False: the draft the Play apps make on the device (Basic Pitch on the mix in every
MuScriptor slot, Beat This! small0 beats), so the device's draft has a reference on the computer."""

from pathlib import Path

from types import SimpleNamespace

from brasscribe_engine import profiles, tuning


def test_the_draft_runs_basic_pitch_alone_with_the_small_beat_tracker():
    p = profiles.build("brass-band", Path("band.wav"), params={"muscriptor": False})
    assert [s.name for s in p.stages] == ["beats", "transcribe.mix.basic-pitch", "arrange", "export"]
    assert p.stage("beats").params == {"model": "small0"}
    arrange = p.stage("arrange").inputs
    assert "melody_support" not in arrange
    for slot in ("melody", "bass", "harmony0"):
        assert (arrange[slot].stage, arrange[slot].file) == ("transcribe.mix.basic-pitch", "mix-bp.mid")
    assert p.stage("transcribe.mix.basic-pitch").derive is None  # as on the device, which does not retune


def _beat_adapter_call(profile: str, params: dict, tmp_path) -> dict:
    """Runs the profile's beats stage with a stub in the adapter's place; what the adapter was called with."""
    stage = profiles.build(profile, tmp_path / "band.wav", params=params).stage("beats")
    seen = {}

    def adapter(name, src, dst, env=None):
        seen.update(name=name, src=src, dst=dst, env=env)

    stage.run(SimpleNamespace(stage=stage, params=stage.params, inputs={"audio": tmp_path / "band.wav"}, out=tmp_path, adapter=adapter))
    return seen


def test_the_beat_model_reaches_the_adapter(tmp_path):
    # The adapter falls back to its own model (final0) when BEAT_THIS_MODEL does not reach it.
    draft = _beat_adapter_call("brass-band", {"muscriptor": False}, tmp_path)
    assert (draft["name"], draft["dst"], draft["env"]) == ("beat-this", tmp_path / "mix.beats", {"BEAT_THIS_MODEL": "small0"})
    assert _beat_adapter_call("solo", {}, tmp_path)["env"] == {"BEAT_THIS_MODEL": "small0"}
    assert _beat_adapter_call("brass-band", {}, tmp_path)["env"] is None


def test_the_draft_never_takes_beats_from_another_model(tmp_path):
    # A song-pipeline directory's mix.beats is the adapter's own model's: the draft makes its own.
    assert profiles.build("brass-band", tmp_path / "b.wav", params={"muscriptor": False}).stage("beats").reuse_subdir is None
    assert profiles.build("brass-band", tmp_path / "b.wav").stage("beats").reuse_subdir == "."


def test_the_full_score_still_uses_muscriptor():
    p = profiles.build("brass-band", Path("band.wav"))
    names = [s.name for s in p.stages]
    assert "transcribe.mix.muscriptor" in names and p.stage("beats").params == {}
    arrange = p.stage("arrange").inputs
    assert arrange["melody"].stage == "transcribe.mix.muscriptor"
    assert arrange["melody_support"].stage == "transcribe.mix.basic-pitch"
    assert p.stage("transcribe.mix.basic-pitch").derive is tuning.derive


def test_the_draft_takes_the_same_options(tmp_path):
    for lineup in ("minimal", "quartet"):
        params = profiles.build("brass-band", tmp_path / "b.wav", params={"muscriptor": False, "lineup": lineup}) \
            .stage("arrange").params
        assert params["arrangement"]["lineup"] == lineup
