//! part_sources calls a part `empty` exactly when the arranger leaves it without notes: the
//! Percussion part of a recording without drums, the Soprano Cornet with no climax to double.

use target_brass::arranger::{part_footers, part_sources, ARRANGED, EMPTY, RECORDING};
use brasscribe_core::model::Composition;
use target_brass::pipeline::arrange_composition;

/// A layered take: solo, bass, strings and brass, drums optional; the solo ff over strings f in the
/// second bar (a climax the Soprano Cornet doubles unless faithful).
fn comp(drums: bool, difficulty: &str) -> Composition {
    let notes = |p: i32| (0..8).map(|i| format!(r#"{{"pitch": {}, "start": {}, "dur": 24}}"#, p + (i % 3), i * 24)).collect::<Vec<_>>().join(",");
    let voice = |id: &str, role: &str, p: i32, on: bool| {
        format!(r#"{{"id": "{id}", "role": "{role}", "layer": "{id}", "notes": [{}]}}"#, if on { notes(p) } else { String::new() })
    };
    let json = format!(
        r#"{{"title": "t", "voices": [{}, {}, {}, {}, {}], "meters": [{{"tick": 0, "beats": 4}}], "keys": [{{"tick": 0, "fifths": 0}}],
        "dynamics": [{{"tick": 0, "layer": "solo", "mark": "mf"}}, {{"tick": 96, "layer": "solo", "mark": "ff"}},
                     {{"tick": 0, "layer": "strings", "mark": "f"}}],
        "arrangement": {{"lineup": "band", "difficulty": "{difficulty}", "transpose_semitones": 0}}}}"#,
        voice("solo", "melody", 67, true),
        voice("bass", "bass", 40, true),
        voice("strings", "harmony", 60, true),
        voice("brass", "harmony", 55, true),
        voice("drums", "rhythm", 38, drums),
    );
    Composition::from_json_str(&json).unwrap()
}

#[test]
fn empty_iff_the_arranged_part_has_no_notes() {
    for drums in [false, true] {
        for difficulty in ["faithful", "standard", "easier"] {
            let c = comp(drums, difficulty);
            let arr = arrange_composition(&c).unwrap();
            for (part, source) in part_sources(&c) {
                assert_eq!(source == EMPTY, arr.part_notes(&part).is_empty(), "{part} ({difficulty}, drums {drums}): {source}");
            }
        }
    }
    let src: std::collections::HashMap<String, &str> = part_sources(&comp(false, "faithful")).into_iter().collect();
    assert_eq!((src["Percussion"], src["Soprano Cornet"], src["Solo Horn"]), (EMPTY, EMPTY, ARRANGED));
    let src: std::collections::HashMap<String, &str> = part_sources(&comp(true, "standard")).into_iter().collect();
    assert_eq!((src["Percussion"], src["Soprano Cornet"]), (RECORDING, ARRANGED));
}

#[test]
fn empty_parts_have_no_footer() {
    let footers = part_footers(&comp(false, "faithful"), "nb");
    assert!(footers.iter().all(|(p, _)| p != "Percussion" && p != "Soprano Cornet"));
    assert!(footers.iter().any(|(p, _)| p == "Solo Horn"));
}
