//! `scribe-core fret` and `tab`: target-fretted's JSON request in, its JSON response out, both unchanged.

use std::fs;
use std::path::PathBuf;
use std::process::Command;

use serde_json::{json, Value};

fn dir(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("scribe-cli-fret-{}-{name}", std::process::id()));
    fs::create_dir_all(&d).unwrap();
    d
}

fn fret(name: &str, request: &str) -> (bool, String, String) {
    call("fret", name, request)
}

fn call(command: &str, name: &str, request: &str) -> (bool, String, String) {
    let d = dir(&format!("{command}-{name}"));
    let (req, out) = (d.join("request.json"), d.join("out").join("answer.json"));
    fs::write(&req, request).unwrap();
    let run = Command::new(env!("CARGO_BIN_EXE_scribe-core")).arg(command).arg("--request").arg(&req).arg("--out").arg(&out).output().unwrap();
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

    // A key a note does not have (a misspelled `techniques`) is refused, not dropped.
    let note = r#"{"instrument": {"preset": "bass-4-standard"}, "notes": [{"pitch": 33, "start": 0, "dur": 24, "technique": ["slide"]}]}"#;
    for command in ["fret", "tab"] {
        let (ok, written, stderr) = call(command, "unknown-note-key", note);
        assert!(!ok && written.is_empty());
        assert!(stderr.contains("unknown field `technique` in a note"), "{command}: {stderr}");
    }
}

#[test]
fn a_missing_argument_is_named() {
    let run = Command::new(env!("CARGO_BIN_EXE_scribe-core")).arg("fret").output().unwrap();
    assert!(!run.status.success());
    assert!(String::from_utf8_lossy(&run.stderr).contains("missing --request"));
}

fn tab_request(layout: &str) -> Value {
    json!({
        "title": "Open strings",
        "instrument": {"preset": "bass-4-standard", "capo": 2},
        "notes": [{"pitch": 30, "start": 0, "dur": 24, "confidence": 0.2}, {"pitch": 35, "start": 24, "dur": 24}, {"pitch": 40, "start": 48, "dur": 25}],
        "tempo_bpm": 96.0, "meter": {"beats": 3, "beat_unit": 4}, "key": {"fifths": 2, "mode": "major"},
        "tab": {"layout": layout, "capo": "element", "doubt_below": 0.4}
    })
}

#[test]
fn tab_answers_with_the_crates_document_and_its_count_of_adjusted_notes() {
    let request = tab_request("tab").to_string();
    let (ok, written, stderr) = call("tab", "ok", &request);
    assert!(ok, "{stderr}");
    assert_eq!(written, target_fretted::json::tab_json(&request).unwrap());
    let v: Value = serde_json::from_str(&written).unwrap();
    assert_eq!(v["adjusted_notes"], json!(1)); // 25 ticks is no note value
    let xml = v["musicxml"].as_str().unwrap();
    assert!(xml.contains("<work-title>Open strings</work-title>"));
    assert!(xml.contains("<sign>TAB</sign>") && xml.contains("<capo>2</capo>"));
    assert!(xml.contains("<beats>3</beats>") && xml.contains("<fifths>2</fifths>"));
    assert!(!xml.contains("<sign>F</sign>"), "the tab layout has no notation staff");
}

#[test]
fn tab_writes_the_layout_asked_for_and_the_fingering_given() {
    let both = call("tab", "both", &tab_request("tab-and-notation").to_string()).1;
    assert!(both.contains("<sign>TAB</sign>") && both.contains("<staves>2</staves>"));
    let notation = call("tab", "notation", &tab_request("notation").to_string()).1;
    assert!(!notation.contains("<sign>TAB</sign>"));

    // A fingering from an earlier answer is written as it stands: the first note on the E string, not solved again.
    let mut request = tab_request("tab");
    let solved: Value = serde_json::from_str(&fret("for-tab", &json!({"instrument": request["instrument"], "notes": request["notes"]}).to_string()).1).unwrap();
    let mut fingering = solved["fingering"].clone();
    assert_eq!((&fingering["notes"][1]["string"], &fingering["notes"][1]["fret"]), (&json!(3), &json!(0)));
    fingering["notes"][1]["string"] = json!(4);
    fingering["notes"][1]["fret"] = json!(5);
    request["fingering"] = fingering;
    let (ok, written, stderr) = call("tab", "given", &request.to_string());
    assert!(ok, "{stderr}");
    let v: Value = serde_json::from_str(&written).unwrap();
    let xml = v["musicxml"].as_str().unwrap().replace(char::is_whitespace, "");
    assert!(xml.contains("<string>4</string><fret>5</fret>") || xml.contains("<fret>5</fret><string>4</string>"));
}

#[test]
fn a_bad_tab_request_fails_with_the_crates_message_and_writes_nothing() {
    let mut request = tab_request("tab");
    request["tab"]["layout"] = json!("grand-staff");
    let (ok, written, stderr) = call("tab", "layout", &request.to_string());
    assert!(!ok && written.is_empty());
    assert!(stderr.contains("not a tablature request"), "{stderr}");
    let run = Command::new(env!("CARGO_BIN_EXE_scribe-core")).arg("tab").arg("--request").arg("r.json").output().unwrap();
    assert!(!run.status.success());

    // A fingering that puts a note where it does not sound is refused, not written.
    let wrong = r#"{"instrument": {"preset": "bass-4-standard"}, "notes": [{"pitch": 33, "start": 0, "dur": 24}],
        "fingering": {"notes": [{"pitch": 33, "string": 1, "fret": 0, "alternatives": [], "out_of_range": false, "pinned": false}]}}"#;
    let (ok, written, stderr) = call("tab", "wrong-place", wrong);
    assert!(!ok && written.is_empty());
    assert!(stderr.contains("string 1 fret 0 sounds pitch 43, not the note's 33"), "{stderr}");
}

/// `tab` with more arguments after `--request` and `--out`.
fn tab_as(name: &str, request: &str, args: &[&str]) -> (bool, String, String) {
    let d = dir(&format!("tab-as-{name}"));
    let (req, out) = (d.join("request.json"), d.join("out").join("answer.txt"));
    fs::write(&req, request).unwrap();
    let run = Command::new(env!("CARGO_BIN_EXE_scribe-core")).arg("tab").arg("--request").arg(&req).arg("--out").arg(&out).args(args).output().unwrap();
    let written = fs::read_to_string(&out).unwrap_or_default();
    fs::remove_dir_all(&d).ok();
    (run.status.success(), written, String::from_utf8_lossy(&run.stderr).into_owned())
}

#[test]
fn tab_writes_the_text_tab_and_the_playing_instructions_as_plain_text() {
    let request = tab_request("tab").to_string();
    let (ok, json, stderr) = tab_as("json", &request, &["--format", "json"]);
    assert!(ok, "{stderr}");
    assert_eq!(json, target_fretted::json::tab_json(&request).unwrap(), "json is the default format");

    let (ok, text, stderr) = tab_as("text", &request, &["--format", "text"]);
    assert!(ok, "{stderr}");
    assert_eq!(text, target_fretted::json::tab_text_json(&request).unwrap());
    assert!(text.starts_with("Open strings\nBass\nTuning: Standard (E A D G), bottom line to top\nCapo: fret 2 "), "{text}");
    assert!(text.contains("\n   ?\nG|------||\nD|-----0||\nA|---0--||\nE|-0----||\n"), "{text}");

    let (ok, en, stderr) = tab_as("en", &request, &["--format", "instructions"]);
    assert!(ok, "{stderr}");
    assert_eq!(en, target_fretted::json::playing_instructions_json(&request).unwrap());
    assert!(en.contains("\nBar 1\n  Beat 1. String 4, open, to check. Quarter note.\n  Beat 2. String 3, open. Quarter note.\n"), "{en}");
    let (ok, nb, stderr) = tab_as("nb", &request, &["--format", "instructions", "--lang", "nb"]);
    assert!(ok, "{stderr}");
    assert!(nb.contains("\nTakt 1\n  Slag 1. Streng 4, løs, bør sjekkes. Fjerdedelsnote.\n  Slag 2. Streng 3, løs. Fjerdedelsnote.\n"), "{nb}");
    assert_eq!(en.lines().count(), nb.lines().count());

    // The flags stand in for the request's `text` options.
    let mut asks = tab_request("tab");
    asks["text"] = json!({"lang": "nb", "width": 30});
    assert_eq!(tab_as("request-lang", &asks.to_string(), &["--format", "instructions"]).1, nb);
    assert_eq!(tab_as("flag-wins", &asks.to_string(), &["--format", "instructions", "--lang", "en"]).1, en);
}

#[test]
fn the_text_tab_is_wrapped_at_the_width_asked_for() {
    let notes: Vec<Value> = (0..32).map(|i| json!({"pitch": 33 + i % 5, "start": 24 * i, "dur": 24})).collect();
    let request = json!({"instrument": {"preset": "bass-4-standard"}, "notes": notes}).to_string();
    let lines_of = |text: &str| text.lines().filter(|l| l.starts_with("G|")).map(str::to_string).collect::<Vec<_>>();
    let wide = lines_of(&tab_as("wide", &request, &["--format", "text"]).1);
    let narrow = lines_of(&tab_as("thirty", &request, &["--format", "text", "--width", "30"]).1);
    assert_eq!((wide.len(), narrow.len()), (2, 3), "eight bars: seven and one, or three to a line");
    assert!(wide.iter().all(|l| l.chars().count() <= 72) && narrow.iter().all(|l| l.chars().count() <= 30));
}

#[test]
fn a_format_language_or_width_that_does_not_exist_is_refused() {
    let request = tab_request("tab").to_string();
    for (name, args, says) in [
        ("format", vec!["--format", "pdf"], "unknown format pdf"),
        ("lang", vec!["--format", "instructions", "--lang", "de"], "en or nb"),
        ("width", vec!["--format", "text", "--width", "wide"], "--width is a number"),
        ("narrow", vec!["--format", "text", "--width", "5"], "24 to 400 characters"),
    ] {
        let (ok, written, stderr) = tab_as(name, &request, &args);
        assert!(!ok && written.is_empty(), "{name}");
        assert!(stderr.contains(says), "{name}: {stderr}");
    }
    let (ok, _, stderr) = tab_as("bad-request", r#"{"instrument": {"preset": "bass-4-standard"}, "notes": [], "frets": 3}"#, &["--format", "text"]);
    assert!(!ok && stderr.contains("not a tablature request"), "{stderr}");
}
