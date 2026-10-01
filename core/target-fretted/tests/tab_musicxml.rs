//! Tablature as MusicXML: staff set-up, notes, rhythm, techniques and doubt marks.

use brasscribe_core::model::Note;
use roxmltree::{Document, Node, ParsingOptions};
use target_fretted::json::tab_musicxml_json;
use target_fretted::{assign, assign_with_techniques, preset, write_tab_musicxml, CapoEncoding, Fingering, Instrument, Layout, NotationClef, NotePlace, Options, TabOptions, TabScore, Technique, PRESET_IDS};

const QUARTER: i64 = 24;
const EIGHTH: i64 = 12;
const BAR: i64 = 96;

fn note(pitch: i32, start: i64, dur: i64) -> Note {
    Note::new(pitch, start, dur, 1.0, Vec::new())
}

fn doubtful(pitch: i32, start: i64, dur: i64, confidence: f64) -> Note {
    Note::new(pitch, start, dur, confidence, Vec::new())
}

fn layout(layout: Layout) -> TabOptions {
    TabOptions { layout, ..TabOptions::default() }
}

/// Solve and write, with one technique list per note (or none).
fn tab_with(inst: &Instrument, notes: &[Note], techniques: &[Vec<Technique>], opts: &TabOptions) -> String {
    let fingering = assign_with_techniques(inst, notes, techniques, &Options::default()).unwrap();
    write_tab_musicxml(&TabScore::new("Test", inst, notes, techniques, &fingering).unwrap(), opts)
}

fn tab(inst: &Instrument, notes: &[Note], opts: &TabOptions) -> String {
    tab_with(inst, notes, &[], opts)
}

fn parse(xml: &str) -> Document<'_> {
    Document::parse_with_options(xml, ParsingOptions { allow_dtd: true, ..Default::default() }).unwrap_or_else(|e| panic!("not well-formed: {e}\n{xml}"))
}

fn all<'a>(doc: &'a Document, name: &'static str) -> Vec<Node<'a, 'a>> {
    doc.descendants().filter(|n| n.has_tag_name(name)).collect()
}

fn child<'a>(n: Node<'a, 'a>, name: &str) -> Option<Node<'a, 'a>> {
    n.children().find(|c| c.has_tag_name(name))
}

fn descendant<'a>(n: Node<'a, 'a>, name: &str) -> Option<Node<'a, 'a>> {
    n.descendants().find(|c| c.has_tag_name(name))
}

fn text<'a>(n: Node<'a, 'a>, name: &str) -> Option<&'a str> {
    descendant(n, name).and_then(|c| c.text())
}

/// MIDI pitch of a `<note>`; None for a rest.
fn midi(n: Node) -> Option<i32> {
    let p = child(n, "pitch")?;
    let step = match text(p, "step")? {
        "C" => 0,
        "D" => 2,
        "E" => 4,
        "F" => 5,
        "G" => 7,
        "A" => 9,
        "B" => 11,
        other => panic!("step {other}"),
    };
    let alter: i32 = text(p, "alter").map_or(0, |a| a.parse().unwrap());
    let octave: i32 = text(p, "octave")?.parse().unwrap();
    Some(12 * (octave + 1) + step + alter)
}

/// (line, MIDI pitch) of every `<staff-tuning>`.
fn staff_tuning(doc: &Document) -> Vec<(u32, i32)> {
    all(doc, "staff-tuning")
        .into_iter()
        .map(|t| {
            let step = match text(t, "tuning-step").unwrap() {
                "C" => 0,
                "D" => 2,
                "E" => 4,
                "F" => 5,
                "G" => 7,
                "A" => 9,
                "B" => 11,
                other => panic!("step {other}"),
            };
            let alter: i32 = text(t, "tuning-alter").map_or(0, |a| a.parse().unwrap());
            let octave: i32 = text(t, "tuning-octave").unwrap().parse().unwrap();
            (t.attribute("line").unwrap().parse().unwrap(), 12 * (octave + 1) + step + alter)
        })
        .collect()
}

/// (string, fret) of a `<note>`.
fn place(n: Node) -> Option<(u8, u8)> {
    let t = descendant(n, "technical")?;
    Some((text(t, "string")?.parse().unwrap(), text(t, "fret")?.parse().unwrap()))
}

fn staff_of<'a>(n: Node<'a, 'a>) -> Option<&'a str> {
    child(n, "staff").and_then(|s| s.text())
}

fn words<'a>(doc: &'a Document) -> Vec<&'a str> {
    all(doc, "words").into_iter().filter_map(|w| w.text()).collect()
}

/// (written type, whether it fills the measure) of each rest in a measure.
fn rests<'a>(m: Node<'a, 'a>) -> Vec<(Option<&'a str>, Option<&'a str>)> {
    m.children().filter(|n| child(*n, "rest").is_some()).map(|n| (text(n, "type"), child(n, "rest").unwrap().attribute("measure"))).collect()
}

/// Types of the `<tie>` elements of a note.
fn ties<'a>(n: Node<'a, 'a>) -> Vec<&'a str> {
    n.children().filter(|c| c.has_tag_name("tie")).map(|t| t.attribute("type").unwrap()).collect()
}

/// Types of the `<tied>` elements of a note.
fn tied<'a>(n: Node<'a, 'a>) -> Vec<&'a str> {
    n.descendants().filter(|c| c.has_tag_name("tied")).map(|t| t.attribute("type").unwrap()).collect()
}

/// Notes (not rests) of a document.
fn sounding<'a>(doc: &'a Document) -> Vec<Node<'a, 'a>> {
    all(doc, "note").into_iter().filter(|n| child(*n, "pitch").is_some()).collect()
}

/// Every measure holds exactly its length on every staff: durations, less the `<backup>`s.
fn assert_measures_full(doc: &Document, bar: i64) {
    let measures = all(doc, "measure");
    assert!(!measures.is_empty());
    for m in measures {
        let mut at = 0;
        let mut ends = Vec::new();
        for c in m.children().filter(|c| c.is_element()) {
            let dur: i64 = child(c, "duration").and_then(|d| d.text()).map_or(0, |d| d.parse().unwrap());
            match c.tag_name().name() {
                "note" if child(c, "chord").is_none() => at += dur,
                "backup" => {
                    ends.push(at);
                    at -= dur;
                    assert_eq!(at, 0, "a backup returns to the start of the measure");
                }
                _ => {}
            }
        }
        ends.push(at);
        let expected = if m.attribute("implicit") == Some("yes") { ends[0] } else { bar };
        assert!(ends.iter().all(|&e| e == expected), "measure {} holds {ends:?}, not {expected}", m.attribute("number").unwrap());
    }
}

// --- the tab staff ---

#[test]
fn staff_tuning_lines_count_from_the_lowest_line() {
    // Line 1 is the bottom tab line: the last string of the tuning.
    let cases: &[(&str, &[i32])] = &[
        ("guitar-standard", &[40, 45, 50, 55, 59, 64]),
        ("guitar-drop-d", &[38, 45, 50, 55, 59, 64]),
        ("bass-4-standard", &[28, 33, 38, 43]),
        ("bass-5-standard", &[23, 28, 33, 38, 43]),
        // Re-entrant: the bottom line is the high G, above the C on line 2.
        ("ukulele-high-g", &[67, 60, 64, 69]),
        ("ukulele-low-g", &[55, 60, 64, 69]),
        ("mandolin", &[55, 62, 69, 76]),
    ];
    for (id, lines) in cases {
        let inst = preset(id).unwrap();
        for l in [Layout::Tab, Layout::TabAndNotation] {
            let xml = tab(&inst, &[note(inst.range().0 + 5, 0, QUARTER)], &layout(l));
            let doc = parse(&xml);
            let details = all(&doc, "staff-details");
            assert_eq!(details.len(), 1, "{id}");
            assert_eq!(text(details[0], "staff-lines"), Some(lines.len().to_string().as_str()), "{id}");
            let expected: Vec<(u32, i32)> = lines.iter().enumerate().map(|(i, &p)| (i as u32 + 1, p)).collect();
            assert_eq!(staff_tuning(&doc), expected, "{id}");
            // The same thing said from the instrument: line k is string n + 1 - k.
            let n = inst.string_count();
            for (line, pitch) in staff_tuning(&doc) {
                assert_eq!(pitch, inst.tuning.strings[n - line as usize].open_pitch, "{id} line {line}");
            }
            assert!(descendant(details[0], "capo").is_none(), "{id}: no capo element without a capo");
        }
    }
}

#[test]
fn every_preset_has_as_many_lines_as_strings() {
    for id in PRESET_IDS {
        let inst = preset(id).unwrap();
        let xml = tab(&inst, &[note(inst.range().0 + 7, 0, QUARTER)], &layout(Layout::Tab));
        let doc = parse(&xml);
        assert_eq!(text(doc.root_element(), "staff-lines").unwrap().parse::<usize>().unwrap(), inst.string_count(), "{id}");
        assert_eq!(all(&doc, "staff-tuning").len(), inst.string_count(), "{id}");
        assert_eq!(text(doc.root_element(), "part-name"), Some(inst.name.as_str()), "{id}");
    }
}

#[test]
fn flat_tunings_are_named_with_flats() {
    let xml = tab(&preset("guitar-eb-standard").unwrap(), &[note(51, 0, QUARTER)], &layout(Layout::Tab));
    let doc = parse(&xml);
    let bottom = all(&doc, "staff-tuning")[0];
    assert_eq!((text(bottom, "tuning-step"), text(bottom, "tuning-alter"), text(bottom, "tuning-octave")), (Some("E"), Some("-1"), Some("2")));
    assert!(words(&doc).contains(&"E\u{266d} standard: E\u{266d} A\u{266d} D\u{266d} G\u{266d} B\u{266d} E\u{266d}"));
    // Drop B has sharps.
    let xml = tab(&preset("guitar-drop-b").unwrap(), &[note(51, 0, QUARTER)], &layout(Layout::Tab));
    assert!(words(&parse(&xml)).contains(&"Drop B: B F\u{266f} B E G\u{266f} C\u{266f}"));
}

#[test]
fn notes_carry_sounding_pitch_string_and_fret() {
    let inst = preset("guitar-standard").unwrap();
    let notes = [note(40, 0, QUARTER), note(48, 24, QUARTER), note(64, 48, QUARTER), note(69, 72, QUARTER)];
    let fingering = assign(&inst, &notes, &Options::default()).unwrap();
    let xml = write_tab_musicxml(&TabScore::new("Test", &inst, &notes, &[], &fingering).unwrap(), &layout(Layout::Tab));
    let doc = parse(&xml);
    let written = sounding(&doc);
    assert_eq!(written.len(), notes.len());
    for ((w, n), f) in written.iter().zip(&notes).zip(&fingering.notes) {
        assert_eq!(midi(*w), Some(n.pitch));
        assert_eq!(place(*w), Some((f.string.unwrap(), f.fret.unwrap())));
        assert_eq!(staff_of(*w), None, "a single staff has no staff numbers");
    }
    let clefs = all(&doc, "clef");
    assert_eq!(clefs.len(), 1);
    assert_eq!(text(clefs[0], "sign"), Some("TAB"));
    assert!(all(&doc, "staves").is_empty());
}

#[test]
fn capo_is_an_element_with_frets_relative_to_it() {
    let inst = preset("guitar-standard").unwrap().with_capo(3);
    // G2 is the capo'd low string: fret 0.
    let notes = [note(43, 0, QUARTER), note(45, 24, QUARTER)];
    let xml = tab(&inst, &notes, &layout(Layout::Tab));
    let doc = parse(&xml);
    assert_eq!(text(doc.root_element(), "capo"), Some("3"));
    // The tuning is the one without the capo.
    assert_eq!(staff_tuning(&doc)[0], (1, 40));
    let written = sounding(&doc);
    assert_eq!(place(written[0]), Some((6, 0)));
    assert_eq!(place(written[1]), Some((6, 2)));
    assert_eq!(midi(written[0]), Some(43), "the pitch is the sounding one");
    assert!(words(&doc).contains(&"Standard: E A D G B E, Capo 3"));
    // staff-details children come in schema order: lines, tunings, capo.
    let details = all(&doc, "staff-details")[0];
    let order: Vec<&str> = details.children().filter(|c| c.is_element()).map(|c| c.tag_name().name()).collect();
    assert_eq!(order.first(), Some(&"staff-lines"));
    assert_eq!(order.last(), Some(&"capo"));
}

#[test]
fn capo_can_be_written_into_the_tuning() {
    let inst = preset("guitar-standard").unwrap().with_capo(3);
    let opts = TabOptions { layout: Layout::Tab, capo: CapoEncoding::Tuning, ..TabOptions::default() };
    let xml = tab(&inst, &[note(43, 0, QUARTER), note(58, 24, QUARTER)], &opts);
    let doc = parse(&xml);
    assert!(all(&doc, "capo").is_empty());
    assert_eq!(staff_tuning(&doc), vec![(1, 43), (2, 48), (3, 53), (4, 58), (5, 62), (6, 67)]);
    let b_flat = all(&doc, "staff-tuning")[3];
    assert_eq!((text(b_flat, "tuning-step"), text(b_flat, "tuning-alter")), (Some("B"), Some("-1")));
    assert_eq!(place(sounding(&doc)[0]), Some((6, 0)));
    assert_eq!(place(sounding(&doc)[1]), Some((3, 0)));
    assert!(words(&doc).contains(&"Standard: E A D G B E, Capo 3"), "the header still names the capo");
}

// --- layouts ---

#[test]
fn tab_and_notation_is_one_part_with_two_staves() {
    let inst = preset("guitar-standard").unwrap();
    let notes = [note(52, 0, EIGHTH), note(55, 12, EIGHTH), note(59, 24, QUARTER), note(52, 48, 48), note(59, 48, 48)];
    let xml = tab(&inst, &notes, &layout(Layout::TabAndNotation));
    let doc = parse(&xml);
    assert_eq!(all(&doc, "part").len(), 1);
    assert_eq!(text(doc.root_element(), "staves"), Some("2"));
    let clefs = all(&doc, "clef");
    assert_eq!(clefs.iter().map(|c| (c.attribute("number"), text(*c, "sign"))).collect::<Vec<_>>(), vec![(Some("1"), Some("G")), (Some("2"), Some("TAB"))]);
    assert_eq!(all(&doc, "staff-details")[0].attribute("number"), Some("2"));

    let on = |staff: &str| -> Vec<Node> { sounding(&doc).into_iter().filter(|n| staff_of(*n) == Some(staff)).collect() };
    let (upper, lower) = (on("1"), on("2"));
    assert_eq!(upper.len(), notes.len());
    assert_eq!(upper.iter().map(|n| midi(*n)).collect::<Vec<_>>(), lower.iter().map(|n| midi(*n)).collect::<Vec<_>>(), "the same notes on both staves");
    assert!(upper.iter().all(|n| place(*n).is_none()), "string and fret only on the tab staff");
    assert!(lower.iter().all(|n| place(*n).is_some()));
    assert!(all(&doc, "note").iter().all(|n| staff_of(*n).is_some()), "every note and rest names its staff");
    assert!(upper.iter().all(|n| text(*n, "voice") == Some("1")) && lower.iter().all(|n| text(*n, "voice") == Some("5")));
    // Notation first, then back to the start of the bar for the tab.
    assert_eq!(all(&doc, "backup").len(), 1);
    assert_eq!(text(all(&doc, "backup")[0], "duration"), Some("96"));
    // Rhythm is on the notation staff: beams there, none under the tab.
    assert!(upper.iter().any(|n| child(*n, "beam").is_some()));
    assert!(lower.iter().all(|n| child(*n, "beam").is_none() && text(*n, "stem") == Some("none")));
    assert_measures_full(&doc, BAR);
}

#[test]
fn tab_alone_keeps_the_rhythm() {
    let inst = preset("bass-4-standard").unwrap();
    // Two eighths, a quarter, a dotted eighth and a 16th, two 16ths and an eighth; then a dotted half.
    let notes = [note(28, 0, EIGHTH), note(31, 12, EIGHTH), note(33, 24, QUARTER), note(35, 48, 18), note(36, 66, 6), note(38, 72, 6), note(36, 78, 6), note(35, 84, EIGHTH), note(40, 96, 72)];
    let xml = tab(&inst, &notes, &layout(Layout::Tab));
    let doc = parse(&xml);
    let written: Vec<Node> = all(&doc, "note");
    let types: Vec<(Option<&str>, usize, bool)> = written.iter().map(|n| (text(*n, "type"), n.children().filter(|c| c.has_tag_name("dot")).count(), child(*n, "rest").is_some())).collect();
    assert_eq!(
        types,
        [
            (Some("eighth"), 0, false),
            (Some("eighth"), 0, false),
            (Some("quarter"), 0, false),
            (Some("eighth"), 1, false),
            (Some("16th"), 0, false),
            (Some("16th"), 0, false),
            (Some("16th"), 0, false),
            (Some("eighth"), 0, false),
            (Some("half"), 1, false),
            (Some("quarter"), 0, true)
        ]
    );
    let beams = |n: Node| -> Vec<(String, String)> { n.children().filter(|c| c.has_tag_name("beam")).map(|b| (b.attribute("number").unwrap().to_string(), b.text().unwrap().to_string())).collect() };
    let b = |n: &str, t: &str| (n.to_string(), t.to_string());
    assert_eq!(beams(written[0]), vec![b("1", "begin")]);
    assert_eq!(beams(written[1]), vec![b("1", "end")]);
    assert!(beams(written[2]).is_empty());
    // A dotted eighth and a 16th: one beam, and a hook on the 16th.
    assert_eq!(beams(written[3]), vec![b("1", "begin")]);
    assert_eq!(beams(written[4]), vec![b("1", "end"), b("2", "backward hook")]);
    // Beams stop at the beat.
    assert_eq!(beams(written[5]), vec![b("1", "begin"), b("2", "begin")]);
    assert_eq!(beams(written[6]), vec![b("1", "continue"), b("2", "end")]);
    assert_eq!(beams(written[7]), vec![b("1", "end")]);
    assert!(beams(written[8]).is_empty());
    assert!(sounding(&doc).iter().all(|n| text(*n, "stem") == Some("down")), "stems go down under the tab");
    assert_measures_full(&doc, BAR);
    assert_eq!(all(&doc, "measure").len(), 2);
    // A whole note has no stem.
    let xml = tab(&inst, &[note(28, 0, 96)], &layout(Layout::Tab));
    assert_eq!(text(sounding(&parse(&xml))[0], "stem"), Some("none"));
}

#[test]
fn notation_alone_has_no_tab_staff() {
    let inst = preset("guitar-standard").unwrap();
    let xml = tab(&inst, &[note(52, 0, QUARTER), note(64, 24, QUARTER)], &layout(Layout::Notation));
    let doc = parse(&xml);
    assert!(all(&doc, "staff-details").is_empty() && all(&doc, "string").is_empty() && all(&doc, "fret").is_empty());
    assert_eq!(all(&doc, "clef").len(), 1);
    assert_eq!(text(doc.root_element(), "sign"), Some("G"));
    assert_eq!(sounding(&doc).iter().map(|n| midi(*n)).collect::<Vec<_>>(), vec![Some(52), Some(64)]);
}

#[test]
fn guitar_and_bass_clefs_sound_an_octave_lower() {
    let clef = |id: &str| {
        let inst = preset(id).unwrap();
        let low = inst.range().0;
        let xml = tab(&inst, &[note(low, 0, QUARTER)], &layout(Layout::TabAndNotation));
        let doc = parse(&xml);
        let c = all(&doc, "clef")[0];
        assert_eq!(midi(sounding(&doc)[0]), Some(low), "{id}: the pitch stays the sounding one");
        assert!(all(&doc, "transpose").is_empty(), "{id}: the clef carries the octave, not a transposition");
        (text(c, "sign").unwrap().to_string(), text(c, "line").unwrap().to_string(), text(c, "clef-octave-change").map(str::to_string))
    };
    let own = |s: &str, l: &str, o: Option<&str>| (s.to_string(), l.to_string(), o.map(str::to_string));
    for id in ["guitar-standard", "guitar-drop-d", "guitar-drop-b", "guitar-7-standard", "guitar-8-standard"] {
        assert_eq!(clef(id), own("G", "2", Some("-1")), "{id}");
    }
    for id in ["bass-4-standard", "bass-4-bead", "bass-5-standard", "bass-6-standard"] {
        assert_eq!(clef(id), own("F", "4", Some("-1")), "{id}");
    }
    for id in ["ukulele-high-g", "ukulele-low-g", "ukulele-baritone", "mandolin"] {
        assert_eq!(clef(id), own("G", "2", None), "{id}");
    }
    // The caller can choose.
    let inst = preset("ukulele-baritone").unwrap();
    let opts = TabOptions { clef: Some(NotationClef::Treble8vb), ..TabOptions::default() };
    assert_eq!(text(parse(&tab(&inst, &[note(55, 0, QUARTER)], &opts)).root_element(), "clef-octave-change"), Some("-1"));
}

// --- measures and rhythm ---

#[test]
fn header_holds_title_tempo_meter_and_key() {
    let inst = preset("mandolin").unwrap();
    let notes = [note(62, 0, 36), note(64, 36, 36)];
    let fingering = assign(&inst, &notes, &Options::default()).unwrap();
    let score = TabScore::new("Jig & <reel>", &inst, &notes, &[], &fingering).unwrap().with_tempo(112.5).with_meter(6, 8).with_key(2, "major");
    let xml = write_tab_musicxml(&score, &layout(Layout::TabAndNotation));
    assert!(xml.starts_with("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE score-partwise PUBLIC \"-//Recordare//DTD MusicXML 4.0 Partwise//EN\""));
    let doc = parse(&xml);
    let root = doc.root_element();
    assert_eq!(root.attribute("version"), Some("4.0"));
    assert_eq!(text(root, "work-title"), Some("Jig & <reel>"));
    assert_eq!(text(root, "part-name"), Some("Mandolin"));
    assert_eq!((text(root, "beats"), text(root, "beat-type")), (Some("6"), Some("8")));
    assert_eq!((text(root, "fifths"), text(root, "mode")), (Some("2"), Some("major")));
    assert_eq!(text(root, "divisions"), Some("24"));
    assert_eq!((text(root, "beat-unit"), text(root, "per-minute")), (Some("quarter"), Some("112.50")));
    assert_eq!(all(&doc, "sound")[0].attribute("tempo"), Some("112.50"));
    // Tuning low line to high, at bar 1.
    let first = all(&doc, "measure")[0];
    assert_eq!(text(first, "words"), Some("GDAE: G D A E"));
    assert_measures_full(&doc, 72);
    assert_eq!(descendant(all(&doc, "measure")[0], "barline").and_then(|b| text(b, "bar-style")), Some("light-heavy"));
}

#[test]
fn compound_time_beams_in_threes() {
    let inst = preset("mandolin").unwrap();
    let notes: Vec<Note> = (0..6).map(|i| note(62 + i, i64::from(i) * EIGHTH, EIGHTH)).collect();
    let fingering = assign(&inst, &notes, &Options::default()).unwrap();
    let score = TabScore::new("Jig", &inst, &notes, &[], &fingering).unwrap().with_meter(6, 8);
    let xml = write_tab_musicxml(&score, &layout(Layout::Tab));
    let doc = parse(&xml);
    let beams: Vec<&str> = sounding(&doc).iter().map(|n| text(*n, "beam").unwrap()).collect();
    assert_eq!(beams, ["begin", "continue", "end", "begin", "continue", "end"]);
}

#[test]
fn compound_time_is_split_on_the_dotted_quarter() {
    let inst = preset("mandolin").unwrap();
    let write = |notes: &[Note], beats: i64| {
        let fingering = assign(&inst, notes, &Options::default()).unwrap();
        write_tab_musicxml(&TabScore::new("Jig", &inst, notes, &[], &fingering).unwrap().with_meter(beats, 8), &layout(Layout::Tab))
    };
    let values = |xml: &str| -> Vec<(String, usize, bool, Vec<String>)> {
        let doc = parse(xml);
        all(&doc, "note").into_iter().map(|n| (text(n, "type").unwrap_or("").to_string(), n.children().filter(|c| c.has_tag_name("dot")).count(), child(n, "rest").is_some(), ties(n).into_iter().map(str::to_string).collect())).collect()
    };
    let v = |t: &str, dots: usize, rest: bool, ties: &[&str]| (t.to_string(), dots, rest, ties.iter().map(|s| s.to_string()).collect::<Vec<_>>());
    // Two dotted quarters fill a 6/8 bar, untied.
    let xml = write(&[note(62, 0, 36), note(64, 36, 36)], 6);
    assert_eq!(values(&xml), [v("quarter", 1, false, &[]), v("quarter", 1, false, &[])]);
    // Quarter and eighth; then an eighth rest, and a quarter that stays inside the second beat.
    let xml = write(&[note(62, 0, 24), note(64, 24, 12), note(66, 48, 24)], 6);
    assert_eq!(values(&xml), [v("quarter", 0, false, &[]), v("eighth", 0, false, &[]), v("eighth", 0, true, &[]), v("quarter", 0, false, &[])]);
    // A dotted half fills the bar; a quarter across the beat is split and tied.
    let xml = write(&[note(62, 0, 72), note(64, 96, 24), note(66, 120, 24)], 6);
    assert_eq!(values(&xml), [
        v("half", 1, false, &[]),
        v("quarter", 0, true, &[]),
        v("eighth", 0, false, &["start"]),
        v("eighth", 0, false, &["stop"]),
        v("quarter", 0, false, &[])
    ]);
    // Three beats of 9/8 are a dotted half tied to a dotted quarter.
    let xml = write(&[note(62, 0, 108)], 9);
    assert_eq!(values(&xml), [v("half", 1, false, &["start"]), v("quarter", 1, false, &["stop"])]);
    assert_measures_full(&parse(&xml), 108);
}

#[test]
fn a_note_across_the_bar_line_is_tied() {
    let inst = preset("guitar-standard").unwrap();
    // A half note from beat 4 into the next bar, then a whole bar's rest after two more beats.
    let notes = [note(55, 0, 72), note(57, 72, 48), note(59, 120, 72)];
    for l in [Layout::Tab, Layout::TabAndNotation, Layout::Notation] {
        let xml = tab(&inst, &notes, &layout(l));
        let doc = parse(&xml);
        assert_measures_full(&doc, BAR);
        let measures = all(&doc, "measure");
        assert_eq!(measures.len(), 2);
        for staff in if l == Layout::TabAndNotation { vec![Some("1"), Some("2")] } else { vec![None] } {
            let a: Vec<Node> = sounding(&doc).into_iter().filter(|n| midi(*n) == Some(57) && staff_of(*n) == staff).collect();
            assert_eq!(a.len(), 2, "{l:?}: one piece in each bar");
            assert_eq!((ties(a[0]), tied(a[0])), (vec!["start"], vec!["start"]));
            assert_eq!((ties(a[1]), tied(a[1])), (vec!["stop"], vec!["stop"]));
            assert_eq!((text(a[0], "duration"), text(a[1], "duration")), (Some("24"), Some("24")));
            assert!(a[0].ancestors().any(|m| m == measures[0]) && a[1].ancestors().any(|m| m == measures[1]));
            if staff != Some("1") && l != Layout::Notation {
                assert_eq!(place(a[0]), place(a[1]), "the tied note keeps its string and fret");
                assert!(place(a[0]).is_some());
            }
        }
    }
}

#[test]
fn gaps_are_rests_and_empty_bars_whole_rests() {
    let inst = preset("guitar-standard").unwrap();
    let notes = [note(60, 24, QUARTER), note(62, 240, QUARTER)];
    let xml = tab(&inst, &notes, &layout(Layout::Tab));
    let doc = parse(&xml);
    assert_measures_full(&doc, BAR);
    let measures = all(&doc, "measure");
    assert_eq!(measures.iter().map(|m| m.attribute("number").unwrap()).collect::<Vec<_>>(), ["1", "2", "3"]);
    assert_eq!(rests(measures[0]), vec![(Some("quarter"), None), (Some("half"), None)]);
    assert_eq!(rests(measures[1]), vec![(None, Some("yes"))]);
    assert_eq!(rests(measures[2]), vec![(Some("half"), None), (Some("quarter"), None)]);
}

#[test]
fn a_pickup_is_an_unnumbered_first_measure() {
    let inst = preset("guitar-standard").unwrap();
    let notes = [note(59, -12, EIGHTH), note(60, 0, 96)];
    let xml = tab(&inst, &notes, &layout(Layout::TabAndNotation));
    let doc = parse(&xml);
    let measures = all(&doc, "measure");
    assert_eq!(measures.iter().map(|m| (m.attribute("number").unwrap(), m.attribute("implicit"))).collect::<Vec<_>>(), [("0", Some("yes")), ("1", None)]);
    assert_eq!(text(all(&doc, "backup")[0], "duration"), Some("12"));
    assert_measures_full(&doc, BAR);
    // A pickup longer than a bar starts on a bar line instead, with rests before it.
    let xml = tab(&inst, &[note(59, -108, EIGHTH), note(60, 0, 96)], &layout(Layout::Tab));
    let doc = parse(&xml);
    assert_eq!(all(&doc, "measure").len(), 3);
    assert!(all(&doc, "measure").iter().all(|m| m.attribute("implicit").is_none()));
    assert_measures_full(&doc, BAR);
}

#[test]
fn triplets_are_written_as_three_in_the_time_of_two() {
    let inst = preset("guitar-standard").unwrap();
    let notes = [note(60, 0, 8), note(62, 8, 8), note(64, 16, 8), note(65, 24, 72)];
    let xml = tab(&inst, &notes, &layout(Layout::Tab));
    let doc = parse(&xml);
    let n = sounding(&doc);
    for t in &n[..3] {
        assert_eq!(text(*t, "type"), Some("eighth"));
        assert_eq!((text(*t, "actual-notes"), text(*t, "normal-notes")), (Some("3"), Some("2")));
    }
    assert!(descendant(n[3], "time-modification").is_none());
    let tuplet = |k: usize| descendant(n[k], "tuplet").and_then(|t| t.attribute("type"));
    assert_eq!((tuplet(0), tuplet(1), tuplet(2)), (Some("start"), None, Some("stop")));
    assert_measures_full(&doc, BAR);
}

#[test]
fn notes_that_start_together_are_a_chord() {
    let inst = preset("guitar-standard").unwrap();
    // Given out of order; written low to high.
    let notes = [note(64, 0, 48), note(52, 0, 48), note(59, 0, 48), note(55, 48, 48)];
    let xml = tab(&inst, &notes, &layout(Layout::Tab));
    let doc = parse(&xml);
    let n = sounding(&doc);
    assert_eq!(n.iter().map(|x| midi(*x).unwrap()).collect::<Vec<_>>(), [52, 59, 64, 55]);
    assert_eq!(n.iter().map(|x| child(*x, "chord").is_some()).collect::<Vec<_>>(), [false, true, true, false]);
    let strings: Vec<u8> = n[..3].iter().map(|x| place(*x).unwrap().0).collect();
    assert!(strings[0] != strings[1] && strings[1] != strings[2] && strings[0] != strings[2]);
    assert_measures_full(&doc, BAR);
}

#[test]
fn a_chord_ends_when_the_next_note_starts() {
    let inst = preset("guitar-standard").unwrap();
    // A whole-note bass under a melody: one voice is written, so the bass is cut at the melody.
    let notes = [note(40, 0, 96), note(64, 0, 24), note(65, 24, 72)];
    let xml = tab(&inst, &notes, &layout(Layout::Tab));
    let doc = parse(&xml);
    let n = sounding(&doc);
    // The melody's dotted half is split at the middle of the bar, as every long value is.
    assert_eq!(n.iter().map(|x| (midi(*x).unwrap(), text(*x, "duration").unwrap())).collect::<Vec<_>>(), [(40, "24"), (64, "24"), (65, "24"), (65, "48")]);
    assert_measures_full(&doc, BAR);
}

#[test]
fn two_voices_on_one_pitch_are_written_once() {
    let inst = preset("guitar-standard").unwrap();
    let notes = [doubtful(60, 0, 24, 0.2), doubtful(60, 0, 48, 0.9), note(64, 0, 48)];
    let xml = tab(&inst, &notes, &layout(Layout::Tab));
    let doc = parse(&xml);
    assert_eq!(sounding(&doc).iter().map(|x| midi(*x).unwrap()).collect::<Vec<_>>(), [60, 64]);
    assert!(!words(&doc).contains(&"?"), "the more confident of the two decides");
}

// --- techniques ---

fn techniques(n: usize, marks: &[(usize, Technique)]) -> Vec<Vec<Technique>> {
    let mut out = vec![Vec::new(); n];
    for &(i, t) in marks {
        out[i].push(t);
    }
    out
}

/// (element, type, number) of the technique marks on a note, in order.
fn marks_on<'a>(n: Node<'a, 'a>, names: &[&str]) -> Vec<(&'a str, &'a str, &'a str)> {
    n.descendants().filter(|c| names.contains(&c.tag_name().name())).map(|c| (c.tag_name().name(), c.attribute("type").unwrap_or(""), c.attribute("number").unwrap_or(""))).collect()
}

#[test]
fn hammer_ons_and_pull_offs_are_start_stop_pairs_with_a_slur() {
    let inst = preset("guitar-standard").unwrap();
    let notes = [note(64, 0, EIGHTH), note(66, 12, EIGHTH), note(64, 24, EIGHTH), note(62, 36, 60)];
    let t = techniques(4, &[(1, Technique::HammerOn), (2, Technique::PullOff)]);
    let xml = tab_with(&inst, &notes, &t, &layout(Layout::Tab));
    let doc = parse(&xml);
    let n = sounding(&doc);
    let names = ["hammer-on", "pull-off", "slur"];
    assert_eq!(marks_on(n[0], &names), [("slur", "start", "1"), ("hammer-on", "start", "1")]);
    // The middle note ends the hammer-on and starts the pull-off.
    assert_eq!(marks_on(n[1], &names), [("slur", "stop", "1"), ("slur", "start", "1"), ("hammer-on", "stop", "1"), ("pull-off", "start", "1")]);
    assert_eq!(marks_on(n[2], &names), [("slur", "stop", "1"), ("pull-off", "stop", "1")]);
    assert!(marks_on(n[3], &names).is_empty());
    assert_eq!(text(n[0], "hammer-on"), Some("H"));
    assert_eq!(text(n[1], "pull-off"), Some("P"));
    // Every start has its stop.
    for name in ["hammer-on", "pull-off", "slur"] {
        let of = |ty: &str| all(&doc, name).iter().filter(|e| e.attribute("type") == Some(ty)).count();
        assert_eq!(of("start"), of("stop"), "{name}");
    }
    let frets: Vec<u8> = n.iter().map(|x| place(*x).unwrap().1).collect();
    let strings: Vec<u8> = n.iter().map(|x| place(*x).unwrap().0).collect();
    assert!(strings[0] == strings[1] && strings[1] == strings[2], "legato stays on one string: {strings:?} {frets:?}");
}

#[test]
fn techniques_in_a_pair_go_on_the_tab_staff_and_slurs_on_both() {
    let inst = preset("guitar-standard").unwrap();
    let notes = [note(64, 0, EIGHTH), note(66, 12, EIGHTH), note(69, 24, 72)];
    let t = techniques(3, &[(1, Technique::HammerOn), (2, Technique::Slide), (2, Technique::Vibrato)]);
    let xml = tab_with(&inst, &notes, &t, &layout(Layout::TabAndNotation));
    let doc = parse(&xml);
    let staff = |e: &Node| e.ancestors().find(|a| a.has_tag_name("note")).and_then(staff_of).map(str::to_string);
    for name in ["hammer-on", "slide", "wavy-line"] {
        assert!(!all(&doc, name).is_empty(), "{name}");
        assert!(all(&doc, name).iter().all(|e| staff(e).as_deref() == Some("2")), "{name} is written on the tab staff");
    }
    let slurs = all(&doc, "slur");
    assert_eq!(slurs.iter().map(|s| (staff(s).unwrap(), s.attribute("type").unwrap(), s.attribute("number").unwrap())).collect::<Vec<_>>(), [
        ("1".to_string(), "start", "1"),
        ("1".to_string(), "stop", "1"),
        ("2".to_string(), "start", "7"),
        ("2".to_string(), "stop", "7")
    ]);
}

#[test]
fn slides_bends_vibrato_let_ring_and_dead_notes() {
    let inst = preset("guitar-standard").unwrap();
    let notes = [note(62, 0, QUARTER), note(64, 24, QUARTER), note(66, 48, QUARTER), note(59, 72, QUARTER), note(57, 96, 48), note(52, 144, 48)];
    let t = techniques(6, &[(1, Technique::Slide), (2, Technique::Bend), (2, Technique::Vibrato), (3, Technique::DeadNote), (4, Technique::LetRing), (5, Technique::LetRing)]);
    let xml = tab_with(&inst, &notes, &t, &layout(Layout::Tab));
    let doc = parse(&xml);
    let n = sounding(&doc);
    // Slide from the first note to the second.
    assert_eq!(marks_on(n[0], &["slide"]), [("slide", "start", "1")]);
    assert_eq!(marks_on(n[1], &["slide"]), [("slide", "stop", "1")]);
    // The bend is written where the string is bent, with the interval to the bent note, and an arc
    // joins the two.
    assert_eq!(text(n[1], "bend-alter"), Some("2"));
    assert!(descendant(n[2], "bend").is_none());
    assert_eq!(marks_on(n[1], &["slur"]), [("slur", "start", "1")]);
    assert_eq!(marks_on(n[2], &["slur"]), [("slur", "stop", "1")]);
    assert_eq!(place(n[1]).unwrap().0, place(n[2]).unwrap().0, "the bent note is on the string it was bent on");
    // Vibrato on the bent note.
    assert_eq!(marks_on(n[2], &["wavy-line"]), [("wavy-line", "start", "1"), ("wavy-line", "stop", "1")]);
    assert!(descendant(n[2], "ornaments").is_some());
    // Dead note: an x notehead, still with its place.
    assert_eq!(text(n[3], "notehead"), Some("x"));
    assert!(place(n[3]).is_some());
    assert!(n.iter().filter(|x| descendant(**x, "notehead").is_some()).count() == 1);
    // Let ring: the words once at the start of the run, and a let-ring tie on each note.
    assert_eq!(words(&doc).iter().filter(|w| **w == "let ring").count(), 1);
    for k in [4, 5] {
        assert!(n[k].descendants().any(|c| c.has_tag_name("tied") && c.attribute("type") == Some("let-ring")));
    }
    assert!(!n[3].descendants().any(|c| c.has_tag_name("tied")));
}

#[test]
fn technique_marks_sit_at_the_ends_of_a_tied_note() {
    let inst = preset("guitar-standard").unwrap();
    // The first note is tied over the bar line; the hammer-on leaves from its last piece.
    let notes = [note(64, 72, 48), note(66, 120, 24)];
    let xml = tab_with(&inst, &notes, &techniques(2, &[(1, Technique::HammerOn)]), &layout(Layout::Tab));
    let doc = parse(&xml);
    let n = sounding(&doc);
    assert_eq!(n.len(), 3);
    assert!(marks_on(n[0], &["hammer-on", "slur"]).is_empty());
    assert_eq!(marks_on(n[1], &["hammer-on", "slur"]), [("slur", "start", "1"), ("hammer-on", "start", "1")]);
    assert_eq!(marks_on(n[2], &["hammer-on", "slur"]), [("slur", "stop", "1"), ("hammer-on", "stop", "1")]);
}

#[test]
fn dead_note_is_a_technique_name_in_json() {
    let request = r#"{"instrument": {"preset": "guitar-standard"}, "notes": [{"pitch": 55, "start": 0, "dur": 24, "techniques": ["dead-note"]}], "tab": {"layout": "tab"}}"#;
    let xml = tab_musicxml_json(request).unwrap();
    assert_eq!(text(parse(&xml).root_element(), "notehead"), Some("x"));
}

// --- doubt and range ---

#[test]
fn a_doubtful_note_is_coloured_and_marked_with_a_question_mark() {
    let inst = preset("guitar-standard").unwrap();
    let notes = [note(60, 0, QUARTER), doubtful(62, 24, QUARTER, 0.314), doubtful(64, 48, 48, 0.4)];
    for l in [Layout::Tab, Layout::TabAndNotation, Layout::Notation] {
        let xml = tab(&inst, &notes, &layout(l));
        let doc = parse(&xml);
        let staves = if l == Layout::TabAndNotation { 2 } else { 1 };
        let coloured: Vec<Node> = sounding(&doc).into_iter().filter(|n| n.attribute("color").is_some()).collect();
        assert_eq!(coloured.len(), staves, "{l:?}: only the note below the threshold");
        for n in &coloured {
            assert_eq!(midi(*n), Some(62));
            assert_eq!(n.attribute("color"), Some("#9A5200"));
            let head = child(*n, "notehead").unwrap();
            assert_eq!((head.attribute("color"), head.text()), (Some("#9A5200"), Some("normal")));
            // The confidence rides along as a processing instruction.
            let pi = n.children().find(|c| c.is_pi()).and_then(|c| c.pi()).unwrap();
            assert_eq!((pi.target, pi.value), ("brasscribe-confidence", Some("0.31")));
        }
        // One "?" above the column, on the tab staff when there is one.
        let marks: Vec<Node> = all(&doc, "direction").into_iter().filter(|d| text(*d, "words") == Some("?")).collect();
        assert_eq!(marks.len(), 1, "{l:?}");
        assert_eq!(marks[0].attribute("placement"), Some("above"));
        assert_eq!(text(marks[0], "staff"), if staves == 2 { Some("2") } else { None });
        // It comes right before the note it marks.
        let next = marks[0].next_siblings().find(|s| s.has_tag_name("note")).unwrap();
        assert_eq!(midi(next), Some(62));
        // Doubt never changes the pitch or the place, and is never a parenthesis.
        assert!(!xml.contains("parentheses"));
        if l == Layout::Tab {
            let plain = parse(&tab(&inst, &[note(60, 0, QUARTER), note(62, 24, QUARTER), note(64, 48, 48)], &layout(l))).descendants().filter(|n| n.has_tag_name("note")).map(|n| (midi(n), place(n))).collect::<Vec<_>>();
            assert_eq!(sounding(&doc).iter().map(|n| (midi(*n), place(*n))).collect::<Vec<_>>(), plain);
        }
    }
}

#[test]
fn the_doubt_threshold_is_an_option() {
    let inst = preset("guitar-standard").unwrap();
    let notes = [doubtful(60, 0, QUARTER, 0.3), doubtful(62, 24, QUARTER, 0.6), doubtful(64, 48, 48, 0.9)];
    let count = |below: f64| {
        let xml = tab(&inst, &notes, &TabOptions { layout: Layout::Tab, doubt_below: below, ..TabOptions::default() });
        let doc = parse(&xml);
        let marks = words(&doc).iter().filter(|w| **w == "?").count();
        assert_eq!(marks, sounding(&doc).iter().filter(|n| n.attribute("color").is_some()).count());
        assert_eq!(marks, xml.matches("<?brasscribe-confidence ").count());
        marks
    };
    assert_eq!((count(0.0), count(0.4), count(0.7), count(1.0)), (0, 1, 2, 3));
}

#[test]
fn a_doubtful_chord_gets_one_question_mark_before_its_first_note() {
    let inst = preset("guitar-standard").unwrap();
    let notes = [doubtful(52, 0, 48, 0.1), note(59, 0, 48), doubtful(64, 0, 48, 0.2), note(60, 48, 48)];
    let xml = tab(&inst, &notes, &layout(Layout::Tab));
    let doc = parse(&xml);
    assert_eq!(words(&doc).iter().filter(|w| **w == "?").count(), 1);
    let mark = all(&doc, "direction").into_iter().find(|d| text(*d, "words") == Some("?")).unwrap();
    let next = mark.next_siblings().skip(1).find(|s| s.is_element()).unwrap();
    assert!(next.has_tag_name("note") && child(next, "chord").is_none());
    assert_eq!(sounding(&doc).iter().map(|n| n.attribute("color").is_some()).collect::<Vec<_>>(), [true, false, true, false]);
}

#[test]
fn a_tied_doubtful_note_is_marked_once() {
    let inst = preset("guitar-standard").unwrap();
    let xml = tab(&inst, &[doubtful(60, 72, 48, 0.1)], &layout(Layout::Tab));
    let doc = parse(&xml);
    assert_eq!(words(&doc).iter().filter(|w| **w == "?").count(), 1);
    assert_eq!(xml.matches("<?brasscribe-confidence 0.10?>").count(), 1);
    assert_eq!(sounding(&doc).iter().filter(|n| n.attribute("color").is_some()).count(), 2, "both pieces keep the colour");
}

#[test]
fn an_out_of_range_note_keeps_its_pitch_and_gets_an_exclamation_mark() {
    let inst = preset("guitar-standard").unwrap();
    // B1 is below the low E string.
    let notes = [note(52, 0, QUARTER), note(35, 24, QUARTER), note(55, 48, 48)];
    for l in [Layout::Tab, Layout::TabAndNotation] {
        let xml = tab(&inst, &notes, &layout(l));
        let doc = parse(&xml);
        let low: Vec<Node> = sounding(&doc).into_iter().filter(|n| midi(*n) == Some(35)).collect();
        assert_eq!(low.len(), if l == Layout::Tab { 1 } else { 2 });
        assert!(low.iter().all(|n| descendant(*n, "technical").is_none()), "no string or fret is invented");
        let marks: Vec<Node> = all(&doc, "direction").into_iter().filter(|d| text(*d, "words") == Some("!")).collect();
        assert_eq!(marks.len(), 1);
        assert_eq!(midi(marks[0].next_siblings().find(|s| s.has_tag_name("note")).unwrap()), Some(35));
        assert!(!words(&doc).contains(&"?"));
        assert_measures_full(&doc, BAR);
    }
}

// --- the document as a whole ---

#[test]
fn the_same_input_gives_the_same_text() {
    let inst = preset("guitar-drop-d").unwrap().with_capo(2);
    let notes = [note(40, 0, 36), doubtful(52, 36, 12, 0.2), note(59, 48, 72), note(64, 48, 72), note(66, 120, 8), note(67, 128, 8), note(69, 136, 8)];
    let t = techniques(7, &[(5, Technique::HammerOn), (6, Technique::Slide)]);
    for l in [Layout::Tab, Layout::TabAndNotation, Layout::Notation] {
        let a = tab_with(&inst, &notes, &t, &layout(l));
        assert_eq!(a, tab_with(&inst, &notes, &t, &layout(l)));
        assert!(!a.contains("/Users/") && !a.contains("encoding-date"));
        assert_measures_full(&parse(&a), BAR);
    }
}

#[test]
fn every_preset_and_layout_is_well_formed_and_fills_its_measures() {
    // A fixed pseudo-random passage per preset: lines, chords, odd lengths, a pickup, doubt.
    let mut seed = 0x2545_f491_4f6c_dd1du64;
    let mut next = |n: u64| {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        seed % n
    };
    let lengths = [3, 6, 8, 9, 12, 16, 18, 24, 30, 36, 48, 60, 96, 120];
    for id in PRESET_IDS {
        let inst = preset(id).unwrap().with_capo(next(4) as u8);
        let (lo, hi) = inst.range();
        let mut notes = Vec::new();
        let mut at = -(next(3) as i64) * 12;
        for _ in 0..40 {
            let len = lengths[next(lengths.len() as u64) as usize];
            for _ in 0..=next(3) {
                let pitch = lo - 2 + next((hi - lo + 4) as u64) as i32;
                notes.push(doubtful(pitch, at, len, next(100) as f64 / 100.0));
            }
            at += lengths[next(lengths.len() as u64) as usize];
        }
        let fingering = assign(&inst, &notes, &Options::default()).unwrap();
        for (beats, unit) in [(4, 4), (3, 4), (6, 8), (5, 8)] {
            let score = TabScore::new(id, &inst, &notes, &[], &fingering).unwrap().with_meter(beats, unit);
            for l in [Layout::Tab, Layout::TabAndNotation, Layout::Notation] {
                let xml = write_tab_musicxml(&score, &layout(l));
                let doc = parse(&xml);
                assert_measures_full(&doc, beats * 96 / unit);
                // Every placed note sounds its pitch at the written string and fret.
                for n in sounding(&doc) {
                    if let Some((string, fret)) = place(n) {
                        assert_eq!(inst.pitch_at(target_fretted::Position { string, fret }), midi(n), "{id}");
                    }
                }
                // Ties come in pairs.
                let ties = |ty: &str| all(&doc, "tie").iter().filter(|t| t.attribute("type") == Some(ty)).count();
                assert_eq!(ties("start"), ties("stop"), "{id}");
            }
        }
    }
}

#[test]
fn a_score_refuses_input_that_does_not_fit_together() {
    let inst = preset("guitar-standard").unwrap();
    let notes = [note(60, 0, QUARTER), note(62, 24, QUARTER)];
    let fingering = assign(&inst, &notes, &Options::default()).unwrap();
    assert!(TabScore::new("x", &inst, &notes, &[], &fingering).is_ok());
    assert!(TabScore::new("x", &inst, &notes[..1], &[], &fingering).unwrap_err().contains("places 2 notes"));
    assert!(TabScore::new("x", &inst, &notes, &[Vec::new()], &fingering).unwrap_err().contains("techniques"));
    let mut wrong = fingering.clone();
    wrong.notes[1].pitch = 63;
    assert!(TabScore::new("x", &inst, &notes, &[], &wrong).unwrap_err().contains("note 1"));
    let mut off = fingering.clone();
    off.notes[0].string = Some(7);
    assert!(TabScore::new("x", &inst, &notes, &[], &off).unwrap_err().contains("string 7"));
    let mut no_frets = inst.clone();
    no_frets.frets = 0;
    assert!(TabScore::new("x", &no_frets, &notes, &[], &fingering).is_err());
}

#[test]
fn an_empty_passage_is_one_bar_of_rest() {
    let inst = preset("ukulele-high-g").unwrap();
    let score = TabScore::new("", &inst, &[], &[], &Fingering { notes: Vec::new() }).unwrap();
    let xml = write_tab_musicxml(&score, &TabOptions::default());
    let doc = parse(&xml);
    assert_eq!(all(&doc, "measure").len(), 1);
    assert!(all(&doc, "work").is_empty(), "no title element for an empty title");
    assert_measures_full(&doc, BAR);
}

// --- JSON ---

#[test]
fn json_solves_and_writes() {
    let request = r#"{"title": "Round", "instrument": {"preset": "ukulele-high-g", "capo": 1},
        "notes": [{"pitch": 68, "start": 0, "dur": 24}, {"pitch": 61, "start": 24, "dur": 24, "confidence": 0.2}],
        "options": {"style": "open-position"}, "tempo_bpm": 72, "meter": {"beats": 2}, "key": {"fifths": -1},
        "tab": {"layout": "tab", "doubt_below": 0.5}}"#;
    let xml = tab_musicxml_json(request).unwrap();
    let doc = parse(&xml);
    let root = doc.root_element();
    assert_eq!(text(root, "work-title"), Some("Round"));
    assert_eq!(text(root, "part-name"), Some("Ukulele (high G)"));
    assert_eq!((text(root, "beats"), text(root, "beat-type"), text(root, "fifths"), text(root, "per-minute"), text(root, "capo")), (Some("2"), Some("4"), Some("-1"), Some("72"), Some("1")));
    // The capo'd open G and C strings.
    assert_eq!(sounding(&doc).iter().map(|n| place(*n)).collect::<Vec<_>>(), [Some((4, 0)), Some((3, 0))]);
    assert_eq!(words(&doc).iter().filter(|w| **w == "?").count(), 1);
    assert_eq!(xml, tab_musicxml_json(request).unwrap());

    // The solver's tempo is used when the request names no other.
    let xml = tab_musicxml_json(r#"{"instrument": {"preset": "mandolin"}, "notes": [], "options": {"tempo_bpm": 140}}"#).unwrap();
    assert_eq!(text(parse(&xml).root_element(), "per-minute"), Some("140"));
}

#[test]
fn json_writes_a_given_fingering_as_it_is() {
    // E4 on the open first string would be the solver's choice; the request says string 2, fret 5.
    let place = NotePlace { pitch: 64, string: Some(2), fret: Some(5), alternatives: Vec::new(), out_of_range: false, pinned: false };
    let request = serde_json::json!({
        "instrument": {"preset": "guitar-standard"},
        "notes": [{"pitch": 64, "start": 0, "dur": 24}],
        "fingering": Fingering { notes: vec![place] },
        "tab": {"layout": "tab", "capo": "tuning"}
    });
    let xml = tab_musicxml_json(&request.to_string()).unwrap();
    let doc = parse(&xml);
    assert_eq!(self::place(sounding(&doc)[0]), Some((2, 5)));
}

#[test]
fn json_refuses_what_it_does_not_know() {
    let err = |request: &str| tab_musicxml_json(request).unwrap_err();
    assert!(err("{").starts_with("not a tablature request"));
    assert!(err(r#"{"instrument": {"preset": "guitar-standard"}, "notes": [], "layout": "tab"}"#).contains("layout"));
    assert!(err(r#"{"instrument": {"preset": "guitar-standard"}, "notes": [], "tab": {"layout": "ascii"}}"#).contains("ascii"));
    assert!(err(r#"{"instrument": {"preset": "guitar-standard"}, "notes": [], "tab": {"paper": "a4"}}"#).contains("paper"));
    assert!(err(r#"{"instrument": {"preset": "lute"}, "notes": []}"#).contains("lute"));
    let short = r#"{"instrument": {"preset": "guitar-standard"}, "notes": [{"pitch": 64, "start": 0, "dur": 24}], "fingering": {"notes": []}}"#;
    assert!(err(short).contains("places 0 notes"));
}

// --- fixture ---

/// The committed study: every feature in four bars. Regenerate it on purpose, from this crate's
/// directory, with `cargo run --example tab < tests/fixtures/study.json > tests/fixtures/study.musicxml`.
#[test]
fn the_study_fixture_is_reproduced() {
    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures");
    let request = std::fs::read_to_string(dir.join("study.json")).unwrap();
    let expected = std::fs::read_to_string(dir.join("study.musicxml")).unwrap();
    let xml = tab_musicxml_json(&request).unwrap();
    assert!(xml == expected, "tests/fixtures/study.musicxml no longer matches the writer's output");

    let doc = parse(&xml);
    assert_measures_full(&doc, BAR);
    let measures = all(&doc, "measure");
    assert_eq!(measures.iter().map(|m| m.attribute("number").unwrap()).collect::<Vec<_>>(), ["0", "1", "2", "3"]);
    assert_eq!(text(doc.root_element(), "capo"), Some("2"));
    assert_eq!(staff_tuning(&doc), vec![(1, 40), (2, 45), (3, 50), (4, 55), (5, 59), (6, 64)]);
    let w = words(&doc);
    assert_eq!(w, ["Standard: E A D G B E, Capo 2", "?", "!", "let ring"]);
    for name in ["hammer-on", "pull-off", "slide", "bend", "wavy-line", "time-modification", "tie", "chord", "notehead"] {
        assert!(!all(&doc, name).is_empty(), "the study has a {name}");
    }
    // The F sharp minor chord at the capo: open low string, then the shape two frets up.
    let tab_notes: Vec<Node> = sounding(&doc).into_iter().filter(|n| staff_of(*n) == Some("2")).collect();
    let last: Vec<(u8, u8)> = tab_notes[tab_notes.len() - 3..].iter().map(|n| place(*n).unwrap()).collect();
    assert_eq!(last, [(6, 0), (5, 2), (4, 2)]);
}
