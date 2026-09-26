"""Deterministic humanization of score notes for playback.

Timing and dynamics come from the Composition's performed fields where they exist
(onset_s against the performed beat map, performed_dur, articulations, velocity), and
from small seeded jitter otherwise. Every random value comes from a keyed hash, not from
a stateful generator, so the result does not depend on evaluation order and can be
reproduced bit-for-bit in another language. The algorithm is specified in
sounds/README.md ("Humanization"); keep the two in sync.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path

TPB = 24  # Composition ticks per beat
MASK64 = (1 << 64) - 1
MAX_DEV_S = 0.040  # clip for performed onset deviations
MIN_CONFIDENCE = 0.5
MATCH_RATE = 0.5
DETUNE_CENTS = (0.0, 4.0, -5.0, 3.0)


def fnv1a64(data: bytes) -> int:
    h = 0xCBF29CE484222325
    for b in data:
        h = ((h ^ b) * 0x100000001B3) & MASK64
    return h


def splitmix64(x: int) -> int:
    x = (x + 0x9E3779B97F4A7C15) & MASK64
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & MASK64
    return x ^ (x >> 31)


def uniform(key: str) -> float:
    """[0, 1) from the key: splitmix64(fnv1a64(utf8(key))) >> 11, times 2^-53."""
    return (splitmix64(fnv1a64(key.encode("utf-8"))) >> 11) * (1.0 / (1 << 53))


def tri(key: str) -> float:
    """Triangular on (-1, 1): uniform(key#a) + uniform(key#b) - 1."""
    return uniform(key + "#a") + uniform(key + "#b") - 1.0


@dataclass
class ScoreNote:
    """One part note: score position in Composition ticks plus its score-tempo seconds."""
    tick: int
    dur_tick: int
    start_s: float  # at the score tempo (MIDI tempo map)
    end_s: float
    pitch: int
    velocity: int


@dataclass
class PlayedNote:
    start: float
    end: float
    pitch: int
    velocity: int
    staccato: bool = False
    from_composition: bool = False


@dataclass
class Performance:
    """What the Composition says about how the music was played."""
    beat_times: list[float]
    first_downbeat: int
    tick_dev: dict[int, float] = field(default_factory=dict)  # D(s): median onset deviation per start tick
    voices: dict[str, dict[tuple[int, int], dict]] = field(default_factory=dict)  # voice -> (tick, pc) -> note
    roles: dict[str, str] = field(default_factory=dict)  # voice -> role

    @staticmethod
    def load(path: Path) -> Performance:
        d = json.loads(Path(path).read_text())
        perf = Performance(list(d.get("beat_times") or []), int(d.get("first_downbeat", 0)))
        devs: dict[int, list[float]] = {}
        for v in d.get("voices", []):
            table = perf.voices.setdefault(v["id"], {})
            perf.roles[v["id"]] = v.get("role", "")
            for n in v["notes"]:
                table.setdefault((n["start"], n["pitch"] % 12), n)
                dev = perf.deviation(n)
                if dev is not None:
                    devs.setdefault(n["start"], []).append(dev)
        perf.tick_dev = {t: clip(statistics.median(v), MAX_DEV_S) for t, v in devs.items()}
        return perf

    def beat_seconds(self, beat: float) -> float:
        """B(b): performed time of beat index b, piecewise linear, extrapolated with the end intervals."""
        bt = self.beat_times
        if len(bt) < 2:
            raise ValueError("Composition has fewer than two beat_times")
        if beat <= 0:
            return bt[0] + beat * (bt[1] - bt[0])
        last = len(bt) - 1
        if beat >= last:
            return bt[last] + (beat - last) * (bt[last] - bt[last - 1])
        i = int(beat)
        return bt[i] + (beat - i) * (bt[i + 1] - bt[i])

    def tick_seconds(self, tick: float) -> float:
        return self.beat_seconds(tick / TPB + self.first_downbeat)

    def deviation(self, n: dict) -> float | None:
        if n.get("onset_s") is None or n.get("confidence", 1.0) < MIN_CONFIDENCE or len(self.beat_times) < 2:
            return None
        return n["onset_s"] - self.tick_seconds(n["start"])

    def match_voice(self, notes: list[ScoreNote]) -> str | None:
        best, best_rate = None, 0.0
        for vid, table in self.voices.items():
            rate = sum((n.tick, n.pitch % 12) in table for n in notes) / max(1, len(notes))
            if rate > best_rate:
                best, best_rate = vid, rate
        return best if best_rate >= MATCH_RATE else None


def clip(x: float, lim: float) -> float:
    return max(-lim, min(lim, x))


def humanize(notes: list[ScoreNote], part: str, player: int, seed: str = "brasscribe",
             perf: Performance | None = None, timing: str = "score") -> tuple[list[PlayedNote], float, dict]:
    """Returns (played notes, detune in cents for the whole player, stats)."""
    if timing == "performed" and perf is None:
        raise ValueError("timing='performed' needs a Composition")
    notes = sorted(notes, key=lambda n: (n.tick, n.pitch))
    pkey = f"{seed}|{part}|{player}|-|"
    lag = 0.002 + 0.008 * tri(pkey + "lag")
    detune = DETUNE_CENTS[player % 4] + 1.5 * tri(pkey + "detune")
    voice = perf.match_voice(notes) if perf else None
    table = perf.voices[voice] if voice else {}
    # Only a part that plays the melody voice keeps that voice's own onset deviations (the
    # soloist leads); every other part takes the ensemble deviation D(s), so the band stays
    # together instead of reproducing transcription scatter between voices as asynchrony.
    own_timing = bool(voice and perf.roles.get(voice) == "melody")
    out, n_own, n_tick = [], 0, 0
    for i, n in enumerate(notes):
        key = f"{seed}|{part}|{player}|{i}|"
        m = table.get((n.tick, n.pitch % 12))
        own = perf.deviation(m) if (perf and m and own_timing) else None
        if own is not None:
            e, from_comp = clip(own, MAX_DEV_S), True
            n_own += 1
        elif perf and n.tick in perf.tick_dev:
            e, from_comp = perf.tick_dev[n.tick], True
            n_tick += 1
        else:
            e, from_comp = 0.0, False
        sigma = 0.004 if from_comp else 0.010
        if timing == "performed":
            base, span = perf.tick_seconds(n.tick), perf.tick_seconds(n.tick + n.dur_tick) - perf.tick_seconds(n.tick)
        else:
            base, span = n.start_s, n.end_s - n.start_s
        f = 1.0
        if m and m.get("performed_dur") and m.get("dur"):
            f = max(0.3, min(1.0, m["performed_dur"] / m["dur"]))
        onset = max(0.0, base + e + lag + sigma * tri(key + "onset"))
        end = onset + max(0.03, span * f)
        v0 = m["velocity"] if (m and m.get("velocity")) else n.velocity
        vel = max(1, min(127, round(v0 + 5 * tri(key + "vel"))))
        stac = bool(m and "staccato" in (m.get("articulations") or []))
        out.append(PlayedNote(onset, end, n.pitch, vel, stac, from_comp))
    stats = {"voice": voice, "own_timing": n_own, "ensemble_timing": n_tick, "jitter_only": len(notes) - n_own - n_tick,
             "lag_ms": round(lag * 1000, 2), "detune_cents": round(detune, 2)}
    return out, detune, stats
