//! C ABI. Strings cross the boundary as NUL-terminated UTF-8. Every call
//! returns 0 on success and writes its result to `*out`; on failure it returns
//! a non-zero code and writes a message to `*err`. Strings returned by the
//! library must be released with [`bc_string_free`].
//!
//! Codes: 0 ok, 1 invalid input, 2 pipeline failure, 3 null argument, 4 panic.

use std::ffi::{c_char, CStr, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};

use crate::CoreError;

pub const BC_OK: i32 = 0;
pub const BC_INVALID: i32 = 1;
pub const BC_FAILED: i32 = 2;
pub const BC_NULL: i32 = 3;
pub const BC_PANIC: i32 = 4;

fn to_c(s: String) -> *mut c_char {
    CString::new(s.replace('\0', " ")).unwrap_or_default().into_raw()
}

unsafe fn from_c(p: *const c_char) -> Option<String> {
    if p.is_null() {
        return None;
    }
    Some(CStr::from_ptr(p).to_string_lossy().into_owned())
}

unsafe fn put(slot: *mut *mut c_char, s: String) {
    if !slot.is_null() {
        *slot = to_c(s);
    }
}

unsafe fn run(out: *mut *mut c_char, err: *mut *mut c_char, f: impl FnOnce() -> Result<String, (i32, String)>) -> i32 {
    match catch_unwind(AssertUnwindSafe(f)) {
        Ok(Ok(s)) => {
            put(out, s);
            BC_OK
        }
        Ok(Err((code, msg))) => {
            put(err, msg);
            code
        }
        Err(_) => {
            put(err, "internal error (panic)".into());
            BC_PANIC
        }
    }
}

fn map_err(e: CoreError) -> (i32, String) {
    let code = if matches!(e, CoreError::Invalid { .. }) { BC_INVALID } else { BC_FAILED };
    (code, e.to_string())
}

/// Release a string returned by this library. Null is ignored.
#[no_mangle]
pub unsafe extern "C" fn bc_string_free(s: *mut c_char) {
    if !s.is_null() {
        drop(CString::from_raw(s));
    }
}

/// Library version, e.g. "0.1.0". Free with `bc_string_free`.
#[no_mangle]
pub extern "C" fn bc_version() -> *mut c_char {
    to_c(brasscribe_core::VERSION.to_string())
}

/// Parse a Composition JSON and write its canonical form to `*out`.
#[no_mangle]
pub unsafe extern "C" fn bc_composition_normalize(json: *const c_char, out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    let Some(json) = from_c(json) else { return BC_NULL };
    run(out, err, || crate::normalize_composition(json).map_err(map_err))
}

/// Arrange a Composition JSON for brass band and write MusicXML to `*out`.
/// `arranger`: "auto", "layers" or "minimal" (null = "auto").
#[no_mangle]
pub unsafe extern "C" fn bc_arrange_musicxml(composition_json: *const c_char, arranger: *const c_char, out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    let Some(json) = from_c(composition_json) else { return BC_NULL };
    let arranger = from_c(arranger).unwrap_or_else(|| "auto".into());
    run(out, err, || crate::arrange_impl(&json, &arranger).map_err(map_err))
}

/// Solo-with-band arrangement from six MIDI files (solo SwiftF0, solo
/// MuScriptor, solo Basic Pitch, bass, orchestra, drums, in that order) and a
/// beat table. Writes the Composition JSON to `*out_composition` and MusicXML
/// to `*out_musicxml`. Free time is detected; no solo contour is used.
#[no_mangle]
pub unsafe extern "C" fn bc_arrange_layers_song(
    midi: *const *const u8,
    midi_len: *const usize,
    beats_text: *const c_char,
    title: *const c_char,
    out_composition: *mut *mut c_char,
    out_musicxml: *mut *mut c_char,
    err: *mut *mut c_char,
) -> i32 {
    if midi.is_null() || midi_len.is_null() {
        return BC_NULL;
    }
    let Some(beats) = from_c(beats_text) else { return BC_NULL };
    let title = from_c(title).unwrap_or_else(|| "Draft".into());
    let mut files: Vec<Vec<u8>> = Vec::with_capacity(6);
    for i in 0..6 {
        let p = *midi.add(i);
        let n = *midi_len.add(i);
        if p.is_null() {
            return BC_NULL;
        }
        files.push(std::slice::from_raw_parts(p, n).to_vec());
    }
    let mut xml = String::new();
    let code = run(out_composition, err, || {
        let layers = crate::LayerMidi {
            solo_swiftf0: files[0].clone(),
            solo_muscriptor: files[1].clone(),
            solo_basic_pitch: files[2].clone(),
            bass: files[3].clone(),
            orchestra: files[4].clone(),
            drums: files[5].clone(),
        };
        let r = crate::arrange_layers_song(layers, beats, title, None, true, None).map_err(map_err)?;
        xml = r.musicxml;
        Ok(r.composition_json)
    });
    if code == BC_OK {
        put(out_musicxml, xml);
    }
    code
}

/// Spell MIDI pitches from their context. `request` is JSON
/// `{"onsets": [beats...], "pitches": [midi...]}`; writes
/// `[{"step": "F", "alter": 1, "octave": 4}, ...]`.
#[no_mangle]
pub unsafe extern "C" fn bc_spell_json(request: *const c_char, out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    let Some(req) = from_c(request) else { return BC_NULL };
    run(out, err, || {
        let v: serde_json::Value = serde_json::from_str(&req).map_err(|e| (BC_INVALID, e.to_string()))?;
        let on: Vec<f64> = v["onsets"].as_array().map(|a| a.iter().filter_map(|x| x.as_f64()).collect()).unwrap_or_default();
        let ps: Vec<i32> = v["pitches"].as_array().map(|a| a.iter().filter_map(|x| x.as_i64()).map(|x| x as i32).collect()).unwrap_or_default();
        if on.len() != ps.len() {
            return Err((BC_INVALID, "onsets and pitches differ in length".into()));
        }
        let rows: Vec<serde_json::Value> = crate::spell_pitches(on, ps)
            .into_iter()
            .map(|s| serde_json::json!({"step": s.step, "alter": s.alter, "octave": s.octave}))
            .collect();
        Ok(serde_json::Value::Array(rows).to_string())
    })
}
