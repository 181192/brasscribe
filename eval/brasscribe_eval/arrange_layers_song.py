"""Solo-with-band arrangement from textural layers (see brasscribe_music.arranger.arrange_layers).

Layers (from layers.py): solo (Mega-53 trumpet), bass, drums, and the orchestra
residual (mix minus solo, bass and drums). The orchestra is split by what the
notes do rather than by timbre, because the separators cannot tell this
recording's strings, keys and orchestral brass apart reliably:
  short notes attacked together with two or more others -> brass choir hits
  everything else -> strings (pads + countermelody)
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf
from brasscribe_music.arranger import FOOTER_LANGS, Arrangement, arrange_layers, composition_lineup, part_footers
from brasscribe_music import musescore
from brasscribe_music.energy import Envelope, gate
from brasscribe_music.durations import SEPARATED_STEM, Contour, apply_written, contour_offsets
from brasscribe_music.beats import clean_beats_gated, downbeat_rate, labels_on, solo_meter
from brasscribe_music.confidence import Model as CalibrationModel
from brasscribe_music.confidence import features as confidence_features
from brasscribe_music.confidence import p_correct, review_groups
from brasscribe_music.confidence import support as contour_support
from brasscribe_music.difficulty import KEY_CHANGE_PENALTY
from brasscribe_music.instruments import CLEF_READINGS, LEADS, PERCUSSION_SOLO, SEAT_IDS, check_reads, lead_lineup, lineup_by_name, seat_by_id
from brasscribe_music.keys import key_plan, semitones_to
from brasscribe_music.freetime import clip_to_regions, mark_fermatas, plan_free_time, unstable_runs
from brasscribe_music.musicxml import band_sounds, build_band_score, write_musicxml
from brasscribe_music.onsets import contour_notes
from brasscribe_music.parts import STYLE as PART_STYLE
from brasscribe_music.parts import split_parts
from brasscribe_music.structure import bar_features, letters, section_starts
from brasscribe_music.separation import check_stem
from brasscribe_music.quantize import TICKS_PER_BEAT, BeatMap, choose_level, quantize
from brasscribe_music.dynamics import layer_dynamics
from brasscribe_music.score_model import Dynamic, ReviewItem, Section, Articulation, Composition, KeySig, Meter, Note, Voice, VoiceRole
from brasscribe_music.spelling import key_of

from .arrange_song import to_notes
from .consensus import cluster
from .lead_sheet import line


def pitched(path: Path) -> list[dict]:
    """The pitched notes of a MIDI file; none when the file is absent (a solo take has only a solo layer)."""
    if not path.exists():
        return []
    pm = pretty_midi.PrettyMIDI(str(path))
    return [{"pitch": n.pitch, "onset": n.start, "offset": n.end} for i in pm.instruments if not i.is_drum for n in i.notes]


def drums_of(path: Path) -> list[dict]:
    if not path.exists():
        return []
    pm = pretty_midi.PrettyMIDI(str(path))
    return [{"pitch": n.pitch, "onset": n.start, "offset": n.end} for i in pm.instruments if i.is_drum for n in i.notes]


def split_orchestra(notes: list[Note]) -> tuple[list[Note], list[Note]]:
    """(hits, lines): short notes sharing an attack with >= 2 others are chordal hits."""
    by_start = Counter(n.start for n in notes)
    hits = [n for n in notes if by_start[n.start] >= 3 and n.dur <= TICKS_PER_BEAT]
    hit_ids = {id(n) for n in hits}
    return hits, [n for n in notes if id(n) not in hit_ids]


SOLO_WINDOW = (52, 88)  # the solo line without a seat: a cornet or trumpet soloist, E3-E6
PART_HOLD_WITHIN = TICKS_PER_BEAT // 2  # detached notes are written as (staccato) 8ths in band parts, not 16ths and rests


def written_line(qnotes, times: np.ndarray, pickup: int, source: str) -> list[Note]:
    """One voice with written durations from its performed lengths (held vs detached, staccato)."""
    out = []
    for q, w in apply_written(qnotes, BeatMap(times), hold_within=PART_HOLD_WITHIN, min_detached=PART_HOLD_WITHIN):
        n = to_notes([q], pickup, source)[0]
        n.performed_dur = int(round(w.performed))
        if w.staccato:
            n.articulations.append(Articulation.STACCATO)
        out.append(n)
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", type=Path, required=True)
    ap.add_argument("--beats", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--title", default="Draft")
    ap.add_argument("--no-render", action="store_true", help="skip the MuseScore PDF/MP3 export of the score and parts")
    ap.add_argument("--solo-contour", type=Path,
                    help="SwiftF0 contour of the solo stem (swiftf0_contour.py); default <layers>/solo-sw.contour.npz if present")
    ap.add_argument("--no-free-time", action="store_true", help="keep the beat grid through free-time passages")
    ap.add_argument("--no-gate", action="store_true", help="keep layer notes where the layer's audio is silent")
    ap.add_argument("--no-beat-cleanup", action="store_true", help="use the tracked beats as they are")
    ap.add_argument("--single-key", action="store_true", help="one key signature for the whole piece")
    ap.add_argument("--lineup", choices=["band", "full", "minimal", "quartet"], default="band",
                    help="band (= full): the 18-part contest band; minimal: the 8-part minimal band; "
                         "quartet: 1st and 2nd Cornet, Tenor Horn and Euphonium")
    ap.add_argument("--difficulty", choices=["faithful", "standard", "easier"], default="faithful")
    ap.add_argument("--seat", choices=SEAT_IDS,
                    help="the player's seat: a solo take is written for it (one part, its range, as played)")
    ap.add_argument("--reads", choices=CLEF_READINGS, help="the clef the seat's part is written in (bass: at concert pitch)")
    ap.add_argument("--lead", choices=LEADS, default="lineup",
                    help="who plays the tune: the lineup's lead, or the seat's part (a solo take always the seat)")
    ap.add_argument("--lang", choices=FOOTER_LANGS, default="en", help="language of the footer on the arranged parts")
    tr = ap.add_mutually_exclusive_group()
    tr.add_argument("--key", help="target concert key of the first key signature: Bb, F#, Am, or FIFTHS[:MODE]")
    tr.add_argument("--transpose", type=int, help="transpose the whole arrangement by N semitones")
    ap.add_argument("--free-tempo", type=float, help="notate free-time passages at this BPM instead of estimating one")
    args = ap.parse_args(argv)
    if args.lead == "seat" and not args.seat:
        ap.error("--lead seat needs --seat")
    try:
        check_reads(args.seat, args.reads)
    except ValueError as e:
        ap.error(str(e))
    return args


def build(args: argparse.Namespace, trace: dict | None = None) -> tuple[Composition, Arrangement]:
    """The Composition and its arrangement (writes separation-check.json into args.out when the layer audio is there).

    `trace`, when given, receives the solo line's intermediate stages (for the fast-notes bench): "line" (notes in
    seconds before quantization), "quantized" ((pitch, start, end) ticks from beat 0), "times" (the beat grid) and
    "pickup" (ticks)."""
    L = args.layers
    args.out.mkdir(parents=True, exist_ok=True)

    solo_mus, solo_bp = pitched(L / "solo-mus.mid"), pitched(L / "solo-bp.mid")
    bass_raw = pitched(L / "bass-mus.mid")
    orch_raw = pitched(L / "orchestra-mus.mid")
    drum_raw = drums_of(L / "drums-mus.mid")
    if not args.no_gate:
        # Drop notes a layer's transcriber found where that layer is (nearly) silent: bleed and residue.
        for name, raw in (("bass", bass_raw), ("orchestra", orch_raw), ("drums", drum_raw)):
            if (L / f"{name}.wav").exists():
                y, sr = sf.read(L / f"{name}.wav", dtype="float32")
                kept, dropped = gate(raw, Envelope.of(y, sr))
                raw[:] = kept
                print(f"gate {name}: dropped {dropped}")

    # Does the solo stem contain the soloist? The layers sum to the mix (the orchestra is the residual).
    layer_wavs = [L / f"{n}.wav" for n in ("solo", "bass", "drums", "orchestra")]
    if all(f.exists() for f in layer_wavs):
        audio = [sf.read(f, dtype="float32") for f in layer_wavs]
        n_min = min(len(y) for y, _ in audio)
        check = check_stem(audio[0][0][:n_min], sum(y[:n_min] for y, _ in audio), audio[0][1])
        print(check.summary())
        (args.out / "separation-check.json").write_text(json.dumps(
            {"stem_minus_mix_db": check.stem_minus_mix_db, "failed": check.failed, "quiet_windows": check.quiet_windows}))
        del audio

    b = np.loadtxt(args.beats, ndmin=2)
    pos = b[:, 1].astype(int)
    gaps = np.diff(np.where(pos == 1)[0])
    beats_per_bar = Counter(gaps).most_common(1)[0][0] if len(gaps) else 1
    onsets = np.array([n["onset"] for n in pitched(L / "solo-sw.mid") + bass_raw + orch_raw])
    down = pos == 1
    raw_times = b[:, 0]
    if not args.no_beat_cleanup:
        # Restore missed and remove inserted beats (outside free time); the bar phase follows
        # the majority of the tracker's downbeat labels.
        cb = clean_beats_gated(raw_times, down, int(beats_per_bar), skip=unstable_runs(raw_times), onsets=onsets)
        raw_times, down = cb.times, cb.downbeat
        print(f"beats: {'cleaned' if cb.applied else 'kept as tracked'}, +{cb.inserted} restored, -{cb.removed} removed")
        first_down = cb.phase(int(beats_per_bar))
    else:
        first_down = int(np.argmax(down))
    times = choose_level(raw_times, onsets)
    doubled = len(times) != len(raw_times)
    if doubled:
        beats_per_bar *= 2
        first_down *= 2
    if Counter(gaps).most_common(1)[0][0] < 2 if len(gaps) else True:
        # The tracker's downbeat labels give no bars (small0 on one instrument labels most beats as
        # downbeats): infer the meter and bar phase on the final grid from the labels' periodicity and
        # the solo's note accents, unless the evidence is too weak (then the grid's own bars stay).
        solo_notes = pitched(L / "solo-sw.mid") or pitched(L / "solo-mus.mid")
        grid_pos = labels_on(times, b[:, 0], pos)
        meter = solo_meter(times, grid_pos == 1, grid_pos, int(beats_per_bar), first_down,
                           np.array([n["onset"] for n in solo_notes]), np.array([n["offset"] - n["onset"] for n in solo_notes]))
        if not meter.from_labels:
            times, beats_per_bar, first_down = meter.times, meter.beats_per_bar, meter.first_downbeat
            down = (np.arange(len(times)) - first_down) % beats_per_bar == 0
            doubled = False  # the labels are replaced by the inferred bars
            print(f"meter inferred: {beats_per_bar} beats per bar, downbeat labels on {downbeat_rate(pos == 1):.0%} of beats")
        else:
            print(f"meter kept ({beats_per_bar} beats per bar): too little evidence to infer one")
    plan = None
    if not args.no_free_time:
        plan = plan_free_time(times, onsets, int(beats_per_bar), first_down, None if doubled else down,
                              tempo=args.free_tempo, tempo_onsets=np.array([n["onset"] for n in pitched(L / "solo-sw.mid")]))
        times, first_down = plan.beat_times, plan.first_downbeat
    coarse = plan.beat_ranges if plan else None
    earliest = float(BeatMap(times).to_beats(np.array([onsets.min()]))[0])
    while first_down > earliest + 1e-6:
        first_down -= beats_per_bar
    pickup = first_down * TICKS_PER_BEAT
    half = TICKS_PER_BEAT // 2

    # Solo: SwiftF0 is the spine (best single source on separated solo stems); notes without
    # SwiftF0 are dropped (0.02-0.36 precise on solo_vote_bench). Each note's confidence is the
    # calibrated probability that it is right (confidence.py: agreement class, length, contour
    # support, separated or not), fitted by confidence_bench on notes with ground truth.
    solo_sw = pitched(L / "solo-sw.mid")
    if args.solo_contour is None and (L / "solo-sw.contour.npz").exists():
        args.solo_contour = L / "solo-sw.contour.npz"
    solo_contour = Contour.load(args.solo_contour) if args.solo_contour else None
    # Faithful: the fast notes as played, pitch-change onsets the segmentation merged (slurred trills and
    # runs) and a finer grid where the onsets need it (docs/plan/fast-notes.md). Standard and easier keep the
    # simpler line they were tuned on.
    fast_notes = args.difficulty == "faithful"
    if fast_notes:
        solo_sw = contour_notes(solo_sw, solo_contour, solo_bp)
    # A solo take (no other layer has notes) for a seat keeps the seat instrument's range; otherwise the
    # solo line is the soloist's, a cornet or trumpet (E3-E6).
    solo_take = bool(args.seat) and not (bass_raw or orch_raw or drum_raw)
    if solo_take and not seat_by_id(args.seat).reads:
        raise SystemExit(PERCUSSION_SOLO)
    if args.lead == "seat" and not solo_take:
        try:
            lead_lineup(lineup_by_name(args.lineup), args.seat)
        except ValueError as e:
            raise SystemExit(f"--lead seat: {e}") from e
    lo, hi = seat_by_id(args.seat).own_part.instrument.pro if solo_take else SOLO_WINDOW
    votes = {"sw": line(solo_sw, lo, hi, top=True), "mus": line(solo_mus, lo, hi, top=True),
             "bp": line(solo_bp, lo, hi, top=True)}
    # Basic Pitch standing in for MuScriptor (the solo path) is one vote for the confidence, not two;
    # the clustering (and so every note's timing) is unchanged.
    mus_is_bp = sorted((n["onset"], n["pitch"]) for n in solo_mus) == sorted((n["onset"], n["pitch"]) for n in solo_bp)
    separated = any((L / f"{n}.wav").exists() for n in ("bass", "drums", "orchestra"))
    model = CalibrationModel.load()
    cand = []
    split_onsets = {n["onset"] for n in votes["sw"] if n.get("split")}
    for c in cluster(votes):
        if "sw" not in c.sources:
            continue
        on, off = float(np.median(c.onsets)), float(np.median(c.offsets))
        src = set(c.sources) - ({"mus"} if mus_is_bp else set())
        x = confidence_features(src, off - on, contour_support(solo_contour, on, c.pitch), separated)
        cand.append({"pitch": c.pitch, "onset": on, "offset": off, "confidence": round(p_correct(x, model), 3),
                     **({"split": True} if any(o in split_onsets for o in c.onsets) else {})})
    solo_line = line(cand, lo, hi, top=True)
    if args.solo_contour:
        # Where the note really ends: the SwiftF0 contour, or the longest confirming model offset.
        ends = contour_offsets(solo_contour, [(n["onset"], n["pitch"]) for n in solo_line],
                               **SEPARATED_STEM)
        for n, e in zip(solo_line, ends):
            n["offset"] = max(n["offset"], e)
    solo_q = quantize(solo_line, times, monophonic=True, auto_level=False, coarse=coarse, dense=fast_notes)
    if trace is not None:
        trace.update(line=[dict(n) for n in solo_line], quantized=[(q.pitch, q.start, q.end) for q in solo_q],
                     times=np.asarray(times, float).copy(), pickup=pickup, coarse=coarse)
    solo = written_line(solo_q, times, pickup, "solo")
    bass = written_line(quantize(line(bass_raw, 24, 55, top=False), times, monophonic=True, auto_level=False, coarse=coarse),
                        times, pickup, "bass")

    solo_keys = {(round(n["onset"], 1), n["pitch"]) for n in solo_line}
    orch = [n for n in orch_raw if 36 <= n["pitch"] <= 88 and (round(n["onset"], 1), n["pitch"]) not in solo_keys]
    orch_q = [n for n in to_notes(quantize(orch, times, auto_level=False, coarse=coarse), pickup, "orchestra") if n.start >= 0]
    hits, lines = split_orchestra(orch_q)

    dq = quantize(drum_raw, times, auto_level=False, coarse=coarse)
    starts = sorted({q.start for q in dq})
    nxt = {s: n for s, n in zip(starts, starts[1:])}
    drums = [Note(q.pitch, q.start - pickup, min(nxt.get(q.start, q.start + half) - q.start, TICKS_PER_BEAT), 1.0, ["drums"])
             for q in dq if q.start - pickup >= 0]

    comp = Composition(args.title, [
        Voice("solo", VoiceRole.MELODY, solo, "trumpet/cornet", "solo"),
        Voice("bass", VoiceRole.BASS, bass, "electric bass", "bass"),
        Voice("strings", VoiceRole.HARMONY, lines, "orchestra", "strings"),
        Voice("brass", VoiceRole.HARMONY, hits, "orchestra hits", "brass"),
        Voice("drums", VoiceRole.RHYTHM, drums, "drum kit", "drums"),
    ], [Meter(0, int(beats_per_bar))], [KeySig(0, 0)], list(map(float, times)), first_down,
        free_regions=plan.regions(first_down) if plan else [])
    for v in comp.voices:
        clip_to_regions(v.notes, comp.free_regions)
    mark_fermatas(solo, comp.free_regions)
    tonal = solo + bass + lines
    _, fifths = key_of([n.start / TICKS_PER_BEAT for n in tonal], [n.dur / TICKS_PER_BEAT for n in tonal], [n.pitch for n in tonal])
    comp.keys = [KeySig(0, fifths)]
    if not args.single_key:
        # Key changes where the music modulates (a change must pay for itself over several bars).
        penalty = KEY_CHANGE_PENALTY[args.difficulty]
        comp.keys = key_plan(solo + lines, int(beats_per_bar) * TICKS_PER_BEAT, bass=bass,
                             **({"penalty": penalty} if penalty else {})).keys
    # Dynamics per layer from its own loudness, per bar.
    bar_ticks = int(beats_per_bar) * TICKS_PER_BEAT
    bm = BeatMap(np.array(comp.beat_times))
    n_bars = comp.end_tick // bar_ticks + 1
    edges = bm.to_seconds(np.arange(n_bars + 1) * beats_per_bar + first_down)
    bars = [(k * bar_ticks, float(edges[k]), float(edges[k + 1])) for k in range(n_bars)]
    envs = {}
    for wav in ("solo", "orchestra", "bass", "drums"):
        if (L / f"{wav}.wav").exists():
            y, sr = sf.read(L / f"{wav}.wav", dtype="float32")
            envs[wav] = Envelope.of(y, sr)
    for layer, wav in (("solo", "solo"), ("strings", "orchestra"), ("brass", "orchestra"), ("bass", "bass"), ("drums", "drums")):
        if wav in envs:
            comp.dynamics += [Dynamic(t, layer, m) for t, m in layer_dynamics(envs[wav], bars)]
    # Rehearsal letters where the layers' energy changes, and where free time ends.
    if envs:
        starts = section_starts(bar_features(list(envs.values()), bars), [r.end // bar_ticks for r in comp.free_regions])
        comp.sections = [Section(b * bar_ticks, lab) for b, lab in zip(starts, letters(len(starts)))]
        print("rehearsal marks at bars", [(s.label, s.tick // bar_ticks + 1) for s in comp.sections])
    # Arrangement options: lineup, difficulty, transposition to a concert key.
    shift = args.transpose if args.transpose is not None else semitones_to(comp.keys[0], args.key) if args.key else 0
    if shift:
        comp = comp.transposed(shift)
        print(f"transposed {shift:+d} semitones; first key now {comp.keys[0].fifths} fifths {comp.keys[0].mode}")
    lineup = "band" if args.lineup in ("band", "full") else args.lineup
    if lineup != "band" or args.difficulty != "faithful" or shift or args.seat:
        comp.arrangement = {"lineup": lineup, "difficulty": args.difficulty, "transpose_semitones": shift}
    if args.seat:
        # The seat's options, like the others; the arrangers read them back (composition_lineup).
        comp.arrangement.update({"seat": args.seat, **({"reads": args.reads} if args.reads else {}),
                                 **({"lead": "seat"} if solo_take or args.lead == "seat" else {})})
    # Review groups: neighbouring uncertain notes in one bar are one review item for the apps.
    bar_ticks = int(beats_per_bar) * TICKS_PER_BEAT
    comp.review = [ReviewItem(v.id, g.start, g.end, g.notes, g.very) for v in comp.voices if v.layer != "drums"
                   for g in review_groups([(n.start, n.end, n.confidence) for n in v.notes], bar_ticks,
                                          1 - model.mark_risk, 1 - model.very_risk)]
    marked = sum(n.confidence < 1 - model.mark_risk for n in solo)
    print(f"solo notes marked uncertain: {marked} of {len(solo)} ({marked / max(1, len(solo)):.0%}), "
          f"{sum(1 for r in comp.review if r.voice == 'solo')} review groups")
    arr = arrange_layers(comp, composition_lineup(comp)[0], difficulty=args.difficulty)
    counts = {k: len(v) for k, v in arr.parts.items()}
    print(f"solo {len(solo)}, bass {len(bass)}, orchestra lines {len(lines)} / hits {len(hits)}, drums {len(drums)}")
    print("band notes per part:", counts)
    print("dynamics:", {layer: [m for d in comp.dynamics if d.layer == layer for m in [d.mark]] for layer in ("solo", "strings", "bass", "drums")})
    print(f"key fifths {fifths}; keys {[(k.tick // (int(beats_per_bar) * TICKS_PER_BEAT) + 1, k.fifths, k.mode) for k in comp.keys]}; "
          f"warnings {len(arr.warnings)}")
    for r in comp.free_regions:
        print(f"free time {r.start_s:.2f}-{r.end_s:.2f} s -> ticks {r.start}-{r.end} at {r.tempo_bpm:.1f} BPM ({r.notation.value})")
    return comp, arr


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    comp, arr = build(args)
    comp.to_json(args.out / "composition.json")
    xml = write_musicxml(build_band_score(arr, comp), args.out / "brass-band.musicxml", band_sounds(arr))
    if not args.no_render:
        musescore.convert(xml, [xml.with_suffix(".pdf"), xml.with_suffix(".mp3")])
    # Individual parts (mscore -P crashes): one MusicXML per part, all rendered in one MuseScore launch.
    parts = split_parts(xml, args.out / "parts", part_footers(comp, args.lang))
    for pdf in [] if args.no_render else musescore.convert_many([(f, f.with_suffix(".pdf")) for f in parts], style=PART_STYLE):
        print(f"(no pdf for {pdf.name})")
    print(xml, "pdf" if xml.with_suffix(".pdf").exists() else "(no pdf)", "mp3" if xml.with_suffix(".mp3").exists() else "(no mp3)")


if __name__ == "__main__":
    main()
