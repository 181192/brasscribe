//! arrange_musicxml_with / bc_arrange_with: re-arranging a composition for a lineup.

use std::ffi::{CStr, CString};
use std::os::raw::c_char;

use brasscribe_ffi::{arrange_musicxml_with, ArrangeOptions};

/// A whole-band take (no layers): C major melody, bass and harmony.
const SONG: &str = r#"{"title": "T", "voices": [
  {"id": "melody", "role": "melody", "notes": [{"pitch": 64, "start": 0, "dur": 96}, {"pitch": 65, "start": 96, "dur": 96}]},
  {"id": "bass", "role": "bass", "notes": [{"pitch": 48, "start": 0, "dur": 96}, {"pitch": 53, "start": 96, "dur": 96}]},
  {"id": "harmony", "role": "harmony", "notes": [
    {"pitch": 60, "start": 0, "dur": 96}, {"pitch": 67, "start": 0, "dur": 96},
    {"pitch": 60, "start": 96, "dur": 96}, {"pitch": 69, "start": 96, "dur": 96}]}],
 "meters": [{"tick": 0, "beats": 4}], "keys": [{"tick": 0, "fifths": 0}]}"#;

/// A solo-with-band take (layers).
const LAYERED: &str = r#"{"title": "L", "voices": [
  {"id": "solo", "role": "melody", "layer": "solo", "notes": [{"pitch": 72, "start": 0, "dur": 96}, {"pitch": 74, "start": 96, "dur": 96}]},
  {"id": "bass", "role": "bass", "layer": "bass", "notes": [{"pitch": 48, "start": 0, "dur": 192}]},
  {"id": "strings", "role": "harmony", "layer": "strings", "notes": [
    {"pitch": 60, "start": 0, "dur": 192}, {"pitch": 64, "start": 0, "dur": 192}, {"pitch": 67, "start": 0, "dur": 192}]}],
 "meters": [{"tick": 0, "beats": 4}], "keys": [{"tick": 0, "fifths": 0}]}"#;

fn parts(xml: &str) -> Vec<String> {
    xml.split("<part-name>").skip(1).map(|s| s.split('<').next().unwrap().to_string()).collect()
}

fn opts(lineup: &str) -> ArrangeOptions {
    ArrangeOptions { lineup: lineup.into(), ..Default::default() }
}

#[test]
fn quartet_on_both_kinds_of_take() {
    let quartet = ["1st Cornet", "2nd Cornet", "Tenor Horn", "Euphonium"];
    assert_eq!(parts(&arrange_musicxml_with(SONG.into(), opts("quartet")).unwrap()), quartet);
    assert_eq!(parts(&arrange_musicxml_with(LAYERED.into(), opts("quartet")).unwrap()), quartet);
}

#[test]
fn band_and_minimal() {
    assert_eq!(parts(&arrange_musicxml_with(LAYERED.into(), opts("full")).unwrap()).len(), 18);
    assert_eq!(parts(&arrange_musicxml_with(LAYERED.into(), opts("minimal")).unwrap()).len(), 8);
    // A whole-band take has no layers for the full band: the minimal band, as the "auto" arranger.
    assert_eq!(parts(&arrange_musicxml_with(SONG.into(), opts("band")).unwrap()).len(), 8);
}

#[test]
fn bad_options_are_invalid() {
    assert!(arrange_musicxml_with(SONG.into(), opts("nonet")).is_err());
    let o = ArrangeOptions { difficulty: "hard".into(), ..opts("quartet") };
    assert!(arrange_musicxml_with(SONG.into(), o).is_err());
    let o = ArrangeOptions { key: Some("Bb".into()), transpose: Some(2), ..opts("quartet") };
    assert!(arrange_musicxml_with(SONG.into(), o).is_err());
}

#[test]
fn transposes() {
    let o = ArrangeOptions { transpose: Some(-2), ..opts("quartet") };
    let xml = arrange_musicxml_with(SONG.into(), o).unwrap();
    assert!(xml.contains("<fifths>0</fifths>"), "concert B-flat is written C on a B-flat cornet");
}

#[test]
fn a_recorded_transposition_is_not_applied_twice() {
    // A take already transposed down 3 (as arrange_layers_song --transpose -3 writes it): C major became A major.
    let done = SONG.replace(r#""keys": [{"tick": 0, "fifths": 0}]}"#, r#""keys": [{"tick": 0, "fifths": 3}],
      "arrangement": {"lineup": "quartet", "difficulty": "faithful", "transpose_semitones": -3}}"#);
    assert!(done.contains("transpose_semitones"));
    let again = arrange_musicxml_with(done.clone(), ArrangeOptions { transpose: Some(-3), ..opts("quartet") }).unwrap();
    let kept = arrange_musicxml_with(done.clone(), opts("quartet")).unwrap();
    assert_eq!(again, kept);
    // Back to the recording's key: up 3 from where it is.
    let back = arrange_musicxml_with(done, ArrangeOptions { transpose: Some(0), ..opts("quartet") }).unwrap();
    assert!(back.contains("<fifths>2</fifths>"), "concert C is written D on a B-flat cornet");
}

#[test]
fn c_abi_takes_the_same_options() {
    let json = CString::new(SONG).unwrap();
    let options = CString::new(r#"{"lineup": "quartet", "difficulty": "easier"}"#).unwrap();
    let mut out: *mut c_char = std::ptr::null_mut();
    let mut err: *mut c_char = std::ptr::null_mut();
    let code = unsafe { brasscribe_ffi::c_api::bc_arrange_with(json.as_ptr(), options.as_ptr(), &mut out, &mut err) };
    assert_eq!(code, 0);
    let xml = unsafe { CStr::from_ptr(out) }.to_str().unwrap().to_string();
    unsafe { brasscribe_ffi::c_api::bc_string_free(out) };
    assert_eq!(parts(&xml)[0], "1st Cornet");
    let bad = CString::new(r#"{"lineup": "nonet"}"#).unwrap();
    let code = unsafe { brasscribe_ffi::c_api::bc_arrange_with(json.as_ptr(), bad.as_ptr(), &mut out, &mut err) };
    assert_ne!(code, 0);
    unsafe { brasscribe_ffi::c_api::bc_string_free(err) };
}
