//! Unit-level conformance: Rust functions against outputs of the Python
//! reference on seeded synthetic inputs (regenerate with
//! `uv run python -m scribe_conformance.fixtures` in core/conformance).

use scribe_core::midi::RawNote;
use scribe_core::notation::duration::{quarter_conversion, Rat};
use scribe_core::py::np_argsort;
use scribe_core::quantize::{choose_level, fill_gaps, quantize, quantize_with};
use scribe_core::spelling::{key_of, spell};
use serde_json::Value;

fn load(name: &str) -> Vec<Value> {
    let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures").join(format!("{name}.json"));
    serde_json::from_str::<Value>(&std::fs::read_to_string(p).unwrap()).unwrap().as_array().unwrap().clone()
}

fn f64s(v: &Value) -> Vec<f64> {
    v.as_array().unwrap().iter().map(|x| x.as_f64().unwrap()).collect()
}

fn i64s(v: &Value) -> Vec<i64> {
    v.as_array().unwrap().iter().map(|x| x.as_i64().unwrap()).collect()
}

#[test]
fn confidence_and_review_groups_match_reference() {
    use scribe_core::confidence::{features, p_correct, review_groups, support, Model};
    use scribe_core::durations::Contour;
    let model = Model::load();
    for (i, c) in load("confidence").iter().enumerate() {
        let k = &c["contour"];
        let contour = Contour {
            t: f64s(&k["t"]),
            midi: k["midi"].as_array().unwrap().iter().map(|x| x.as_f64().unwrap_or(f64::NAN)).collect(),
            loudness_db: vec![0.0; k["t"].as_array().unwrap().len()],
            confidence: if k["confidence"].is_null() { None } else { Some(f64s(&k["confidence"])) },
        };
        let use_c = c["use_contour"].as_bool().unwrap();
        for n in c["notes"].as_array().unwrap() {
            let sup = support(if use_c { Some(&contour) } else { None }, n["onset"].as_f64().unwrap(), n["pitch"].as_i64().unwrap() as i32);
            assert_eq!(sup.map(f64::to_bits), n["support"].as_f64().map(f64::to_bits), "case {i}: support");
            let src = n["sources"].as_array().unwrap().iter().map(|s| s.as_str().unwrap().to_string()).collect();
            let x = features(&src, n["dur"].as_f64().unwrap(), sup, c["separated"].as_bool().unwrap());
            assert_eq!(p_correct(&x, &model).to_bits(), n["p"].as_f64().unwrap().to_bits(), "case {i}: p_correct");
        }
        let ev: Vec<(i64, i64, f64)> =
            c["events"].as_array().unwrap().iter().map(|e| (e[0].as_i64().unwrap(), e[1].as_i64().unwrap(), e[2].as_f64().unwrap())).collect();
        let got: Vec<(i64, i64, i64, bool)> =
            review_groups(&ev, c["bar"].as_i64().unwrap(), model.mark_below(), model.very_below()).into_iter().map(|g| (g.start, g.end, g.notes, g.very)).collect();
        let want: Vec<(i64, i64, i64, bool)> = c["groups"]
            .as_array()
            .unwrap()
            .iter()
            .map(|g| (g[0].as_i64().unwrap(), g[1].as_i64().unwrap(), g[2].as_i64().unwrap(), g[3].as_bool().unwrap()))
            .collect();
        assert_eq!(got, want, "case {i}: groups");
    }
}

#[test]
fn solo_meter_matches_reference() {
    use scribe_core::beats::{labels_on, solo_meter, track_bar_phase, PHASE_JUMP_COST};
    for (i, c) in load("meter").iter().enumerate() {
        let (t, grid, on, du) = (f64s(&c["t"]), f64s(&c["grid"]), f64s(&c["onsets"]), f64s(&c["durations"]));
        let pos = i64s(&c["pos"]);
        let gp = labels_on(&grid, &t, &pos, 0);
        assert_eq!(gp, i64s(&c["grid_pos"]), "case {i}: labels");
        let down: Vec<bool> = gp.iter().map(|&p| p == 1).collect();
        let m = solo_meter(&grid, &down, &gp, 1, 0, &on, &du);
        let want = &c["meter"];
        assert_eq!(m.beats_per_bar, want[0].as_i64().unwrap(), "case {i}: bpb");
        assert_eq!(m.first_downbeat, want[1].as_i64().unwrap(), "case {i}: first");
        assert_eq!((m.from_labels, m.compound), (want[2].as_bool().unwrap(), want[3].as_bool().unwrap()), "case {i}");
        assert_eq!(m.strength.to_bits(), want[4].as_f64().unwrap().to_bits(), "case {i}: strength");
        assert_eq!(m.times, if want[5].is_null() { None } else { Some(f64s(&want[5])) }, "case {i}: times");
        let tr = &c["track"];
        let (tb, first) = track_bar_phase(&t, &pos.iter().map(|&p| (p == 1) as i64 as f64).collect::<Vec<_>>(), tr[0].as_i64().unwrap(), PHASE_JUMP_COST, None);
        assert_eq!(tb, f64s(&tr[1]), "case {i}: tracked times");
        assert_eq!(first, tr[2].as_i64().unwrap(), "case {i}: tracked first");
    }
}

#[test]
fn spelling_and_key_match_reference() {
    for (i, c) in load("spelling").iter().enumerate() {
        let on = f64s(&c["onsets"]);
        let du = f64s(&c["durations"]);
        let ps: Vec<i32> = i64s(&c["pitches"]).into_iter().map(|x| x as i32).collect();
        let got: Vec<(String, i64, i64)> = spell(&on, &ps).iter().map(|s| (s.step.to_string(), s.alter as i64, s.octave as i64)).collect();
        let want: Vec<(String, i64, i64)> = c["spelled"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| (x[0].as_str().unwrap().to_string(), x[1].as_i64().unwrap(), x[2].as_i64().unwrap()))
            .collect();
        assert_eq!(got, want, "spelling case {i}");
        let (name, fifths) = key_of(&du, &ps);
        assert_eq!(name, c["key"].as_str().unwrap(), "key case {i}");
        assert_eq!(fifths as i64, c["fifths"].as_i64().unwrap(), "fifths case {i}");
    }
}

#[test]
fn quantize_matches_reference() {
    for (i, c) in load("quantize").iter().enumerate() {
        let beats = f64s(&c["beats"]);
        let notes: Vec<RawNote> = c["notes"]
            .as_array()
            .unwrap()
            .iter()
            .map(|n| RawNote::new(n["pitch"].as_i64().unwrap() as i32, n["onset"].as_f64().unwrap(), n["offset"].as_f64().unwrap()))
            .collect();
        let on: Vec<f64> = notes.iter().map(|n| n.onset).collect();
        assert_eq!(choose_level(&beats, &on), f64s(&c["level"]), "level case {i}");
        let q = quantize(&notes, &beats, c["monophonic"].as_bool().unwrap(), c["auto_level"].as_bool().unwrap());
        let rows = |q: &[scribe_core::quantize::QNote]| -> Vec<Vec<i64>> { q.iter().map(|x| vec![x.pitch as i64, x.start, x.end]).collect() };
        let want: Vec<Vec<i64>> = c["quantized"].as_array().unwrap().iter().map(i64s).collect();
        assert_eq!(rows(&q), want, "quantize case {i}");
        let filled = fill_gaps(q, 12, 0.0);
        let want: Vec<Vec<i64>> = c["filled"].as_array().unwrap().iter().map(i64s).collect();
        assert_eq!(rows(&filled), want, "fill_gaps case {i}");
    }
}

#[test]
fn dense_quantize_matches_reference() {
    for (i, c) in load("quantize_dense").iter().enumerate() {
        let beats = f64s(&c["beats"]);
        let notes: Vec<RawNote> = c["notes"]
            .as_array()
            .unwrap()
            .iter()
            .map(|n| {
                let mut r = RawNote::new(n["pitch"].as_i64().unwrap() as i32, n["onset"].as_f64().unwrap(), n["offset"].as_f64().unwrap());
                r.confidence = n["confidence"].as_f64();
                r
            })
            .collect();
        let coarse: Option<Vec<(f64, f64)>> =
            c["coarse"].as_array().map(|r| r.iter().map(|x| (x[0].as_f64().unwrap(), x[1].as_f64().unwrap())).collect());
        let q = quantize_with(&notes, &beats, true, false, coarse.as_deref(), true);
        let got: Vec<(i64, i64, i64, u64)> = q.iter().map(|x| (x.pitch as i64, x.start, x.end, x.confidence.to_bits())).collect();
        let want: Vec<(i64, i64, i64, u64)> = c["quantized"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| (x[0].as_i64().unwrap(), x[1].as_i64().unwrap(), x[2].as_i64().unwrap(), x[3].as_f64().unwrap().to_bits()))
            .collect();
        assert_eq!(got, want, "dense quantize case {i}");
    }
}

#[test]
fn contour_onsets_match_reference() {
    use scribe_core::durations::Contour;
    use scribe_core::onsets::contour_notes;
    let notes_of = |v: &Value| -> Vec<RawNote> {
        v.as_array()
            .unwrap()
            .iter()
            .map(|n| RawNote::new(n["pitch"].as_i64().unwrap() as i32, n["onset"].as_f64().unwrap(), n["offset"].as_f64().unwrap()))
            .collect()
    };
    for (i, c) in load("onsets").iter().enumerate() {
        let t = f64s(&c["t"]);
        let contour = Contour {
            midi: c["midi"].as_array().unwrap().iter().map(|x| x.as_f64().unwrap_or(f64::NAN)).collect(),
            loudness_db: vec![0.0; t.len()],
            confidence: if c["confidence"].is_null() { None } else { Some(f64s(&c["confidence"])) },
            t,
        };
        let got: Vec<(i64, u64, u64, bool)> = contour_notes(&notes_of(&c["notes"]), Some(&contour), &notes_of(&c["others"]))
            .iter()
            .map(|n| (n.pitch as i64, n.onset.to_bits(), n.offset.to_bits(), n.split))
            .collect();
        let want: Vec<(i64, u64, u64, bool)> = c["out"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| (x[0].as_i64().unwrap(), x[1].as_f64().unwrap().to_bits(), x[2].as_f64().unwrap().to_bits(), x[3].as_bool().unwrap()))
            .collect();
        assert_eq!(got, want, "onsets case {i}");
    }
}

#[test]
fn argsort_order_matches_numpy() {
    for (i, c) in load("argsort").iter().enumerate() {
        let v: Vec<i32> = i64s(&c["values"]).into_iter().map(|x| x as i32).collect();
        let want: Vec<usize> = i64s(&c["argsort"]).into_iter().map(|x| x as usize).collect();
        assert_eq!(np_argsort(&v), want, "argsort case {i}");
    }
}

#[test]
fn free_time_plans_match_reference() {
    use scribe_core::freetime::{local_tempo, plan_free_time, unstable_runs};
    for (i, c) in load("freetime").iter().enumerate() {
        let t = f64s(&c["t"]);
        let on = f64s(&c["onsets"]);
        let runs: Vec<(usize, usize)> = unstable_runs(&t);
        let want: Vec<(usize, usize)> = c["runs"].as_array().unwrap().iter().map(|r| (r[0].as_u64().unwrap() as usize, r[1].as_u64().unwrap() as usize)).collect();
        assert_eq!(runs, want, "runs case {i}");
        assert_eq!(local_tempo(&on, t[0], t[t.len() - 1]), c["local_tempo"].as_f64().unwrap(), "local tempo case {i}");
        let downs: Option<Vec<bool>> = c["downbeats"].as_array().map(|a| a.iter().map(|x| x.as_bool().unwrap()).collect());
        let tempo_on: Option<Vec<f64>> = c["tempo_onsets"].as_array().map(|_| f64s(&c["tempo_onsets"]));
        let first = c["first"].as_i64().unwrap();
        let p = plan_free_time(&t, &on, c["bpb"].as_i64().unwrap(), first, downs.as_deref(), c["tempo"].as_f64(), tempo_on.as_deref());
        let w = &c["plan"];
        assert_eq!(p.beat_times, f64s(&w["beat_times"]), "beat times case {i}");
        assert_eq!(p.first_downbeat, w["first_downbeat"].as_i64().unwrap(), "first downbeat case {i}");
        let spans: Vec<(i64, i64, f64, f64, f64)> = p.spans.iter().map(|s| (s.start as i64, s.end as i64, s.start_s, s.end_s, s.bpm)).collect();
        let want: Vec<(i64, i64, f64, f64, f64)> = w["spans"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| (s[0].as_i64().unwrap(), s[1].as_i64().unwrap(), s[2].as_f64().unwrap(), s[3].as_f64().unwrap(), s[4].as_f64().unwrap()))
            .collect();
        assert_eq!(spans, want, "spans case {i}");
        assert_eq!(p.notation, w["notation"].as_str().unwrap(), "notation case {i}");
        let regions: Vec<(i64, i64, f64, f64, f64)> = p.regions(first).iter().map(|r| (r.start, r.end, r.start_s, r.end_s, r.tempo_bpm)).collect();
        let want: Vec<(i64, i64, f64, f64, f64)> = w["regions"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| (s[0].as_i64().unwrap(), s[1].as_i64().unwrap(), s[2].as_f64().unwrap(), s[3].as_f64().unwrap(), s[4].as_f64().unwrap()))
            .collect();
        assert_eq!(regions, want, "regions case {i}");
    }
}

#[test]
fn contour_offsets_and_written_durations_match_reference() {
    use scribe_core::durations::{contour_offsets, written_durations, written_durations_with, Contour, ContourSettings, WriteOptions, SEPARATED_STEM};
    use scribe_core::quantize::{BeatMap, QNote};
    for (i, c) in load("durations").iter().enumerate() {
        let contour = Contour::from_hz(f64s(&c["t"]), &f64s(&c["hz"]), f64s(&c["db"]));
        let want_midi: Vec<Option<f64>> = c["midi"].as_array().unwrap().iter().map(|x| x.as_f64()).collect();
        assert_eq!(contour.midi.len(), want_midi.len(), "hz -> midi length case {i}");
        // log2 is not correctly rounded, so glibc and the MSVC CRT can differ from Apple's libm by an ulp.
        for (j, (&got, want)) in contour.midi.iter().zip(&want_midi).enumerate() {
            match want {
                None => assert!(got.is_nan(), "hz -> midi case {i}[{j}]: {got} != NaN"),
                Some(w) => assert!((got - w).abs() <= 1e-9, "hz -> midi case {i}[{j}]: {got} != {w}"),
            }
        }
        let notes: Vec<(f64, i32)> = c["notes"].as_array().unwrap().iter().map(|n| (n[0].as_f64().unwrap(), n[1].as_i64().unwrap() as i32)).collect();
        let settings = if c["separated"].as_bool().unwrap() { SEPARATED_STEM } else { ContourSettings::default() };
        assert_eq!(contour_offsets(&contour, &notes, settings), f64s(&c["ends"]), "contour offsets case {i}");
        let q: Vec<QNote> = c["qnotes"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| QNote {
                pitch: x[0].as_i64().unwrap() as i32,
                start: x[1].as_i64().unwrap(),
                end: x[2].as_i64().unwrap(),
                onset_s: x[3].as_f64().unwrap(),
                offset_s: x[4].as_f64().unwrap(),
                confidence: 1.0,
                articulations: Vec::new(),
            })
            .collect();
        let bm = BeatMap::new(&f64s(&c["beats"])).unwrap();
        let w = written_durations(&q, if c["use_beat_map"].as_bool().unwrap() { Some(&bm) } else { None });
        let got: Vec<(i64, f64, bool)> = w.iter().map(|x| (x.dur, x.performed, x.staccato)).collect();
        let want: Vec<(i64, f64, bool)> = c["written"].as_array().unwrap().iter().map(|x| (x[0].as_i64().unwrap(), x[1].as_f64().unwrap(), x[2].as_bool().unwrap())).collect();
        assert_eq!(got, want, "written durations case {i}");
        let o = WriteOptions { keep_grid: true, ..WriteOptions::default() };
        let w = written_durations_with(&q, if c["use_beat_map"].as_bool().unwrap() { Some(&bm) } else { None }, o);
        let got: Vec<(i64, f64, bool)> = w.iter().map(|x| (x.dur, x.performed, x.staccato)).collect();
        let want: Vec<(i64, f64, bool)> = c["written_on_grid"].as_array().unwrap().iter().map(|x| (x[0].as_i64().unwrap(), x[1].as_f64().unwrap(), x[2].as_bool().unwrap())).collect();
        assert_eq!(got, want, "written durations on the beats' grids case {i}");
    }
}

#[test]
fn quarter_conversion_matches_reference() {
    for c in load("duration") {
        let ql = Rat::new(c["num"].as_i64().unwrap(), c["den"].as_i64().unwrap());
        let (comps, tup) = quarter_conversion(ql);
        let got: Vec<(String, i64)> = comps.iter().map(|d| (d.typ.name().to_string(), d.dots as i64)).collect();
        let want: Vec<(String, i64)> = c["components"].as_array().unwrap().iter().map(|x| (x[0].as_str().unwrap().to_string(), x[1].as_i64().unwrap())).collect();
        assert_eq!(got, want, "components of {ql:?}");
        let got_t = tup.map(|t| (t.actual, t.normal, t.dur_normal.unwrap().typ.name().to_string(), t.dur_normal.unwrap().dots as i64));
        let want_t = c["tuplet"].as_array().map(|t| (t[0].as_i64().unwrap(), t[1].as_i64().unwrap(), t[2].as_str().unwrap().to_string(), t[3].as_i64().unwrap()));
        assert_eq!(got_t, want_t, "tuplet of {ql:?}");
    }
}

#[test]
fn trills_match_reference() {
    use scribe_core::model::Note;
    use scribe_core::trills::{collapse_trills, with_trills};
    let raw = |v: &Value| -> Vec<RawNote> {
        v.as_array()
            .unwrap()
            .iter()
            .map(|n| RawNote::new(n["pitch"].as_i64().unwrap() as i32, n["onset"].as_f64().unwrap(), n["offset"].as_f64().unwrap()))
            .collect()
    };
    let notes = |v: &Value| -> Vec<Note> { serde_json::from_value(v.clone()).unwrap() };
    for (i, c) in load("trills").iter().enumerate() {
        let got: Vec<(i32, u64, u64, i32)> =
            with_trills(&raw(&c["line"]), &raw(&c["perf"])).iter().map(|n| (n.pitch, n.onset.to_bits(), n.offset.to_bits(), n.trill)).collect();
        let want: Vec<(i32, u64, u64, i32)> = c["with_trills"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| (x[0].as_i64().unwrap() as i32, x[1].as_f64().unwrap().to_bits(), x[2].as_f64().unwrap().to_bits(), x[3].as_i64().unwrap() as i32))
            .collect();
        assert_eq!(got, want, "with_trills case {i}");
        assert_eq!(collapse_trills(&notes(&c["notes"])), notes(&c["collapsed"]), "collapse_trills case {i}");
    }
}
