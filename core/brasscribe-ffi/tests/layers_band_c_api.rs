//! bc_arrange_layers_band (the C ABI Windows Play calls with four WAV stems) against the UniFFI
//! arrange_layers_band, on Mikkel's layers. Skips when data/mikkel/repro is not in the checkout.

use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use std::path::{Path, PathBuf};

use brasscribe_ffi::c_api::{bc_arrange_layers_band, bc_string_free};
use brasscribe_ffi::{arrange_layers_band, LayerMidi, LayerStems, LayersSongOptions};

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
    let midi: Vec<*const u8> = i.midi.iter().map(|m| m.as_ptr()).collect();
    let midi_len: Vec<usize> = i.midi.iter().map(|m| m.len()).collect();
    let wav: Vec<*const u8> = i.wav.iter().map(|w| w.as_ptr()).collect();
    let wav_len: Vec<usize> = i.wav.iter().map(|w| w.len()).collect();
    let beats = CString::new(i.beats.clone()).unwrap();
    let title = CString::new("Mikkel").unwrap();
    let (mut out, mut err): (*mut c_char, *mut c_char) = (std::ptr::null_mut(), std::ptr::null_mut());
    let code = unsafe {
        bc_arrange_layers_band(midi.as_ptr(), midi_len.as_ptr(), wav.as_ptr(), wav_len.as_ptr(), beats.as_ptr(), title.as_ptr(),
                               std::ptr::null(), &mut out, &mut err)
    };
    assert_eq!(code, 0, "bc_arrange_layers_band failed: {}", if err.is_null() { String::new() } else { unsafe { CStr::from_ptr(err) }.to_string_lossy().into_owned() });
    let text = unsafe { CStr::from_ptr(out) }.to_str().unwrap().to_owned();
    unsafe { bc_string_free(out) };
    serde_json::from_str(&text).unwrap()
}

#[test]
fn c_abi_with_stems_matches_uniffi() {
    let Some(d) = repro() else { return };
    let i = inputs(&d);
    let c = c_abi(&i);
    let m = |k: usize| i.midi[k].clone();
    let w = |k: usize| Some(i.wav[k].clone());
    let u = arrange_layers_band(
        LayerMidi { solo_swiftf0: m(0), solo_muscriptor: m(1), solo_basic_pitch: m(2), bass: m(3), orchestra: m(4), drums: m(5) },
        LayerStems { solo: w(0), bass: w(1), drums: w(2), orchestra: w(3) },
        i.beats.clone(),
        "Mikkel".into(),
        LayersSongOptions::default(),
    )
    .unwrap();
    assert_eq!(c["composition"].as_str().unwrap(), u.composition_json);
    assert_eq!(c["musicxml"].as_str().unwrap(), u.musicxml);
    assert_eq!(c["separation_check"].as_str(), u.separation_check_json.as_deref());
    assert_eq!(c["parts"].as_array().unwrap().len(), u.parts.len());
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
