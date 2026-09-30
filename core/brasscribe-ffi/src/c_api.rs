//! C ABI. Strings cross the boundary as NUL-terminated UTF-8. Every call
//! returns 0 on success and writes its result to `*out`; on failure it returns
//! a non-zero code and writes a message to `*err`. Strings returned by the
//! library must be released with [`bc_string_free`].
//!
//! Codes: 0 ok, 1 invalid input, 2 pipeline failure, 3 null argument, 4 panic.

use std::ffi::{c_char, CStr, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};

use brasscribe_core::durations::Contour;

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

/// Re-arrange a Composition JSON for a lineup and difficulty and write MusicXML to `*out`.
/// `options` may be null (defaults) or
/// `{"lineup": "band" | "minimal" | "quartet", "difficulty": "faithful" | "standard" | "easier",
///   "key": "Bb" | null, "transpose": null, "seat": ..., "reads": ..., "lead": ..., "trills": true | false | null}` (the keys of
///   [`bc_arrange_layers_song`]); `transpose`
/// is the total from the recording, as in `arrange_musicxml_with`.
#[no_mangle]
pub unsafe extern "C" fn bc_arrange_with(composition_json: *const c_char, options: *const c_char, out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    let Some(json) = from_c(composition_json) else { return BC_NULL };
    run(out, err, || {
        let opts = options_json(options)?;
        let o = crate::ArrangeOptions {
            lineup: opts.get("lineup").and_then(|v| v.as_str()).unwrap_or("band").to_string(),
            difficulty: opts.get("difficulty").and_then(|v| v.as_str()).unwrap_or("faithful").to_string(),
            key: opts.get("key").and_then(|v| v.as_str()).map(String::from),
            transpose: transpose_of(&opts)?,
            seat: str_of(&opts, "seat"),
            reads: str_of(&opts, "reads"),
            lead: str_of(&opts, "lead"),
            trills: opts.get("trills").and_then(|v| v.as_bool()),
        };
        crate::arrange_with_impl(&json, &o).map_err(map_err)
    })
}

/// Solo-with-band arrangement from six MIDI files (solo SwiftF0, solo
/// MuScriptor, solo Basic Pitch, bass, orchestra, drums, in that order) and a
/// beat table. Writes the Composition JSON to `*out_composition` and MusicXML
/// to `*out_musicxml`.
///
/// `options_json` may be null (defaults) or
/// `{"solo_contour": {"times": [...], "pitch_hz": [...], "loudness_db": [...]},
///   "free_time": true, "free_tempo": null, "gate": true, "beat_cleanup": true,
///   "key_changes": true, "lineup": "band" | "minimal" | "quartet",
///   "difficulty": "faithful" | "standard" | "easier", "key": "Bb" | null,
///   "transpose": null, "seat": "euphonium" | null, "reads": "treble" | "bass" | null,
///   "lead": "lineup" | "seat" | null, "lang": "en" | "nb" | null}`: the SwiftF0 contour of the solo stem (where
/// sustained notes end), free-time detection on/off, a fixed BPM for free-time
/// passages, the energy gate, beat cleanup, key changes, the lineup, the
/// difficulty, a transposition (to a concert key or by semitones) and the language of the
/// arranged parts' footer. Without stems the
/// gate, dynamics and rehearsal marks have nothing to read; see
/// [`bc_arrange_layers_band`].
#[no_mangle]
pub unsafe extern "C" fn bc_arrange_layers_song(
    midi: *const *const u8,
    midi_len: *const usize,
    beats_text: *const c_char,
    title: *const c_char,
    options_json: *const c_char,
    out_composition: *mut *mut c_char,
    out_musicxml: *mut *mut c_char,
    err: *mut *mut c_char,
) -> i32 {
    let options = from_c(options_json);
    let Some(midi) = midi_slices(midi, midi_len) else { return BC_NULL };
    let Some(beats) = from_c(beats_text) else { return BC_NULL };
    let title = from_c(title).unwrap_or_else(|| "Draft".into());
    let mut xml = String::new();
    let code = run(out_composition, err, || {
        let opts: serde_json::Value = match &options {
            Some(s) if !s.trim().is_empty() => serde_json::from_str(s).map_err(|e| (BC_INVALID, format!("options: {e}")))?,
            _ => serde_json::Value::Null,
        };
        let mut o = options_of(&opts)?;
        let contour = json_contour(&mut o);
        let b = crate::LayerBytes { midi, stems: [None; 4] };
        let r = crate::band_bytes(&b, &beats, &title, o, contour).map_err(map_err)?;
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
        let bad = |what: &str| (BC_INVALID, format!("{what} must be a list of numbers"));
        let list = |k: &str| v[k].as_array().map(|a| a.as_slice()).unwrap_or(&[]);
        let on: Vec<f64> = list("onsets").iter().map(|x| x.as_f64().ok_or_else(|| bad("onsets"))).collect::<Result<_, _>>()?;
        let ps: Vec<i32> = list("pitches")
            .iter()
            .map(|x| x.as_i64().and_then(|p| i32::try_from(p).ok()).ok_or_else(|| bad("pitches")))
            .collect::<Result<_, _>>()?;
        if on.len() != ps.len() {
            return Err((BC_INVALID, "onsets and pitches differ in length".into()));
        }
        let rows: Vec<serde_json::Value> = crate::spell_pitches(on, ps)
            .map_err(map_err)?
            .into_iter()
            .map(|s| serde_json::json!({"step": s.step, "alter": s.alter, "octave": s.octave}))
            .collect();
        Ok(serde_json::Value::Array(rows).to_string())
    })
}

fn options_of(opts: &serde_json::Value) -> Result<crate::LayersSongOptions, (i32, String)> {
    // A null or other non-number in a contour array is the value a frame without one has (as the
    // array form reads a non-finite value), so the arrays keep one value per frame.
    let floats = |v: &serde_json::Value, missing: f64| -> Vec<f64> {
        v.as_array().map(|a| a.iter().map(|x| x.as_f64().unwrap_or(missing)).collect()).unwrap_or_default()
    };
    let flag = |k: &str| opts.get(k).and_then(|v| v.as_bool()).unwrap_or(true);
    Ok(crate::LayersSongOptions {
        solo_contour: opts.get("solo_contour").filter(|c| c.is_object()).map(|c| crate::SoloContour {
            times: floats(&c["times"], 0.0),
            pitch_hz: floats(&c["pitch_hz"], 0.0),
            loudness_db: floats(&c["loudness_db"], -140.0),
            confidence: c.get("confidence").filter(|v| v.is_array()).map(|v| floats(v, 0.0)),
        }),
        free_time: flag("free_time"),
        free_tempo: opts.get("free_tempo").and_then(|v| v.as_f64()),
        gate: flag("gate"),
        beat_cleanup: flag("beat_cleanup"),
        key_changes: flag("key_changes"),
        lineup: opts.get("lineup").and_then(|v| v.as_str()).unwrap_or("band").to_string(),
        difficulty: opts.get("difficulty").and_then(|v| v.as_str()).unwrap_or("faithful").to_string(),
        trills: opts.get("trills").and_then(|v| v.as_bool()).unwrap_or(false),
        key: opts.get("key").and_then(|v| v.as_str()).map(String::from),
        transpose: transpose_of(opts)?,
        seat: str_of(opts, "seat"),
        reads: str_of(opts, "reads"),
        lead: str_of(opts, "lead"),
        lang: str_of(opts, "lang"),
    })
}

/// The `transpose` option: absent or null, or a whole number of semitones within ±48.
fn transpose_of(opts: &serde_json::Value) -> Result<Option<i32>, (i32, String)> {
    match opts.get("transpose").filter(|v| !v.is_null()) {
        None => Ok(None),
        Some(v) => {
            let t = v.as_i64().ok_or_else(|| (BC_INVALID, format!("transpose must be a whole number of semitones, not {v}")))?;
            brasscribe_core::model::check_transpose(t).map(Some).map_err(|e| (BC_INVALID, e))
        }
    }
}

fn str_of(opts: &serde_json::Value, key: &str) -> Option<String> {
    opts.get(key).and_then(|v| v.as_str()).map(String::from)
}

/// The player's part in a lineup: writes `{"part": "Euphonium" | null, "exact": bool, "same_key": bool,
/// "takes": "Solo Cornet" | null}`
/// to `*out` for `lineup` ("band", "minimal", "quartet") and `seat` (an id of [`bc_seats`]).
#[no_mangle]
pub unsafe extern "C" fn bc_seat_part(lineup: *const c_char, seat: *const c_char, out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    let (Some(lineup), Some(seat)) = (from_c(lineup), from_c(seat)) else { return BC_NULL };
    run(out, err, || {
        let sp = crate::seat_part(lineup, seat).map_err(map_err)?;
        Ok(serde_json::json!({"part": sp.part, "exact": sp.exact, "same_key": sp.same_key, "takes": sp.takes}).to_string())
    })
}

/// Where each part of a Composition's arrangement comes from, in score order: writes
/// `[{"part": "Solo Cornet", "source": "your-recording" | "recording" | "arranged"}, ...]` to `*out`.
#[no_mangle]
pub unsafe extern "C" fn bc_part_sources(composition_json: *const c_char, out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    let Some(json) = from_c(composition_json) else { return BC_NULL };
    run(out, err, || {
        let rows: Vec<serde_json::Value> =
            crate::part_sources(json).map_err(map_err)?.into_iter().map(|p| serde_json::json!({"part": p.part, "source": p.source})).collect();
        Ok(serde_json::Value::Array(rows).to_string())
    })
}

/// The seats (the contest band's in score order, then the trumpet): writes `[{"id": "2nd-cornet", "name": "2nd Cornet",
/// "nb_name": "2. kornett", "instrument": "bb-cornet", "clef": "treble", "reads": ["treble"], "tune": true}, ...]` to `*out`.
#[no_mangle]
pub unsafe extern "C" fn bc_seats(out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    run(out, err, || {
        let rows: Vec<serde_json::Value> = crate::seats()
            .into_iter()
            .map(|s| serde_json::json!({"id": s.id, "name": s.name, "nb_name": s.nb_name, "instrument": s.instrument, "clef": s.clef, "reads": s.reads, "tune": s.tune}))
            .collect();
        Ok(serde_json::Value::Array(rows).to_string())
    })
}

/// A part's name in Norwegian (the core's one table): writes the name to `*out`, unchanged when the
/// table doesn't know it.
#[no_mangle]
pub unsafe extern "C" fn bc_part_name_nb(name: *const c_char, out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    let Some(name) = from_c(name) else { return BC_NULL };
    run(out, err, || Ok(crate::part_name_nb(name)))
}

unsafe fn options_json(p: *const c_char) -> Result<serde_json::Value, (i32, String)> {
    match from_c(p) {
        Some(s) if !s.trim().is_empty() => serde_json::from_str(&s).map_err(|e| (BC_INVALID, format!("options: {e}"))),
        _ => Ok(serde_json::Value::Null),
    }
}

/// Like [`bc_arrange_layers_song`], plus the stems' audio: `wav` and `wav_len`
/// hold four WAV files (solo, bass, drums, orchestra; a null pointer = not
/// given). Writes one JSON object to `*out`:
/// `{"composition": "<composition.json text>", "musicxml": "...",
///   "parts": [{"file_name": "...", "musicxml": "..."}], "separation_check": "<json text>" | null}`.
///
/// Every buffer is borrowed for the duration of the call and never copied: the
/// stems are read in place while they are decoded.
#[no_mangle]
pub unsafe extern "C" fn bc_arrange_layers_band(
    midi: *const *const u8,
    midi_len: *const usize,
    wav: *const *const u8,
    wav_len: *const usize,
    beats_text: *const c_char,
    title: *const c_char,
    options: *const c_char,
    out: *mut *mut c_char,
    err: *mut *mut c_char,
) -> i32 {
    bc_arrange_layers_band_contour(midi, midi_len, wav, wav_len, std::ptr::null(), 0, beats_text, title, options, out, err)
}

/// [`bc_arrange_layers_band`] with the solo contour as arrays instead of JSON:
/// `contour` holds four pointers to `contour_len` doubles each (times in
/// seconds, pitch in Hz, loudness in dB, SwiftF0 confidence; a null confidence
/// = none), borrowed for the call like the stems. Non-finite values are read
/// as the JSON form has them: time 0, pitch 0 Hz (no pitch), loudness −140 dB,
/// confidence 0. A null `contour` falls back to `solo_contour` in `options`;
/// `contour_len` 0 is an empty contour.
#[no_mangle]
pub unsafe extern "C" fn bc_arrange_layers_band_contour(
    midi: *const *const u8,
    midi_len: *const usize,
    wav: *const *const u8,
    wav_len: *const usize,
    contour: *const *const f64,
    contour_len: usize,
    beats_text: *const c_char,
    title: *const c_char,
    options: *const c_char,
    out: *mut *mut c_char,
    err: *mut *mut c_char,
) -> i32 {
    let Some(midi) = midi_slices(midi, midi_len) else { return BC_NULL };
    let Some(beats) = from_c(beats_text) else { return BC_NULL };
    let title = from_c(title).unwrap_or_else(|| "Draft".into());
    let mut stems: [Option<&[u8]>; 4] = [None; 4];
    if !wav.is_null() && !wav_len.is_null() {
        for (i, slot) in stems.iter_mut().enumerate() {
            *slot = bytes(*wav.add(i), *wav_len.add(i));
        }
    }
    let arrays = if contour.is_null() { None } else { Some([0, 1, 2, 3].map(|i| *contour.add(i))) };
    if matches!(arrays, Some(a) if contour_len > 0 && a[..3].iter().any(|p| p.is_null())) {
        return BC_NULL;
    }
    run(out, err, move || {
        let opts = options_json(options)?;
        let mut o = options_of(&opts)?;
        let c = match arrays {
            Some([t, hz, db, conf]) => {
                let read = |p: *const f64, bad: f64| -> Vec<f64> {
                    if p.is_null() || contour_len == 0 {
                        return Vec::new();
                    }
                    std::slice::from_raw_parts(p, contour_len).iter().map(|&x| if x.is_finite() { x } else { bad }).collect()
                };
                let hz = read(hz, 0.0);
                let conf = (!conf.is_null()).then(|| read(conf, 0.0));
                Some(Contour::from_hz(read(t, 0.0), &hz, read(db, -140.0)).with_confidence(conf))
            }
            None => json_contour(&mut o),
        };
        let b = crate::LayerBytes { midi, stems };
        let r = crate::band_bytes(&b, &beats, &title, o, c).map_err(map_err)?;
        let parts: Vec<serde_json::Value> = r.parts.iter().map(|p| serde_json::json!({"file_name": p.file_name, "musicxml": p.musicxml})).collect();
        Ok(serde_json::json!({"composition": r.composition_json, "musicxml": r.musicxml, "parts": parts, "separation_check": r.separation_check_json}).to_string())
    })
}

/// A borrowed view of `len` bytes at `p`; None for a null pointer. A zero length is an empty slice.
unsafe fn bytes<'a>(p: *const u8, len: usize) -> Option<&'a [u8]> {
    if p.is_null() {
        None
    } else if len == 0 {
        Some(&[])
    } else {
        Some(std::slice::from_raw_parts(p, len))
    }
}

/// The six MIDI files as borrowed slices; None when an array or a file pointer is null.
unsafe fn midi_slices<'a>(midi: *const *const u8, midi_len: *const usize) -> Option<[&'a [u8]; 6]> {
    if midi.is_null() || midi_len.is_null() {
        return None;
    }
    let mut out: [&[u8]; 6] = [&[]; 6];
    for (i, slot) in out.iter_mut().enumerate() {
        *slot = bytes(*midi.add(i), *midi_len.add(i))?;
    }
    Some(out)
}

/// The solo contour of the options JSON, built as the pipeline reads it.
fn json_contour(o: &mut crate::LayersSongOptions) -> Option<Contour> {
    o.solo_contour.take().map(|c| Contour::from_hz(c.times, &c.pitch_hz, c.loudness_db).with_confidence(c.confidence))
}

/// Humanize one player's notes. `request` is JSON
/// `{"notes": [{"tick", "dur_tick", "start_s", "end_s", "pitch", "velocity"}...],
///   "part": "Solo Cornet", "player": 0, "seed": "brasscribe",
///   "timing": "score" | "performed", "composition": {...} | null}`;
/// writes `{"notes": [{"start", "end", "pitch", "velocity", "staccato",
/// "from_composition"}...], "detune": cents, "stats": {...}}`.
#[no_mangle]
pub unsafe extern "C" fn bc_humanize_json(request: *const c_char, out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    use brasscribe_core::humanize as h;
    let Some(req) = from_c(request) else { return BC_NULL };
    run(out, err, || {
        let v: serde_json::Value = serde_json::from_str(&req).map_err(|e| (BC_INVALID, e.to_string()))?;
        let notes: Vec<h::ScoreNote> = serde_json::from_value(v.get("notes").cloned().unwrap_or_default()).map_err(|e| (BC_INVALID, format!("notes: {e}")))?;
        let perf = match v.get("composition").filter(|c| c.is_object()) {
            Some(c) => Some(h::Performance::from_value(c).map_err(|e| (BC_INVALID, e))?),
            None => None,
        };
        let timing = match v.get("timing").and_then(|t| t.as_str()) {
            None | Some("score") => h::Timing::Score,
            Some("performed") => h::Timing::Performed,
            Some(t) => return Err((BC_INVALID, format!("unknown timing {t}"))),
        };
        let part = v.get("part").and_then(|x| x.as_str()).unwrap_or("");
        let player = v.get("player").and_then(|x| x.as_i64()).unwrap_or(0);
        let seed = v.get("seed").and_then(|x| x.as_str()).unwrap_or("brasscribe");
        let r = h::humanize(&notes, part, player, seed, perf.as_ref(), timing).map_err(|e| (BC_INVALID, e))?;
        Ok(r.to_json_string())
    })
}

/// Opaque talking-score document.
pub struct BcTalkingScore(crate::talking::TalkingScore);

/// Build a talking score from MusicXML and (optionally, may be null) the
/// Composition JSON. Writes a handle to `*out`; release with
/// [`bc_talking_score_free`].
#[no_mangle]
pub unsafe extern "C" fn bc_talking_score_new(musicxml: *const c_char, composition_json: *const c_char, out: *mut *mut BcTalkingScore, err: *mut *mut c_char) -> i32 {
    let Some(xml) = from_c(musicxml) else { return BC_NULL };
    if out.is_null() {
        return BC_NULL;
    }
    let comp = from_c(composition_json);
    let r = catch_unwind(AssertUnwindSafe(|| -> Result<serde_json::Value, (i32, String)> {
        let c: Option<serde_json::Value> = comp.map(|c| serde_json::from_str(&c)).transpose().map_err(|e| (BC_INVALID, e.to_string()))?;
        brasscribe_core::talking_score::build(&xml, c.as_ref()).map_err(|e| (BC_INVALID, e))
    }));
    match r {
        Ok(Ok(doc)) => {
            *out = Box::into_raw(Box::new(BcTalkingScore(crate::talking::TalkingScore::from_doc(doc))));
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

/// Release a talking score. Null is ignored.
#[no_mangle]
pub unsafe extern "C" fn bc_talking_score_free(ts: *mut BcTalkingScore) {
    if !ts.is_null() {
        drop(Box::from_raw(ts));
    }
}

/// The document as JSON (spec §6 shape).
#[no_mangle]
pub unsafe extern "C" fn bc_talking_score_json(ts: *const BcTalkingScore, out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    let Some(t) = ts.as_ref() else { return BC_NULL };
    run(out, err, || Ok(brasscribe_core::pyjson::dumps(t.0.doc())))
}

fn cursor_of(v: &serde_json::Value) -> brasscribe_core::talking_score::Cursor {
    // An index past usize (a 32-bit target) is past every part and bar too.
    let g = |k: &str| v.get(k).and_then(|x| x.as_u64()).map_or(0, |x| usize::try_from(x).unwrap_or(usize::MAX));
    brasscribe_core::talking_score::Cursor { part: g("part"), bar: g("bar"), event: g("event") }
}

/// Announce at a cursor. `request`: `{"cursor": {"part", "bar", "event"},
/// "context": {"part", "bar", "pitch_mode"}, "settings": {"lang", "pitch_mode",
/// "verbosity", "octave_style", "announce_confident"}, "by_bar": false}`.
/// Writes `{"text": "...", "context": {...}}`: the announcement and the
/// context it leaves behind.
#[no_mangle]
pub unsafe extern "C" fn bc_talking_score_announce(ts: *const BcTalkingScore, request: *const c_char, out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    use brasscribe_core::talking_score as t;
    let Some(ts) = ts.as_ref() else { return BC_NULL };
    let Some(req) = from_c(request) else { return BC_NULL };
    run(out, err, || {
        let v: serde_json::Value = serde_json::from_str(&req).map_err(|e| (BC_INVALID, e.to_string()))?;
        let n = serde_json::Value::Null;
        let c = cursor_of(v.get("cursor").unwrap_or(&n));
        let s = t::settings_from_json(v.get("settings").unwrap_or(&n));
        let ctx = t::context_from_json(v.get("context").unwrap_or(&n));
        let text = t::announce_at(ts.0.doc(), c, &ctx, &s, v.get("by_bar").and_then(|x| x.as_bool()).unwrap_or(false)).map_err(|e| (BC_INVALID, e))?;
        let p = &ts.0.doc()["parts"][c.part];
        let next = serde_json::json!({"part": p["name"], "bar": p["bars"][c.bar]["number"], "pitch_mode": s.pitch_mode});
        Ok(serde_json::json!({"text": text, "context": next}).to_string())
    })
}

/// One navigation step. `request`: `{"cursor": {...}, "unit": "note" | "bar" |
/// "part" | "uncertain", "forward": true}`. Writes the new cursor as JSON, or
/// `null` at either end of the score.
#[no_mangle]
pub unsafe extern "C" fn bc_talking_score_navigate(ts: *const BcTalkingScore, request: *const c_char, out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    use brasscribe_core::talking_score as t;
    let Some(ts) = ts.as_ref() else { return BC_NULL };
    let Some(req) = from_c(request) else { return BC_NULL };
    run(out, err, || {
        let v: serde_json::Value = serde_json::from_str(&req).map_err(|e| (BC_INVALID, e.to_string()))?;
        let unit = match v.get("unit").and_then(|x| x.as_str()).unwrap_or("note") {
            "note" => t::Unit::Note,
            "bar" => t::Unit::Bar,
            "part" => t::Unit::Part,
            "uncertain" => t::Unit::Uncertain,
            u => return Err((BC_INVALID, format!("unknown unit {u}"))),
        };
        let c = cursor_of(v.get("cursor").unwrap_or(&serde_json::Value::Null));
        Ok(match t::navigate(ts.0.doc(), c, unit, v.get("forward").and_then(|x| x.as_bool()).unwrap_or(true)) {
            Some(n) => serde_json::json!({"part": n.part, "bar": n.bar, "event": n.event}).to_string(),
            None => "null".into(),
        })
    })
}

/// Export the talking score. `format`: "text" or "html"; `settings_json` may be
/// null (defaults).
#[no_mangle]
pub unsafe extern "C" fn bc_talking_score_export(ts: *const BcTalkingScore, format: *const c_char, settings_json: *const c_char, out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    use brasscribe_core::talking_score as t;
    let Some(ts) = ts.as_ref() else { return BC_NULL };
    let format = from_c(format).unwrap_or_else(|| "text".into());
    let settings = from_c(settings_json);
    run(out, err, || {
        let v: serde_json::Value = match &settings {
            Some(s) if !s.trim().is_empty() => serde_json::from_str(s).map_err(|e| (BC_INVALID, e.to_string()))?,
            _ => serde_json::Value::Null,
        };
        let s = t::settings_from_json(&v);
        match format.as_str() {
            "text" => Ok(t::to_text(ts.0.doc(), &s, None)),
            "html" => Ok(t::to_html(ts.0.doc(), &s, None)),
            f => Err((BC_INVALID, format!("unknown format {f}"))),
        }
    })
}

/// Announce one event outside a document (the conformance-vector form):
/// `{"part": {...}, "bar": {...}, "event": {...}, "context": {...}, "settings": {...}, "by_bar": false}`.
#[no_mangle]
pub unsafe extern "C" fn bc_talking_announce_json(request: *const c_char, out: *mut *mut c_char, err: *mut *mut c_char) -> i32 {
    let Some(req) = from_c(request) else { return BC_NULL };
    run(out, err, || crate::talking::announce_json(&req).map_err(|e| (BC_INVALID, e)))
}
