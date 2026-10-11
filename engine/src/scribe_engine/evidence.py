"""What each transcriber heard at the notes Brasscribe is unsure about, from a run's stage MIDI files."""

from __future__ import annotations

import json
from pathlib import Path

UNCERTAIN_BELOW = 0.7
# A model counts as hearing a note when it starts one within this window of the chosen onset.
ONSET_WINDOW_S = 0.12

MODEL_NAMES = {"swift-f0": "SwiftF0", "basic-pitch": "Basic Pitch", "muscriptor": "MuScriptor", "mega53": "MEGA53"}


def _stage_models(run_dir: Path) -> dict[str, list[tuple[str, Path]]]:
    """layer -> [(model, midi path)] for every finished transcribe.<layer>.<model> stage."""
    out: dict[str, list[tuple[str, Path]]] = {}
    stages = run_dir / "stages"
    for d in sorted(stages.glob("transcribe.*.*")) if stages.is_dir() else []:
        _, layer, model = d.name.split(".", 2)
        for mid in sorted(d.glob("*.mid")):
            out.setdefault(layer, []).append((model, mid))
    return out


def _notes(path: Path) -> list[tuple[float, float, int]]:
    import pretty_midi

    try:
        pm = pretty_midi.PrettyMIDI(str(path))
    except Exception:  # noqa: BLE001 - a missing or broken model output just gives no evidence
        return []
    return sorted((n.start, n.end, n.pitch) for inst in pm.instruments if not inst.is_drum for n in inst.notes)


def _heard(notes: list[tuple[float, float, int]], onset: float, pitch: int) -> dict:
    near = [n for n in notes if abs(n[0] - onset) <= ONSET_WINDOW_S]
    if not near:
        held = [n for n in notes if n[0] <= onset < n[1]]
        return {"pitch": held[0][2] if held else None, "agrees": bool(held) and held[0][2] == pitch}
    # In a polyphonic layer the melody's rival is the nearest pitch, not the lowest one sounding.
    best = min(near, key=lambda n: (abs(n[2] - pitch), abs(n[0] - onset)))
    return {"pitch": best[2], "agrees": best[2] == pitch}


def _layer_for(voice: dict, layers: dict[str, list]) -> str | None:
    for key in (voice.get("layer"), *voice.get("sources", []), voice.get("id")):
        if key in layers:
            return key
    candidates = [k for k in ("solo", "vocals", "mix") if k in layers]
    return candidates[0] if candidates and voice.get("role") == "melody" else None


def evidence(run_dir: Path) -> dict:
    comp_path = run_dir / "outputs" / "composition.json"
    if not comp_path.is_file():
        return {"models": [], "notes": []}
    comp = json.loads(comp_path.read_text())
    layers = _stage_models(run_dir)
    cache: dict[Path, list] = {}
    used: set[str] = set()
    notes = []
    for voice in comp.get("voices", []):
        uncertain = [n for n in voice.get("notes", []) if n.get("confidence", 1.0) < UNCERTAIN_BELOW]
        if not uncertain:
            continue
        sources = {s for n in uncertain for s in n.get("sources", [])}
        layer = _layer_for({**voice, "sources": sorted(sources)}, layers)
        models = layers.get(layer, []) if layer else []
        for n in uncertain:
            onset = n.get("onset_s")
            heard = []
            if onset is not None:
                for model, mid in models:
                    heard.append({"model": model, "name": MODEL_NAMES.get(model, model),
                                  **_heard(cache.setdefault(mid, _notes(mid)), onset, n["pitch"])})
                    used.add(model)
            notes.append({"voice": voice["id"], "start": n["start"], "pitch": n["pitch"], "confidence": n["confidence"],
                          "onset_s": onset, "models": heard})
    return {"models": [{"model": m, "name": MODEL_NAMES.get(m, m)} for m in sorted(used)], "notes": notes}
