"""Read-only views for Studio: registry, datasets, sources, arranger validation, MuseScore round trip."""

from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import tempfile
from pathlib import Path

from .config import Settings
from .names import valid_id

# Licences as recorded in docs/plan/apps-plan.md §7 and docs/research/00-summary.md §0/§3.
DATASETS = {
    "choralebricks-brass4": {"licence": "CC-BY 4.0", "source_url": "https://zenodo.org/records/20849469",
                             "download": "python -m brasscribe_eval.choralebricks (from the downloaded ChoraleBricks v1.1.0)"},
    "urmp-brass": {"licence": None, "source_url": None,
                   "download": "python -m brasscribe_eval.urmp (from the downloaded URMP dataset)"},
    "slakh-trumpet": {"licence": None, "source_url": None,
                      "download": "python -m brasscribe_eval.slakh (from the downloaded BabySlakh)"},
}


def _tree(root: Path) -> tuple[int, int]:
    size = files = 0
    for p in root.rglob("*"):
        if p.is_file():
            files += 1
            size += p.stat().st_size
    return size, files


def datasets(settings: Settings) -> list[dict]:
    root = settings.datasets_dir
    names = sorted(set(DATASETS) | ({p.name for p in root.iterdir() if p.is_dir()} if root.is_dir() else set()))
    out = []
    for name in names:
        d = root / name
        items = [p for p in d.iterdir() if (p / "reference.json").exists()] if d.is_dir() else []
        common = set.intersection(*({f.name for f in i.iterdir() if f.suffix in (".mid", ".beats")} for i in items)) \
            if items else set()
        size, files = _tree(d) if d.is_dir() else (0, 0)
        meta = DATASETS.get(name, {})
        out.append({"name": name, "path": str(d), "licence": meta.get("licence"), "source_url": meta.get("source_url"),
                    "bytes": size, "files": files, "items": len(items), "present": bool(items),
                    "cached_outputs": sorted(common), "download": meta.get("download")})
    return out


def sources(settings: Settings) -> list[dict]:
    import soundfile as sf

    def duration(p: Path) -> float | None:
        try:
            return round(sf.info(str(p)).duration, 3)
        except Exception:  # noqa: BLE001 - unreadable files just lack a duration
            return None

    out = []
    cap = settings.data_dir / "captures"
    for p in sorted(p for p in cap.glob("*.wav") if valid_id(p.name) and inside(cap, p)) if cap.is_dir() else []:
        out.append({"kind": "capture", "id": f"capture:{p.name}", "name": p.stem, "path": str(p), "dataset": None,
                    "duration_s": duration(p)})
    root = settings.datasets_dir
    for ds in sorted(p for p in root.iterdir() if valid_id(p.name) and p.is_dir()) if root.is_dir() else []:
        for item in sorted(ds.iterdir()):
            mix = item / "mix.wav"
            if valid_id(item.name) and inside(root, mix) and mix.exists():
                out.append({"kind": "dataset", "id": f"dataset:{ds.name}/{item.name}", "name": item.name,
                            "path": str(mix), "dataset": ds.name, "duration_s": duration(mix)})
    return out


def resolve_source(settings: Settings, source_id: str) -> Path | None:
    """The file behind an id from sources(): capture:<file> or dataset:<set>/<item>, each part a valid id."""
    kind, _, rest = source_id.partition(":")
    if kind == "capture" and valid_id(rest):
        root, p = settings.data_dir / "captures", settings.data_dir / "captures" / rest
    elif kind == "dataset" and rest.count("/") == 1 and all(map(valid_id, rest.split("/"))):
        root, p = settings.datasets_dir, settings.datasets_dir / rest / "mix.wav"
    else:
        return None
    return p if inside(root, p) and p.is_file() else None


def inside(root: Path, path: Path) -> bool:
    root, path = root.resolve(), path.resolve()
    return path == root or root in path.parents


# ------------------------------------------------------------- validation

_DROPPED = re.compile(r"^(?P<part>.+?): dropped (?P<pitch>\d+) at tick (?P<tick>-?\d+)")
_MOVED = re.compile(r"^(?P<part>.+?): moved (?P<pitch>\d+) to \d+ at tick (?P<tick>-?\d+)")
_FITTED = re.compile(r"^(?P<part>.+?): phrase at tick (?P<tick>-?\d+) (?:needed per-note octave fitting|split at its leaps to fit the range)")


def validation(composition: Path) -> list[dict]:
    """Arranger warnings for a run's Composition, located by bar and beat."""
    from brasscribe_music.arranger import arrange_composition
    from brasscribe_music.score_model import Composition

    comp = Composition.from_json(composition)
    arr = arrange_composition(comp)
    beats = comp.meters[0].beats if comp.meters else 4
    out = []
    for w in arr.warnings:
        m = _DROPPED.match(w) or _FITTED.match(w) or _MOVED.match(w)
        tick = int(m["tick"]) if m else None
        bar = beat = None
        if tick is not None:
            b = tick / comp.ticks_per_beat
            bar, beat = int(b // beats) + 1, round(b % beats + 1, 3)
        out.append({"part": m["part"] if m else None, "bar": bar, "beat": beat, "tick": tick, "kind": "range",
                    "severity": "error" if m and m.re is _DROPPED else "warning", "message": w})
    return out


# ------------------------------------------------------------- round trip

_LINE = re.compile(r"^(?P<name>.+?)\s+sound=(?P<sound>\S+)\s+notes=\s*(?P<n>\d+)\s+(?P<res>OK|MISMATCH)")
_DRUMS = re.compile(r"^(?P<name>.+?)\s+drum kit\s+events=\s*(?P<n>\d+)")


def roundtrip(outputs: Path) -> dict:
    """MuseScore round trip of a run's MusicXML (brasscribe_eval.musescore_roundtrip), run in a temp copy."""
    from brasscribe_eval.musescore_roundtrip import check

    from brasscribe_music import musescore

    mscore = musescore.binary()
    if not mscore:
        return {"status": "not_run", "musescore": None, "detail": "mscore (MuseScore CLI) not installed"}
    with tempfile.TemporaryDirectory() as tmp:
        for f in ("brass-band.musicxml", "composition.json"):
            shutil.copy(outputs / f, Path(tmp) / f)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = check(Path(tmp) / "brass-band.musicxml", Path(tmp) / "composition.json")
        from brasscribe_music.arranger import arrange, arrange_layers
        from brasscribe_music.score_model import Composition

        comp = Composition.from_json(Path(tmp) / "composition.json")
        arr = arrange_layers(comp) if any(v.layer for v in comp.voices) else arrange(comp)
    parts = []
    for line in buf.getvalue().splitlines():
        if m := _LINE.match(line):
            parts.append({"name": m["name"].strip(), "sound": m["sound"], "notes": int(m["n"]), "match": m["res"] == "OK"})
        elif m := _DRUMS.match(line):
            parts.append({"name": m["name"].strip(), "sound": None, "notes": int(m["n"]), "match": None})
    pitched = [p for p in parts if p["match"] is not None]
    notes_in = sum(len(notes) for name, notes in arr.parts.items() if name != "Percussion")
    return {"status": "pass" if ok else "fail", "musescore": mscore, "parts": len(parts),
            "notes_in": notes_in, "notes_out": sum(p["notes"] for p in pitched),
            "detail": None if ok else ", ".join(p["name"] for p in pitched if not p["match"]) + " differ",
            "part_results": parts}
