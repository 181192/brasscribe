"""Write site/shared/research/measured/per-piece.json: the per-piece scores behind the means in eval/baselines.json.

`scribe bench` gates means over an eval set. The research pages also show how far the pieces spread
around a mean, so this script scores every piece with the suites' own code and saves the values.
It refuses to write when a mean of its values is not the gated baseline (beyond the gate's
tolerance): the file then describes other outputs than the ones the baselines were taken from.

    pixi run python site/shared/research/per_piece.py          # needs data/eval (see eval/README.md)

The site build reads the file and drops a spread whose mean no longer matches the baselines, so
run this again after a deliberate baseline change.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import mir_eval
import numpy as np
from scribe_eval.quant_bench import evaluate, reference_beats
from scribe_eval.score import load_notes, score
from scribe_eval.suites import SETS, _songs, load_baselines

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "measured" / "per-piece.json"
DATA = ROOT / "data"

# suite -> (eval set, models, metrics)
TRANSCRIPTION = {
    "chorales-transcription": ("chorales", ("basic-pitch", "muscriptor-medium", "muscriptor-large", "muscriptor-medium-brass"),
                               ("onset_f1", "onset100_f1")),
    "urmp-transcription": ("urmp", ("basic-pitch", "muscriptor-medium"), ("onset_f1", "onset100_f1")),
}
QUANT = {"quant-chorales": "chorales", "quant-urmp": "urmp"}
QUANT_KEYS = ("position_acc", "subdivision_acc", "duration_acc")


def main() -> None:
    suites = load_baselines()["targets"]["brass"]["suites"]
    tolerance = load_baselines()["tolerance"]
    out: dict[str, dict] = {}

    def keep(suite: str, key: str, values: list[float]) -> None:
        stored = suites[suite]["metrics"].get(key)
        if stored is None:
            return
        stored = stored["value"] if isinstance(stored, dict) else stored
        mean = sum(values) / len(values)
        if abs(mean - stored) > tolerance:
            raise SystemExit(f"{suite} {key}: mean of the pieces is {mean:.3f}, the baseline is {stored}")
        out.setdefault(suite, {})[key] = [round(v, 3) for v in values]

    for suite, (label, models, metrics) in TRANSCRIPTION.items():
        songs = _songs(DATA / "eval" / SETS[label])
        out.setdefault(suite, {})["pieces"] = len(songs)
        out[suite]["notes"] = sum(len(load_notes(s / "reference.json")) for s in songs)
        for model in models:
            rows = [score(load_notes(s / "reference.json"), load_notes(s / f"{model}.mid")) for s in songs]
            for metric in metrics:
                keep(suite, f"{model}.{metric}", [r[metric] for r in rows])
            # Recall per voice of the quartet: a mean over the pieces, which no suite gates.
            for voice in "SATB":
                for metric in (f"recall_{voice}", f"recall100_{voice}"):
                    if all(metric in r for r in rows):
                        out[suite][f"{model}.{metric}"] = round(sum(r[metric] for r in rows) / len(rows), 3)
    for suite, label in QUANT.items():
        songs = _songs(DATA / "eval" / SETS[label])
        out.setdefault(suite, {})["pieces"] = len(songs)
        given = [evaluate(s, None, beats_override=reference_beats(s)) for s in songs]
        tracked = [evaluate(s, None, "beat-this.beats") for s in songs if (s / "beat-this.beats").exists()]
        for name, rows in (("reference_beats", given), ("beat_this", tracked)):
            for key in QUANT_KEYS:
                keep(suite, f"{name}.{key}", [r[key] for r in rows])
        # The tracker's beats themselves, by the field's measure: F-measure within ±70 ms (mir_eval.beat), against
        # quarter-note beats interpolated from the notated positions of the reference notes. Not gated.
        # The same for a candidate tracker where its beats are stored beside the mix (md-beat-this.beats: md_beat_this,
        # model run1), with the note positions its beats give, scored as the gated ones are.
        for tracker, beats in (("beat_this", "beat-this.beats"), ("md_beat_this", "md-beat-this.beats")):
            have = [s for s in songs if (s / beats).exists()]
            if len(have) != len(songs):
                continue
            out[suite][f"{tracker}.beat_f"] = [
                round(float(mir_eval.beat.f_measure(mir_eval.beat.trim_beats(np.unique(reference_beats(s))),
                                                    mir_eval.beat.trim_beats(np.unique(np.loadtxt(s / beats)[:, 0])))), 3)
                for s in have]
            if tracker != "beat_this":
                rows = [evaluate(s, None, beats) for s in have]
                for key in QUANT_KEYS:
                    out[suite][f"{tracker}.{key}"] = [round(r[key], 3) for r in rows]

    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    doc = {
        "provenance": {
            "what": "Per-piece values of metrics whose means are gated in eval/baselines.json, in the order of the eval set's pieces; "
                    "the size of each set; and, as single numbers, each model's mean recall per voice of the quartets (S, A, T, B), "
                    "which the scorer reports and no suite gates; and the beat F-measure of the tracked beats per piece (±70 ms), not gated.",
            "command": "pixi run python site/shared/research/per_piece.py",
            "commit": commit,
            "data": "data/eval/choralebricks-brass4 and data/eval/urmp-brass with the cached model outputs the baselines were taken from",
        },
        "suites": out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
