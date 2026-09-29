"""The pop-rock profile arranges its Percussion part for the pop kit; every other profile keeps the band kit."""

from pathlib import Path

from brasscribe_engine import profiles
from brasscribe_engine.stages import _supported


def test_pop_rock_asks_for_the_pop_kit():
    params = profiles.build("pop-rock", Path("song.wav"), params={}).stage("arrange").params
    assert params["arrangement"]["kit"] == "pop"


def test_other_profiles_keep_the_band_kit_and_their_cache_keys():
    for name in ("brass-band", "orchestra-with-soloist", "solo"):
        params = profiles.build(name, Path("song.wav"), params={}).stage("arrange").params
        assert "kit" not in params.get("arrangement", {}), name


def test_both_arrangers_take_the_kit():
    # _arrangement_flags fails a stage whose arranger does not list the flag.
    for module in ("brasscribe_eval.arrange_song", "brasscribe_eval.arrange_layers_song"):
        assert "--kit" in _supported(module), module
