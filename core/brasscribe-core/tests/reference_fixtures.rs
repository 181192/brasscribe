//! Unit-level conformance: Rust functions against outputs of the Python
//! reference on seeded synthetic inputs (regenerate with
//! `uv run python -m brasscribe_conformance.fixtures` in core/conformance).

use brasscribe_core::midi::RawNote;
use brasscribe_core::notation::duration::{quarter_conversion, Rat};
use brasscribe_core::py::np_argsort;
use brasscribe_core::quantize::{choose_level, fill_gaps, quantize};
use brasscribe_core::spelling::{key_of, spell};
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
        let rows = |q: &[brasscribe_core::quantize::QNote]| -> Vec<Vec<i64>> { q.iter().map(|x| vec![x.pitch as i64, x.start, x.end]).collect() };
        let want: Vec<Vec<i64>> = c["quantized"].as_array().unwrap().iter().map(i64s).collect();
        assert_eq!(rows(&q), want, "quantize case {i}");
        let filled = fill_gaps(q, 12, 0.0);
        let want: Vec<Vec<i64>> = c["filled"].as_array().unwrap().iter().map(i64s).collect();
        assert_eq!(rows(&filled), want, "fill_gaps case {i}");
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
