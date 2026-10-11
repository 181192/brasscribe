//! Input the apps might pass that is not music: every call returns an error (invalid input where the
//! input is at fault) or a result, and never panics, hangs or runs out of memory. Through the UniFFI
//! functions and the C ABI, on small inputs built here.

use std::ffi::{CStr, CString};
use std::os::raw::c_char;

use scribe_ffi::c_api::{
    sc_arrange_layers_band, sc_arrange_musicxml, sc_arrange_with, sc_humanize_json, sc_spell_json, sc_string_free, sc_talking_score_free,
    sc_talking_score_navigate, sc_talking_score_new, ScTalkingScore, SC_INVALID, SC_OK,
};
use scribe_ffi::talking::{talking_settings_default, TalkingScore};
use scribe_ffi::{
    arrange_layers_band, arrange_musicxml, arrange_musicxml_with, arrange_song, choose_metrical_level, quantize_notes, spell_pitches, ArrangeOptions,
    CoreError, LayerMidi, LayerStems, LayersSongOptions, PerformedNote, SoloContour,
};

// ---- inputs ----

/// A standard MIDI file (480 ticks per beat, 120 BPM: a beat is 0.5 s) with (pitch, start, length) notes in ticks.
fn smf(notes: &[(u8, u32, u32)]) -> Vec<u8> {
    let mut ev: Vec<(u32, u8, u8)> = Vec::new();
    for &(p, s, d) in notes {
        ev.push((s, 0x90, p));
        ev.push((s + d, 0x80, p));
    }
    ev.sort_by_key(|e| (e.0, e.1));
    let vlq = |mut v: u32, out: &mut Vec<u8>| {
        let mut b = vec![(v & 0x7f) as u8];
        v >>= 7;
        while v > 0 {
            b.push((v & 0x7f) as u8 | 0x80);
            v >>= 7;
        }
        out.extend(b.iter().rev());
    };
    let mut track = Vec::new();
    let mut at = 0;
    for (t, status, p) in ev {
        vlq(t - at, &mut track);
        at = t;
        track.extend([status, p, if status == 0x90 { 90 } else { 0 }]);
    }
    track.extend([0, 0xff, 0x2f, 0]);
    let mut f = b"MThd".to_vec();
    f.extend(6u32.to_be_bytes());
    f.extend([0, 0, 0, 1, 0x01, 0xe0]);
    f.extend(b"MTrk");
    f.extend((track.len() as u32).to_be_bytes());
    f.extend(track);
    f
}

/// A tune of eight quarter notes from beat 1.
fn tune() -> Vec<u8> {
    let steps = [72, 74, 76, 77, 79, 77, 76, 74];
    smf(&steps.iter().enumerate().map(|(i, &p)| (p, 480 + 480 * i as u32, 440)).collect::<Vec<_>>())
}

fn layers(solo: Vec<u8>) -> LayerMidi {
    LayerMidi {
        solo_swiftf0: solo.clone(),
        solo_muscriptor: solo.clone(),
        solo_basic_pitch: solo,
        bass: smf(&[]),
        orchestra: smf(&[]),
        drums: smf(&[]),
    }
}

/// Sixteen beats half a second apart, four to a bar.
fn beats() -> String {
    (0..16).map(|i| format!("{} {}\n", i as f64 * 0.5, i % 4 + 1)).collect()
}

fn comp(edit: impl FnOnce(&mut serde_json::Value)) -> String {
    let mut v = serde_json::json!({
        "title": "T",
        "voices": [
            {"id": "melody", "role": "melody", "notes": [{"pitch": 64, "start": 0, "dur": 96}, {"pitch": 65, "start": 96, "dur": 96}]},
            {"id": "bass", "role": "bass", "notes": [{"pitch": 48, "start": 0, "dur": 192}]},
        ],
        "meters": [{"tick": 0, "beats": 4}],
        "keys": [{"tick": 0, "fifths": 0}],
    });
    edit(&mut v);
    v.to_string()
}

fn reason<T: std::fmt::Debug>(r: Result<T, CoreError>) -> String {
    match r {
        Err(CoreError::Invalid { reason }) => reason,
        other => panic!("expected invalid input, got {other:?}"),
    }
}

/// A C string argument.
fn cs(s: &str) -> CString {
    CString::new(s).unwrap()
}

/// Code and text (the result or the error) of a C ABI call that writes `*out` and `*err`.
fn c_call(f: impl FnOnce(*mut *mut c_char, *mut *mut c_char) -> i32) -> (i32, String) {
    let (mut out, mut err): (*mut c_char, *mut c_char) = (std::ptr::null_mut(), std::ptr::null_mut());
    let code = f(&mut out, &mut err);
    let p = if code == SC_OK { out } else { err };
    let text = if p.is_null() { String::new() } else { unsafe { CStr::from_ptr(p) }.to_string_lossy().into_owned() };
    unsafe {
        sc_string_free(out);
        sc_string_free(err);
    }
    (code, text)
}

fn c_band(l: &LayerMidi, wav: [Option<&[u8]>; 4], beats: &str, options: &str) -> (i32, String) {
    let midi = [&l.solo_swiftf0, &l.solo_muscriptor, &l.solo_basic_pitch, &l.bass, &l.orchestra, &l.drums];
    let ptr: Vec<*const u8> = midi.iter().map(|m| m.as_ptr()).collect();
    let len: Vec<usize> = midi.iter().map(|m| m.len()).collect();
    let wptr: Vec<*const u8> = wav.iter().map(|w| w.map_or(std::ptr::null(), |w| w.as_ptr())).collect();
    let wlen: Vec<usize> = wav.iter().map(|w| w.map_or(0, |w| w.len())).collect();
    let (b, t, o) = (cs(beats), cs("T"), cs(options));
    c_call(|out, err| unsafe { sc_arrange_layers_band(ptr.as_ptr(), len.as_ptr(), wptr.as_ptr(), wlen.as_ptr(), b.as_ptr(), t.as_ptr(), o.as_ptr(), out, err) })
}

fn band(l: LayerMidi, stems: LayerStems, beats: &str, o: LayersSongOptions) -> Result<scribe_ffi::BandOutput, CoreError> {
    arrange_layers_band(l, stems, beats.into(), "T".into(), o)
}

fn opts() -> LayersSongOptions {
    LayersSongOptions::default()
}

/// A mono float32 WAV at 8 kHz.
fn wav_f32(samples: &[f32]) -> Vec<u8> {
    let data: Vec<u8> = samples.iter().flat_map(|x| x.to_le_bytes()).collect();
    let mut fmt = Vec::new();
    fmt.extend(3u16.to_le_bytes());
    fmt.extend(1u16.to_le_bytes());
    fmt.extend(8000u32.to_le_bytes());
    fmt.extend(32000u32.to_le_bytes());
    fmt.extend(4u16.to_le_bytes());
    fmt.extend(32u16.to_le_bytes());
    let mut body = b"WAVEfmt ".to_vec();
    body.extend(16u32.to_le_bytes());
    body.extend(fmt);
    body.extend(b"data");
    body.extend((data.len() as u32).to_le_bytes());
    body.extend(data);
    let mut w = b"RIFF".to_vec();
    w.extend((body.len() as u32).to_le_bytes());
    w.extend(body);
    w
}

// ---- the inputs above are music ----

#[test]
fn the_small_inputs_arrange() {
    let out = band(layers(tune()), LayerStems::default(), &beats(), opts()).unwrap();
    assert!(out.musicxml.contains("<score-partwise"));
    assert!(arrange_song(tune(), None, smf(&[(48, 480, 1900)]), vec![tune()], beats(), "T".into()).is_ok());
    assert!(arrange_musicxml(comp(|_| {}), "auto".into()).is_ok());
}

// ---- Composition ----

#[test]
fn a_meter_of_a_hundred_thousand_beats_is_refused_on_a_small_stack() {
    // 512 KiB: an iOS secondary thread, where the bar used to be split recursively until the stack ran out.
    let r = std::thread::Builder::new()
        .stack_size(512 * 1024)
        .spawn(|| arrange_musicxml(comp(|v| v["meters"][0]["beats"] = 100_000.into()), "auto".into()))
        .unwrap()
        .join()
        .unwrap();
    assert!(reason(r).contains("a bar has 1 to 32 beats"));
    for beats in [1_000_000, 0, -3] {
        assert!(reason(arrange_musicxml(comp(|v| v["meters"][0]["beats"] = beats.into()), "auto".into())).contains("a bar has 1 to 32 beats"));
    }
    let (json, auto) = (cs(&comp(|v| v["meters"][0]["beats"] = (-3).into())), cs("auto"));
    assert_eq!(c_call(|out, err| unsafe { sc_arrange_musicxml(json.as_ptr(), auto.as_ptr(), out, err) }).0, SC_INVALID);
}

#[test]
fn notes_that_cannot_be_written_are_refused() {
    assert!(reason(arrange_musicxml(comp(|v| v["voices"][0]["notes"][0]["dur"] = (-12).into()), "auto".into())).contains("length -12"));
    // One note of 200,000,000 ticks used to be written out as millions of tied bars.
    let long = comp(|v| v["voices"][0]["notes"][0]["dur"] = 200_000_000.into());
    assert!(reason(arrange_musicxml(long.clone(), "auto".into())).contains("length"));
    assert!(reason(arrange_musicxml_with(long, ArrangeOptions::default())).contains("length"));
    let late = comp(|v| v["voices"][1]["notes"][0]["start"] = 1_000_000_000.into());
    assert!(reason(arrange_musicxml(late, "auto".into())).contains("longer than the 20000 beats"));
}

#[test]
fn a_title_with_control_characters_gives_readable_musicxml() {
    let xml = arrange_musicxml(comp(|v| v["title"] = "bell\u{1}".into()), "auto".into()).unwrap();
    assert!(xml.contains(">bell<"));
    // The talking score parses the MusicXML strictly.
    assert!(TalkingScore::new(xml, None).is_ok());
}

// ---- beat tables ----

#[test]
fn a_beat_table_that_does_not_increase_is_refused() {
    // Equal first beats and a note before them used to put the first note at minus infinity and loop forever.
    let equal = format!("0.5 1\n0.5 2\n{}", (2..16).map(|i| format!("{} {}\n", i as f64 * 0.5, i % 4 + 1)).collect::<String>());
    let early = smf(&[(72, 0, 400), (74, 480 * 4, 400)]);
    assert!(reason(arrange_song(early.clone(), None, smf(&[(48, 0, 400)]), vec![], equal.clone(), "T".into())).contains("increase"));
    assert!(reason(band(layers(early.clone()), LayerStems::default(), &equal, opts())).contains("increase"));
    assert_eq!(c_band(&layers(early), [None; 4], &equal, "").0, SC_INVALID);
    for bad in ["nan 1\n0.5 2\n1.0 3\n", "0 1\ninf 2\n", "0 1\n0.5 nan\n"] {
        assert!(reason(arrange_song(tune(), None, smf(&[]), vec![], bad.into(), "T".into())).contains("not a number"), "{bad:?}");
    }
}

#[test]
fn quantizing_and_the_metrical_level_refuse_what_is_not_a_number() {
    let note = |onset: f64| PerformedNote { pitch: 60, onset, offset: onset + 0.4, confidence: None };
    assert_eq!(quantize_notes(vec![note(0.5)], vec![0.0, 0.5, 1.0], true, false, 0).unwrap().len(), 1);
    assert!(reason(quantize_notes(vec![note(f64::NAN)], vec![0.0, 0.5, 1.0], true, false, 0)).contains("numbers"));
    assert!(reason(quantize_notes(vec![note(0.5)], vec![0.0, f64::NAN, 1.0], true, false, 0)).contains("increase"));
    assert!(reason(quantize_notes(vec![note(0.5)], vec![0.0, 0.0, 1.0], true, false, 0)).contains("increase"));
    assert_eq!(choose_metrical_level(vec![0.0, 1.0, 2.0], vec![0.1]).unwrap(), vec![0.0, 1.0, 2.0]);
    assert!(reason(choose_metrical_level(vec![0.0, f64::NAN, 2.0], vec![0.1])).contains("increase"));
    assert!(reason(choose_metrical_level(vec![0.0, 1.0, 2.0], vec![f64::INFINITY])).contains("numbers"));
}

// ---- options ----

#[test]
fn bad_band_options_are_invalid_input() {
    let cases: [(LayersSongOptions, &str, &str); 8] = [
        (LayersSongOptions { lineup: "xyz".into(), ..opts() }, r#"{"lineup": "xyz"}"#, "lineup"),
        (LayersSongOptions { difficulty: "hard".into(), ..opts() }, r#"{"difficulty": "hard"}"#, "difficulty"),
        (LayersSongOptions { seat: Some("nope".into()), ..opts() }, r#"{"seat": "nope"}"#, "seat"),
        (LayersSongOptions { key: Some("Q".into()), ..opts() }, r#"{"key": "Q"}"#, "key"),
        (LayersSongOptions { seat: Some("euphonium".into()), reads: Some("alto".into()), ..opts() }, r#"{"seat": "euphonium", "reads": "alto"}"#, "reads"),
        (LayersSongOptions { lead: Some("x".into()), ..opts() }, r#"{"lead": "x"}"#, "lead"),
        (LayersSongOptions { free_tempo: Some(1e6), ..opts() }, r#"{"free_tempo": 1e6}"#, "tempo"),
        (LayersSongOptions { transpose: Some(1000), ..opts() }, r#"{"transpose": 1000}"#, "transposition"),
    ];
    for (o, json, what) in cases {
        let r = reason(band(layers(tune()), LayerStems::default(), &beats(), o));
        assert!(r.contains(what), "{what}: {r}");
        let (code, err) = c_band(&layers(tune()), [None; 4], &beats(), json);
        assert_eq!(code, SC_INVALID, "{json}: {err}");
        assert!(err.contains(what), "{json}: {err}");
    }
    for bpm in [f64::INFINITY, f64::NAN, 0.0, -60.0] {
        assert!(reason(band(layers(tune()), LayerStems::default(), &beats(), LayersSongOptions { free_tempo: Some(bpm), ..opts() })).contains("tempo"));
    }
    assert!(band(layers(tune()), LayerStems::default(), &beats(), LayersSongOptions { free_tempo: Some(120.0), ..opts() }).is_ok());
}

#[test]
fn transpositions_beyond_four_octaves_are_invalid() {
    for t in [4294967296i64, 2147483648, -2147483649, 49, -1000] {
        let (json, o) = (cs(&comp(|_| {})), cs(&format!(r#"{{"transpose": {t}}}"#)));
        let (code, err) = c_call(|out, err| unsafe { sc_arrange_with(json.as_ptr(), o.as_ptr(), out, err) });
        assert_eq!(code, SC_INVALID, "{t}: {err}");
        let (code, _) = c_band(&layers(tune()), [None; 4], &beats(), &format!(r#"{{"transpose": {t}}}"#));
        assert_eq!(code, SC_INVALID, "{t}");
    }
    let (json, o) = (cs(&comp(|_| {})), cs(r#"{"transpose": 2.5}"#));
    assert_eq!(c_call(|out, err| unsafe { sc_arrange_with(json.as_ptr(), o.as_ptr(), out, err) }).0, SC_INVALID);
    let with = |t: i32| ArrangeOptions { transpose: Some(t), ..Default::default() };
    assert!(arrange_musicxml_with(comp(|_| {}), with(48)).is_ok());
    assert!(reason(arrange_musicxml_with(comp(|_| {}), with(1000))).contains("transposition"));
    // Already transposed by an amount no composition records.
    let recorded = comp(|v| v["arrangement"] = serde_json::json!({"transpose_semitones": 4294967296i64}));
    assert!(reason(arrange_musicxml_with(recorded, with(2))).contains("transposition"));
    // A note taken past MIDI 127.
    let high = comp(|v| v["voices"][0]["notes"][0]["pitch"] = 120.into());
    assert!(reason(arrange_musicxml_with(high, with(12))).contains("outside MIDI"));
    // A key given as an enormous number of fifths is just a pitch class.
    let k = ArrangeOptions { key: Some("9223372036854775807".into()), ..Default::default() };
    assert!(arrange_musicxml_with(comp(|_| {}), k).is_ok());
}

// ---- contour and stems ----

#[test]
fn contour_arrays_of_different_lengths_are_invalid() {
    let c = |n_hz: usize, n_db: usize, conf: Option<usize>| SoloContour {
        times: (0..4).map(|i| i as f64 * 0.016).collect(),
        pitch_hz: vec![440.0; n_hz],
        loudness_db: vec![-20.0; n_db],
        confidence: conf.map(|n| vec![0.9; n]),
    };
    assert!(band(layers(tune()), LayerStems::default(), &beats(), LayersSongOptions { solo_contour: Some(c(4, 4, Some(4))), ..opts() }).is_ok());
    for (hz, db, conf) in [(2, 4, None), (4, 2, None), (4, 4, Some(1))] {
        let o = LayersSongOptions { solo_contour: Some(c(hz, db, conf)), ..opts() };
        assert!(reason(band(layers(tune()), LayerStems::default(), &beats(), o)).contains("contour"));
    }
    let json = |pitch: &str| format!(r#"{{"solo_contour": {{"times": [0, 0.016, 0.032], "pitch_hz": {pitch}, "loudness_db": [-20, -20, -20]}}}}"#);
    // A null is a frame without pitch, not a frame fewer.
    assert_eq!(c_band(&layers(tune()), [None; 4], &beats(), &json("[440, null, 440]")).0, SC_OK);
    let (code, err) = c_band(&layers(tune()), [None; 4], &beats(), &json("[440, 440]"));
    assert_eq!(code, SC_INVALID);
    assert!(err.contains("contour"), "{err}");
}

#[test]
fn stems_that_are_cut_off_or_not_numbers() {
    let good = wav_f32(&[0.1; 800]);
    let mut cut = good.clone();
    cut.truncate(12 + 8 + 10); // inside the fmt chunk
    let stems = |w: &[u8]| LayerStems { solo: Some(w.to_vec()), bass: Some(w.to_vec()), ..Default::default() };
    assert!(reason(band(layers(tune()), stems(&cut), &beats(), opts())).contains("fmt"));
    assert_eq!(c_band(&layers(tune()), [Some(&cut), None, None, None], &beats(), "").0, SC_INVALID);
    let nan = wav_f32(&[f32::NAN; 8000]);
    assert!(band(layers(tune()), stems(&nan), &beats(), opts()).is_ok());
    assert_eq!(c_band(&layers(tune()), [Some(&nan), Some(&nan), Some(&nan), Some(&nan)], &beats(), "").0, SC_OK);
}

#[test]
fn a_take_longer_than_any_piece_is_refused() {
    // A second note three days after the first: the arrangement would be hundreds of thousands of bars.
    let far = || smf(&[(72, 480, 440), (74, 0x0fff_ffff, 440)]);
    let r = band(layers(far()), LayerStems::default(), &beats(), opts());
    assert!(matches!(&r, Err(e) if e.to_string().contains("longer than the 20000 beats")), "{r:?}");
    let r = arrange_song(far(), None, smf(&[(48, 480, 480)]), vec![], beats(), "T".into());
    assert!(matches!(&r, Err(e) if e.to_string().contains("longer than the 20000 beats")), "{r:?}");
}

// ---- spelling ----

#[test]
fn spelling_needs_one_onset_per_pitch() {
    assert_eq!(spell_pitches(vec![0.0, 1.0], vec![66, 69]).unwrap().len(), 2);
    assert!(reason(spell_pitches(vec![0.0], vec![66, 69])).contains("1 onsets for 2 pitches"));
    assert!(reason(spell_pitches(vec![0.0, 1.0, 2.0], vec![66, 69])).contains("3 onsets for 2 pitches"));
    assert!(reason(spell_pitches(vec![f64::NAN, 1.0], vec![66, 69])).contains("numbers"));
    for req in [r#"{"onsets": [0, null], "pitches": [66, 69]}"#, r#"{"onsets": [0, 1], "pitches": [66, 4294967296]}"#, r#"{"onsets": [0], "pitches": [66, 69]}"#] {
        let r = cs(req);
        assert_eq!(c_call(|out, err| unsafe { sc_spell_json(r.as_ptr(), out, err) }).0, SC_INVALID, "{req}");
    }
}

// ---- humanizing ----

#[test]
fn humanizing_with_beat_times_at_the_ends_of_the_float_range() {
    let c = comp(|v| {
        v["beat_times"] = serde_json::json!([-1e308, 1e308]);
        v["voices"][0]["notes"][0]["onset_s"] = 0.1.into();
        v["voices"][1]["notes"][0]["onset_s"] = 0.2.into();
    });
    let req = format!(
        r#"{{"notes": [{{"tick": 0, "dur_tick": 96, "start_s": 0.0, "end_s": 2.0, "pitch": 64, "velocity": 80}}], "part": "Solo Cornet", "composition": {c}}}"#
    );
    let r = cs(&req);
    assert_eq!(c_call(|out, err| unsafe { sc_humanize_json(r.as_ptr(), out, err) }).0, SC_OK);
}

// ---- talking score ----

fn musicxml(attributes: &str, note_extra: &str) -> String {
    format!(
        r#"<?xml version="1.0"?><score-partwise><part-list><score-part id="P1"><part-name>Solo Cornet</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes>{attributes}<time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>B</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type>{note_extra}</note></measure></part></score-partwise>"#
    )
}

#[test]
fn talking_score_of_odd_musicxml() {
    let ok = TalkingScore::new(musicxml("<divisions>1</divisions>", ""), None).unwrap();
    assert!(ok.to_text(talking_settings_default(), None).contains("Solo Cornet"));
    // Zero divisions or a tuplet of zero notes would divide by zero; the reference raises too.
    assert!(reason(TalkingScore::new(musicxml("<divisions>0</divisions>", ""), None).map(|_| ())).contains("divisions"));
    let zero_tuplet = "<time-modification><actual-notes>0</actual-notes><normal-notes>2</normal-notes></time-modification>";
    assert!(reason(TalkingScore::new(musicxml("<divisions>1</divisions>", zero_tuplet), None).map(|_| ())).contains("tuplet"));
    let (xml, none) = (cs(&musicxml("<divisions>0</divisions>", "")), std::ptr::null());
    let mut ts: *mut ScTalkingScore = std::ptr::null_mut();
    let mut err: *mut c_char = std::ptr::null_mut();
    assert_eq!(unsafe { sc_talking_score_new(xml.as_ptr(), none, &mut ts, &mut err) }, SC_INVALID);
    unsafe { sc_string_free(err) };
    // A key signature of i64::MIN fifths flattens all seven steps, as in the reference: its B is a B flat,
    // so a written B is announced as B natural.
    let flats = TalkingScore::new(musicxml("<divisions>1</divisions><key><fifths>-9223372036854775808</fifths></key>", ""), None).unwrap();
    let text = flats.to_text(talking_settings_default(), None);
    assert!(text.contains("B-natural 4"), "{text}");
}

#[test]
fn talking_score_parts_and_cursors_out_of_range() {
    let ts = TalkingScore::new(musicxml("<divisions>1</divisions>", ""), None).unwrap();
    let s = talking_settings_default;
    assert_eq!(ts.to_text(s(), Some(vec![99])), ts.to_text(s(), Some(vec![])));
    assert!(ts.to_html(s(), Some(vec![0, 99, u32::MAX])).contains("Solo Cornet"));
    assert!(ts.part_lines(99, s()).is_empty());
    let xml = cs(&musicxml("<divisions>1</divisions>", ""));
    let mut h: *mut ScTalkingScore = std::ptr::null_mut();
    let mut err: *mut c_char = std::ptr::null_mut();
    assert_eq!(unsafe { sc_talking_score_new(xml.as_ptr(), std::ptr::null(), &mut h, &mut err) }, SC_OK);
    for unit in ["part", "bar"] {
        let req = cs(&format!(r#"{{"cursor": {{"part": 18446744073709551615, "bar": 18446744073709551615, "event": 0}}, "unit": "{unit}", "forward": true}}"#));
        assert_eq!(c_call(|out, err| unsafe { sc_talking_score_navigate(h, req.as_ptr(), out, err) }), (SC_OK, "null".into()), "{unit}");
    }
    unsafe { sc_talking_score_free(h) };
}
