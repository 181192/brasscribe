"""Offline reference renderer for the realistic sound tier.

    uv run --project sounds python sounds/render.py SCORE.musicxml|SCORE.mid -o OUT_DIR
        [--tier realistic|baseline] [--engine sfizz|fluidsynth] [--room central-hall]
        [--listener audience|conductor] [--no-humanize]

Pipeline (the native players are expected to reproduce each stage):
  1. MusicXML -> concert-pitch MIDI with the MuseScore CLI (same timing as MuseScore's own audio).
  2. Split by MIDI track into score parts; map parts to built instruments (sounds/mapping.json).
  3. Humanize deterministically per player: onset jitter, velocity jitter, a fixed detune
     (pitch bend) and a fixed lag, so unison desks never sum as sample clones.
  4. Articulation: a note uses the staccato instrument only when it is at most 0.3 s long and
     lasts under 60% of the time to the next onset; everything else uses the sustain.
  5. Per-player sampler render: sfizz_render with the SFZ (reference) or FluidSynth with the SF2.
     Percussion is rendered with MS Basic through FluidSynth in every tier.
  6. Placement (sounds/seating.json): distance delay and 1/r gain, bell directivity shelf,
     constant-power panning with a small interaural delay and far-ear shadow, and
     first-order early reflections from a shoebox stage model.
  7. Late reverb: convolution with the stereo-decoded OpenAIR IR, direct sound removed.
  8. Loudness-normalise to -16 LUFS (peak <= -1 dBFS) and write WAV + MP3 + dry stems.

The baseline tier renders every part with MS Basic (General MIDI) through FluidSynth,
dry and centre-panned per MuseScore's own mixer defaults, for per-part comparison.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import mido
import numpy as np
import pyloudnorm
import soundfile as sf
import soxr
from scipy import signal

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from dsp import SR, apply_eq  # noqa: E402

BUILT = ROOT / "data" / "sounds" / "built"
RAW = ROOT / "data" / "sounds" / "raw"
MSBASIC = RAW / "msbasic" / "MS Basic.sf3"
SFIZZ = Path(os.environ.get("SFIZZ_RENDER", ROOT / "data" / "sounds" / "tools" / "bin" / "sfizz_render"))
SPEED_OF_SOUND = 343.0
STAC_MAX_S = 0.30
STAC_GATE = 0.6  # note length / time to the next onset below which a short note counts as detached
TARGET_LUFS = -16.0

# Stereo IRs derived from the OpenAIR downloads. B-format (FuMa W,X,Y,Z) is decoded to two
# virtual cardioids at +-55 degrees.
ROOMS = {
    "central-hall": {"zip": "central-hall-university-york", "file": "b-format/ir_centre_stalls.wav", "kind": "bformat",
                     "shoebox": {"width": 22.0, "back_wall_y": 8.5, "ceiling": 11.0}},
    "jack-lyons": {"zip": "jack-lyons-concert-hall-university-york", "file": "b-format/rir_jack_lyons_lp2_96k.wav",
                   "kind": "bformat", "shoebox": {"width": 20.0, "back_wall_y": 8.0, "ceiling": 12.0}},
    "jack-lyons-conductor": {"zip": "jack-lyons-concert-hall-university-york", "file": "b-format/rir_jack_lyons_lp1_96k.wav",
                             "kind": "bformat", "shoebox": {"width": 20.0, "back_wall_y": 8.0, "ceiling": 12.0}},
    "dixon-studio": {"zip": "dixon-studio-theatre-university-york", "file": "b-format/r1_rir_bformat.wav",
                     "kind": "bformat", "shoebox": {"width": 14.0, "back_wall_y": 8.5, "ceiling": 7.0}},
    "ncem": {"zip": "st-margarets-church-ncem-5-piece-band-spatial-measurements",
             "file": ["stereo/3_c414_l.wav", "stereo/3_c414_r.wav"], "kind": "pair",
             "shoebox": {"width": 12.0, "back_wall_y": 8.5, "ceiling": 10.0}},
    "usina": {"zip": "usina-del-arte-symphony-hall", "file": "stereo/usina_main_s1_p3.wav", "kind": "stereo",
              "shoebox": {"width": 26.0, "back_wall_y": 9.0, "ceiling": 14.0}},
}
CRITICAL_DISTANCE_M = 5.0  # direct and reverberant energy are equal at this distance


@dataclass
class Note:
    start: float
    end: float
    pitch: int
    velocity: int


@dataclass
class Part:
    name: str
    program: int
    channel: int
    notes: list[Note] = field(default_factory=list)


# ------------------------------------------------------------------ score input

def to_midi(score: Path, work: Path) -> Path:
    if score.suffix.lower() in (".mid", ".midi"):
        return score
    out = work / (score.stem + ".mid")
    subprocess.run(["mscore", "-o", str(out), str(score)], capture_output=True)  # exits non-zero after writing
    if not out.exists():
        raise SystemExit(f"MuseScore did not write {out}")
    return out


def fix_name(s: str) -> str:
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def read_parts(midi_path: Path) -> tuple[list[Part], float]:
    mid = mido.MidiFile(str(midi_path))
    tempo_map = []  # (tick, tempo)
    tick = 0
    for msg in mido.merge_tracks(mid.tracks):
        tick += msg.time
        if msg.type == "set_tempo":
            tempo_map.append((tick, msg.tempo))
    if not tempo_map or tempo_map[0][0] > 0:
        tempo_map.insert(0, (0, 500000))

    def seconds(t: int) -> float:
        s, last_t, last_tempo = 0.0, 0, tempo_map[0][1]
        for tt, tempo in tempo_map[1:]:
            if tt >= t:
                break
            s += (tt - last_t) * last_tempo / 1e6 / mid.ticks_per_beat
            last_t, last_tempo = tt, tempo
        return s + (t - last_t) * last_tempo / 1e6 / mid.ticks_per_beat

    parts = []
    for tr in mid.tracks:
        name = next((fix_name(m.name) for m in tr if m.type == "track_name"), "")
        notes, on, tick, program, channel = [], {}, 0, 0, None
        for m in tr:
            tick += m.time
            if m.type == "program_change" and channel is None:
                program = m.program
            if m.type == "note_on" and m.velocity > 0:
                channel = m.channel
                on.setdefault(m.note, []).append((tick, m.velocity))
            elif m.type in ("note_off", "note_on") and on.get(m.note):
                t0, v = on[m.note].pop(0)
                notes.append(Note(seconds(t0), seconds(tick), m.note, v))
        if name and notes:
            parts.append(Part(name, program, channel if channel is not None else 0, sorted(notes, key=lambda n: n.start)))
    return parts, mid.length


# ------------------------------------------------------------------ humanization

def humanize(notes: list[Note], seed: str, player: int, enabled: bool) -> tuple[list[Note], float]:
    """Returns (notes, detune cents). Deterministic per (part, player)."""
    if not enabled:
        return notes, 0.0
    rng = random.Random(f"{seed}/{player}")
    detune = [0.0, 4.0, -5.0, 3.0][player % 4] + rng.uniform(-1.5, 1.5)
    lag = rng.uniform(-0.006, 0.010)
    out = []
    for n in notes:
        dt = lag + rng.gauss(0, 0.006)
        v = int(np.clip(n.velocity + rng.randint(-5, 5), 1, 127))
        out.append(Note(max(0.0, n.start + dt), max(n.start + dt + 0.03, n.end + dt), n.pitch, v))
    return out, detune


def detached(notes: list[Note]) -> list[bool]:
    """Staccato when a note is short AND clearly separated from the next onset in the part.

    Scores without articulation marks export every quaver at full length, so length alone
    would play running melodic quavers as staccato; the gate ratio keeps them legato.
    """
    onsets = sorted({round(n.start, 4) for n in notes})
    out = []
    for n in notes:
        later = [t for t in onsets if t > n.start + 0.01]
        ioi = (later[0] - n.start) if later else None
        dur = n.end - n.start
        out.append(dur <= STAC_MAX_S and ioi is not None and dur / ioi < STAC_GATE)
    return out


def write_midi(path: Path, notes: list[Note], program: int = 0, channel: int = 0, bend_cents: float = 0.0,
               bank: int | None = None) -> None:
    tpb, tempo = 960, 500000  # 120 bpm: 1920 ticks per second
    mid = mido.MidiFile(ticks_per_beat=tpb)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    if bank is not None:
        tr.append(mido.Message("control_change", channel=channel, control=0, value=bank, time=0))
    tr.append(mido.Message("program_change", channel=channel, program=program, time=0))
    if bend_cents:
        tr.append(mido.Message("pitchwheel", channel=channel, pitch=int(round(bend_cents / 200 * 8191)), time=0))
    events = []
    notes = sorted(notes, key=lambda n: n.start)
    last_start: dict[int, float] = {}
    for n in reversed(notes):  # never let a note overlap the next note of the same pitch
        nxt = last_start.get(n.pitch)
        if nxt is not None and n.end > nxt - 0.005:
            n = Note(n.start, max(n.start + 0.01, nxt - 0.005), n.pitch, n.velocity)
        last_start[n.pitch] = n.start
        events.append((n.end, 0, mido.Message("note_off", channel=channel, note=n.pitch, velocity=0)))
        events.append((n.start, 1, mido.Message("note_on", channel=channel, note=n.pitch, velocity=n.velocity)))
    events.sort(key=lambda e: (e[0], e[1]))
    last = 0
    for t, _, m in events:
        tick = int(round(t * 1920))
        m.time = max(0, tick - last)
        last = max(last, tick)
        tr.append(m)
    tr.append(mido.MetaMessage("end_of_track", time=int(1920 * 1.5)))
    mid.save(str(path))


# ------------------------------------------------------------------ sampler engines

def read_mono(path: Path, length: int) -> np.ndarray:
    x, sr = sf.read(str(path), dtype="float64", always_2d=True)
    if sr != SR:
        x = soxr.resample(x, sr, SR)
    y = x.mean(axis=1)
    out = np.zeros(length)
    n = min(length, len(y))
    out[:n] = y[:n]
    return out


def render_sfizz(sfz: Path, midi: Path, wav: Path) -> None:
    subprocess.run([str(SFIZZ), "--sfz", str(sfz), "--midi", str(midi), "--wav", str(wav), "-s", str(SR), "-q", "3",
                    "--use-eot"],
                   check=True, capture_output=True)


def render_fluidsynth(sf2: Path, midi: Path, wav: Path, gain: float = 1.0) -> None:
    subprocess.run(["fluidsynth", "-ni", "-q", "-R", "0", "-C", "0", "-g", str(gain), "-r", str(SR), "-F", str(wav),
                    str(sf2), str(midi)], check=True, capture_output=True)


# ------------------------------------------------------------------ placement

def pan_player(x: np.ndarray, src: tuple[float, float], lst: tuple[float, float], bell: str, seating: dict,
               ref_dist: float = 1.0) -> np.ndarray:
    """Direct sound of one player at the listener: delay, 1/r, bell shelf, pan, ITD, head shadow."""
    dx, dy = src[0] - lst[0], src[1] - lst[1]
    dist = math.hypot(dx, dy, 1.2 - 1.2) or 0.5
    az = math.atan2(dx, dy)
    d = seating["bell_directivity"][bell]
    y = apply_eq(x, [{"type": "highshelf", "f": d["f"], "gain_db": d["highshelf_db"], "q": 0.7}]) if d["highshelf_db"] else x
    return stereo_image(y, az, dist, ref_dist)


def stereo_image(x: np.ndarray, az: float, dist: float, ref_dist: float = 1.0) -> np.ndarray:
    g = ref_dist / max(dist, 0.5)
    p = max(-1.0, min(1.0, math.sin(az) * 1.3))  # -1 left .. +1 right
    theta = (p + 1) * math.pi / 4
    gl, gr = math.cos(theta), math.sin(theta)
    itd = 0.00035 * math.sin(az)  # seconds; positive = right ear first
    base = int(round(dist / SPEED_OF_SOUND * SR))
    dl = base + max(0, int(round(itd * SR)))
    dr = base + max(0, int(round(-itd * SR)))
    shadow = abs(math.sin(az)) * 5.0  # dB above 2 kHz on the far ear
    far = apply_eq(x, [{"type": "highshelf", "f": 2000, "gain_db": -shadow, "q": 0.7}]) if shadow > 0.3 else x
    left = far if az > 0 else x
    right = far if az < 0 else x
    out = np.zeros((len(x) + max(dl, dr) + 1, 2))
    out[dl : dl + len(x), 0] += left * gl * g
    out[dr : dr + len(x), 1] += right * gr * g
    return out


def early_reflections(x: np.ndarray, src: tuple[float, float], lst: tuple[float, float], box: dict) -> np.ndarray:
    """First-order image sources: side walls, back wall of the stage, floor and ceiling."""
    h_src, h_lst = 1.2, 1.2
    w = box["width"] / 2
    images = [
        ((-2 * w - src[0], src[1]), 0.0, 0.65),  # left wall
        ((2 * w - src[0], src[1]), 0.0, 0.65),  # right wall
        ((src[0], 2 * box["back_wall_y"] - src[1]), 0.0, 0.7),  # stage back wall
        ((src[0], src[1]), -2 * h_src, 0.35),  # floor
        ((src[0], src[1]), 2 * (box["ceiling"] - h_src), 0.5),  # ceiling
    ]
    out = None
    for (ix, iy), dz, coef in images:
        dx, dy = ix - lst[0], iy - lst[1]
        dist = math.sqrt(dx * dx + dy * dy + (h_src + dz - h_lst) ** 2)
        y = stereo_image(apply_eq(x, [{"type": "lowpass", "f": 6000, "q": 0.707}]) * coef, math.atan2(dx, dy), dist)
        out = y if out is None else _add(out, y)
    return out


def _add(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if len(a) < len(b):
        a, b = b, a
    a = a.copy()
    a[: len(b)] += b
    return a


def room_ir(room: str) -> np.ndarray:
    """Stereo IR at SR with the direct sound and first 20 ms removed (placement supplies those)."""
    cache = BUILT / "rooms" / f"{room}.wav"
    if cache.exists():
        return sf.read(str(cache), dtype="float64")[0]
    spec = ROOMS[room]
    base = RAW / "openair" / spec["zip"]
    if spec["kind"] == "pair":
        chans = []
        for f in spec["file"]:
            x, sr = sf.read(str(base / f), dtype="float64", always_2d=True)
            chans.append(x[:, 0])
        n = min(map(len, chans))
        st = np.stack([c[:n] for c in chans], axis=1)
    else:
        x, sr = sf.read(str(base / spec["file"]), dtype="float64", always_2d=True)
        if spec["kind"] == "bformat":
            w, bx, by = x[:, 0], x[:, 1], x[:, 2]
            ang = math.radians(55)
            left = 0.5 * (math.sqrt(2) * w + bx * math.cos(ang) + by * math.sin(ang))
            right = 0.5 * (math.sqrt(2) * w + bx * math.cos(ang) - by * math.sin(ang))
            st = np.stack([left, right], axis=1)
        else:
            st = x[:, :2]
    if sr != SR:
        st = soxr.resample(st, sr, SR)
    peak = int(np.argmax(np.abs(st).sum(axis=1)))
    cut = peak + int(0.020 * SR)
    fade = int(0.015 * SR)
    ir = st[cut:].copy()
    ir[:fade] *= np.linspace(0, 1, fade)[:, None]
    tail = int(0.05 * SR)
    ir[-tail:] *= np.linspace(1, 0, tail)[:, None]
    ir /= math.sqrt(np.sum(ir ** 2) / 2)  # unit energy per channel
    cache.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(cache), ir.astype(np.float32), SR, subtype="FLOAT")
    return ir


# ------------------------------------------------------------------ main render

def player_positions(seat: dict, n: int, spread: float) -> list[tuple[float, float]]:
    if n == 1:
        return [(seat["x"], seat["y"])]
    # spread the desk along the arc tangent (perpendicular to the direction to the conductor)
    r = math.hypot(seat["x"], seat["y"]) or 1.0
    tx, ty = -seat["y"] / r, seat["x"] / r
    offs = np.linspace(-spread * (n - 1) / 2, spread * (n - 1) / 2, n)
    return [(seat["x"] + o * tx, seat["y"] + o * ty) for o in offs]


def render(args: argparse.Namespace) -> None:
    out = Path(args.out)
    (out / "stems").mkdir(parents=True, exist_ok=True)
    mapping = json.loads((HERE / "mapping.json").read_text())
    seating = json.loads((HERE / "seating.json").read_text())
    work = Path(tempfile.mkdtemp(prefix="brasscribe-render-"))
    midi = to_midi(Path(args.score), work)
    parts, length_s = read_parts(midi)
    n = int((length_s + 4.0) * SR)
    lst_spec = seating["listeners"][args.listener]
    lst = (lst_spec["x"], lst_spec["y"])

    jobs = []  # (part, player index, target, notes, detune, position)
    for p in parts:
        pm = mapping["parts"].get(p.name)
        if pm is None:
            print(f"warning: part {p.name!r} not in mapping.json, skipped", file=sys.stderr)
            continue
        seat = seating["seats"][pm["seat"]]
        players = pm["players"] if args.tier == "realistic" else [pm["players"][0]]
        pos = player_positions(seat, len(players), seating["player_spread_m"])
        for i, pl in enumerate(players):
            notes, detune = humanize(p.notes, p.name, i, args.humanize and args.tier == "realistic")
            jobs.append((p, i, pl["target"], notes, detune, pos[i]))

    def run(job):
        p, i, target, notes, detune, _ = job
        tag = f"{p.name.replace(' ', '_').replace('♭', 'b')}_{i}"
        if args.tier == "baseline" or target == "msbasic-drums":
            m = work / f"{tag}.mid"
            is_drum = p.channel == 9
            write_midi(m, notes, program=p.program, channel=9 if is_drum else 0)
            w = work / f"{tag}.wav"
            render_fluidsynth(MSBASIC, m, w, gain=0.5)
            return job, read_mono(w, n)
        acc = np.zeros(n)
        short = detached(notes)
        stac = [x for x, d in zip(notes, short) if d]
        sus = [Note(x.start, x.start + (x.end - x.start) * 0.97, x.pitch, x.velocity) for x, d in zip(notes, short) if not d]
        for art, ns in (("sus", sus), ("stac", stac)):
            if not ns:
                continue
            m = work / f"{tag}_{art}.mid"
            w = work / f"{tag}_{art}.wav"
            if args.engine == "sfizz":
                write_midi(m, ns, bend_cents=detune)
                render_sfizz(BUILT / target / f"{target}-{art}.sfz", m, w)
            else:
                write_midi(m, ns, program=0 if art == "sus" else 1, bend_cents=detune)
                render_fluidsynth(BUILT / target / f"{target}.sf2", m, w)
            acc += read_mono(w, n)
        return job, acc

    with cf.ThreadPoolExecutor(max(1, (os.cpu_count() or 4) // 2)) as ex:
        results = list(ex.map(run, jobs))

    mix = np.zeros((n + SR, 2))
    send = np.zeros(n)
    dry_stems: dict[str, np.ndarray] = {}
    box = ROOMS[args.room]["shoebox"]
    for (p, i, target, _, _, pos), dry in results:
        pm = mapping["parts"][p.name]
        g = 10 ** (pm.get("gain_db", 0.0) / 20)
        dry = dry * g
        dry_stems[p.name] = dry_stems.get(p.name, np.zeros(n)) + dry
        if args.tier == "baseline":
            mix[:n] += dry[:, None] * math.sqrt(0.5)
            continue
        seat = seating["seats"][pm["seat"]]
        direct = pan_player(dry, pos, lst, seat["bell"], seating)
        er = early_reflections(dry, pos, lst, box)
        placed = _add(direct, er)
        mix[: min(len(mix), len(placed))] += placed[: len(mix)]
        send += dry
    if args.tier == "realistic":
        ir = room_ir(args.room)
        # reverberant energy equals direct energy at the critical distance (1/r law, ref 1 m)
        wet_gain = 1.0 / CRITICAL_DISTANCE_M
        wet = np.stack([signal.oaconvolve(send, ir[:, c]) for c in range(2)], axis=1) * wet_gain
        mix = _add(mix, wet)
    for name, x in dry_stems.items():
        sf.write(str(out / "stems" / f"{name.replace(' ', '_').replace('♭', 'b')}.wav"), x.astype(np.float32), SR,
                 subtype="FLOAT")
    # trim trailing silence, normalise loudness
    alive = np.nonzero(np.abs(mix).max(axis=1) > 1e-4)[0]
    mix = mix[: alive[-1] + int(0.2 * SR)] if len(alive) else mix
    meter = pyloudnorm.Meter(SR)
    lufs = meter.integrated_loudness(mix)
    mix *= 10 ** ((TARGET_LUFS - lufs) / 20)
    peak = np.abs(mix).max()
    if peak > 10 ** (-1 / 20):
        mix *= 10 ** (-1 / 20) / peak
    name = f"{Path(args.score).stem}.{args.tier}"
    wav = out / f"{name}.wav"
    sf.write(str(wav), mix.astype(np.float32), SR, subtype="PCM_24")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "192k",
                    str(out / f"{name}.mp3")], check=True)
    info = {"score": str(args.score), "tier": args.tier, "engine": args.engine, "room": args.room,
            "listener": args.listener, "humanize": args.humanize, "players": len(jobs),
            "duration_s": round(len(mix) / SR, 2), "lufs_before_norm": round(lufs, 2),
            "lufs": round(meter.integrated_loudness(mix), 2), "peak_dbfs": round(20 * math.log10(np.abs(mix).max()), 2)}
    (out / f"{name}.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(info))
    shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("score")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--tier", choices=["realistic", "baseline"], default="realistic")
    ap.add_argument("--engine", choices=["sfizz", "fluidsynth"], default="sfizz")
    ap.add_argument("--room", choices=sorted(ROOMS), default="central-hall")
    ap.add_argument("--listener", default="audience")
    ap.add_argument("--no-humanize", dest="humanize", action="store_false")
    args = ap.parse_args()
    if args.engine == "sfizz" and args.tier == "realistic" and not SFIZZ.exists():
        raise SystemExit(f"{SFIZZ} missing: run sounds/tools/build-sfizz.sh or use --engine fluidsynth")
    render(args)


if __name__ == "__main__":
    main()
