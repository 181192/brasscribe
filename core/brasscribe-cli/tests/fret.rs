//! `brasscribe-core fret`: target-fretted's JSON request in, its JSON response out, both unchanged.

use std::fs;
use std::path::PathBuf;
use std::process::Command;

use serde_json::{json, Value};

fn dir(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("brasscribe-cli-fret-{}-{name}", std::process::id()));
    fs::create_dir_all(&d).unwrap();
    d
}

fn fret(name: &str, request: &str) -> (bool, String, String) {
    let d = dir(name);
    let (req, out) = (d.join("request.json"), d.join("out").join("fingering.json"));
    fs::write(&req, request).unwrap();
    let run = Command::new(env!("CARGO_BIN_EXE_brasscribe-core")).arg("fret").arg("--request").arg(&req).arg("--out").arg(&out).output().unwrap();
    let written = fs::read_to_string(&out).unwrap_or_default();
    fs::remove_dir_all(&d).ok();
    (run.status.success(), written, String::from_utf8_lossy(&run.stderr).into_owned())
}

#[test]
fn the_response_is_the_crates_own() {
    // A bass line down to D1, with a pickup note before tick 0: out of range in standard tuning.
    let request = json!({
        "instrument": {"preset": "bass-4-standard"},
        "notes": [{"pitch": 26, "start": -12, "dur": 12}, {"pitch": 33, "start": 0, "dur": 24}, {"pitch": 38, "start": 24, "dur": 24}],
        "options": {"style": "as-played", "tempo_bpm": 96.0}
    })
    .to_string();
    let (ok, written, stderr) = fret("ok", &request);
    assert!(ok, "{stderr}");
    assert_eq!(written, target_fretted::json::solve_json(&request).unwrap());
    let v: Value = serde_json::from_str(&written).unwrap();
    let notes = v["fingering"]["notes"].as_array().unwrap();
    assert_eq!(notes.len(), 3);
    assert_eq!(notes[0]["out_of_range"], json!(true));
    assert_eq!((&notes[1]["string"], &notes[1]["fret"]), (&json!(3), &json!(0)));
    assert_eq!(v["tuning_suggestions"][0]["preset"], json!("bass-4-drop-d"));
    assert_eq!(v["instrument"]["tuning"]["strings"].as_array().unwrap().len(), 4);
}

#[test]
fn a_bad_request_fails_with_the_crates_message_and_writes_nothing() {
    let (ok, written, stderr) = fret("unknown-key", r#"{"instrument": {"preset": "bass-4-standard"}, "notes": [], "frets": 3}"#);
    assert!(!ok);
    assert!(written.is_empty());
    assert!(stderr.contains("not a fingering request"), "{stderr}");

    let (ok, _, stderr) = fret("unknown-preset", r#"{"instrument": {"preset": "bass-9"}, "notes": []}"#);
    assert!(!ok);
    assert!(stderr.contains("bass-9"), "{stderr}");
}

#[test]
fn a_missing_argument_is_named() {
    let run = Command::new(env!("CARGO_BIN_EXE_brasscribe-core")).arg("fret").output().unwrap();
    assert!(!run.status.success());
    assert!(String::from_utf8_lossy(&run.stderr).contains("missing --request"));
}
