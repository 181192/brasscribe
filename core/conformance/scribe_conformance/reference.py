"""Run one conformance case through the Python reference (music/ + eval/ entry points).

The entry points are called as they are; only their MuseScore rendering
(PDF/MP3 via subprocess) is switched off, because it is not part of the
symbolic output under test.
"""

from __future__ import annotations

import json
import shutil
import sys
import warnings
from pathlib import Path

from .cases import REPO, Case, synth_layers

sys.path.insert(0, str(REPO / "eval"))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
from brasscribe_eval import arrange_bench, arrange_layers_song, arrange_song, lead_sheet  # noqa: E402
from brasscribe_eval.score import load_notes  # noqa: E402
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml  # noqa: E402
from brasscribe_music.quantize import quantize  # noqa: E402


class _NoSubprocess:
    @staticmethod
    def run(*_a, **_k):
        return None


for _m in (arrange_layers_song, arrange_song, lead_sheet):
    _m.subprocess = _NoSubprocess


def _main(mod, argv: list[str]) -> None:
    old = sys.argv
    sys.argv = ["reference", *argv]
    try:
        mod.main()
    finally:
        sys.argv = old


def run(case: Case, out: Path) -> None:
    """Writes the case's reference outputs into an emptied `out`, so none is left from an earlier run."""
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    a = case.args
    if case.kind == "meter":
        from brasscribe_music.beats import meter_of

        b = np.loadtxt(a["beats"], ndmin=2)
        pos = b[:, 1].astype(int)
        notes = json.loads(Path(a["notes"]).read_text())
        m = meter_of(b[:, 0], pos == 1, np.array([n["onset"] for n in notes]),
                     np.array([n["offset"] - n["onset"] for n in notes]), positions=pos)
        (out / "meter.json").write_text(json.dumps({
            "beats_per_bar": int(m.beats_per_bar), "first_downbeat": int(m.first_downbeat), "from_labels": bool(m.from_labels),
            "compound": bool(m.compound), "strength": float(m.strength),
            "times": None if m.times is None else [float(x) for x in m.times]}))
        return
    if case.kind == "layers":
        if "song" in a:
            synth_layers(a["song"], a["layers"])
        _main(arrange_layers_song, ["--layers", str(a["layers"]), "--beats", str(a["beats"]), "--out", str(out),
                                    "--title", a["title"], "--no-render",
                                    *(["--solo-contour", str(a["contour"])] if "contour" in a else []),
                                    *a.get("options", [])])
    elif case.kind == "song":
        _main(arrange_song, ["--beats", str(a["beats"]), "--melody", str(a["melody"]), "--melody-support", str(a["support"]),
                             "--bass", str(a["bass"]), "--harmony", *map(str, a["harmony"]), "--out", str(out),
                             "--title", a["title"], "--no-render", *a.get("options", [])])
    elif case.kind == "lead":
        _main(lead_sheet, ["--beats", str(a["beats"]), "--melody", str(a["melody"]), "--melody-support", str(a["support"]),
                           "--bass", str(a["bass"]), "--out", str(out / "lead.musicxml"), "--title", a["title"]])
    elif case.kind == "bench":
        from brasscribe_music.instruments import lineup_by_name

        opts = a.get("options", [])
        lineup = opts[opts.index("--lineup") + 1] if "--lineup" in opts else "minimal"
        comp = arrange_bench.composition_from_reference(a["reference"].parent, a["title"])
        if lineup != "minimal":
            comp.arrangement = {"lineup": lineup, "difficulty": "faithful", "transpose_semitones": 0}
        _, arr = arrange_bench.evaluate(comp, lineup_by_name(lineup))
        comp.to_json(out / "composition.json")
        write_musicxml(build_band_score(arr, comp), out / "brass-band.musicxml", band_sounds(arr))
    elif case.kind == "quant":
        ref = [r for r in load_notes(a["reference"]) if "quarter" in r]
        beats = np.loadtxt(a["beats"])[:, 0]
        q = quantize(ref, beats)
        rows = [{"pitch": x.pitch, "start": x.start, "end": x.end, "onset_s": x.onset_s, "offset_s": x.offset_s,
                 "confidence": x.confidence} for x in q]
        (out / "quant.json").write_text(json.dumps(rows, indent=1))
    else:
        raise ValueError(case.kind)
