"""The research pages' figures. Read by site/research.py; a page shows one with {{chart <name>}} or
{{pipeline <name>}}.

Words are named, not written here: T("rhythm.title") is `title` under [figure.rhythm] of words.en.toml and
words.nb.toml, and T("rhythm.row_n", part) fills that text's %1 with `part`. A name that is the same in every
language (a model, a dataset) is written as it is. A row's `keys` name its measurements, one per series (None: not
measured); site/research.py says what a key is. `{key}` in a title, caption or note prints that
measurement, so the words around it must stay true when it moves: `holds` lists what the title
asserts, and the build fails when one of them stops being true.
"""

B = "brass/"
F = "fretted/"
CHORALES_N = T("shared.chorales_n")
URMP_N = T("shared.urmp_n")
CHORALES = T("shared.chorales")
URMP = T("shared.urmp")
CHORALES_NOTE = T("shared.chorales_note")
URMP_NOTE = T("shared.urmp_note")
RECORDINGS = T("shared.recordings")
F1_AXIS = T("shared.f1_axis")
SHARE_AXIS = T("shared.share_axis")

INSTRUMENTS = (("trumpet", T("shared.trumpet")), ("flugelhorn", T("shared.flugelhorn")), ("horn", T("shared.horn")),
               ("baritone", T("shared.baritone")), ("trombone", T("shared.trombone")), ("tuba", T("shared.tuba")))


def transcription(suite, rows):
    return [{"label": label, "keys": [f"{B}{suite}/{model}.onset_f1" if "50" in has else None,
                                      f"{B}{suite}/{model}.onset100_f1" if "100" in has else None]} for label, model, has in rows]


FIGURES = {
    # ------------------------------------------------------------------------------- brass
    "notes-found": {
        "title": T("notes-found.title"),
        "holds": ["brass/chorales-transcription/muscriptor-medium.onset100_f1 > brass/chorales-transcription/basic-pitch.onset100_f1",
                  "brass/urmp-transcription/muscriptor-medium.onset100_f1 > brass/urmp-transcription/basic-pitch.onset100_f1",
                  "brass/slakh-transcription/pipeB-sw-muscriptor.onset100_f1 > brass/slakh-transcription/muscriptor-medium.onset100_f1"],
        "sub": T("notes-found.sub"),
        "axis": F1_AXIS,
        "series": [T("notes-found.series1"), T("notes-found.series2")],
        "view_label": RECORDINGS,
        "views": [
            {"label": CHORALES, "note": CHORALES_NOTE, "n": CHORALES_N,
             "rows": transcription("chorales-transcription", [("MuScriptor medium", "muscriptor-medium", "100 50"), ("Basic Pitch", "basic-pitch", "100 50")])},
            {"label": URMP, "note": URMP_NOTE, "n": URMP_N,
             "rows": transcription("urmp-transcription", [("MuScriptor medium", "muscriptor-medium", "100 50"), ("Basic Pitch", "basic-pitch", "100 50")])},
            {"label": T("notes-found.view_label"),
             "note": T("notes-found.view_note"),
             "n": T("notes-found.view_n"),
             "rows": transcription("slakh-transcription", [
                 (T("notes-found.row1"), "pipeB-sw-muscriptor", "100"),
                 (T("notes-found.row2"), "muscriptor-medium", "100"),
                 (T("notes-found.row3"), "pipeB-sw-basicpitch", "100"),
                 (T("notes-found.row4"), "basic-pitch", "100")])},
        ],
        "caption": T("notes-found.caption"),
        "source": T("notes-found.source"),
    },
    "rhythm": {
        "title": T("rhythm.title"),
        "holds": ["brass/quant-chorales/beat_this.position_acc < 0.5", "brass/quant-urmp/beat_this.position_acc < 0.5",
                  "brass/quant-chorales/reference_beats.position_acc >= 0.9", "brass/quant-urmp/reference_beats.position_acc >= 0.9"],
        "format": "pct",
        "sub": T("rhythm.sub"),
        "axis": T("rhythm.axis"),
        "series": [T("rhythm.series1"), T("rhythm.series2")],
        "view_label": RECORDINGS,
        "views": [{"label": label, "note": note, "n": n, "rows": [
            {"label": text, "keys": [f"{B}{suite}/reference_beats.{key}", f"{B}{suite}/beat_this.{key}"]} for text, key in (
                (T("rhythm.row1"), "position_acc"),
                (T("rhythm.row2"), "subdivision_acc"),
                (T("rhythm.row3"), "duration_acc"))]}
            for label, note, n, suite in ((CHORALES, CHORALES_NOTE, CHORALES_N, "quant-chorales"), (URMP, URMP_NOTE, URMP_N, "quant-urmp"))],
        "caption": T("rhythm.caption"),
        "source": T("rhythm.source"),
    },
    "solo-written": {
        "title": T("solo-written.title"),
        "holds": ["brass/solo-beat-model/urmp.small0.written_f1 < 0.3", "brass/solo-beat-model/choralebricks.small0.written_f1 < 0.3",
                  "brass/solo-beat-model/urmp.final0.written_f1 < 0.3", "brass/solo-beat-model/choralebricks.final0.written_f1 < 0.3",
                  "brass/solo-beat-model/urmp.small0.written_f1 > 0.2", "brass/solo-beat-model/choralebricks.small0.written_f1 > 0.2",
                  "brass/solo-beat-model/urmp.small0.onset_f1 > 0.7", "brass/solo-beat-model/choralebricks.small0.onset_f1 > 0.7"],
        "sub": T("solo-written.sub"),
        "axis": T("solo-written.axis"),
        "series": [T("solo-written.series1"),
                   T("solo-written.series2")],
        "view_label": T("solo-written.views_name"),
        "views": [{"label": label, "note": note, "rows": [
            {"label": text, "keys": [f"{B}solo-beat-model/{part}.{model}.onset_f1", f"{B}solo-beat-model/{part}.{model}.written_f1"],
             "n": T("solo-written.row_n", part)}
            for text, part in ((T("solo-written.row1"), "urmp"),
                               (T("solo-written.row2"), "choralebricks"))]}
            for label, note, model in (
                (T("solo-written.view1"), T("solo-written.view2"), "small0"),
                (T("solo-written.view3"), T("solo-written.view4"), "final0"))],
        "caption": T("solo-written.caption"),
        "source": T("solo-written.source"),
    },
    "solo-instruments": {
        "title": T("solo-instruments.title"),
        "holds": [f"brass/solo-instruments/{i}.seat_f1 >= 0.85" for i, _ in INSTRUMENTS] + ["brass/solo-instruments/tuba.today_f1 < 0.1"]
                 + [f"brass/solo-instruments/{i}.sw_f1 >= 0.85" for i, _ in INSTRUMENTS] + ["brass/solo-instruments/tuba.bp_f1 < 0.6"],
        "sub": T("solo-instruments.sub"),
        "axis": F1_AXIS,
        "series": [T("solo-instruments.series1"), T("solo-instruments.series2")],
        "view_label": T("solo-instruments.views_name"),
        "views": [{"label": T("solo-instruments.view_label1"),
                   "rows": [{"label": label, "keys": [f"{B}solo-instruments/{i}.seat_f1", f"{B}solo-instruments/{i}.today_f1"],
                             "n": T("solo-instruments.row_n", i)} for i, label in INSTRUMENTS]},
                  {"label": T("solo-instruments.view_label2"), "series": ["SwiftF0", "Basic Pitch"],
                   "rows": [{"label": label, "keys": [f"{B}solo-instruments/{i}.sw_f1", f"{B}solo-instruments/{i}.bp_f1"],
                             "n": T("solo-instruments.row_n", i)} for i, label in INSTRUMENTS]}],
        "caption": T("solo-instruments.caption"),
        "source": T("solo-instruments.source"),
    },
    "voices": {
        "title": T("voices.title"),
        "holds": ["brass/seat-voices/muscriptor-medium.S_f1 > 0.85", "brass/seat-voices/muscriptor-medium.T_f1 < 0.4",
                  "brass/seat-voices/basic-pitch.T_f1 < 0.4", "brass/seat-voices/consensus.T_f1 < 0.4",
                  "p/chorales-transcription/muscriptor-medium.recall_T < 0.55", "p/chorales-transcription/muscriptor-medium.recall_B < 0.55",
                  "p/chorales-transcription/muscriptor-medium.recall_S > 0.8"],
        "sub": T("voices.sub"),
        "axis": F1_AXIS,
        "series": ["MuScriptor medium", "Basic Pitch", T("voices.series")],
        "view_label": T("voices.views_name"),
        "views": [{"label": T("voices.view_label"), "n": CHORALES_N, "rows": [
            {"label": label, "keys": [f"{B}seat-voices/{m}.{v}_f1" for m in ("muscriptor-medium", "basic-pitch", "consensus")]} for v, label in (
                ("S", T("voices.row1")), ("A", T("voices.row2")),
                ("T", T("voices.row3")), ("B", T("voices.row4")))]}] + [
            {"label": label, "n": CHORALES_N, "format": "pct", "series": ["MuScriptor medium", "Basic Pitch"],
                   "axis": T("voices.view_axis"),
                   "note": T("voices.view_note"),
                   "rows": [{"label": text, "keys": [f"p/chorales-transcription/{m}.{key}_{v}" for m in ("muscriptor-medium", "basic-pitch")]} for v, text in (
                       ("S", T("voices.row1")), ("A", T("voices.row2")),
                       ("T", T("voices.row3")), ("B", T("voices.row4")))]}
                  for label, key in ((T("voices.view1"), "recall100"), (T("voices.view2"), "recall"))],
        "caption": T("voices.caption"),
        "source": T("voices.source"),
    },
    "doubt": {
        "title": T("doubt.title"),
        "holds": [f"brass/solo-instruments/{i}.q_hit < 0.34" for i, _ in INSTRUMENTS] + [f"brass/solo-instruments/{i}.q_false_alarm < 0.05" for i, _ in INSTRUMENTS]
                 + ["m/review_marks_held_out/wrong_notes_caught < m/review_marks_held_out/odd_even_wrong_notes_caught",
                    "m/review_marks_held_out/mark_precision < m/review_marks_held_out/odd_even_mark_precision"],
        "format": "pct",
        "sub": T("doubt.sub"),
        "axis": SHARE_AXIS,
        "series": [T("doubt.series1"), T("doubt.series2")],
        "view_label": T("doubt.views_name"),
        "views": [{"label": T("doubt.held_label"), "note": T("doubt.held_note"), "axis": T("doubt.held_axis"),
                   "series": [T("doubt.series1"), T("doubt.held_series2")],
                   "rows": [{"label": T("doubt.held_row1"), "n": T("doubt.held_n1"),
                             "keys": ["m/review_marks_held_out/wrong_notes_caught", "m/review_marks_held_out/mark_precision"]},
                            {"label": T("doubt.held_row2"), "n": T("doubt.held_n2"),
                             "keys": ["m/review_marks_held_out/odd_even_wrong_notes_caught", "m/review_marks_held_out/odd_even_mark_precision"]}]},
                  {"label": T("doubt.view_label"),
                   "note": T("doubt.view_note"),
                   "rows": [{"label": label, "keys": [f"{B}solo-instruments/{i}.q_hit", f"{B}solo-instruments/{i}.q_false_alarm"],
                             "n": T("doubt.row_n", i)} for i, label in INSTRUMENTS]}],
        "caption": T("doubt.caption"),
        "source": T("doubt.source"),
    },
    "fast-notes": {
        "title": T("fast-notes.title"),
        "holds": ["brass/fast-notes/small0.sw.fig_recall > 0.5", "brass/fast-notes/small0.sw.fig_recall < 0.7",
                  "brass/fast-notes/small0.written.fig_recall < brass/fast-notes/small0.line.fig_recall",
                  "brass/fast-notes/oracle.written.fig_recall < brass/fast-notes/oracle.line.fig_recall",
                  "m/fast_notes/oracle_fig_after > m/fast_notes/oracle_fig_before", "m/fast_notes/oracle_fig_after < 0.5",
                  "m/fast_notes/small0_fig_after > m/fast_notes/small0_fig_before", "m/fast_notes/small0_fig_after < 0.5"],
        "format": "pct",
        "sub": T("fast-notes.sub"),
        "axis": T("fast-notes.axis"),
        "series": [T("fast-notes.series1"), T("fast-notes.series2")],
        "view_label": T("fast-notes.views_name"),
        "views": [{"label": T("fast-notes.view_label"),
                   "n": T("fast-notes.view_n1"),
                   "rows": [{"label": label, "keys": [f"{B}fast-notes/oracle.{stage}.fig_recall", f"{B}fast-notes/small0.{stage}.fig_recall"]} for stage, label in (
                       ("sw", T("fast-notes.row1")),
                       ("line", T("fast-notes.row2")),
                       ("quantized", T("fast-notes.row3")),
                       ("written", T("fast-notes.row4")))]}] + [
            {"label": label, "series": [T("fast-notes.view_series1"), T("fast-notes.view_series2")],
                   "axis": T("fast-notes.view_axis"), "n": T("fast-notes.view_n2"),
                   "rows": [{"label": text, "keys": [f"m/fast_notes/{beats}_{key}_before", f"m/fast_notes/{beats}_{key}_after"]} for text, key in (
                       (T("fast-notes.row5"), "fig"),
                       (T("fast-notes.row6"), "f1"),
                       (T("fast-notes.row7"), "alt"))]}
                  for label, beats in ((T("fast-notes.view1"), "oracle"), (T("fast-notes.view2"), "small0"))],
        "caption": T("fast-notes.caption"),
        "source": T("fast-notes.source"),
    },
    "agreement": {
        "title": T("agreement.title"),
        "holds": ["brass/solo-vote/precision.bp+mus+sw > 0.9", "brass/solo-vote/precision.mus+sw > 0.9", "brass/solo-vote/precision.bp+sw > 0.85",
                  "brass/solo-vote/precision.sw < 0.6", "brass/solo-vote/precision.bp+mus < 0.5"],
        "format": "pct",
        "sub": T("agreement.sub"),
        "axis": T("agreement.axis"),
        "series": [T("agreement.series")],
        "views": [{"label": T("agreement.view_label"), "rows": [
            {"label": label, "keys": [f"{B}solo-vote/precision.{key}"], "n": T("agreement.row_n", n)} for key, n, label in (
                ("mus+sw", "n_mus_sw", T("agreement.row1")),
                ("bp+mus+sw", "n_all", T("agreement.row2")),
                ("bp+sw", "n_bp_sw", T("agreement.row3")),
                ("sw", "n_sw", T("agreement.row4")),
                ("bp+mus", "n_bp_mus", T("agreement.row5")))]}],
        "caption": T("agreement.caption"),
        "source": T("agreement.source"),
    },
    "models": {
        "title": T("models.title"),
        "holds": ["brass/chorales-transcription/muscriptor-large.onset_f1 < brass/chorales-transcription/muscriptor-medium.onset_f1",
                  "brass/chorales-transcription/muscriptor-medium-brass.onset_f1 < brass/chorales-transcription/muscriptor-medium.onset_f1",
                  "brass/chorales-transcription/muscriptor-large-brass.onset_f1 < brass/chorales-transcription/muscriptor-large.onset_f1"],
        "spread": False,
        "sub": T("models.sub"),
        "axis": F1_AXIS,
        "series": [T("models.series1"), T("models.series2")],
        "views": [{"label": CHORALES, "n": CHORALES_N, "rows": [
            {"label": label, "keys": [f"{B}chorales-transcription/{m}.onset_f1", f"{B}chorales-transcription/{m}.onoff_f1"]} for m, label in (
                ("muscriptor-medium", T("models.row1")),
                ("basic-pitch-retuned", T("models.row2")),
                ("basic-pitch", T("models.row3")),
                ("muscriptor-large", T("models.row4")),
                ("muscriptor-medium-brass", T("models.row5")),
                ("muscriptor-large-brass", T("models.row6")))]}],
        "caption": T("models.caption"),
        "source": T("models.source"),
    },
    "inner-parts": {
        "title": T("inner-parts.title"),
        "holds": ["brass/arrange/quartet.alto_recall_pc > 0.75", "brass/arrange/quartet.tenor_recall_pc > 0.75",
                  "brass/quartet-audio/mus.alto_recall_pc < 0.6", "brass/quartet-audio/mus.tenor_recall_pc < 0.6",
                  "brass/quartet-audio/mus.tenor_recall_pc > 0.4"],
        "format": "pct",
        "sub": T("inner-parts.sub"),
        "axis": T("inner-parts.axis"),
        "series": [T("inner-parts.series1"), T("inner-parts.series2"),
                   T("inner-parts.series3")],
        "views": [{"label": CHORALES, "n": CHORALES_N, "rows": [
            {"label": label, "keys": [f"{B}arrange/quartet.{v}_recall_pc", f"{B}quartet-audio/mus.{v}_recall_pc", f"{B}quartet-audio/bp.{v}_recall_pc"]}
            for v, label in (("alto", T("inner-parts.row1")), ("tenor", T("inner-parts.row2")))]}],
        "caption": T("inner-parts.caption"),
        "source": T("inner-parts.source"),
    },
    "speed": {
        "title": T("speed.title"),
        "holds": ["c/swift-f0/coreml-fp32-ALL.s_per_min < 1", "c/basic-pitch/coreml-b1-fp32-ALL.s_per_min < 1", "c/beat-this/small0/coreml-fp16-ALL.s_per_min < 1",
                  "c/bs-roformer-sw/coreml-fp16-ALL.s_per_min > 1", "c/mega53/coreml-fp16-ALL.s_per_min > 1"],
        "sub": T("speed.sub"),
        "series": [T("speed.series1"),
                   T("speed.series2")],
        "view_label": T("speed.views_name"),
        "views": [{"label": label, "format": how, "scale": "log", "log": span, "axis": axis, "note": note,
                   "n": T("speed.view_n"),
                   "rows": [{"label": name, "keys": [f"c/{model}/{converted}.{field}", f"c/{model}/{reference}.{field}"]} for name, model, converted, reference in (
                       (T("speed.row1"), "swift-f0", "coreml-fp32-ALL", "ort-cpu-upstream"),
                       (T("speed.row2"), "basic-pitch", "coreml-b1-fp32-ALL", "tf-savedmodel"),
                       (T("speed.row3"), "beat-this", "small0/coreml-fp16-ALL", "small0/torch-cpu"),
                       (T("speed.row4"), "bs-roformer-sw", "coreml-fp16-ALL", "torch-cpu"),
                       (T("speed.row5"), "mega53", "coreml-fp16-ALL", "torch-cpu"),
                       (T("speed.row6"), "muscriptor", "onnx-ort-cpu", "torch-cpu"))]}
                  for label, how, field, span, axis, note in (
                      (T("speed.view1"), "sec", "s_per_min", (-2, 3),
                       T("speed.view2"),
                       T("speed.view3")),
                      (T("speed.view4"), "gb", "peak_gb", (-1, 2),
                       T("speed.view5"),
                       T("speed.view6")))],
        "caption": T("speed.caption"),
        "source": T("speed.source"),
    },
    "conversions": {
        "title": T("conversions.title"),
        "holds": ["c/swift-f0/coreml-fp16-CPU_AND_NE.parity < c/swift-f0/threshold_f1", "c/basic-pitch/coreml-b1-fp16-CPU_AND_NE.parity < c/swift-f0/threshold_f1",
                  "c/swift-f0/coreml-fp32-ALL.parity >= c/swift-f0/threshold_f1", "c/swift-f0/coreml-split-CPU_AND_NE.parity >= c/swift-f0/threshold_f1",
                  "c/basic-pitch/coreml-b1-fp32-ALL.parity >= c/swift-f0/threshold_f1", "c/beat-this/small0/coreml-fp16-ALL.parity >= c/swift-f0/threshold_f1",
                  "c/bs-roformer-sw/coreml-fp16-ALL.parity >= c/swift-f0/threshold_f1", "c/mega53/coreml-fp16-ALL.parity >= c/swift-f0/threshold_f1"],
        "format": "f3", "spread": False,
        "sub": T("conversions.sub"),
        "axis": T("conversions.axis"),
        "mark": ("c/swift-f0/threshold_f1", T("conversions.mark")),
        "series": [T("conversions.series")],
        "views": [{"label": T("conversions.view_label"),
                   "n": T("conversions.view_n"),
                   "rows": [{"label": label, "keys": [f"c/{key}.parity"]} for label, key in (
                       (T("conversions.row1"), "swift-f0/coreml-fp32-ALL"),
                       (T("conversions.row2"), "swift-f0/coreml-fp16-CPU_AND_NE"),
                       (T("conversions.row3"), "swift-f0/coreml-split-CPU_AND_NE"),
                       (T("conversions.row4"), "basic-pitch/coreml-b1-fp32-ALL"),
                       (T("conversions.row5"), "basic-pitch/coreml-b1-fp16-CPU_AND_NE"),
                       (T("conversions.row6"), "beat-this/small0/coreml-fp16-ALL"),
                       (T("conversions.row7"), "bs-roformer-sw/coreml-fp16-ALL"),
                       (T("conversions.row8"), "mega53/coreml-fp16-ALL"),
                       (T("conversions.row9"), "muscriptor/onnx-ort-cpu"),
                       (T("conversions.row10"), "muscriptor/coreml-fp16-ALL"))]}],
        "caption": T("conversions.caption"),
        "source": T("conversions.source"),
    },
    "solo-stages": {
        "title": T("solo-stages.title"),
        "holds": ["m/solo_stages/muscriptor > m/solo_stages/basic_pitch", "m/solo_stages/muscriptor > m/solo_stages/beats", "m/solo_stages/swift_f0 < 1"],
        "format": "sec", "max": "auto",
        "sub": T("solo-stages.sub"),
        "axis": T("solo-stages.axis"),
        "series": [T("solo-stages.series")],
        "views": [{"label": T("solo-stages.view_label"), "n": T("solo-stages.view_n"),
                   "rows": [{"label": label, "keys": [f"m/solo_stages/{key}"]} for label, key in (
                       (T("solo-stages.row1"), "beats"), (T("solo-stages.row2"), "swift_f0"),
                       (T("solo-stages.row3"), "basic_pitch"), (T("solo-stages.row4"), "muscriptor"),
                       (T("solo-stages.row5"), "contour"))]}],
        "caption": T("solo-stages.caption"),
        "source": T("solo-stages.source"),
    },
    "consensus": {
        "title": T("consensus.title"),
        "holds": ["brass/consensus-slakh/t0.8.onset100_f1 < brass/slakh-transcription/pipeB-sw-muscriptor.onset100_f1",
                  "brass/consensus-chorales/best.onset100_f1 < 0.78", "brass/consensus-urmp/t0.8.onset100_f1 < 0.9"],
        "sub": T("consensus.sub"),
        "axis": F1_AXIS,
        "series": [T("consensus.series1"), T("consensus.series2")],
        "views": [{"label": RECORDINGS, "rows": [
            {"label": CHORALES, "keys": [B + "chorales-transcription/muscriptor-medium.onset100_f1", B + "consensus-chorales/best.onset100_f1"], "n": CHORALES_N},
            {"label": URMP, "keys": [B + "urmp-transcription/muscriptor-medium.onset100_f1", B + "consensus-urmp/t0.8.onset100_f1"], "n": URMP_N},
            {"label": T("consensus.row_label"),
             "keys": [B + "slakh-transcription/pipeB-sw-muscriptor.onset100_f1", B + "consensus-slakh/t0.8.onset100_f1"],
             "n": T("consensus.row_n")}]}],
        "caption": T("consensus.caption"),
        "source": T("consensus.source"),
    },
    "melody": {
        "title": T("melody.title"),
        "holds": [f"brass/melody/muscriptor_supported.{k} > brass/melody/union.{k}" for k in ("slakh", "urmp", "chorales")],
        "sub": T("melody.sub"),
        "axis": F1_AXIS,
        "series": [T("melody.series"), URMP, CHORALES],
        "views": [{"label": T("melody.view_label"),
                   "n": T("melody.view_n"),
                   "rows": [{"label": label, "keys": [f"{B}melody/{key}.{k}" for k in ("slakh", "urmp", "chorales")]} for label, key in (
                       (T("melody.row1"), "muscriptor_supported"),
                       (T("melody.row2"), "agreement"),
                       (T("melody.row3"), "union"))]}],
        "caption": T("melody.caption"),
        "source": T("melody.source"),
    },
    "solo-trackers": {
        "title": T("solo-trackers.title"),
        "holds": ["brass/solo-vote/sw.onset100_f1 > brass/solo-vote/mus.onset100_f1", "brass/solo-vote/sw.onset100_f1 > brass/solo-vote/bp.onset100_f1",
                  "brass/solo-vote/sw.onset100_f1 >= brass/solo-vote/vote2.onset100_f1"],
        "sub": T("solo-trackers.sub"),
        "axis": F1_AXIS,
        "series": [T("solo-trackers.series")],
        "views": [{"label": T("solo-trackers.view_label"),
                   "n": T("solo-trackers.view_n"),
                   "rows": [{"label": label, "keys": [f"{B}solo-vote/{key}.onset100_f1"]} for label, key in (
                       (T("solo-trackers.row1"), "sw"), (T("solo-trackers.row2"), "vote2"),
                       (T("solo-trackers.row3"), "mus"), (T("solo-trackers.row4"), "bp"))]}],
        "caption": T("solo-trackers.caption"),
        "source": T("solo-trackers.source"),
    },
    "beats": {
        "title": T("beats.title"),
        "holds": ["p/quant-chorales/md_beat_this.position_acc > brass/quant-chorales/beat_this.position_acc",
                  "p/quant-urmp/md_beat_this.position_acc > brass/quant-urmp/beat_this.position_acc"],
        "sub": T("beats.sub"),
        "axis": T("beats.axis"),
        "series": [T("beats.series1"), T("beats.series2")],
        "view_label": RECORDINGS,
        "views": [{"label": label, "note": note, "n": n, "rows": [
            {"label": T("beats.row_label1"),
             "keys": [f"p/{suite}/beat_this.beat_f", f"p/{suite}/md_beat_this.beat_f"]},
            {"label": T("beats.row_label2"),
             "keys": [f"{B}{suite}/beat_this.position_acc", f"p/{suite}/md_beat_this.position_acc"]}]}
            for label, note, n, suite in ((CHORALES, CHORALES_NOTE, CHORALES_N, "quant-chorales"), (URMP, URMP_NOTE, URMP_N, "quant-urmp"))],
        "caption": T("beats.caption"),
        "source": T("beats.source"),
    },
    "durations": {
        "title": T("durations.title"),
        "holds": ["brass/durations/chorales.audio > 0.85", "brass/durations/urmp.audio < 0.7", "brass/durations/urmp.audio > 0.6",
                  "brass/durations/urmp.audio > brass/durations/urmp.performed", "brass/durations/chorales.audio > brass/durations/chorales.performed"],
        "format": "pct",
        "sub": T("durations.sub"),
        "axis": T("durations.axis"),
        "series": [URMP, CHORALES],
        "views": [{"label": T("durations.view_label"),
                   "n": T("durations.view_n"),
                   "rows": [{"label": label, "keys": [f"{B}durations/urmp.{key}", f"{B}durations/chorales.{key}"]} for label, key in (
                       (T("durations.row1"), "performed"),
                       (T("durations.row2"), "fill8"),
                       (T("durations.row3"), "audio"))]}],
        "caption": T("durations.caption"),
        "source": T("durations.source"),
    },
    "brass-pipeline": {
        "title": T("brass-pipeline.title"),
        "desc": T("brass-pipeline.desc"),
        "legend": [T("brass-pipeline.legend1"), T("brass-pipeline.legend2"), T("brass-pipeline.legend3")],
        "caption": T("brass-pipeline.caption"),
        "rows": [
            [("rule", T("brass-pipeline.row1"), T("brass-pipeline.row2"))],
            [("human", T("brass-pipeline.row3"), T("brass-pipeline.row4"))],
            [("model", T("brass-pipeline.row5"), T("brass-pipeline.row6")),
             ("model", T("brass-pipeline.row7"), T("brass-pipeline.row8"))],
            [("model", T("brass-pipeline.row9"), T("brass-pipeline.row10")),
             ("rule", T("brass-pipeline.row11"), T("brass-pipeline.row12"))],
            [("rule", T("brass-pipeline.row13"), T("brass-pipeline.row14")),
             ("rule", T("brass-pipeline.row15"), T("brass-pipeline.row16"))],
            [("rule", T("brass-pipeline.row17"), T("brass-pipeline.row18"))],
            [("rule", T("brass-pipeline.row19"), T("brass-pipeline.row20"))],
            [("rule", T("brass-pipeline.row21"), T("brass-pipeline.row22"))],
            [("rule", T("brass-pipeline.row23"), T("brass-pipeline.row24"))],
            [("rule", T("brass-pipeline.row25"), T("brass-pipeline.row26"))],
            [("rule", T("brass-pipeline.row27"), T("brass-pipeline.row28"))],
            [("human", T("brass-pipeline.row29"), T("brass-pipeline.row30"))],
            [("rule", T("brass-pipeline.row31"), T("brass-pipeline.row32"))],
        ],
    },
    # ------------------------------------------------------------------------------- fretted
    "tab-notes": {
        "title": T("tab-notes.title"),
        "holds": ["fretted/bass-tab/song.onset_f1 > 0.8", "fretted/bass-tab/instrument.onset_f1 > 0.8", "fretted/guitar-tab/report.solo.onset_f1 > 0.7",
                  "fretted/guitar-tab/report.comp.onset_f1 > 0.7", "fretted/guitar-tab/song.onset_f1 < 0.5"],
        "sub": T("tab-notes.sub"),
        "axis": T("tab-notes.axis"),
        "series": [T("tab-notes.series1"), T("tab-notes.series2")],
        "view_label": T("tab-notes.views_name"),
        "views": [
            {"label": T("tab-notes.view_label1"),
             "note": T("tab-notes.view_note1"),
             "rows": [
                 {"label": T("tab-notes.row_label1"), "keys": [F + "bass-tab/instrument.onset_f1", F + "bass-tab/song.onset_f1"],
                  "n": T("tab-notes.row_n1")},
                 {"label": T("tab-notes.row_label2"), "keys": [F + "guitar-tab/report.solo.onset_f1", None],
                  "n": T("tab-notes.row_n2")},
                 {"label": T("tab-notes.row_label3"), "keys": [F + "guitar-tab/report.comp.onset_f1", None],
                  "n": T("tab-notes.row_n3")},
                 {"label": T("tab-notes.row_label4"), "keys": [F + "guitar-tab/idmt.report.onset_f1", None],
                  "n": T("tab-notes.row_n4")},
                 {"label": T("tab-notes.row_label5"), "keys": [None, F + "guitar-tab/song.onset_f1"],
                  "n": T("tab-notes.row_n5")}]},
            {"label": T("tab-notes.view_label2"),
             "note": T("tab-notes.view_note2"),
             "rows": [{"label": label, "keys": [F + f"{suite}/{group}.instrument.onset_f1", F + f"{suite}/{group}.song.onset_f1"],
                       "n": T("tab-notes.row_n6", suite, group)}
                      for label, suite, group in (
                          (T("tab-notes.row1"), "ukulele-tab", "ukulele_high_g_heldout"),
                          (T("tab-notes.row2"), "ukulele-tab", "ukulele_low_g_heldout"),
                          (T("tab-notes.row3"), "ukulele-tab", "ukulele_baritone_heldout"),
                          (T("tab-notes.row4"), "mandolin-tab", "mandolin_heldout"),
                          (T("tab-notes.row5"), "guitar-rendered-tab", "guitar_nylon_heldout"),
                          (T("tab-notes.row6"), "guitar-rendered-tab", "guitar_clean_heldout"))]},
            {"label": T("tab-notes.view_label3"),
             "note": T("tab-notes.view_note3"),
             "rows": [{"label": label, "keys": [F + f"{suite}/{group}.instrument.onset_f1", F + f"{suite}/{group}.song.onset_f1"],
                       "n": T("tab-notes.row_n6", suite, group)}
                      for label, suite, group in (
                          (T("tab-notes.row1"), "ukulele-tab", "ukulele_high_g_heldout_dev"),
                          (T("tab-notes.row2"), "ukulele-tab", "ukulele_low_g_heldout_dev"),
                          (T("tab-notes.row3"), "ukulele-tab", "ukulele_baritone_heldout_dev"),
                          (T("tab-notes.row4"), "mandolin-tab", "mandolin_heldout_dev"),
                          (T("tab-notes.row5"), "guitar-rendered-tab", "guitar_nylon_heldout_dev"),
                          (T("tab-notes.row6"), "guitar-rendered-tab", "guitar_clean_heldout_dev"))]},
        ],
        "caption": T("tab-notes.caption"),
        "source": T("tab-notes.source"),
    },
    "tab-strings": {
        "title": T("tab-strings.title"),
        "holds": ["fretted/guitar-tab/report.solo.string_agreement < 0.5", "fretted/guitar-tab/tune.solo.string_agreement < 0.5",
                  "fretted/guitar-tab/idmt.report.string_agreement < 0.5", "fretted/guitar-tab/report.comp.string_agreement > 0.6"],
        "format": "pct",
        "sub": T("tab-strings.sub"),
        "axis": T("tab-strings.axis"),
        "series": [T("tab-strings.series1"), T("tab-strings.series2")],
        "view_label": T("tab-strings.views_name"),
        "views": [{"label": label, "note": note, "rows": [
            {"label": text, "keys": [F + f"guitar-tab/{group}.string_agreement", F + f"guitar-tab/{group}.string_recall"],
             "n": T("tab-strings.row_n", group)}
            for text, group in ((T("tab-strings.row1"), f"{split}.solo"), (T("tab-strings.row2"), f"{split}.comp"),
                                (T("tab-strings.row3"), f"idmt.{split}"))]}
            for label, note, split in (
                (T("tab-strings.view1"), T("tab-strings.view2"), "report"),
                (T("tab-strings.view3"), T("tab-strings.view4"), "tune"))],
        "caption": T("tab-strings.caption"),
        "source": T("tab-strings.source"),
    },
    "tab-doubt": {
        "title": T("tab-doubt.title"),
        "holds": [f"fretted/{k}.doubt_recall < 0.4" for k in ("bass-tab/song", "bass-tab/instrument", "guitar-tab/report.solo", "guitar-tab/report.comp", "guitar-tab/song")]
                 + [f"fretted/{k}.doubt_precision > 0.7" for k in ("bass-tab/song", "bass-tab/instrument", "guitar-tab/report.solo", "guitar-tab/report.comp", "guitar-tab/song")],
        "format": "pct",
        "sub": T("tab-doubt.sub"),
        "axis": SHARE_AXIS,
        "series": [T("tab-doubt.series1"), T("tab-doubt.series2")],
        "views": [{"label": T("tab-doubt.view_label"), "rows": [
            {"label": label, "keys": [F + f"{key}.doubt_precision", F + f"{key}.doubt_recall"], "n": T("tab-doubt.row_n", key, count, unit)}
            for label, key, count, unit in (
                (T("tab-doubt.row1"), "bass-tab/song", "tracks", T("tab-doubt.row2")),
                (T("tab-doubt.row3"), "bass-tab/instrument", "tracks", T("tab-doubt.row2")),
                (T("tab-doubt.row4"), "guitar-tab/report.solo", "excerpts", T("tab-doubt.row5")),
                (T("tab-doubt.row6"), "guitar-tab/report.comp", "excerpts", T("tab-doubt.row5")),
                (T("tab-doubt.row7"), "guitar-tab/song", "excerpts", T("tab-doubt.row8")))]}],
        "caption": T("tab-doubt.caption"),
        "source": T("tab-doubt.source"),
    },
    "tab-tempo": {
        "title": T("tab-tempo.title"),
        "holds": [f"fretted/{k}.meter_ok > 0.9" for k in ("bass-tab/song", "bass-tab/instrument", "guitar-tab/report.solo", "guitar-tab/report.comp", "guitar-tab/song")]
                 + [f"fretted/{k}.tempo_ok >= 0.6" for k in ("bass-tab/song", "bass-tab/instrument", "guitar-tab/report.solo", "guitar-tab/report.comp", "guitar-tab/song")]
                 + [f"fretted/{k}.tempo_ok < 0.95" for k in ("bass-tab/song", "bass-tab/instrument", "guitar-tab/report.solo", "guitar-tab/report.comp", "guitar-tab/song")],
        "format": "pct",
        "sub": T("tab-tempo.sub"),
        "axis": T("tab-tempo.axis"),
        "series": [T("tab-tempo.series1"), T("tab-tempo.series2")],
        "views": [{"label": T("tab-tempo.view_label"), "rows": [
            {"label": label, "keys": [F + f"{key}.tempo_ok", F + f"{key}.meter_ok"], "n": T("tab-tempo.row_n", key, count, unit)}
            for label, key, count, unit in (
                (T("tab-tempo.row1"), "bass-tab/song", "tracks", T("tab-tempo.row2")),
                (T("tab-tempo.row3"), "bass-tab/instrument", "tracks", T("tab-tempo.row2")),
                (T("tab-tempo.row4"), "guitar-tab/report.solo", "excerpts", T("tab-tempo.row5")),
                (T("tab-tempo.row6"), "guitar-tab/report.comp", "excerpts", T("tab-tempo.row5")),
                (T("tab-tempo.row7"), "guitar-tab/song", "excerpts", T("tab-tempo.row8")))]}],
        "caption": T("tab-tempo.caption"),
        "source": T("tab-tempo.source"),
    },
    "tab-phone": {
        "title": T("tab-phone.title"),
        "holds": ["fretted/bass-tab/phone.hp0.onset_f1 > fretted/bass-tab/phone.hp100.onset_f1", "fretted/bass-tab/phone.hp100.onset_f1 > fretted/bass-tab/phone.hp200.onset_f1",
                  "fretted/bass-tab/phone.hp200.onset_f1 > fretted/bass-tab/phone.hp300.onset_f1"],
        "sub": T("tab-phone.sub"),
        "axis": T("tab-phone.axis"),
        "series": [T("tab-phone.series")],
        "views": [{"label": T("tab-phone.view_label"),
                   "note": T("tab-phone.view_note"),
                   "rows": [
            {"label": label, "keys": [F + f"bass-tab/phone.hp{cut}.onset_f1"], "n": T("tab-phone.row_n", cut)}
            for cut, label in ((0, T("tab-phone.row1")), (100, T("tab-phone.row2")),
                               (200, T("tab-phone.row3")), (300, T("tab-phone.row4")))]}],
        "caption": T("tab-phone.caption"),
        "source": T("tab-phone.source"),
    },
    "tab-slots": {
        "title": T("tab-slots.title"),
        "holds": [f"fretted/guitar-tab/report.comp.slot_16th_off <= fretted/guitar-tab/{g}.slot_16th_off" for g in ("tune.solo", "tune.comp", "report.solo")]
                 + [f"fretted/guitar-tab/report.solo.slot_16th_off >= fretted/guitar-tab/{g}.slot_16th_off" for g in ("tune.solo", "tune.comp", "report.comp")]
                 + [f"m/tab_grid_choice/tune_comp_dense <= m/tab_grid_choice/{g}_dense" for g in ("tune_solo", "report_solo", "report_comp")]
                 + [f"m/tab_grid_choice/tune_solo_dense >= m/tab_grid_choice/{g}_dense" for g in ("tune_comp", "report_solo", "report_comp")]
                 + ["m/tab_grid_choice/tune_comp_dense > fretted/guitar-tab/report.solo.slot_16th_off"],
        "format": "pct",
        "sub": T("tab-slots.sub"),
        "axis": T("tab-slots.axis"),
        "series": [T("tab-slots.series1"), T("tab-slots.series2")],
        "views": [{"label": "GuitarSet", "note": T("tab-slots.view_note"), "rows": [
            {"label": text, "keys": [F + f"guitar-tab/{group}.{kind}.slot_16th_off", f"m/tab_grid_choice/{group}_{kind}_dense"],
             "n": T("tab-slots.row_n", group, kind)}
            for text, group, kind in ((T("tab-slots.row1"), "tune", "solo"), (T("tab-slots.row2"), "tune", "comp"),
                                      (T("tab-slots.row3"), "report", "solo"), (T("tab-slots.row4"), "report", "comp"))]}],
        "caption": T("tab-slots.caption"),
        "source": T("tab-slots.source"),
    },
    "tab-heldout": {
        "title": T("tab-heldout.title"),
        "holds": ["fretted/guitar-tab/report.solo.chord_recall < fretted/guitar-tab/tune.solo.chord_recall", "fretted/guitar-tab/report.solo.chord_recall < 0.5"],
        "format": "pct",
        "sub": T("tab-heldout.sub"),
        "series": [T("tab-heldout.series1"), T("tab-heldout.series2")],
        "view_label": T("tab-heldout.views_name"),
        "views": [{"label": label, "axis": axis, "format": "f2" if key == "onset_f1" else "pct", "rows": [
            {"label": text, "keys": [F + f"guitar-tab/tune.{kind}.{key}", F + f"guitar-tab/report.{kind}.{key}"],
             "n": T("tab-heldout.row_n", kind)}
            for text, kind in ((T("tab-heldout.row1"), "solo"), (T("tab-heldout.row2"), "comp"))]}
            for label, key, axis in (
                (T("tab-heldout.view1"), "chord_recall", T("tab-heldout.view2")),
                (T("tab-heldout.view3"), "chord_precision", T("tab-heldout.view4")),
                (T("tab-heldout.view5"), "onset_f1", T("tab-heldout.view6")))],
        "caption": T("tab-heldout.caption"),
        "source": T("tab-heldout.source"),
    },
    "fret-pipeline": {
        "title": T("fret-pipeline.title"),
        "desc": T("fret-pipeline.desc"),
        "legend": [T("fret-pipeline.legend1"), T("fret-pipeline.legend2"), T("fret-pipeline.legend3")],
        "caption": T("fret-pipeline.caption"),
        "rows": [
            [("rule", T("fret-pipeline.row1"), T("fret-pipeline.row2"))],
            [("human", T("fret-pipeline.row3"), T("fret-pipeline.row4"))],
            [("model", T("fret-pipeline.row5"), T("fret-pipeline.row6")),
             ("model", T("fret-pipeline.row7"), T("fret-pipeline.row8"))],
            [("model", T("fret-pipeline.row9"), T("fret-pipeline.row10")),
             ("rule", T("fret-pipeline.row11"), T("fret-pipeline.row12"))],
            [("rule", T("fret-pipeline.row13"), T("fret-pipeline.row14"))],
            [("rule", T("fret-pipeline.row15"), T("fret-pipeline.row16"))],
            [("rule", T("fret-pipeline.row17"), T("fret-pipeline.row18"))],
            [("human", T("fret-pipeline.row19"), T("fret-pipeline.row20"))],
            [("rule", T("fret-pipeline.row21"), T("fret-pipeline.row22"))],
        ],
    },
}
