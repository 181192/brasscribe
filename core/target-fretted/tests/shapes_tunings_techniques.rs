//! Chord shapes, tuning suggestion and playing techniques.

use brasscribe_core::model::Note;
use target_fretted::json::{solve_json, Response};
use target_fretted::{assign, assign_with_techniques, check, check_with_techniques, preset, suggest_tunings, Fingering, Instrument, Options, Position, Style, Technique, Violation};

const EIGHTH: i64 = 12;

fn note(pitch: i32, start: i64) -> Note {
    Note::new(pitch, start, EIGHTH, 1.0, Vec::new())
}

fn line(pitches: &[i32]) -> Vec<Note> {
    pitches.iter().enumerate().map(|(i, &p)| note(p, i as i64 * EIGHTH)).collect()
}

fn chord(pitches: &[i32]) -> Vec<Note> {
    pitches.iter().map(|&p| note(p, 0)).collect()
}

fn opts(style: Style) -> Options {
    Options { style, ..Options::default() }
}

/// One technique list per note, from (note, technique) marks.
fn marks(notes: &[Note], marks: &[(usize, Technique)]) -> Vec<Vec<Technique>> {
    let mut out = vec![Vec::new(); notes.len()];
    for &(i, t) in marks {
        out[i].push(t);
    }
    out
}

/// Solve in open-position style with techniques, asserting no violations.
fn solve_t(inst: &Instrument, notes: &[Note], m: &[(usize, Technique)]) -> Fingering {
    let o = opts(Style::OpenPosition);
    let t = marks(notes, m);
    let f = assign_with_techniques(inst, notes, &t, &o).unwrap();
    let v = check_with_techniques(inst, notes, &t, &f, &o);
    assert!(v.is_empty(), "violations {v:?} in {:?}", f.notes.iter().map(|n| n.position()).collect::<Vec<_>>());
    f
}

fn solve(inst: &Instrument, notes: &[Note], o: &Options) -> Fingering {
    let f = assign(inst, notes, o).unwrap();
    let v = check(inst, notes, &f, o);
    assert!(v.is_empty(), "violations {v:?} in {:?}", f.notes.iter().map(|n| n.position()).collect::<Vec<_>>());
    f
}

/// Frets low string first, `x` = not played.
fn shape(inst: &Instrument, f: &Fingering) -> String {
    let mut frets = vec!["x".to_string(); inst.string_count()];
    for n in &f.notes {
        let p = n.position().unwrap();
        frets[p.string as usize - 1] = p.fret.to_string();
    }
    frets.reverse();
    frets.join("-")
}

const ALL_STYLES: [Style; 3] = [Style::OpenPosition, Style::AsPlayed, Style::Lead];

#[test]
fn power_chords_take_the_standard_shape() {
    let g = preset("guitar-standard").unwrap();
    let drop_d = preset("guitar-drop-d").unwrap();
    for style in ALL_STYLES {
        assert_eq!(shape(&g, &solve(&g, &chord(&[48, 55, 60]), &opts(style))), "x-3-5-5-x-x", "C5 {style:?}");
        assert_eq!(shape(&g, &solve(&g, &chord(&[48, 55]), &opts(style))), "x-3-5-x-x-x", "C5 dyad {style:?}");
        // Drop D: the one-finger shape.
        assert_eq!(shape(&drop_d, &solve(&drop_d, &chord(&[43, 50, 55]), &opts(style))), "5-5-5-x-x-x", "G5 {style:?}");
    }
    // A riff of power chords keeps the shape on every chord.
    let riff: Vec<Note> = [[40, 47, 52], [43, 50, 55], [45, 52, 57], [43, 50, 55]]
        .iter()
        .enumerate()
        .flat_map(|(i, c)| c.iter().map(move |&p| note(p, i as i64 * 24)))
        .collect();
    let f = solve(&g, &riff, &opts(Style::AsPlayed));
    for c in f.notes.chunks(3) {
        let strings: Vec<u8> = c.iter().map(|n| n.string.unwrap()).collect();
        assert_eq!(strings[0], strings[1] + 1, "{strings:?}");
        assert_eq!(strings[1], strings[2] + 1, "{strings:?}");
    }
}

#[test]
fn strummed_ukulele_chords_fill_every_string() {
    for id in ["ukulele-high-g", "ukulele-low-g"] {
        let uke = preset(id).unwrap();
        let g4 = uke.open_pitch(4).unwrap();
        let cases: [(&str, [i32; 4], &str); 4] = [
            ("G", [g4, 62, 67, 71], "0-2-3-2"),
            ("Am", [g4 + 2, 60, 64, 69], "2-0-0-0"),
            ("F", [g4 + 2, 60, 65, 69], "2-0-1-0"),
            ("C", [g4, 60, 64, 72], "0-0-0-3"),
        ];
        for (name, pitches, want) in cases {
            for style in [Style::OpenPosition, Style::AsPlayed] {
                let f = solve(&uke, &chord(&pitches), &opts(style));
                assert_eq!(shape(&uke, &f), want, "{id} {name} {style:?}");
            }
        }
    }
    // With a capo the shapes keep their frets.
    let uke = preset("ukulele-high-g").unwrap().with_capo(2);
    let f = solve(&uke, &chord(&[69, 64, 69, 73]), &opts(Style::OpenPosition));
    assert_eq!(shape(&uke, &f), "0-2-3-2");
}

#[test]
fn strummed_mandolin_chords_take_the_open_shape() {
    let m = preset("mandolin").unwrap();
    let f = solve(&m, &chord(&[55, 62, 71, 79]), &opts(Style::OpenPosition));
    assert_eq!(shape(&m, &f), "0-0-2-3");
    let f = solve(&m, &chord(&[57, 62, 69, 78]), &opts(Style::OpenPosition));
    assert_eq!(shape(&m, &f), "2-0-0-2");
}

#[test]
fn doubled_notes_outside_a_shape_still_share_a_position() {
    let g = preset("guitar-standard").unwrap();
    let f = solve(&g, &chord(&[64, 64, 60]), &Options::default());
    assert_eq!(f.notes[0].position(), f.notes[1].position());
}

#[test]
fn a_drop_d_bass_line_is_flagged_in_standard_and_drop_d_is_suggested() {
    let riff = [26, 33, 38, 26, 31, 33, 36, 38, 26, 26];
    let notes = line(&riff);
    let standard = preset("bass-4-standard").unwrap();
    let f = assign(&standard, &notes, &Options::default()).unwrap();
    assert!(f.notes[0].out_of_range, "D1 is below a standard bass");

    let fits = suggest_tunings("bass-4", &notes, 0);
    assert_eq!(fits[0].preset, "bass-4-drop-d", "{fits:?}");
    assert_eq!(fits[0].out_of_range, 0);
    assert_eq!(fits.last().unwrap().out_of_range, 4, "{fits:?}");

    let drop_d = preset(&fits[0].preset).unwrap();
    let f = solve(&drop_d, &notes, &Options::default());
    assert!(f.notes.iter().all(|n| !n.out_of_range));
    assert_eq!(f.notes[0].position(), Some(Position { string: 4, fret: 0 }));

    // The same through JSON: the suggestion comes with the result.
    let body = serde_json::json!({"instrument": {"preset": "bass-4-standard"}, "notes": notes});
    let resp: Response = serde_json::from_str(&solve_json(&body.to_string()).unwrap()).unwrap();
    assert_eq!(resp.tuning_suggestions[0].preset, "bass-4-drop-d");
    assert_eq!(resp.tuning_suggestions[0].tuning, "Drop D");
}

#[test]
fn a_down_tuned_riff_ranks_its_own_tuning_before_a_drop_tuning() {
    // An E-flat riff reaches below standard. Drop D is closer to standard and fits too, but the
    // riff is built on E-flat, the lowest string of E-flat standard.
    let guitar = line(&[39, 46, 51, 44, 42]);
    let fits = suggest_tunings("guitar", &guitar, 0);
    assert_eq!(fits[0].preset, "guitar-eb-standard", "{fits:?}");
    assert!(fits[0].low_string_fits);
    let bass = line(&[27, 34, 39, 32, 30, 27]);
    assert_eq!(suggest_tunings("bass-4", &bass, 0)[0].preset, "bass-4-eb-standard");
    let drop_d = line(&[26, 33, 38, 26, 31, 33, 36, 38, 26, 26]);
    assert_eq!(suggest_tunings("bass-4", &drop_d, 0)[0].preset, "bass-4-drop-d");
    let guitar_d = line(&[38, 45, 50, 38, 43, 45]);
    assert_eq!(suggest_tunings("guitar", &guitar_d, 0)[0].preset, "guitar-drop-d");
}

#[test]
fn ordinary_material_stays_in_standard_tuning() {
    // Ode to Joy, lowest C4.
    let ode = line(&[64, 64, 65, 67, 67, 65, 64, 62, 60, 60, 62, 64, 64, 62, 62]);
    // A C major scale from C3, and a melody down to D3.
    let c_scale = line(&[48, 50, 52, 53, 55, 57, 59, 60]);
    let to_d3 = line(&[57, 55, 53, 52, 50, 52, 55]);
    for (name, notes) in [("ode", &ode), ("C scale", &c_scale), ("to D3", &to_d3)] {
        let fits = suggest_tunings("guitar", notes, 0);
        assert_eq!(fits[0].preset, "guitar-standard", "{name}: {fits:?}");
    }
    // A bass line down to D2.
    let bass = line(&[38, 43, 45, 47, 50, 45, 43, 38]);
    assert_eq!(suggest_tunings("bass-4", &bass, 0)[0].preset, "bass-4-standard");
    // A guitar line on D2 is drop D.
    let drop_d = line(&[38, 38, 45, 50, 38, 48, 50]);
    assert_eq!(suggest_tunings("guitar", &drop_d, 0)[0].preset, "guitar-drop-d");
}

#[test]
fn tuning_suggestion_prefers_standard_when_it_fits() {
    let notes = line(&[28, 31, 33, 35, 36, 38, 40, 43]);
    assert_eq!(suggest_tunings("bass-4", &notes, 0)[0].preset, "bass-4-standard");
    let low_b = line(&[23, 28, 30, 31]);
    assert_eq!(suggest_tunings("bass-4", &low_b, 0)[0].preset, "bass-4-bead");
    assert_eq!(suggest_tunings("bass-5", &low_b, 0)[0].preset, "bass-5-standard");
    let guitar_d = line(&[38, 45, 50, 38, 43, 45]);
    assert_eq!(suggest_tunings("guitar", &guitar_d, 0)[0].preset, "guitar-drop-d");
    let guitar_b = line(&[35, 42, 47, 35]);
    assert_eq!(suggest_tunings("guitar", &guitar_b, 0)[0].preset, "guitar-drop-b");
    let seven_bb = line(&[34, 39, 44, 46]);
    // Standard material stays in standard tuning.
    let e_minor = line(&[40, 43, 45, 47, 50, 52, 55, 57]);
    assert_eq!(suggest_tunings("guitar", &e_minor, 0)[0].preset, "guitar-standard");
    assert_eq!(suggest_tunings("guitar-7", &seven_bb, 0)[0].preset, "guitar-7-eb-standard");
    assert!(suggest_tunings("banjo", &seven_bb, 0).is_empty());
    // Every preset of the family is ranked once.
    assert_eq!(suggest_tunings("guitar", &guitar_d, 0).len(), target_fretted::family_presets("guitar").len());
}

#[test]
fn hammer_ons_slides_and_bends_stay_on_the_string() {
    let g = preset("guitar-standard").unwrap();
    // D4 then E4: in open position E4 is the open first string, unless it is hammered on.
    let notes = line(&[62, 64]);
    let free = solve(&g, &notes, &opts(Style::OpenPosition));
    assert_eq!(free.notes[1].position(), Some(Position { string: 1, fret: 0 }));
    for t in [Technique::HammerOn, Technique::Slide] {
        let f = solve_t(&g, &notes, &[(1, t)]);
        assert_eq!(f.notes[0].string, f.notes[1].string, "{t:?}");
        assert!(f.notes[1].fret.unwrap() > 0);
    }
    // A pull-off back down keeps the string too.
    let notes = line(&[64, 62]);
    let f = solve_t(&g, &notes, &[(1, Technique::PullOff)]);
    assert_eq!(f.notes[0].string, f.notes[1].string);

    // A bend needs a fretted note: B3 is otherwise the open second string.
    let notes = line(&[57, 59]);
    assert_eq!(solve(&g, &notes, &opts(Style::OpenPosition)).notes[1].fret, Some(0));
    let f = solve_t(&g, &notes, &[(1, Technique::Bend)]);
    assert!(f.notes[1].fret.unwrap() > 0);
    assert_eq!(f.notes[0].string, f.notes[1].string);
    // Vibrato adds no constraint.
    assert_eq!(solve_t(&g, &notes, &[(1, Technique::Vibrato)]).notes[1].fret, Some(0));
}

#[test]
fn a_bent_note_can_also_ring() {
    let g = preset("guitar-standard").unwrap();
    // A3, then B3 bent and let ring for a bar, then E4 while it rings.
    let notes = vec![note(57, 0), Note::new(59, 12, 96, 1.0, Vec::new()), note(64, 36)];
    let f = solve_t(&g, &notes, &[(1, Technique::Bend), (1, Technique::LetRing)]);
    assert!(f.notes[1].fret.unwrap() > 0);
    assert_eq!(f.notes[0].string, f.notes[1].string);
    assert_ne!(f.notes[2].string, f.notes[1].string);
}

#[test]
fn legato_beyond_reach_is_reported_not_honoured() {
    let g = preset("guitar-standard").unwrap();
    // A hammer-on of a seventh (10 frets) and a slide of an octave and a half (18 frets).
    for (pitches, t, frets) in [([52, 62], Technique::HammerOn, 10), ([52, 70], Technique::Slide, 18)] {
        let notes = line(&pitches);
        let tech = marks(&notes, &[(1, t)]);
        let o = opts(Style::OpenPosition);
        let f = assign_with_techniques(&g, &notes, &tech, &o).unwrap();
        assert_eq!(check_with_techniques(&g, &notes, &tech, &f, &o), vec![Violation::TechniqueReach { note: 1, previous: 0, frets }], "{t:?}");
    }
    // Within reach: a slide of 7 frets and a hammer-on of 5.
    for (pitches, t) in [([52, 59], Technique::Slide), ([52, 57], Technique::HammerOn)] {
        let f = solve_t(&g, &line(&pitches), &[(1, t)]);
        assert_eq!(f.notes[0].string, f.notes[1].string, "{t:?}");
    }
}

#[test]
fn let_ring_reserves_its_string_until_it_ends() {
    let g = preset("guitar-standard").unwrap();
    // G3 rings for a bar; A3 would otherwise sit on the same (third) string.
    let mut notes = vec![Note::new(55, 0, 96, 1.0, Vec::new())];
    notes.push(note(57, 24));
    let free = solve(&g, &notes, &opts(Style::OpenPosition));
    assert_eq!(free.notes[1].string, Some(3));
    let ring = [(0, Technique::LetRing)];
    let f = solve_t(&g, &notes, &ring);
    assert_ne!(f.notes[1].string, f.notes[0].string);

    // Further away than the next onset, too.
    let mut notes = vec![Note::new(55, 0, 96, 1.0, Vec::new())];
    notes.extend([note(64, 12), note(60, 24), note(57, 36)]);
    let f = solve_t(&g, &notes, &ring);
    assert!(f.notes[1..].iter().all(|n| n.string != f.notes[0].string), "{:?}", f.notes.iter().map(|n| n.position()).collect::<Vec<_>>());
    // After the ringing note ends, its string is free again.
    let mut notes = vec![Note::new(55, 0, 12, 1.0, Vec::new())];
    notes.push(note(57, 24));
    assert_eq!(solve_t(&g, &notes, &ring).notes[1].string, Some(3));
}

#[test]
fn the_check_reports_broken_technique_constraints() {
    let g = preset("guitar-standard").unwrap();
    let o = opts(Style::OpenPosition);
    let notes = line(&[62, 64]);
    let tech = marks(&notes, &[(1, Technique::HammerOn)]);
    let mut f = solve_t(&g, &notes, &[(1, Technique::HammerOn)]);
    f.notes[1].string = Some(1);
    f.notes[1].fret = Some(0);
    assert_eq!(check_with_techniques(&g, &notes, &tech, &f, &o), vec![Violation::TechniqueString { note: 1, previous: 0 }]);

    let moved = vec![note(59, 0), note(59, EIGHTH)];
    let tech = marks(&moved, &[(1, Technique::Bend)]);
    let mut f = assign(&g, &moved, &o).unwrap();
    for n in f.notes.iter_mut() {
        n.string = Some(2);
        n.fret = Some(0);
    }
    assert!(check_with_techniques(&g, &moved, &tech, &f, &o).contains(&Violation::BendOnOpenString { note: 1 }));

    let notes = vec![Note::new(55, 0, 96, 1.0, Vec::new()), note(57, 24)];
    let tech = marks(&notes, &[(0, Technique::LetRing)]);
    let mut f = assign(&g, &notes, &o).unwrap();
    f.notes[0].string = Some(3);
    f.notes[0].fret = Some(0);
    f.notes[1].string = Some(3);
    f.notes[1].fret = Some(2);
    assert_eq!(check_with_techniques(&g, &notes, &tech, &f, &o), vec![Violation::RingCut { string: 3, ringing: 0, note: 1 }]);
    // Without the techniques the same fingering is fine.
    assert!(check(&g, &notes, &f, &o).is_empty());
    // A technique list of the wrong length is refused.
    assert!(assign_with_techniques(&g, &notes, &[Vec::new()], &o).is_err());
}

#[test]
fn techniques_come_in_on_json_notes() {
    let body = r#"{"instrument": {"preset": "guitar-standard"}, "options": {"style": "open-position"},
                   "notes": [{"pitch": 62, "start": 0, "dur": 12}, {"pitch": 64, "start": 12, "dur": 12, "techniques": ["hammer-on"]}]}"#;
    let resp: Response = serde_json::from_str(&solve_json(body).unwrap()).unwrap();
    assert_eq!(resp.fingering.notes[0].string, resp.fingering.notes[1].string);
    assert!(resp.violations.is_empty());
    let both = r#"{"instrument": {"preset": "guitar-standard"},
                   "notes": [{"pitch": 57, "start": 0, "dur": 12}, {"pitch": 59, "start": 12, "dur": 96, "techniques": ["bend", "let-ring"]}]}"#;
    let resp: Response = serde_json::from_str(&solve_json(both).unwrap()).unwrap();
    assert!(resp.fingering.notes[1].fret.unwrap() > 0);
    for bad in [
        r#"{"instrument": {"preset": "guitar-standard"}, "notes": [{"pitch": 62, "start": 0, "dur": 12, "techniques": ["tap"]}]}"#,
        r#"{"instrument": {"preset": "guitar-standard"}, "notes": [{"pitch": 62, "start": 0, "dur": 12, "techniques": ["hammer_on"]}]}"#,
        r#"{"instrument": {"preset": "guitar-standard"}, "notes": [{"pitch": 62, "start": 0, "dur": 12, "techniques": "bend"}]}"#,
        r#"{"instrument": {"preset": "guitar-standard"}, "notes": [], "options": {"techniques": [{"note": 0, "technique": "bend"}]}}"#,
    ] {
        assert!(solve_json(bad).is_err(), "{bad}");
    }
}

#[test]
fn a_pentatonic_lick_stays_in_its_box() {
    let g = preset("guitar-standard").unwrap();
    // E minor pentatonic at the twelfth fret. Every note also exists lower on the neck, and the
    // descending runs used to slide down the first string towards the nut.
    let licks: [&[i32]; 3] = [
        &[76, 74, 71, 67, 69, 71, 74, 76, 79, 76],
        &[79, 76, 74, 71, 69, 67, 64, 62, 59, 57, 55, 52],
        &[76, 79, 76, 74, 71, 74, 71, 69, 67, 69, 67, 64],
    ];
    for lick in licks {
        for style in [Style::AsPlayed, Style::Lead] {
            let f = solve(&g, &line(lick), &opts(style));
            for n in &f.notes {
                let fret = n.fret.unwrap();
                assert!((12..=15).contains(&fret), "{style:?}: {:?}", f.notes.iter().map(|n| n.position().unwrap()).collect::<Vec<_>>());
            }
        }
    }
}
