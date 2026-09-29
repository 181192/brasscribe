#!/usr/bin/env python3
"""The band kit, drum by drum and dynamic by dynamic, through two players: fits Apple's per-drum kit trims.

    python3 sounds/tools/kit_probe.py score OUT_DIR          # OUT_DIR/kit-probe/brass-band.musicxml
    python3 sounds/tools/kit_probe.py compare ALPHATAB.wav APPLE.wav

The score is one Percussion part (the arranger's drum instruments and <midi-unpitched> keys) at 60 bpm: for every
drum the arranger writes, one hit at each dynamic from pp to fff, two seconds apart. Render it with the Windows
harness (RenderHarnessTests.Render_scores, the -m12 file) and PlaybackKit's (renderScores, room-m12, hall off), then
compare: each hit's level (RMS of its first 1.5 s) on both, and per drum the median difference, which is the dB
Apple's kit trim for that drum is off by (band.apple_kit_trim_db in sounds/playback-levels.json).
"""
import sys
from pathlib import Path

# (GM key, display step, display octave, notehead, name), as the arranger's drum map writes them (musicxml.DRUM_MAP)
DRUMS = [
    (35, "E", 4, "normal", "Acoustic Bass Drum"), (36, "F", 4, "normal", "Bass Drum"), (37, "C", 5, "x", "Side Stick"),
    (38, "C", 5, "normal", "Snare Drum"), (40, "C", 5, "normal", "Electric Snare"), (41, "A", 4, "normal", "Low Floor Tom"),
    (42, "G", 5, "x", "Closed Hi-Hat"), (43, "A", 4, "normal", "Floor Tom"), (44, "D", 4, "x", "Pedal Hi-Hat"),
    (45, "D", 5, "normal", "Low Tom"), (46, "G", 5, "circle-x", "Open Hi-Hat"), (47, "D", 5, "normal", "Low-Mid Tom"),
    (48, "E", 5, "normal", "Hi-Mid Tom"), (49, "A", 5, "x", "Crash Cymbal"), (50, "E", 5, "normal", "High Tom"),
    (51, "F", 5, "x", "Ride Cymbal"), (52, "A", 5, "x", "Chinese Cymbal"), (53, "F", 5, "diamond", "Ride Bell"),
    (54, "B", 5, "x", "Tambourine"), (55, "A", 5, "x", "Splash Cymbal"), (56, "B", 5, "x", "Cowbell"),
    (57, "A", 5, "x", "Crash Cymbal 2"), (59, "F", 5, "x", "Ride Cymbal 2"),
]
DYNAMICS = ["pp", "p", "mf", "f", "ff", "fff"]
HIT_S = 2.0


def score() -> str:
    insts = "".join(f'<score-instrument id="I1-{k}"><instrument-name>{n}</instrument-name></score-instrument>' for k, *_, n in DRUMS)
    midis = "".join(f'<midi-instrument id="I1-{k}"><midi-channel>10</midi-channel><midi-unpitched>{k + 1}</midi-unpitched></midi-instrument>'
                    for k, *_ in DRUMS)
    bars = []
    for i, (k, step, octave, head, _) in enumerate(DRUMS):
        for j, dyn in enumerate(DYNAMICS):
            attrs = ""
            if i == 0 and j % 2 == 0 and j == 0:
                attrs = ('<attributes><divisions>1</divisions><time><beats>2</beats><beat-type>4</beat-type></time>'
                         '<clef><sign>percussion</sign></clef></attributes>'
                         '<direction><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>60</per-minute>'
                         '</metronome></direction-type><sound tempo="60"/></direction>')
            notehead = f"<notehead>{head}</notehead>" if head != "normal" else ""
            bars.append(f'<measure number="{len(bars) + 1}">{attrs}'
                        f'<direction><direction-type><dynamics><{dyn}/></dynamics></direction-type></direction>'
                        f'<note><unpitched><display-step>{step}</display-step><display-octave>{octave}</display-octave></unpitched>'
                        f'<duration>2</duration><instrument id="I1-{k}"/><type>half</type>{notehead}</note></measure>')
    return ('<?xml version="1.0" encoding="utf-8"?>\n<score-partwise version="4.0"><part-list><score-part id="P1">'
            f'<part-name>Percussion</part-name>{insts}{midis}</score-part></part-list><part id="P1">{"".join(bars)}</part>'
            '</score-partwise>\n')


def compare(at: str, ap: str) -> None:
    import numpy as np
    import soundfile as sf

    def levels(path: str) -> list[float]:
        x, sr = sf.read(path, dtype="float64", always_2d=True)
        m = x.mean(axis=1)
        out = []
        for i in range(len(DRUMS) * len(DYNAMICS)):
            seg = m[int(i * HIT_S * sr): int((i * HIT_S + 1.5) * sr)]
            out.append(10 * np.log10(np.mean(seg ** 2) + 1e-20))
        return out

    a, p = levels(at), levels(ap)
    print(f"{'drum':16}" + "".join(f"{d:>7}" for d in DYNAMICS) + "  median (Apple - alphaSynth, dB)")
    for i, (k, *_, name) in enumerate(DRUMS):
        d = [p[i * len(DYNAMICS) + j] - a[i * len(DYNAMICS) + j] for j in range(len(DYNAMICS))]
        print(f"{k:3} {name:12}" + "".join(f"{x:+7.1f}" for x in d) + f"  {float(np.median(d)):+6.1f}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["score"]:
        out = Path(sys.argv[2]) / "kit-probe"
        out.mkdir(parents=True, exist_ok=True)
        (out / "brass-band.musicxml").write_text(score(), encoding="utf-8")
        print(out / "brass-band.musicxml")
    elif sys.argv[1:2] == ["compare"]:
        compare(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(2)
