//! Unit-level conformance of the brass-band target: Rust functions against outputs of the Python
//! reference (the fixtures are the shared core's, regenerated with
//! `uv run python -m brasscribe_conformance.fixtures` in core/conformance).

use serde_json::Value;

fn load(name: &str) -> Vec<Value> {
    let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../brasscribe-core/tests/fixtures").join(format!("{name}.json"));
    serde_json::from_str::<Value>(&std::fs::read_to_string(p).unwrap()).unwrap().as_array().unwrap().clone()
}

fn i64s(v: &Value) -> Vec<i64> {
    v.as_array().unwrap().iter().map(|x| x.as_i64().unwrap()).collect()
}

#[test]
fn voice_satb_matches_reference() {
    use target_brass::arranger::{chord_root, perfect_parallels, voice_satb};
    let opt = |v: &Value| v.as_i64().map(|x| x as i32);
    let pair = |v: &Value| (v[0].as_i64().unwrap() as i32, v[1].as_i64().unwrap() as i32);
    for (i, c) in load("voice_satb").iter().enumerate() {
        let pcs: Vec<i32> = i64s(&c["pcs"]).into_iter().map(|x| x as i32).collect();
        let (sop, bass, top) = (opt(&c["soprano"]), opt(&c["bass"]), opt(&c["soprano_top"]));
        let prev: Option<[Option<i32>; 4]> = c["prev"].as_array().map(|p| [opt(&p[0]), opt(&p[1]), opt(&p[2]), opt(&p[3])]);
        let got = voice_satb(&pcs, sop, bass, prev.as_ref(), pair(&c["alto_range"]), pair(&c["tenor_range"]), top);
        let want = c["pair"].as_array().map(|_| pair(&c["pair"]));
        assert_eq!(got, want, "case {i}");
        assert_eq!(chord_root(&pcs, bass.map(|b| b.rem_euclid(12))) as i64, c["root"].as_i64().unwrap(), "root {i}");
        if let Some(p) = prev {
            let cur = [sop, got.map(|g| g.0), got.map(|g| g.1), bass];
            assert_eq!(perfect_parallels(&p, &cur) as i64, c["parallels"].as_i64().unwrap(), "parallels {i}");
        }
    }
}

#[test]
fn seats_match_reference() {
    use target_brass::instruments::{check_reads, seat_part};
    for c in load("seats") {
        let seat = c["seat"].as_str().unwrap();
        if let Some(reads) = c["reads"].as_str() {
            assert_eq!(check_reads(Some(seat), Some(reads)).is_ok(), c["ok"].as_bool().unwrap(), "{seat} reads {reads}");
            continue;
        }
        let sp = seat_part(c["lineup"].as_str().unwrap(), seat).unwrap();
        assert_eq!(sp.part, c["part"].as_str(), "{c}");
        assert_eq!(sp.exact, c["exact"].as_bool().unwrap(), "{c}");
        assert_eq!(sp.same_key, c["same_key"].as_bool().unwrap(), "{c}");
        assert_eq!(sp.takes, c["takes"].as_str(), "{c}");
    }
}

#[test]
fn part_sources_match_reference() {
    use target_brass::arranger::part_sources;
    use brasscribe_core::model::Composition;
    for (i, c) in load("part_sources").iter().enumerate() {
        let comp: Composition = serde_json::from_value(c["composition"].clone()).unwrap();
        let want: Vec<(String, String)> =
            c["sources"].as_array().unwrap().iter().map(|p| (p[0].as_str().unwrap().into(), p[1].as_str().unwrap().into())).collect();
        let got: Vec<(String, String)> = part_sources(&comp).into_iter().map(|(p, s)| (p, s.to_string())).collect();
        assert_eq!(got, want, "case {i}");
    }
}

#[test]
fn difficulty_trills_match_reference() {
    use target_brass::difficulty::apply_difficulty_opts;
    use target_brass::instruments::minimal_band;
    use brasscribe_core::model::Note;
    let notes = |v: &Value| -> Vec<Note> { serde_json::from_value(v.clone()).unwrap() };
    for (i, c) in load("trills").iter().enumerate() {
        let Some(runs) = c["difficulty"].as_array() else { continue };
        let parts: Vec<(String, Vec<Note>)> =
            c["parts"].as_array().unwrap().iter().map(|p| (p[0].as_str().unwrap().to_string(), notes(&p[1]))).collect();
        for r in runs {
            let (mode, trills) = (r["mode"].as_str().unwrap(), r["trills"].as_bool());
            let got = apply_difficulty_opts(parts.clone(), &minimal_band(), mode, None, trills).unwrap();
            for w in r["parts"].as_array().unwrap() {
                let name = w[0].as_str().unwrap();
                let g = got.iter().find(|(n, _)| n == name).map(|(_, v)| v.clone()).unwrap_or_default();
                assert_eq!(g, notes(&w[1]), "difficulty case {i} {mode} {trills:?} {name}");
            }
        }
    }
}
