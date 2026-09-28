//! bc_arrange_layers_band (the C ABI Windows Play calls with four WAV stems) against the UniFFI
//! arrange_layers_band, on Mikkel's layers, with and without the solo contour as arrays. The Mikkel
//! cases skip when data/mikkel/repro is not in the checkout (BRASSCRIBE_REPO points at one that has it).

use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use std::path::{Path, PathBuf};

use brasscribe_ffi::c_api::{bc_arrange_layers_band, bc_arrange_layers_band_contour, bc_string_free, BC_INVALID, BC_NULL};
use brasscribe_ffi::{arrange_layers_band, LayerMidi, LayerStems, LayersSongOptions, SoloContour};

const MIDI: [&str; 6] = ["solo-sw.mid", "solo-mus.mid", "solo-bp.mid", "bass-mus.mid", "orchestra-mus.mid", "drums-mus.mid"];
const WAV: [&str; 4] = ["solo.wav", "bass.wav", "drums.wav", "orchestra.wav"];

fn repro() -> Option<PathBuf> {
    let root = std::env::var_os("BRASSCRIBE_REPO").map(PathBuf::from).unwrap_or_else(|| Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."));
    let d = root.join("data/mikkel/repro");
    (d.join("layers/solo.wav").exists() && d.join("mix.beats").exists()).then_some(d)
}

struct Inputs {
    midi: Vec<Vec<u8>>,
    wav: Vec<Vec<u8>>,
    beats: String,
}

fn inputs(d: &Path) -> Inputs {
    let read = |n: &str| std::fs::read(d.join("layers").join(n)).unwrap();
    Inputs { midi: MIDI.map(read).to_vec(), wav: WAV.map(read).to_vec(), beats: std::fs::read_to_string(d.join("mix.beats")).unwrap() }
}

fn c_abi(i: &Inputs) -> serde_json::Value {
    c_abi_with(i, None, None)
}

/// bc_arrange_layers_band, or bc_arrange_layers_band_contour when `contour` is given
/// (times, pitch, loudness, confidence), with `options` as the options JSON.
fn c_abi_with(i: &Inputs, contour: Option<&[Vec<f64>; 4]>, options: Option<&str>) -> serde_json::Value {
    let midi: Vec<*const u8> = i.midi.iter().map(|m| m.as_ptr()).collect();
    let midi_len: Vec<usize> = i.midi.iter().map(|m| m.len()).collect();
    let wav: Vec<*const u8> = i.wav.iter().map(|w| w.as_ptr()).collect();
    let wav_len: Vec<usize> = i.wav.iter().map(|w| w.len()).collect();
    let beats = CString::new(i.beats.clone()).unwrap();
    let title = CString::new("Mikkel").unwrap();
    let options = options.map(|o| CString::new(o).unwrap());
    let options_ptr = options.as_ref().map_or(std::ptr::null(), |o| o.as_ptr());
    let (mut out, mut err): (*mut c_char, *mut c_char) = (std::ptr::null_mut(), std::ptr::null_mut());
    let code = unsafe {
        match contour {
            None => bc_arrange_layers_band(midi.as_ptr(), midi_len.as_ptr(), wav.as_ptr(), wav_len.as_ptr(), beats.as_ptr(), title.as_ptr(),
                                           options_ptr, &mut out, &mut err),
            Some(c) => {
                let arrays: Vec<*const f64> = c.iter().map(|a| a.as_ptr()).collect();
                bc_arrange_layers_band_contour(midi.as_ptr(), midi_len.as_ptr(), wav.as_ptr(), wav_len.as_ptr(), arrays.as_ptr(), c[0].len(),
                                               beats.as_ptr(), title.as_ptr(), options_ptr, &mut out, &mut err)
            }
        }
    };
    assert_eq!(code, 0, "bc_arrange_layers_band failed: {}", if err.is_null() { String::new() } else { unsafe { CStr::from_ptr(err) }.to_string_lossy().into_owned() });
    let text = unsafe { CStr::from_ptr(out) }.to_str().unwrap().to_owned();
    unsafe { bc_string_free(out) };
    serde_json::from_str(&text).unwrap()
}

fn uniffi(i: &Inputs, options: LayersSongOptions) -> brasscribe_ffi::BandOutput {
    let m = |k: usize| i.midi[k].clone();
    let w = |k: usize| Some(i.wav[k].clone());
    arrange_layers_band(
        LayerMidi { solo_swiftf0: m(0), solo_muscriptor: m(1), solo_basic_pitch: m(2), bass: m(3), orchestra: m(4), drums: m(5) },
        LayerStems { solo: w(0), bass: w(1), drums: w(2), orchestra: w(3) },
        i.beats.clone(),
        "Mikkel".into(),
        options,
    )
    .unwrap()
}

fn assert_same(c: &serde_json::Value, u: &brasscribe_ffi::BandOutput) {
    assert_eq!(c["composition"].as_str().unwrap(), u.composition_json);
    assert_eq!(c["musicxml"].as_str().unwrap(), u.musicxml);
    assert_eq!(c["separation_check"].as_str(), u.separation_check_json.as_deref());
    let parts = c["parts"].as_array().unwrap();
    assert_eq!(parts.len(), u.parts.len());
    for (p, q) in parts.iter().zip(&u.parts) {
        assert_eq!(p["file_name"].as_str().unwrap(), q.file_name);
        assert_eq!(p["musicxml"].as_str().unwrap(), q.musicxml);
    }
}

/// A synthetic solo contour over the first 60 s at 100 frames/s: Bb4 held in 2 s phrases with
/// 0.5 s breaths, a NaN pitch and a NaN loudness in every breath.
fn synthetic_contour() -> [Vec<f64>; 4] {
    let n = 6000;
    let t: Vec<f64> = (0..n).map(|k| k as f64 * 0.01).collect();
    let voiced = |k: usize| (k % 250) < 200;
    let hz = (0..n).map(|k| if voiced(k) { 466.16 } else if k % 250 == 210 { f64::NAN } else { 0.0 }).collect();
    let db = (0..n).map(|k| if voiced(k) { -18.0 } else if k % 250 == 220 { f64::NAN } else { -70.0 }).collect();
    let conf = (0..n).map(|k| if voiced(k) { 0.9 } else { 0.1 }).collect();
    [t, hz, db, conf]
}

/// The contour as the C ABI reads it: non-finite pitch as 0 Hz, non-finite loudness as −140 dB.
fn sanitized(c: &[Vec<f64>; 4]) -> SoloContour {
    let fix = |v: &Vec<f64>, bad: f64| v.iter().map(|&x| if x.is_finite() { x } else { bad }).collect::<Vec<f64>>();
    SoloContour { times: fix(&c[0], 0.0), pitch_hz: fix(&c[1], 0.0), loudness_db: fix(&c[2], -140.0), confidence: Some(fix(&c[3], 0.0)) }
}

#[test]
fn c_abi_with_stems_matches_uniffi() {
    let Some(d) = repro() else { return };
    let i = inputs(&d);
    assert_same(&c_abi(&i), &uniffi(&i, LayersSongOptions::default()));
}

#[test]
fn c_abi_contour_arrays_match_uniffi_and_json() {
    let Some(d) = repro() else { return };
    let i = inputs(&d);
    let contour = synthetic_contour();
    let want = uniffi(&i, LayersSongOptions { solo_contour: Some(sanitized(&contour)), ..Default::default() });
    // The contour changes the score, so the comparison below is not vacuous.
    assert_ne!(want.musicxml, uniffi(&i, LayersSongOptions::default()).musicxml);
    assert_same(&c_abi_with(&i, Some(&contour), None), &want);

    // The same contour as options JSON, through the call without contour arrays.
    let s = sanitized(&contour);
    let json = serde_json::json!({"solo_contour": {"times": s.times, "pitch_hz": s.pitch_hz, "loudness_db": s.loudness_db, "confidence": s.confidence}});
    assert_same(&c_abi_with(&i, None, Some(&json.to_string())), &want);
    // Arrays and JSON together: the arrays are read.
    let arrays_over_json = c_abi_with(&i, Some(&contour), Some(&json.to_string()));
    assert_same(&arrays_over_json, &want);
}

#[test]
fn c_abi_rejects_null_and_empty_inputs() {
    let empty: [*const u8; 6] = [b"".as_ptr(); 6];
    let lens = [0usize; 6];
    let beats = CString::new("0.5 1\n1.0 2\n").unwrap();
    let (mut out, mut err): (*mut c_char, *mut c_char) = (std::ptr::null_mut(), std::ptr::null_mut());
    unsafe {
        let code = bc_arrange_layers_band(std::ptr::null(), lens.as_ptr(), std::ptr::null(), std::ptr::null(), beats.as_ptr(), std::ptr::null(),
                                          std::ptr::null(), &mut out, &mut err);
        assert_eq!(code, BC_NULL);
        let mut midi = empty;
        midi[3] = std::ptr::null();
        let code = bc_arrange_layers_band(midi.as_ptr(), lens.as_ptr(), std::ptr::null(), std::ptr::null(), beats.as_ptr(), std::ptr::null(),
                                          std::ptr::null(), &mut out, &mut err);
        assert_eq!(code, BC_NULL);
        // Contour arrays with a null time array but a length.
        let arrays: [*const f64; 4] = [std::ptr::null(); 4];
        let code = bc_arrange_layers_band_contour(empty.as_ptr(), lens.as_ptr(), std::ptr::null(), std::ptr::null(), arrays.as_ptr(), 3,
                                                  beats.as_ptr(), std::ptr::null(), std::ptr::null(), &mut out, &mut err);
        assert_eq!(code, BC_NULL);
        // Zero-length buffers are empty inputs, not null ones: an error from the MIDI parser, not a crash.
        let code = bc_arrange_layers_band_contour(empty.as_ptr(), lens.as_ptr(), std::ptr::null(), std::ptr::null(), arrays.as_ptr(), 0,
                                                  beats.as_ptr(), std::ptr::null(), std::ptr::null(), &mut out, &mut err);
        assert_eq!(code, BC_INVALID);
        assert!(!err.is_null());
        bc_string_free(err);
    }
}

/// Only the C ABI call, for measuring its peak memory:
/// `/usr/bin/time -l cargo test -p brasscribe-ffi --release --test layers_band_c_api -- --ignored c_abi_alone`
#[test]
#[ignore]
fn c_abi_alone() {
    let Some(d) = repro() else { return };
    let c = c_abi(&inputs(&d));
    assert!(c["musicxml"].as_str().unwrap().contains("<score-partwise"));
}

/// Counts live heap bytes and their peak, for [`c_abi_heap_peak`].
mod heap {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};

    pub static LIVE: AtomicUsize = AtomicUsize::new(0);
    pub static PEAK: AtomicUsize = AtomicUsize::new(0);

    fn grow(n: usize) {
        PEAK.fetch_max(LIVE.fetch_add(n, Relaxed) + n, Relaxed);
    }

    struct Counting;

    unsafe impl GlobalAlloc for Counting {
        unsafe fn alloc(&self, l: Layout) -> *mut u8 {
            grow(l.size());
            System.alloc(l)
        }
        unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
            LIVE.fetch_sub(l.size(), Relaxed);
            System.dealloc(p, l)
        }
        unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
            if n > l.size() {
                grow(n - l.size());
            } else {
                LIVE.fetch_sub(l.size() - n, Relaxed);
            }
            System.realloc(p, l, n)
        }
    }

    #[global_allocator]
    static COUNTING: Counting = Counting;
}

/// Heap peak of the C ABI call, the caller's inputs included (RSS also counts pages the allocator
/// keeps after a free). Run it alone, other tests share the counter: `cargo test -p brasscribe-ffi --release --test layers_band_c_api -- --ignored c_abi_heap_peak --nocapture`
#[test]
#[ignore]
fn c_abi_heap_peak() {
    use std::sync::atomic::Ordering::Relaxed;
    let Some(d) = repro() else { return };
    let i = inputs(&d);
    let held = heap::LIVE.load(Relaxed);
    heap::PEAK.store(held, Relaxed);
    let c = c_abi(&i);
    assert!(c["musicxml"].as_str().unwrap().contains("<score-partwise"));
    eprintln!("inputs {} MB, heap peak {} MB", held >> 20, heap::PEAK.load(Relaxed) >> 20);
}
