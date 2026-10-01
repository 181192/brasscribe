//! Behaviour of the fingering solver on whole passages.

use brasscribe_core::model::Note;
use target_fretted::json::{solve_json, InstrumentChoice, Request, Response};
use target_fretted::{assign, check, preset, Fingering, Instrument, Options, Pin, Position, Style, Violation, PRESET_IDS};

const EIGHTH: i64 = 12;

fn note(pitch: i32, start: i64) -> Note {
    Note::new(pitch, start, EIGHTH, 1.0, Vec::new())
}

/// A single-note line, one note per eighth.
fn line(pitches: &[i32]) -> Vec<Note> {
    pitches.iter().enumerate().map(|(i, &p)| note(p, i as i64 * EIGHTH)).collect()
}

/// Chords one after another, each lasting a bar.
fn chords(list: &[&[i32]]) -> Vec<Note> {
    list.iter().enumerate().flat_map(|(i, c)| c.iter().map(move |&p| note(p, i as i64 * 96))).collect()
}

fn opts(style: Style) -> Options {
    Options { style, ..Options::default() }
}

fn solve(inst: &Instrument, notes: &[Note], o: &Options) -> Fingering {
    let f = assign(inst, notes, o).unwrap();
    let v = check(inst, notes, &f, o);
    assert!(v.is_empty(), "violations {v:?} in {:?}", f.notes.iter().map(|n| n.position()).collect::<Vec<_>>());
    f
}

fn positions(f: &Fingering) -> Vec<Position> {
    f.notes.iter().map(|n| n.position().expect("every note placed")).collect()
}

/// A chord's frets as a guitar player writes them, low string (6) first; `x` = not played.
fn shape(inst: &Instrument, f: &Fingering, from: usize, count: usize) -> String {
    let mut frets = vec!["x".to_string(); inst.string_count()];
    for n in &f.notes[from..from + count] {
        let p = n.position().unwrap();
        frets[p.string as usize - 1] = p.fret.to_string();
    }
    frets.reverse();
    frets.join("-")
}

/// A tiny deterministic generator (SplitMix64) for the property tests.
struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    fn below(&mut self, n: i64) -> i64 {
        (self.next() % n.max(1) as u64) as i64
    }

    fn range(&mut self, lo: i64, hi: i64) -> i64 {
        lo + self.below(hi - lo + 1)
    }
}

fn instruments() -> Vec<Instrument> {
    PRESET_IDS.iter().flat_map(|id| [preset(id).unwrap(), preset(id).unwrap().with_capo(3)]).collect()
}

// Pitches (MIDI) used below.
const C3: i32 = 48;
const D3: i32 = 50;
const E3: i32 = 52;
const F3: i32 = 53;
const G3: i32 = 55;
const A3: i32 = 57;
const B3: i32 = 59;
const C4: i32 = 60;
const D4: i32 = 62;
const E4: i32 = 64;
const F4: i32 = 65;
const G4: i32 = 67;
const A4: i32 = 69;
const B4: i32 = 71;
const C5: i32 = 72;
const D5: i32 = 74;
const E5: i32 = 76;

#[test]
fn pitches_are_never_changed_and_out_of_range_notes_are_flagged() {
    for inst in instruments() {
        let (lo, hi) = inst.range();
        for seed in 0..12u64 {
            let mut rng = Rng(seed * 7919 + inst.string_count() as u64);
            let mut notes = Vec::new();
            let mut t = 0;
            for _ in 0..rng.range(1, 30) {
                for _ in 0..rng.range(1, inst.string_count() as i64 + 2) {
                    notes.push(note(rng.range(i64::from(lo) - 6, i64::from(hi) + 6) as i32, t));
                }
                t += rng.range(0, 3) * 6;
            }
            let o = opts([Style::OpenPosition, Style::AsPlayed, Style::Lead][seed as usize % 3]);
            let f = assign(&inst, &notes, &o).unwrap();
            assert_eq!(f, assign(&inst, &notes, &o).unwrap(), "{}: same input, same output", inst.tuning.name);
            assert_eq!(f.notes.len(), notes.len());
            for (n, place) in notes.iter().zip(&f.notes) {
                assert_eq!(place.pitch, n.pitch);
                let playable = !inst.positions(n.pitch).is_empty();
                assert_eq!(place.out_of_range, !playable, "{} pitch {}", inst.tuning.name, n.pitch);
                if let Some(pos) = place.position() {
                    assert_eq!(inst.pitch_at(pos), Some(n.pitch), "{} {pos:?}", inst.tuning.name);
                }
                for alt in &place.alternatives {
                    assert_eq!(inst.pitch_at(*alt), Some(n.pitch));
                    assert_ne!(Some(*alt), place.position());
                }
            }
            // The only violation allowed on arbitrary input: in-range notes left without a string
            // (more pitches start together than strings, or no voicing fits the hand).
            for v in check(&inst, &notes, &f, &o) {
                assert!(matches!(v, Violation::NoString { .. } | Violation::SpanTooWide { .. }), "{}: {v:?}", inst.tuning.name);
            }
        }
    }
}

/// Events built from positions that fit the hand, plus notes below the instrument's range.
fn playable_passage(inst: &Instrument, rng: &mut Rng, o: &Options) -> Vec<Note> {
    let strings = inst.string_count() as i64;
    let capo = i64::from(inst.capo);
    let mut notes = Vec::new();
    let mut t = 0;
    for _ in 0..rng.range(1, 24) {
        let base = rng.range(capo + 1, i64::from(inst.frets) - 3);
        let mut free: Vec<u8> = (1..=strings as u8).collect();
        let mut necks = Vec::new();
        for _ in 0..rng.range(1, strings) {
            let s = free.remove(rng.below(free.len() as i64) as usize);
            let fret = if rng.below(4) == 0 { 0 } else { (base + rng.range(0, 3) - capo) as u8 };
            let pos = Position { string: s, fret };
            let Some(pitch) = inst.pitch_at(pos) else { continue };
            let neck = inst.neck_fret(pos).unwrap();
            let mut all = necks.clone();
            if neck > 0 {
                all.push(neck);
            }
            let (lo, hi) = (all.iter().min().copied().unwrap_or(0), all.iter().max().copied().unwrap_or(0));
            if lo > 0 && inst.fret_mm(hi) - inst.fret_mm(lo) > o.hand.max_mm {
                continue;
            }
            necks = all;
            notes.push(note(pitch, t));
        }
        if rng.below(5) == 0 {
            notes.push(note(inst.range().0 - 1 - rng.below(5) as i32, t));
        }
        t += rng.range(1, 4) * 6;
    }
    notes
}

#[test]
fn playable_input_gets_no_violations() {
    for inst in instruments() {
        for seed in 0..15u64 {
            let mut rng = Rng(seed * 104_729 + u64::from(inst.capo) + inst.frets as u64);
            let o = opts([Style::OpenPosition, Style::AsPlayed, Style::Lead][seed as usize % 3]);
            let notes = playable_passage(&inst, &mut rng, &o);
            let f = solve(&inst, &notes, &o);
            for (n, place) in notes.iter().zip(&f.notes) {
                assert_eq!(place.out_of_range, place.position().is_none());
                assert_eq!(place.pitch, n.pitch);
            }
        }
    }
}

#[test]
fn c_major_scale_stays_in_first_position() {
    let g = preset("guitar-standard").unwrap();
    let up = [C3, D3, E3, F3, G3, A3, B3, C4, D4, E4, F4, G4];
    let mut scale = up.to_vec();
    scale.extend(up.iter().rev().skip(1));
    for style in [Style::OpenPosition, Style::AsPlayed] {
        let f = solve(&g, &line(&scale), &opts(style));
        // First position: every fret 0 to 4.
        for p in positions(&f) {
            assert!(p.fret <= 4, "{style:?}: {p:?}");
        }
        assert_eq!(f.notes[0].position(), Some(Position { string: 5, fret: 3 }));
    }
}

#[test]
fn a_melody_up_the_neck_is_not_written_on_open_strings() {
    let g = preset("guitar-standard").unwrap();
    // C4 to E5 and back: E5 exists only at the 12th fret of string 1 (or higher), so the whole
    // phrase belongs around frets 7 to 12, not in first position on the thin strings.
    let up = [C4, D4, E4, F4, G4, A4, B4, C5, D5, E5];
    let mut phrase = up.to_vec();
    phrase.extend(up.iter().rev().skip(1));
    for style in [Style::AsPlayed, Style::Lead] {
        let f = solve(&g, &line(&phrase), &opts(style));
        for (p, pitch) in positions(&f).iter().zip(&phrase) {
            assert!(p.fret >= 5, "{style:?}: pitch {pitch} at {p:?}; all {:?}", positions(&f));
        }
    }
}

#[test]
fn a_lick_at_the_twelfth_fret_does_not_slide_down_to_open_strings() {
    let g = preset("guitar-standard").unwrap();
    // Starts and ends at string 1 fret 12; the notes between all exist around frets 9 to 12.
    let lick = [E5, D5, B4, A4, G4, E4, G4, A4, B4, D5, E5];
    for style in [Style::OpenPosition, Style::AsPlayed, Style::Lead] {
        let f = solve(&g, &line(&lick), &opts(style));
        for p in positions(&f) {
            assert!(p.fret >= 7, "{style:?}: {:?}", positions(&f));
        }
    }
}

#[test]
fn open_chords_get_the_standard_open_shapes() {
    let g = preset("guitar-standard").unwrap();
    let list: [(&[i32], &str); 5] = [
        (&[43, 47, 50, 55, 59, 67], "3-2-0-0-0-3"),
        (&[48, 52, 55, 60, 64], "x-3-2-0-1-0"),
        (&[50, 57, 62, 66], "x-x-0-2-3-2"),
        (&[40, 47, 52, 55, 59, 64], "0-2-2-0-0-0"),
        (&[45, 52, 57, 60, 64], "x-0-2-2-1-0"),
    ];
    let o = opts(Style::OpenPosition);
    for (chord, want) in list {
        let f = solve(&g, &chords(&[chord]), &o);
        assert_eq!(shape(&g, &f, 0, chord.len()), want);
    }
    let all: Vec<&[i32]> = list.iter().map(|(c, _)| *c).collect();
    let f = solve(&g, &chords(&all), &o);
    let mut at = 0;
    for (chord, want) in list {
        assert_eq!(shape(&g, &f, at, chord.len()), want, "in the progression");
        at += chord.len();
    }
}

#[test]
fn reentrant_ukulele_uses_the_high_g_string() {
    let high = preset("ukulele-high-g").unwrap();
    let f = solve(&high, &[note(G4, 0)], &opts(Style::OpenPosition));
    assert_eq!(f.notes[0].position(), Some(Position { string: 4, fret: 0 }));
    assert!(f.notes[0].alternatives.contains(&Position { string: 2, fret: 3 }));
    let f = solve(&high, &[note(G3, 0)], &opts(Style::OpenPosition));
    assert!(f.notes[0].out_of_range, "G3 is below a high-G ukulele");

    let low = preset("ukulele-low-g").unwrap();
    let f = solve(&low, &line(&[G3, A3, B3, C4]), &opts(Style::OpenPosition));
    assert_eq!(f.notes[0].position(), Some(Position { string: 4, fret: 0 }));
    for p in positions(&f).iter().take(3) {
        assert_eq!(p.string, 4);
    }
}

#[test]
fn eb_standard_matches_standard_a_half_step_up() {
    let std = preset("guitar-standard").unwrap();
    let eb = preset("guitar-eb-standard").unwrap();
    let riff = [40, 43, 45, 40, 43, 46, 45, 40, 43, 45, 43, 40, 52, 55, 57, 59];
    for style in [Style::OpenPosition, Style::AsPlayed, Style::Lead] {
        let a = solve(&std, &line(&riff), &opts(style));
        let lowered: Vec<i32> = riff.iter().map(|p| p - 1).collect();
        let b = solve(&eb, &line(&lowered), &opts(style));
        assert_eq!(positions(&a), positions(&b), "{style:?}");
        let c = solve(&std, &chords(&[&[40, 47, 52, 55, 59, 64], &[45, 52, 57, 60, 64]]), &opts(style));
        let d = solve(&eb, &chords(&[&[39, 46, 51, 54, 58, 63], &[44, 51, 56, 59, 63]]), &opts(style));
        assert_eq!(positions(&c), positions(&d), "{style:?} chords");
    }
}

#[test]
fn capo_keeps_open_shapes_relative_to_the_capo() {
    let g = preset("guitar-standard").unwrap().with_capo(2);
    let list: [(&[i32], &str); 5] = [
        (&[45, 49, 52, 57, 61, 69], "3-2-0-0-0-3"),
        (&[50, 54, 57, 62, 66], "x-3-2-0-1-0"),
        (&[52, 59, 64, 68], "x-x-0-2-3-2"),
        (&[42, 49, 54, 57, 61, 66], "0-2-2-0-0-0"),
        (&[47, 54, 59, 62, 66], "x-0-2-2-1-0"),
    ];
    let all: Vec<&[i32]> = list.iter().map(|(c, _)| *c).collect();
    let f = solve(&g, &chords(&all), &opts(Style::OpenPosition));
    let mut at = 0;
    for (chord, want) in list {
        assert_eq!(shape(&g, &f, at, chord.len()), want);
        at += chord.len();
    }
}

#[test]
fn five_string_bass_plays_low_b_on_string_five() {
    let b = preset("bass-5-standard").unwrap();
    let riff = [23, 23, 25, 26, 23, 28, 26, 23];
    let f = solve(&b, &line(&riff), &opts(Style::AsPlayed));
    for (p, pitch) in positions(&f).iter().zip(&riff) {
        if *pitch < 28 {
            assert_eq!(p.string, 5, "pitch {pitch}");
        }
    }
    let four = preset("bass-4-standard").unwrap();
    let f = assign(&four, &line(&[23, 28]), &Options::default()).unwrap();
    assert!(f.notes[0].out_of_range && !f.notes[1].out_of_range);
}

#[test]
fn a_pin_moves_the_note_and_the_neighbours_stay_playable() {
    let g = preset("guitar-standard").unwrap();
    let phrase = [E4, F4, G4, A4, G4, F4, E4];
    let o = opts(Style::AsPlayed);
    let free = solve(&g, &line(&phrase), &o);
    let pinned_string = if free.notes[3].string == Some(3) { 2 } else { 3 };
    let o = Options { pins: vec![Pin { note: 3, string: pinned_string }], ..o };
    let f = solve(&g, &line(&phrase), &o);
    assert_eq!(f.notes[3].string, Some(pinned_string));
    assert!(f.notes[3].pinned && !f.notes[2].pinned);
    // A pin on a string that cannot sound the pitch is reported, and the note still gets a place.
    let bad = Options { pins: vec![Pin { note: 0, string: 6 }], ..o };
    let f = assign(&g, &line(&[E5]), &bad).unwrap();
    assert!(f.notes[0].position().is_some());
    assert_eq!(check(&g, &line(&[E5]), &f, &bad), vec![Violation::PinNotHonoured { note: 0, string: 6 }]);
}

#[test]
fn a_pinned_chord_note_reflows_the_rest_of_the_chord() {
    let g = preset("guitar-standard").unwrap();
    let c = chords(&[&[48, 52, 55, 60, 64]]);
    // The top E4 moved to string 2 fret 5: C4 can no longer be on string 2.
    let o = Options { pins: vec![Pin { note: 4, string: 2 }], ..opts(Style::OpenPosition) };
    let f = solve(&g, &c, &o);
    assert_eq!(f.notes[4].position(), Some(Position { string: 2, fret: 5 }));
    assert_ne!(f.notes[3].string, Some(2));
}

#[test]
fn a_repeated_phrase_keeps_its_fingering() {
    let g = preset("guitar-standard").unwrap();
    // Once after a passage up the neck, once after one low in open position: on their own, the
    // two contexts pull the riff to different places.
    let riff = [G4, A4, B4, D5, B4, A4];
    let mut pitches = vec![E5, D5, C5, B4];
    pitches.extend(riff);
    pitches.extend([40, 43, 45, 47, 40, 43, 45, 47]);
    pitches.extend(riff);
    for style in [Style::OpenPosition, Style::AsPlayed, Style::Lead] {
        let f = solve(&g, &line(&pitches), &opts(style));
        let p = positions(&f);
        assert_eq!(p[4..10], p[18..24], "{style:?}: {p:?}");
    }
}

#[test]
fn more_notes_than_strings_are_left_unplaced_not_moved() {
    let g = preset("guitar-standard").unwrap();
    let cluster = [40, 45, 50, 55, 59, 64, 67, 71];
    let notes = chords(&[&cluster]);
    let f = assign(&g, &notes, &Options::default()).unwrap();
    let placed = f.notes.iter().filter(|n| n.position().is_some()).count();
    assert_eq!(placed, 6);
    assert!(f.notes.iter().all(|n| !n.out_of_range));
    let v = check(&g, &notes, &f, &Options::default());
    assert_eq!(v.len(), 2);
    assert!(v.iter().all(|v| matches!(v, Violation::NoString { .. })));
}

#[test]
fn doubled_notes_share_one_position() {
    let g = preset("guitar-standard").unwrap();
    let notes = vec![note(E4, 0), note(E4, 0), note(C4, 0)];
    let f = solve(&g, &notes, &Options::default());
    assert_eq!(f.notes[0].position(), f.notes[1].position());
}

#[test]
fn json_round_trip_matches_the_direct_call() {
    let notes = chords(&[&[48, 52, 55, 60, 64]]);
    let o = opts(Style::OpenPosition);
    let req = Request { instrument: InstrumentChoice::Preset { preset: "guitar-standard".into(), capo: 0 }, notes: notes.iter().cloned().map(Into::into).collect(), options: o.clone() };
    let text = solve_json(&serde_json::to_string(&req).unwrap()).unwrap();
    let resp: Response = serde_json::from_str(&text).unwrap();
    let g = preset("guitar-standard").unwrap();
    assert_eq!(resp.fingering, assign(&g, &notes, &o).unwrap());
    assert!(resp.violations.is_empty());

    let hand = r#"{"instrument": {"preset": "ukulele-high-g"}, "notes": [{"pitch": 67, "start": 0, "dur": 24}],
                   "options": {"style": "open-position"}}"#;
    let resp: Response = serde_json::from_str(&solve_json(hand).unwrap()).unwrap();
    assert_eq!(resp.fingering.notes[0].position(), Some(Position { string: 4, fret: 0 }));

    let custom = serde_json::json!({"instrument": g, "notes": [{"pitch": 40, "start": 0, "dur": 24}]});
    let resp: Response = serde_json::from_str(&solve_json(&custom.to_string()).unwrap()).unwrap();
    assert_eq!(resp.fingering.notes[0].position(), Some(Position { string: 6, fret: 0 }));

    assert!(solve_json(r#"{"instrument": {"preset": "banjo"}, "notes": []}"#).is_err());
    assert!(solve_json(r#"{"instrument": {"preset": "guitar-standard"}, "notes": [{"pitch": -2147483648, "start": 0, "dur": 24}]}"#).is_err());
    assert!(solve_json(r#"{"instrument": {"preset": "guitar-standard"}, "notes": [{"pitch": 60, "start": 9223372036854775807, "dur": 24}]}"#).is_err());
    assert!(solve_json(r#"{"instrument": {"preset": "guitar-standard"}, "notes": [], "options": {"tempo_bpm": 0}}"#).is_err());
    assert!(solve_json(r#"{"instrument": {"preset": "guitar-standard"}, "notes": [], "options": {"pins": [{"note": 3, "string": 1}]}}"#).is_err());
}

#[test]
fn json_rejects_unknown_keys_with_a_clear_error() {
    let notes = r#""notes": [{"pitch": 64, "start": 0, "dur": 24}]"#;
    let err = |body: String| solve_json(&body).unwrap_err();

    let e = err(format!(r#"{{"instrument": {{"preset": "guitar-standard", "frets": 5}}, {notes}}}"#));
    assert!(e.contains("instrument preset") && e.contains("frets"), "{e}");
    let e = err(format!(r#"{{"instrument": {{"preset": "guitar-standard"}}, {notes}, "extra": 1}}"#));
    assert!(e.contains("extra"), "{e}");
    let e = err(format!(r#"{{"instrument": {{"preset": "guitar-standard"}}, {notes}, "options": {{"stlye": "lead"}}}}"#));
    assert!(e.contains("stlye"), "{e}");
    let e = err(format!(r#"{{"instrument": {{"preset": "guitar-standard"}}, {notes}, "options": {{"hand": {{"max": 150}}}}}}"#));
    assert!(e.contains("max"), "{e}");
    let e = err(format!(r#"{{"instrument": {{"preset": "guitar-standard"}}, {notes}, "options": {{"pins": [{{"note": 0, "string": 1, "fret": 0}}]}}}}"#));
    assert!(e.contains("fret"), "{e}");

    // A malformed custom instrument names the missing or unknown field.
    let mut g = serde_json::to_value(preset("guitar-standard").unwrap()).unwrap();
    g.as_object_mut().unwrap().remove("frets");
    let e = err(format!(r#"{{"instrument": {g}, {notes}}}"#));
    assert!(e.contains("custom instrument") && e.contains("frets") && !e.contains("untagged"), "{e}");
    let mut g = serde_json::to_value(preset("guitar-standard").unwrap()).unwrap();
    g["tuning"]["strings"][0]["open"] = 64.into();
    let e = err(format!(r#"{{"instrument": {g}, {notes}}}"#));
    assert!(e.contains("custom instrument") && e.contains("open"), "{e}");
    let e = err(format!(r#"{{"instrument": "guitar-standard", {notes}}}"#));
    assert!(e.contains("preset"), "{e}");
}

#[test]
fn json_accepts_partial_hand_limits() {
    let body = r#"{"instrument": {"preset": "guitar-standard"}, "notes": [{"pitch": 64, "start": 0, "dur": 24}],
                   "options": {"hand": {"max_mm": 160}}}"#;
    let req: Request = serde_json::from_str(body).unwrap();
    assert_eq!(req.options.hand.max_mm, 160.0);
    assert_eq!(req.options.hand.comfortable_mm, target_fretted::HandLimits::default().comfortable_mm);
    assert!(solve_json(body).is_ok());
}
