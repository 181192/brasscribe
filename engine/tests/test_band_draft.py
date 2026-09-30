"""brass-band with muscriptor=False: the draft the Play apps make on the device (Basic Pitch on the mix in every
MuScriptor slot, Beat This! small0 beats), so the device's draft has a reference on the computer."""

from pathlib import Path

from brasscribe_engine import profiles, tuning


def test_the_draft_runs_basic_pitch_alone_with_the_small_beat_tracker():
    p = profiles.build("brass-band", Path("band.wav"), params={"muscriptor": False})
    assert [s.name for s in p.stages] == ["beats", "transcribe.mix.basic-pitch", "arrange", "export"]
    assert p.stage("beats").params["env"] == {"BEAT_THIS_MODEL": "small0"}
    arrange = p.stage("arrange").inputs
    assert "melody_support" not in arrange
    for slot in ("melody", "bass", "harmony0"):
        assert (arrange[slot].stage, arrange[slot].file) == ("transcribe.mix.basic-pitch", "mix-bp.mid")
    assert p.stage("transcribe.mix.basic-pitch").derive is None  # as on the device, which does not retune


def test_the_full_score_still_uses_muscriptor():
    p = profiles.build("brass-band", Path("band.wav"))
    names = [s.name for s in p.stages]
    assert "transcribe.mix.muscriptor" in names and "env" not in p.stage("beats").params
    arrange = p.stage("arrange").inputs
    assert arrange["melody"].stage == "transcribe.mix.muscriptor"
    assert arrange["melody_support"].stage == "transcribe.mix.basic-pitch"
    assert p.stage("transcribe.mix.basic-pitch").derive is tuning.derive


def test_the_draft_takes_the_same_options(tmp_path):
    for lineup in ("minimal", "quartet"):
        params = profiles.build("brass-band", tmp_path / "b.wav", params={"muscriptor": False, "lineup": lineup}) \
            .stage("arrange").params
        assert params["arrangement"]["lineup"] == lineup
