//! Tab fingering through the bindings: `target-fretted`'s JSON request in and its JSON answer out,
//! through the UniFFI functions and the C ABI. What a request gets wrong is invalid input, never a
//! panic.

use std::ffi::{CStr, CString};
use std::os::raw::c_char;

use brasscribe_ffi::c_api::{bc_fretted_fingering_json, bc_fretted_tab_json, bc_string_free, BC_INVALID, BC_NULL, BC_OK};
use brasscribe_ffi::fretted::{fretted_fingering_json, fretted_tab_json};
use brasscribe_ffi::CoreError;
use serde_json::{json, Value};

/// A line on a 4-string bass down to D1, which standard tuning cannot play.
fn request() -> Value {
    json!({
        "instrument": {"preset": "bass-4-standard"},
        "notes": [
            {"pitch": 26, "start": 0, "dur": 24},
            {"pitch": 33, "start": 24, "dur": 24, "confidence": 0.3},
            {"pitch": 38, "start": 48, "dur": 12},
            {"pitch": 40, "start": 60, "dur": 36, "techniques": ["hammer-on"]},
        ],
        "options": {"style": "open-position", "tempo_bpm": 96},
    })
}

/// A full instrument with `strings` strings a fourth apart, edited.
fn custom(edit: &dyn Fn(&mut Value), strings: usize) -> Value {
    let open: Vec<Value> = (0..strings).map(|i| json!({"open_pitch": 43 - 5 * (i % 4) as i32, "first_fret": 0})).collect();
    let mut inst = json!({"name": "Custom", "tuning": {"name": "Fourths", "strings": open}, "frets": 20, "scale_length_mm": 864.0, "capo": 0});
    edit(&mut inst);
    inst
}

fn reason(r: Result<String, CoreError>) -> String {
    match r {
        Err(CoreError::Invalid { reason }) => reason,
        other => panic!("expected invalid input, got {other:?}"),
    }
}

/// Code and text (the result or the error) of a C ABI call on one request.
fn c_call(f: unsafe extern "C" fn(*const c_char, *mut *mut c_char, *mut *mut c_char) -> i32, request: &str) -> (i32, String) {
    let req = CString::new(request).unwrap();
    let (mut out, mut err): (*mut c_char, *mut c_char) = (std::ptr::null_mut(), std::ptr::null_mut());
    let code = unsafe { f(req.as_ptr(), &mut out, &mut err) };
    let p = if code == BC_OK { out } else { err };
    let text = if p.is_null() { String::new() } else { unsafe { CStr::from_ptr(p) }.to_string_lossy().into_owned() };
    unsafe {
        bc_string_free(out);
        bc_string_free(err);
    }
    (code, text)
}

#[test]
fn fingering_answers_with_the_crates_own_json() {
    let request = request().to_string();
    let answer = fretted_fingering_json(request.clone()).unwrap();
    assert_eq!(answer, target_fretted::json::solve_json(&request).unwrap(), "the crate's answer, unchanged");
    assert_eq!(c_call(bc_fretted_fingering_json, &request), (BC_OK, answer.clone()), "the C ABI gives the same text");

    let v: Value = serde_json::from_str(&answer).unwrap();
    let notes = v["fingering"]["notes"].as_array().unwrap();
    assert_eq!(notes.len(), 4, "one place per note, in the order of the request");
    assert_eq!((&notes[0]["out_of_range"], &notes[0]["string"]), (&json!(true), &Value::Null));
    assert_eq!((&notes[1]["string"], &notes[1]["fret"]), (&json!(3), &json!(0)), "A1 is the open third string");
    assert!(notes[2]["alternatives"].is_array());
    // The hammer-on stays on the string of the note it comes from.
    assert_eq!(notes[3]["string"], notes[2]["string"]);
    assert_eq!(v["violations"], json!([]));
    assert_eq!(v["tuning_suggestions"][0]["preset"], json!("bass-4-drop-d"));
    assert_eq!(v["instrument"]["tuning"]["strings"].as_array().unwrap().len(), 4);
}

#[test]
fn a_pin_moves_its_note_and_the_rest_follows() {
    let mut r = request();
    // D2 on the third string (fret 5), not the open second string.
    r["options"]["pins"] = json!([{"note": 2, "string": 3}]);
    let v: Value = serde_json::from_str(&fretted_fingering_json(r.to_string()).unwrap()).unwrap();
    let notes = v["fingering"]["notes"].as_array().unwrap();
    assert_eq!((&notes[2]["string"], &notes[2]["fret"], &notes[2]["pinned"]), (&json!(3), &json!(5), &json!(true)));
    assert_eq!(notes[3]["string"], json!(3), "the hammer-on follows the pinned note");
    assert_eq!(v["violations"], json!([]));
}

#[test]
fn a_pin_the_string_cannot_sound_is_reported_not_refused() {
    let mut r = request();
    // A1 is below the open first string (G2): the pin cannot be honoured.
    r["options"]["pins"] = json!([{"note": 1, "string": 1}]);
    for answer in [fretted_fingering_json(r.to_string()).unwrap(), c_call(bc_fretted_fingering_json, &r.to_string()).1] {
        let v: Value = serde_json::from_str(&answer).unwrap();
        assert_eq!(v["violations"], json!([{"kind": "pin-not-honoured", "note": 1, "string": 1}]));
        let place = &v["fingering"]["notes"][1];
        assert_eq!((&place["string"], &place["fret"]), (&json!(3), &json!(0)), "the note keeps a place that sounds it");
    }
}

#[test]
fn a_pin_on_a_string_or_note_that_does_not_exist_is_invalid_input() {
    for (pin, says) in [(json!({"note": 1, "string": 9}), "a pin names string 9 of 4"), (json!({"note": 4, "string": 1}), "a pin names note 4 of 4"), (json!({"note": 0, "string": 0}), "a pin names string 0 of 4")] {
        let mut r = request();
        r["options"]["pins"] = json!([pin]);
        assert_eq!(reason(fretted_fingering_json(r.to_string())), says);
        assert_eq!(c_call(bc_fretted_fingering_json, &r.to_string()), (BC_INVALID, format!("invalid input: {says}")));
        // The tab request solves first, so it refuses the same pin.
        assert_eq!(reason(fretted_tab_json(r.to_string())), says);
    }
}

#[test]
fn tab_answers_with_musicxml_and_the_count_of_moved_notes() {
    let mut r = request();
    r["title"] = json!("Line");
    r["meter"] = json!({"beats": 3, "beat_unit": 4});
    r["tab"] = json!({"layout": "tab"});
    r["notes"][2]["start"] = json!(49);
    let request = r.to_string();
    let answer = fretted_tab_json(request.clone()).unwrap();
    assert_eq!(answer, target_fretted::json::tab_json(&request).unwrap(), "the crate's answer, unchanged");
    assert_eq!(c_call(bc_fretted_tab_json, &request), (BC_OK, answer.clone()), "the C ABI gives the same text");

    let v: Value = serde_json::from_str(&answer).unwrap();
    assert_eq!(v["adjusted_notes"], json!(1));
    let xml = v["musicxml"].as_str().unwrap();
    assert!(xml.starts_with("<?xml") && xml.contains("<work-title>Line</work-title>"));
    assert!(xml.contains("<sign>TAB</sign>") && xml.contains("<staff-lines>4</staff-lines>"));
    assert!(xml.contains("<beats>3</beats>") && xml.contains("! D1"));

    // A fingering from an earlier answer, edited, is written as it is.
    let solved: Value = serde_json::from_str(&fretted_fingering_json(self::request().to_string()).unwrap()).unwrap();
    let mut edited = self::request();
    edited["fingering"] = solved["fingering"].clone();
    edited["fingering"]["notes"][1]["string"] = json!(4);
    edited["fingering"]["notes"][1]["fret"] = json!(5);
    edited["tab"] = json!({"layout": "tab"});
    let v: Value = serde_json::from_str(&fretted_tab_json(edited.to_string()).unwrap()).unwrap();
    assert!(v["musicxml"].as_str().unwrap().contains("<string>4</string>\n            <fret>5</fret>"), "{}", v["musicxml"].as_str().unwrap());
}

#[test]
fn what_is_not_a_request_is_invalid_input() {
    let with = |edit: &dyn Fn(&mut Value)| {
        let mut r = request();
        edit(&mut r);
        r.to_string()
    };
    let bad: Vec<String> = vec![
        String::new(),
        "{".into(),
        "null".into(),
        "[]".into(),
        "{\"notes\": []}".into(),
        with(&|r| r["instrument"] = json!({"preset": "no-such-instrument"})),
        with(&|r| r["instrument"] = json!("bass-4-standard")),
        with(&|r| r["instrument"] = json!({"preset": "bass-4-standard", "frets": 30})),
        with(&|r| r["instrument"] = json!({"preset": "bass-4-standard", "capo": 255})),
        with(&|r| r["instrument"] = json!({"preset": "bass-4-standard", "capo": 21})),
        with(&|r| r["instrument"] = custom(&|_| {}, 0)),
        with(&|r| r["instrument"] = custom(&|_| {}, 300)),
        with(&|r| r["instrument"] = custom(&|i| i["tuning"]["strings"][0]["open_pitch"] = json!(-5), 4)),
        with(&|r| r["instrument"] = custom(&|i| i["tuning"]["strings"][0]["open_pitch"] = json!(200), 4)),
        with(&|r| r["instrument"] = custom(&|i| i["tuning"]["strings"][0]["first_fret"] = json!(30), 4)),
        with(&|r| r["instrument"] = custom(&|i| i["frets"] = json!(0), 4)),
        with(&|r| r["instrument"] = custom(&|i| i["scale_length_mm"] = json!(0.0), 4)),
        with(&|r| r["instrument"] = custom(&|i| i["scale_length_mm"] = json!(-1.0), 4)),
        with(&|r| r["surprise"] = json!(1)),
        with(&|r| r["options"]["style"] = json!("shred")),
        with(&|r| r["options"]["tempo_bpm"] = json!(0)),
        with(&|r| r["options"]["hand"] = json!({"comfortable_mm": 200.0, "max_mm": 100.0})),
        with(&|r| r["notes"][0]["pitch"] = json!(128)),
        with(&|r| r["notes"][0]["pitch"] = json!("C")),
        with(&|r| r["notes"][0]["techniques"] = json!(["tapping"])),
        with(&|r| r["notes"][3]["technique"] = json!(["hammer-on"])),
        with(&|r| r["notes"][0]["string"] = json!(2)),
        with(&|r| r["notes"] = Value::Array((0..20_001).map(|i| json!({"pitch": 40, "start": 12 * i, "dur": 12})).collect())),
        with(&|r| r["notes"][0]["start"] = json!(i64::MAX)),
        with(&|r| r["notes"][0]["start"] = json!(i64::MIN)),
        with(&|r| r["notes"][0]["dur"] = json!(i64::MAX)),
    ];
    for request in &bad {
        for (uniffi, c) in [(fretted_fingering_json as fn(String) -> Result<String, CoreError>, bc_fretted_fingering_json as unsafe extern "C" fn(_, _, _) -> i32), (fretted_tab_json, bc_fretted_tab_json)] {
            let said = reason(uniffi(request.clone()));
            assert!(!said.is_empty(), "{request}");
            assert_eq!(c_call(c, request), (BC_INVALID, format!("invalid input: {said}")), "{request}");
            // A caller that passes no place for the answer or the message still gets the code.
            let req = CString::new(request.as_str()).unwrap();
            assert_eq!(unsafe { c(req.as_ptr(), std::ptr::null_mut(), std::ptr::null_mut()) }, BC_INVALID, "{request}");
        }
    }
    // What only the page can get wrong.
    for edit in [json!({"meter": {"beats": 4, "beat_unit": 3}}), json!({"key": {"fifths": 9}}), json!({"tempo_bpm": 5}), json!({"tab": {"doubt_below": 2.0}}), json!({"tab": {"layout": "grid"}})] {
        let mut r = request();
        for (k, v) in edit.as_object().unwrap() {
            r[k] = v.clone();
        }
        assert!(!reason(fretted_tab_json(r.to_string())).is_empty());
        assert_eq!(c_call(bc_fretted_tab_json, &r.to_string()).0, BC_INVALID, "{r}");
    }
    // A full instrument that makes sense is taken as it is, and has no tuning suggestions.
    let mut r = request();
    r["instrument"] = custom(&|_| {}, 4);
    let v: Value = serde_json::from_str(&fretted_fingering_json(r.to_string()).unwrap()).unwrap();
    assert_eq!((&v["instrument"]["name"], &v["tuning_suggestions"]), (&json!("Custom"), &json!([])));
    assert_eq!(c_call(bc_fretted_tab_json, &r.to_string()).0, BC_OK);
    // A fingering that puts a note where it does not sound is refused, with the place and the pitch.
    let solved: Value = serde_json::from_str(&fretted_fingering_json(request().to_string()).unwrap()).unwrap();
    let mut r = request();
    r["fingering"] = solved["fingering"].clone();
    r["fingering"]["notes"][1]["string"] = json!(1);
    assert_eq!(reason(fretted_tab_json(r.to_string())), "note 1: string 1 fret 0 sounds pitch 43, not the note's 33");
    assert_eq!(c_call(bc_fretted_tab_json, &r.to_string()).0, BC_INVALID);
    r["fingering"]["notes"][1]["fret"] = json!(99);
    assert_eq!(reason(fretted_tab_json(r.to_string())), "note 1: the instrument has no string 1 fret 99");
    r["fingering"]["notes"][1] = json!({"pitch": 33, "string": 3, "fret": 0, "alternatives": [], "out_of_range": false, "pinned": false, "finger": 1});
    assert!(reason(fretted_tab_json(r.to_string())).contains("unknown field `finger`"));
    // A zero-length note can be fingered and cannot be written.
    let mut r = request();
    r["notes"][0]["dur"] = json!(0);
    assert!(fretted_fingering_json(r.to_string()).is_ok());
    assert!(reason(fretted_tab_json(r.to_string())).contains("a note needs a length"));
}

#[test]
fn a_null_request_is_a_null_argument() {
    let (mut out, mut err): (*mut c_char, *mut c_char) = (std::ptr::null_mut(), std::ptr::null_mut());
    assert_eq!(unsafe { bc_fretted_fingering_json(std::ptr::null(), &mut out, &mut err) }, BC_NULL);
    assert_eq!(unsafe { bc_fretted_tab_json(std::ptr::null(), &mut out, &mut err) }, BC_NULL);
    assert!(out.is_null() && err.is_null());
}

#[test]
fn large_and_odd_passages_come_back_without_a_panic() {
    // More notes at once than strings, a long line, and an empty passage.
    let cluster: Vec<Value> = (0..12).map(|i| json!({"pitch": 28 + 3 * i, "start": 0, "dur": 24})).collect();
    let line: Vec<Value> = (0..2000).map(|i| json!({"pitch": 28 + (i * 7) % 36, "start": 6 * i, "dur": 5})).collect();
    for notes in [cluster, line, Vec::new()] {
        let r = json!({"instrument": {"preset": "bass-5-standard", "capo": 3}, "notes": notes}).to_string();
        let v: Value = serde_json::from_str(&fretted_fingering_json(r.clone()).unwrap()).unwrap();
        assert_eq!(v["fingering"]["notes"].as_array().unwrap().len(), notes.len());
        assert_eq!(c_call(bc_fretted_tab_json, &r).0, BC_OK);
    }
}
