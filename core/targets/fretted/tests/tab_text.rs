//! The text tab and the playing instructions: what they look like, and what holds for every
//! instrument and every passage (each note once, columns in line, bars kept whole, the same text
//! every time, the same structure in both languages).

use std::collections::BTreeMap;

use brasscribe_core::model::Note;
use roxmltree::{Document, Node, ParsingOptions};
use target_fretted::json::{playing_instructions_json, tab_text_json};
use target_fretted::{
    preset, write_playing_instructions, write_tab_musicxml, write_tab_text, Fingering, Instrument, Layout, NotePlace, Position, TabOptions, TabScore, Technique, TextOptions, MAX_NOTES, MAX_TEXT_WIDTH,
    MIN_TEXT_WIDTH, PRESET_IDS, TEXT_WIDTH,
};

// ---------------------------------------------------------------- passages

/// A small generator with a fixed sequence per seed, so every run tests the same passages.
struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0
    }

    fn below(&mut self, n: u64) -> u64 {
        self.next() % n
    }

    fn one_in(&mut self, n: u64) -> bool {
        self.below(n) == 0
    }
}

struct Passage {
    notes: Vec<Note>,
    techniques: Vec<Vec<Technique>>,
    fingering: Fingering,
}

impl Passage {
    fn new() -> Passage {
        Passage { notes: Vec::new(), techniques: Vec::new(), fingering: Fingering { notes: Vec::new() } }
    }

    #[allow(clippy::too_many_arguments)] // a note is this many things
    fn placed(&mut self, inst: &Instrument, string: u8, fret: u8, start: i64, dur: i64, confidence: f64, techniques: &[Technique]) {
        let pitch = inst.pitch_at(Position { string, fret }).unwrap();
        self.notes.push(Note::new(pitch, start, dur, confidence, Vec::new()));
        self.techniques.push(techniques.to_vec());
        self.fingering.notes.push(NotePlace { pitch, string: Some(string), fret: Some(fret), alternatives: Vec::new(), out_of_range: false, pinned: false });
    }

    /// A note below every string: it has no place.
    fn lost(&mut self, pitch: i32, start: i64, dur: i64) {
        self.notes.push(Note::new(pitch, start, dur, 1.0, Vec::new()));
        self.techniques.push(Vec::new());
        self.fingering.notes.push(NotePlace { pitch, string: None, fret: None, alternatives: Vec::new(), out_of_range: true, pinned: false });
    }

    fn score(&self, inst: &Instrument) -> TabScore {
        TabScore::new("Made-up passage", inst, &self.notes, &self.techniques, &self.fingering).unwrap()
    }
}

/// A made-up passage for `inst`: single notes, chords, rests, notes held over bar lines, triplets,
/// frets above 9, techniques, doubtful notes and notes with no place, sometimes after a pickup.
fn passage(inst: &Instrument, seed: u64) -> Passage {
    let mut rng = Rng(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15) | 1);
    let mut p = Passage::new();
    let strings = inst.string_count() as u64;
    let top = u64::from((inst.frets - inst.capo).min(17));
    let mut at: i64 = if rng.one_in(2) { -[12, 24, 36][rng.below(3) as usize] } else { 0 };
    // The single note before, when the next note may be reached from it on its string.
    let mut before: Option<(u8, u8)> = None;
    for _ in 0..36 {
        let dur = [6, 12, 12, 24, 24, 24, 36, 48, 96, 120][rng.below(10) as usize];
        let confidence = if rng.one_in(6) { 0.2 } else { 1.0 };
        match rng.below(12) {
            0 => {
                before = None;
            }
            1 => {
                p.lost(5, at, dur);
                before = None;
            }
            2..=4 => {
                // A chord on strings of its own, sometimes with a note that has no place.
                let mut free: Vec<u8> = (1..=strings as u8).collect();
                for _ in 0..(2 + rng.below(strings.min(4) - 1)) {
                    let string = free.remove(rng.below(free.len() as u64) as usize);
                    let techniques = if rng.one_in(4) { vec![Technique::LetRing] } else { Vec::new() };
                    p.placed(inst, string, rng.below(top + 1) as u8, at, dur, confidence, &techniques);
                }
                if rng.one_in(5) {
                    p.lost(7, at, dur);
                }
                before = None;
            }
            5 => {
                // A triplet of eighths.
                let string = 1 + rng.below(strings) as u8;
                for k in 0..3 {
                    p.placed(inst, string, rng.below(top + 1) as u8, at + 8 * k, 8, 1.0, &[]);
                }
                at += 24;
                before = None;
                continue;
            }
            _ => {
                let (string, fret, techniques) = match before {
                    Some((string, from)) if rng.one_in(2) => {
                        let fret = if from + 3 <= top as u8 && rng.one_in(2) { from + 1 + rng.below(3) as u8 } else { from.saturating_sub(1 + rng.below(3) as u8) };
                        let how = match (fret.cmp(&from), rng.below(3)) {
                            (std::cmp::Ordering::Equal, _) => vec![],
                            (_, 0) => vec![Technique::Slide],
                            (std::cmp::Ordering::Greater, 1) if from > 0 => vec![Technique::Bend],
                            (std::cmp::Ordering::Greater, _) => vec![Technique::HammerOn],
                            (std::cmp::Ordering::Less, _) => vec![Technique::PullOff],
                        };
                        (string, fret, how)
                    }
                    _ => {
                        let how = match rng.below(8) {
                            0 => vec![Technique::Vibrato],
                            1 => vec![Technique::DeadNote],
                            2 => vec![Technique::LetRing],
                            _ => vec![],
                        };
                        (1 + rng.below(strings) as u8, rng.below(top + 1) as u8, how)
                    }
                };
                p.placed(inst, string, fret, at, dur, confidence, &techniques);
                before = Some((string, fret));
            }
        }
        at += dur;
    }
    p
}

fn text_options(width: usize, lang: &str) -> TextOptions {
    TextOptions { width, lang: lang.into() }
}

fn tab_text(score: &TabScore, width: usize) -> String {
    write_tab_text(score, &TabOptions::default(), &text_options(width, "en")).unwrap()
}

fn instructions(score: &TabScore, lang: &str) -> String {
    write_playing_instructions(score, &TabOptions::default(), &text_options(TEXT_WIDTH, lang)).unwrap()
}

/// Every preset with a few passages each.
fn cases() -> Vec<(String, Instrument, Passage)> {
    let mut out = Vec::new();
    for (i, id) in PRESET_IDS.iter().enumerate() {
        let inst = preset(id).unwrap().with_capo((i % 3) as u8);
        for seed in 0..4 {
            let p = passage(&inst, (i as u64) * 16 + seed);
            out.push((format!("{id}, passage {seed}"), inst.clone(), p));
        }
    }
    out
}

// ---------------------------------------------------------------- the MusicXML, to compare with

fn parse(xml: &str) -> Document<'_> {
    Document::parse_with_options(xml, ParsingOptions { allow_dtd: true, ..Default::default() }).unwrap()
}

fn descendant<'a>(n: Node<'a, 'a>, name: &str) -> Option<Node<'a, 'a>> {
    n.descendants().find(|c| c.has_tag_name(name))
}

/// Per measure of the tab staff: (string, what stands on the line) of every note where it starts,
/// sorted. A dead note is "x" and a note with vibrato has a "~" after its fret, as the text has them.
fn written(score: &TabScore) -> Vec<Vec<(u8, String)>> {
    let xml = write_tab_musicxml(score, &TabOptions { layout: Layout::Tab, ..TabOptions::default() }).unwrap().musicxml;
    let doc = parse(&xml);
    doc.descendants()
        .filter(|n| n.has_tag_name("measure"))
        .map(|m| {
            let mut notes: Vec<(u8, String)> = m
                .children()
                .filter(|n| n.has_tag_name("note") && !n.children().any(|c| c.has_tag_name("tie") && c.attribute("type") == Some("stop")))
                .filter_map(|n| {
                    let string = descendant(n, "string")?.text()?.parse().ok()?;
                    let fret = descendant(n, "fret")?.text()?;
                    let dead = descendant(n, "notehead").is_some_and(|h| h.text() == Some("x"));
                    Some((string, if dead { "x".to_string() } else if descendant(n, "wavy-line").is_some() { format!("{fret}~") } else { fret.to_string() }))
                })
                .collect();
            notes.sort();
            notes
        })
        .collect()
}

/// How many columns of the tab have a "?" above them, and how many a boxed "!".
fn marks(score: &TabScore) -> (usize, usize) {
    let xml = write_tab_musicxml(score, &TabOptions { layout: Layout::Tab, ..TabOptions::default() }).unwrap().musicxml;
    let doc = parse(&xml);
    let words: Vec<&str> = doc.descendants().filter(|n| n.has_tag_name("words")).filter_map(|n| n.text()).collect();
    (words.iter().filter(|w| **w == "?").count(), words.iter().filter(|w| w.starts_with("! ")).count())
}

// ---------------------------------------------------------------- reading a text tab

/// One system of a text tab: the rows above the lines, and one line per string.
struct System {
    above: Vec<String>,
    lines: Vec<String>,
}

/// The systems of a text tab for an instrument with `strings` strings: the blocks whose last
/// `strings` rows all have a bar line.
fn systems(text: &str, strings: usize) -> Vec<System> {
    text.split("\n\n")
        .filter_map(|block| {
            let rows: Vec<&str> = block.lines().collect();
            let split = rows.len().checked_sub(strings)?;
            let (above, lines) = rows.split_at(split);
            (lines.iter().all(|l| l.contains('|')) && above.iter().all(|a| a.starts_with(' '))).then(|| System { above: above.iter().map(|s| s.to_string()).collect(), lines: lines.iter().map(|s| s.to_string()).collect() })
        })
        .collect()
}

fn chars(s: &str) -> usize {
    s.chars().count()
}

/// A line of a system after its label and opening bar line.
fn body(line: &str) -> &str {
    &line[line.find('|').unwrap() + 1..]
}

/// What stands in the cells of one string's bar: each cell is `cell` characters, a lead (`-` or a
/// technique) and then a fret, an x or nothing, filled with `-`.
fn cells(bar: &str, cell: usize, context: &str) -> Vec<String> {
    let c: Vec<char> = bar.chars().collect();
    assert_eq!(c.len() % cell, 0, "{context}: a bar of {} characters is not whole cells of {cell}: {bar:?}", c.len());
    c.chunks(cell)
        .filter_map(|chunk| {
            assert!("-hp/\\b".contains(chunk[0]), "{context}: a cell starts with {:?} in {bar:?}", chunk[0]);
            let text: String = chunk[1..].iter().collect();
            let text = text.trim_end_matches('-').to_string();
            assert!(!text.contains('-'), "{context}: a number is not at the start of its cell in {bar:?}");
            assert!(text.is_empty() || text == "x" || text.trim_end_matches('~').chars().all(|d| d.is_ascii_digit()), "{context}: {text:?} in {bar:?}");
            (!text.is_empty()).then_some(text)
        })
        .collect()
}

/// The cell width a passage is written with: the widest fret (with its vibrato mark), and the lead.
fn cell_width(score: &TabScore) -> usize {
    1 + written(score).iter().flatten().map(|(_, t)| t.len()).max().unwrap_or(1)
}

// ---------------------------------------------------------------- what the text tab looks like

#[test]
fn a_bass_line_as_text() {
    let bass = preset("bass-4-standard").unwrap();
    let mut p = Passage::new();
    // A pickup, a doubtful note, a hammer-on, a note held into the next bar and a slide.
    p.placed(&bass, 4, 3, -12, 12, 1.0, &[]);
    p.placed(&bass, 3, 0, 0, 24, 1.0, &[]);
    p.placed(&bass, 3, 3, 24, 24, 0.3, &[]);
    p.placed(&bass, 2, 0, 48, 12, 1.0, &[]);
    p.placed(&bass, 2, 2, 60, 12, 1.0, &[Technique::HammerOn]);
    p.placed(&bass, 1, 0, 72, 48, 1.0, &[]);
    p.placed(&bass, 3, 5, 144, 24, 1.0, &[]);
    p.placed(&bass, 3, 7, 168, 24, 1.0, &[Technique::Slide]);
    let score = p.score(&bass).with_tempo(96.0);
    let want = "\
Made-up passage
Bass
Tuning: Standard (E A D G), bottom line to top
Capo: none
Tempo: 96 quarter notes per minute
Time: 4/4

     1                2
          ?
G|--|-------------0--|--------||
D|--|---------0h2----|--------||
A|--|-0---3----------|-----5/7||
E|-3|----------------|--------||

?  a note to check: it was not heard clearly
h  hammer-on
/  slide up
";
    assert_eq!(tab_text(&score, TEXT_WIDTH), want);
}

#[test]
fn guitar_chords_stand_in_one_column_with_frets_of_two_digits_in_line() {
    let guitar = preset("guitar-standard").unwrap().with_capo(2);
    let mut p = Passage::new();
    for (string, fret) in [(5, 0), (4, 2), (3, 2), (2, 1)] {
        p.placed(&guitar, string, fret, 0, 48, 1.0, &[]);
    }
    for (string, fret) in [(4, 12), (3, 10), (2, 9), (1, 12)] {
        p.placed(&guitar, string, fret, 48, 24, 1.0, &[Technique::LetRing]);
    }
    p.placed(&guitar, 1, 12, 72, 12, 1.0, &[]);
    p.placed(&guitar, 1, 14, 84, 12, 1.0, &[Technique::Bend]);
    p.lost(30, 96, 48);
    p.placed(&guitar, 6, 0, 96, 48, 1.0, &[Technique::DeadNote]);
    p.placed(&guitar, 2, 10, 144, 48, 1.0, &[Technique::Vibrato]);
    let score = p.score(&guitar).with_tempo(72.0);
    let want = "\
Made-up passage
Guitar
Tuning: Standard (E A D G B E), bottom line to top
Capo: fret 2 (frets are counted from the capo)
Tempo: 72 quarter notes per minute
Time: 4/4

  1                                2
                   let ring
                                    !
E|-----------------12------12-b14-|----------------||
B|-1---------------9--------------|---------10~----||
G|-2---------------10-------------|----------------||
D|-2---------------12-------------|----------------||
A|-0------------------------------|----------------||
E|--------------------------------|-x--------------||

!  a note with no string to play it on, not in the lines: bar 2: F#1
b  bend: the string is bent up to the pitch of the fret after the b
~  vibrato
x  dead note: the string is muted
";
    assert_eq!(tab_text(&score, TEXT_WIDTH), want);
}

#[test]
fn every_instrument_has_one_line_per_string_named_after_its_tuning() {
    for (id, labels) in [
        ("bass-4-standard", vec!["G", "D", "A", "E"]),
        ("bass-5-standard", vec!["G", "D", "A", "E", "B"]),
        ("bass-6-standard", vec!["C", "G", "D", "A", "E", "B"]),
        ("guitar-standard", vec!["E", "B", "G", "D", "A", "E"]),
        ("guitar-eb-standard", vec!["Eb", "Bb", "Gb", "Db", "Ab", "Eb"]),
        ("guitar-drop-b", vec!["C#", "G#", "E ", "B ", "F#", "B "]),
        ("guitar-7-standard", vec!["E", "B", "G", "D", "A", "E", "B"]),
        ("guitar-8-standard", vec!["E ", "B ", "G ", "D ", "A ", "E ", "B ", "F#"]),
        ("ukulele-high-g", vec!["A", "E", "C", "G"]),
        ("ukulele-low-g", vec!["A", "E", "C", "G"]),
        ("ukulele-baritone", vec!["E", "B", "G", "D"]),
        // One line per course of two strings.
        ("mandolin", vec!["E", "A", "D", "G"]),
    ] {
        let said = instructions(&{
            let inst = preset(id).unwrap();
            let mut p = Passage::new();
            p.placed(&inst, 1, 2, 0, 96, 1.0, &[]);
            p.score(&inst)
        }, "en");
        let strings = labels.len();
        if id == "mandolin" {
            assert!(said.contains("\nMandolin, 4 pairs of strings. Each pair is played as one string and has one number.\n"), "{said}");
        } else {
            assert!(said.contains(&format!(", {strings} strings.\nString 1 is the string nearest the floor as you play. String {strings} is nearest the ceiling.\n")), "{id}\n{said}");
        }
        let inst = preset(id).unwrap();
        let mut p = Passage::new();
        p.placed(&inst, 1, 2, 0, 96, 1.0, &[]);
        let text = tab_text(&p.score(&inst), TEXT_WIDTH);
        let s = systems(&text, labels.len());
        assert_eq!(s.len(), 1, "{id}\n{text}");
        let got: Vec<&str> = s[0].lines.iter().map(|l| &l[..l.find('|').unwrap()]).collect();
        assert_eq!(got, labels, "{id}");
        assert!(s[0].lines[0].ends_with("|-2------||"), "{id}: string 1 is the top line\n{text}");
        assert!(text.is_ascii(), "{id}: sharps and flats are written # and b\n{text}");
    }
}

#[test]
fn the_legend_holds_only_the_marks_that_occur() {
    let bass = preset("bass-4-standard").unwrap();
    let mut p = Passage::new();
    p.placed(&bass, 1, 2, 0, 96, 1.0, &[]);
    let text = tab_text(&p.score(&bass), TEXT_WIDTH);
    assert!(text.ends_with("G|-2------||\nD|--------||\nA|--------||\nE|--------||\n"), "no legend without marks\n{text}");

    p.placed(&bass, 1, 0, 96, 96, 1.0, &[Technique::PullOff]);
    let text = tab_text(&p.score(&bass), TEXT_WIDTH);
    assert!(text.ends_with("||\n\np  pull-off\n"), "{text}");
}

#[test]
fn a_second_note_on_one_string_is_named_not_dropped() {
    // A fingering edited by hand can put two notes of a chord on one string: a line holds one number.
    let bass = preset("bass-4-standard").unwrap();
    let mut p = Passage::new();
    p.placed(&bass, 2, 2, 0, 96, 1.0, &[]);
    p.placed(&bass, 2, 5, 0, 96, 1.0, &[]);
    let score = p.score(&bass);
    let text = tab_text(&score, TEXT_WIDTH);
    assert!(text.contains("\n   !\nG|--------||\nD|-2------||\n"), "{text}");
    assert!(
        text.ends_with("\n\n!  a note that cannot be played together with another note on its\n   string, not in the lines: bar 1: G2 (string 2)\n"),
        "{text}"
    );
    // The instructions say the same: the note that is written, and the note that is not.
    let en = instructions(&score, "en");
    assert!(en.ends_with("\nBar 1\n  Beat 1. Chord, 2 notes: string 2, fret 2; G 2, cannot be played together with the note on string 2. Whole note.\n"), "{en}");
    let nb = instructions(&score, "nb");
    assert!(nb.ends_with("\nTakt 1\n  Slag 1. Akkord, 2 toner: streng 2, bånd 2; G 2, kan ikke spilles sammen med tonen på streng 2. Helnote.\n"), "{nb}");
    assert!(!text.contains("no string to play it on") && !en.contains("no string to play it on"));
}

#[test]
fn no_question_marks_when_the_doubt_threshold_is_zero() {
    let bass = preset("bass-4-standard").unwrap();
    let mut p = Passage::new();
    p.placed(&bass, 1, 2, 0, 96, 0.1, &[]);
    let score = p.score(&bass);
    assert!(tab_text(&score, TEXT_WIDTH).contains("\n   ?\n"));
    assert!(instructions(&score, "en").contains("to check"));
    let shown = TabOptions { doubt_below: 0.0, ..TabOptions::default() };
    assert!(!write_tab_text(&score, &shown, &TextOptions::default()).unwrap().contains('?'));
    assert!(!write_playing_instructions(&score, &shown, &TextOptions::default()).unwrap().contains("to check"));
}

#[test]
fn doubt_is_never_shown_with_parentheses() {
    for (name, inst, p) in cases() {
        let text = tab_text(&p.score(&inst), TEXT_WIDTH);
        let tab: String = systems(&text, inst.string_count()).iter().flat_map(|s| s.above.iter().chain(&s.lines)).cloned().collect();
        assert!(!tab.contains('(') && !tab.contains(')'), "{name}\n{text}");
    }
}

#[test]
fn let_ring_is_shortened_where_there_is_no_room_for_the_words() {
    let bass = preset("bass-4-standard").unwrap();
    let mut p = Passage::new();
    // Three runs of ringing notes with a plain note between them, a quarter apart.
    for (k, ring) in [true, false, true, false, true].into_iter().enumerate() {
        p.placed(&bass, 1, 2, 24 * k as i64, 24, 1.0, if ring { &[Technique::LetRing] } else { &[] });
    }
    p.placed(&bass, 1, 2, 120, 72, 1.0, &[]);
    let text = tab_text(&p.score(&bass), TEXT_WIDTH);
    assert!(text.contains("\n   r   l.r. let ring\nG|-2-2-2-2|-2-2----||\n"), "{text}");
    assert!(text.ends_with("\nlet ring, l.r., r  let ring: the notes ring on\n"), "{text}");
}

// ---------------------------------------------------------------- what always holds

#[test]
fn every_note_is_in_the_text_exactly_once() {
    for (name, inst, p) in cases() {
        let score = p.score(&inst);
        let want = written(&score);
        let cell = cell_width(&score);
        let strings = inst.string_count();
        for width in [MIN_TEXT_WIDTH, TEXT_WIDTH, MAX_TEXT_WIDTH] {
            let text = tab_text(&score, width);
            let s = systems(&text, strings);
            // Each string's line from the first bar to the last, and its bars.
            let mut got: Vec<Vec<(u8, String)>> = Vec::new();
            for string in 0..strings {
                let line: String = s.iter().map(|sys| body(&sys.lines[string])).collect();
                let line = line.strip_suffix("||").unwrap_or_else(|| panic!("{name}: the last bar closes with two bar lines\n{text}"));
                let bars: Vec<&str> = line.split('|').collect();
                got.resize(bars.len(), Vec::new());
                for (b, bar) in bars.iter().enumerate() {
                    got[b].extend(cells(bar, cell, &name).into_iter().map(|t| (string as u8 + 1, t)));
                }
            }
            for bar in &mut got {
                bar.sort();
            }
            assert_eq!(got, want, "{name}, width {width}: bar for bar, the notes of the tab staff\n{text}");

            // A "?" per doubtful column and a "!" per column with a note that has no place.
            let above: String = s.iter().flat_map(|sys| &sys.above).cloned().collect();
            let (doubt, lost) = marks(&score);
            assert_eq!((above.matches('?').count(), above.matches('!').count()), (doubt, lost), "{name}, width {width}\n{text}");
            // Each of those notes is named once in the legend.
            let no_place = p.fingering.notes.iter().filter(|n| n.string.is_none()).count();
            // The legend's line may run on over indented lines, and names the notes of twelve bars.
            let legend: Vec<&str> = text.rsplit("\n\n").next().unwrap().lines().skip_while(|l| !l.starts_with("!  ")).enumerate().take_while(|(i, l)| *i == 0 || l.starts_with(' ')).map(|(_, l)| l.trim()).collect();
            let legend = legend.join(" ");
            let named: usize = legend.split_once("not in the lines: ").map_or(0, |(_, bars)| {
                bars.split("; ").map(|at| at.strip_prefix("and ").and_then(|n| n.strip_suffix(" more")).map_or_else(|| at.split_once(": ").unwrap().1.split(' ').count(), |n| n.parse().unwrap())).sum()
            });
            assert_eq!(named, no_place, "{name}: notes named after the !\n{text}");
        }
    }
}

#[test]
fn columns_are_in_line_on_every_instrument() {
    for (name, inst, p) in cases() {
        let score = p.score(&inst);
        let cell = cell_width(&score);
        let text = tab_text(&score, TEXT_WIDTH);
        let s = systems(&text, inst.string_count());
        assert!(!s.is_empty(), "{name}");
        for sys in &s {
            let bar_lines = |l: &str| l.chars().enumerate().filter(|(_, c)| *c == '|').map(|(i, _)| i).collect::<Vec<_>>();
            for line in &sys.lines {
                assert_eq!(chars(line), chars(&sys.lines[0]), "{name}: lines of one length\n{text}");
                assert_eq!(bar_lines(line), bar_lines(&sys.lines[0]), "{name}: bar lines under each other\n{text}");
                // Every number starts a cell's width from the one before, so tens stand over ones.
                for bar in body(line).split('|') {
                    cells(bar, cell, &name);
                }
            }
            for row in &sys.above {
                assert!(chars(row) <= chars(&sys.lines[0]), "{name}: nothing above the lines runs past them\n{text}");
                assert_eq!(row.trim_end(), row, "{name}: no spaces at the end of a row");
                let top: Vec<char> = sys.lines[0].chars().collect();
                for (i, c) in row.chars().enumerate() {
                    // A mark stands over the place of a number: the second character of a cell.
                    if c == '?' || c == '!' && row.chars().nth(i + 1) != Some('?') {
                        let first = if c == '?' && i > 0 && row.chars().nth(i - 1) == Some('!') { i - 1 } else { i };
                        let bar_start = top[..first].iter().rposition(|c| *c == '|').unwrap();
                        assert_eq!((first - bar_start - 1) % cell, 1, "{name}: a mark over a number's place\n{text}");
                    }
                    // A bar number stands right after its bar line.
                    if c.is_ascii_digit() && (i == 0 || !row.chars().nth(i - 1).unwrap().is_ascii_digit()) {
                        assert_eq!(top[i - 1], '|', "{name}: a bar number at the start of its bar\n{text}");
                    }
                }
            }
        }
    }
}

#[test]
fn frets_of_two_digits_keep_the_columns() {
    let guitar = preset("guitar-standard").unwrap();
    let mut p = Passage::new();
    for (k, fret) in [9u8, 10, 0, 12, 7, 22, 5, 15].into_iter().enumerate() {
        p.placed(&guitar, 1, fret, 12 * k as i64, 12, 1.0, &[]);
        p.placed(&guitar, 2, 22 - fret, 12 * k as i64, 12, 1.0, &[]);
    }
    let text = tab_text(&p.score(&guitar), TEXT_WIDTH);
    assert!(text.contains("E|-9--10-0--12-7--22-5--15||\nB|-13-12-22-10-15-0--17-7-||\n"), "{text}");
}

#[test]
fn a_line_never_passes_the_width_and_a_bar_is_only_divided_when_it_is_wider_than_the_page() {
    for (name, inst, p) in cases() {
        let score = p.score(&inst);
        let strings = inst.string_count();
        let whole: String = systems(&tab_text(&score, MAX_TEXT_WIDTH), strings).iter().map(|s| body(&s.lines[0]).to_string()).collect();
        // The width of each bar with its closing bar lines.
        let last = whole.matches('|').count() - 2;
        let bars: Vec<usize> = whole.trim_end_matches('|').split('|').enumerate().map(|(i, b)| chars(b) + if i == last { 2 } else { 1 }).collect();
        for width in [MIN_TEXT_WIDTH, 31, 40, TEXT_WIDTH, 100] {
            let text = tab_text(&score, width);
            let s = systems(&text, strings);
            for sys in &s {
                for row in sys.above.iter().chain(&sys.lines) {
                    assert!(chars(row) <= width, "{name}: a row of {} characters on a page of {width}\n{text}", chars(row));
                }
            }
            let joined: String = s.iter().map(|sys| body(&sys.lines[0]).to_string()).collect();
            assert_eq!(joined, whole, "{name}, width {width}: the same bars as on a wide page");

            let room = width - chars(&s[0].lines[0][..s[0].lines[0].find('|').unwrap()]) - 1;
            let (mut bar, mut open) = (0, false);
            for sys in &s {
                let b = body(&sys.lines[0]);
                let closed = b.ends_with('|');
                if open || !closed {
                    assert!(bars[bar] > room, "{name}, width {width}: bar {} of {} characters is divided, with room for {room}\n{text}", bar + 1, bars[bar]);
                    assert_eq!(b.trim_end_matches('|').matches('|').count(), 0, "{name}: a divided bar has its lines to itself\n{text}");
                }
                bar += b.trim_end_matches('|').matches('|').count() + usize::from(closed);
                open = !closed;
            }
            assert_eq!(bar, bars.len(), "{name}, width {width}");
        }
    }
}

#[test]
fn a_bar_wider_than_the_page_takes_lines_of_its_own() {
    let guitar = preset("guitar-standard").unwrap();
    let mut p = Passage::new();
    p.placed(&guitar, 1, 0, 0, 96, 1.0, &[]);
    for k in 0..32 {
        p.placed(&guitar, 2, (k % 13) as u8, 96 + 3 * k, 3, 1.0, &[]);
    }
    p.placed(&guitar, 3, 0, 192, 96, 1.0, &[]);
    let text = tab_text(&p.score(&guitar), 40);
    let s = systems(&text, 6);
    let lines: Vec<&str> = s.iter().map(|sys| sys.lines[1].as_str()).collect();
    assert_eq!(
        lines,
        [
            "B|------------|",
            "B|-0--1--2--3--4--5--6--7--8--9--10-11",
            "B|-12-0--1--2--3--4--5--6--7--8--9--10",
            "B|-11-12-0--1--2--3--4--5-|",
            "B|------------||",
        ],
        "{text}"
    );
    assert_eq!(s.iter().map(|sys| sys.above.first().map(|a| a.trim())).collect::<Vec<_>>(), [Some("1"), Some("2"), None, None, Some("3")]);
}

#[test]
fn the_same_score_gives_the_same_text() {
    for (name, inst, p) in cases() {
        let (a, b) = (p.score(&inst), p.score(&inst));
        assert_eq!(tab_text(&a, TEXT_WIDTH), tab_text(&b, TEXT_WIDTH), "{name}");
        for lang in ["en", "nb"] {
            assert_eq!(instructions(&a, lang), instructions(&b, lang), "{name}");
        }
    }
}

// ---------------------------------------------------------------- playing instructions

#[test]
fn a_bass_line_as_playing_instructions_in_both_languages() {
    let bass = preset("bass-4-standard").unwrap().with_capo(2);
    let mut p = Passage::new();
    p.placed(&bass, 4, 3, -12, 12, 1.0, &[]);
    p.placed(&bass, 3, 0, 0, 24, 1.0, &[]);
    p.placed(&bass, 3, 3, 36, 12, 0.3, &[]);
    p.placed(&bass, 2, 0, 48, 12, 1.0, &[]);
    p.placed(&bass, 2, 2, 60, 12, 1.0, &[Technique::HammerOn]);
    p.placed(&bass, 1, 0, 72, 120, 1.0, &[Technique::LetRing]);
    p.lost(20, 288, 24);
    p.placed(&bass, 3, 5, 312, 36, 1.0, &[]);
    p.placed(&bass, 3, 7, 348, 36, 1.0, &[Technique::Slide]);
    let score = p.score(&bass).with_tempo(96.0);
    let en = "\
Made-up passage

Bass, 4 strings.
String 1 is the string nearest the floor as you play. String 4 is nearest the ceiling.
Tuning: Standard. Open strings from string 4 to string 1: E, A, D, G.
Capo on fret 2. Frets are counted from the capo.
Tempo: 96 quarter notes per minute.
Time signature: 4 4.
A note marked \"to check\" was not heard clearly.

Pickup
  Beat 4 and. String 4, fret 3. Eighth note.

Bar 1
  Beat 1. String 3, open. Quarter note.
  Beat 2. Eighth rest.
  Beat 2 and. String 3, fret 3, to check. Eighth note.
  Beat 3. String 2, open. Eighth note.
  Beat 3 and. String 2, fret 2, hammer-on. Eighth note.
  Beat 4. String 1, open, let ring. Quarter note tied to whole note.

Bar 2
  Held from bar 1.

Bar 3
  Whole-bar rest.

Bar 4
  Beat 1. G-sharp 0, no string to play it on. Quarter note.
  Beat 2. String 3, fret 5. Quarter note tied to eighth note.
  Beat 3 and. String 3, fret 7, slide from fret 5. Eighth note tied to quarter note.
";
    let nb = "\
Made-up passage

Bass, 4 strenger.
Streng 1 er strengen nærmest gulvet når du spiller. Streng 4 er nærmest taket.
Stemming: Standard. Løse strenger fra streng 4 til streng 1: E, A, D, G.
Capo på bånd 2. Båndene telles fra capoen.
Tempo: 96 fjerdedelsnoter per minutt.
Taktart: 4 fjerdedeler.
En tone merket «bør sjekkes» ble ikke hørt tydelig.

Opptakt
  Slag 4-og. Streng 4, bånd 3. Åttendedelsnote.

Takt 1
  Slag 1. Streng 3, løs. Fjerdedelsnote.
  Slag 2. Åttendedelspause.
  Slag 2-og. Streng 3, bånd 3, bør sjekkes. Åttendedelsnote.
  Slag 3. Streng 2, løs. Åttendedelsnote.
  Slag 3-og. Streng 2, bånd 2, hammer-on. Åttendedelsnote.
  Slag 4. Streng 1, løs, la klinge. Fjerdedelsnote bundet til helnote.

Takt 2
  Holdes fra takt 1.

Takt 3
  Pause hele takten.

Takt 4
  Slag 1. Giss 0, ingen streng å spille den på. Fjerdedelsnote.
  Slag 2. Streng 3, bånd 5. Fjerdedelsnote bundet til åttendedelsnote.
  Slag 3-og. Streng 3, bånd 7, slide fra bånd 5. Åttendedelsnote bundet til fjerdedelsnote.
";
    assert_eq!(instructions(&score, "en"), en);
    assert_eq!(instructions(&score, "nb"), nb);
    assert_eq!(instructions(&score, "nb-NO"), nb);
}

#[test]
fn a_chord_is_said_from_its_highest_numbered_string_and_repeated_bars_point_back() {
    let uke = preset("ukulele-high-g").unwrap();
    let mut p = Passage::new();
    for bar in [0, 1, 4] {
        for (string, fret) in [(1, 3), (2, 0), (3, 0), (4, 0)] {
            p.placed(&uke, string, fret, 96 * bar, 48, 1.0, &[Technique::LetRing]);
        }
        p.placed(&uke, 2, 1, 96 * bar + 48, 16, 1.0, &[]);
        p.placed(&uke, 2, 3, 96 * bar + 64, 8, 1.0, &[]);
        p.placed(&uke, 1, 0, 96 * bar + 72, 24, 1.0, &[Technique::DeadNote]);
    }
    let score = p.score(&uke);
    let en = instructions(&score, "en");
    assert!(
        en.ends_with(
            "\
Bar 1
  Beat 1. Chord, 4 notes, let ring: string 4, open; string 3, open; string 2, open; string 1, fret 3. Half note.
  Beat 3. String 2, fret 1. Quarter note in a triplet.
  Beat 3, triplet 3. String 2, fret 3. Eighth note in a triplet.
  Beat 4. String 1, dead note. Quarter note.

Bar 2
  Same as bar 1.

Bars 3\u{2013}4
  Rest, 2 bars.

Bar 5
  Same as bar 1.
"
        ),
        "{en}"
    );
    let nb = instructions(&score, "nb");
    assert!(nb.starts_with("Made-up passage\n\nUkulele (høy G), 4 strenger.\n"), "{nb}");
    assert!(
        nb.ends_with(
            "\
Takt 1
  Slag 1. Akkord, 4 toner, la klinge: streng 4, løs; streng 3, løs; streng 2, løs; streng 1, bånd 3. Halvnote.
  Slag 3. Streng 2, bånd 1. Fjerdedelsnote i triol.
  Slag 3, triol 3. Streng 2, bånd 3. Åttendedelsnote i triol.
  Slag 4. Streng 1, dempet tone. Fjerdedelsnote.

Takt 2
  Samme som takt 1.

Takt 3\u{2013}4
  Pause, 2 takter.

Takt 5
  Samme som takt 1.
"
        ),
        "{nb}"
    );
}

#[test]
fn open_strings_are_named_in_words_in_each_language() {
    let inst = preset("guitar-eb-standard").unwrap();
    let mut p = Passage::new();
    p.placed(&inst, 1, 0, 0, 96, 1.0, &[]);
    let score = p.score(&inst);
    assert!(instructions(&score, "en").contains("Tuning: E-flat standard. Open strings from string 6 to string 1: E-flat, A-flat, D-flat, G-flat, B-flat, E-flat.\n"));
    assert!(instructions(&score, "nb").contains("Stemming: Ess standard. Løse strenger fra streng 6 til streng 1: Ess, Ass, Dess, Gess, B, Ess.\n"));
    let standard = preset("guitar-standard").unwrap();
    let mut p = Passage::new();
    p.placed(&standard, 1, 0, 0, 96, 1.0, &[]);
    assert!(instructions(&p.score(&standard), "nb").contains("E, A, D, G, H, E.\n"), "B natural is H in Norwegian");
}

/// The lines of the bars of playing instructions, by bar number (0 is the pickup); a bar that
/// points back holds the lines of the bar it names.
fn bar_lines(text: &str, bar: &str, pickup: &str, same: &str) -> BTreeMap<usize, Vec<String>> {
    let mut out: BTreeMap<usize, Vec<String>> = BTreeMap::new();
    let mut numbers: Vec<usize> = Vec::new();
    for line in text.lines() {
        if let Some(said) = line.strip_prefix("  ") {
            for n in &numbers {
                match said.strip_prefix(same).map(|n| n.trim_end_matches('.').parse::<usize>().unwrap()) {
                    Some(earlier) => {
                        let lines = out[&earlier].clone();
                        out.insert(*n, lines);
                    }
                    None => out.entry(*n).or_default().push(said.to_string()),
                }
            }
        } else if line == pickup {
            numbers = vec![0];
        } else if let Some(n) = line.strip_prefix(bar).filter(|n| n.starts_with(' ') || n.starts_with("s ")) {
            let n = n.trim_start_matches('s').trim();
            let ends: Vec<usize> = n.split('\u{2013}').map(|x| x.parse().unwrap()).collect();
            numbers = (ends[0]..=*ends.last().unwrap()).collect();
        } else {
            numbers.clear();
        }
    }
    out
}

/// (string, what is played on it) for every note a line of instructions says.
fn said(line: &str, string: &str, fret: &str, open: &str, dead: &str) -> Vec<(u8, String)> {
    let lower = line.to_lowercase();
    lower
        .match_indices(&format!("{string} "))
        .filter_map(|(i, m)| {
            let rest = &lower[i + m.len()..];
            let n: u8 = rest.split(',').next()?.parse().ok()?;
            let what = rest.split(", ").nth(1)?;
            let what = what.split(['.', ';', ',']).next()?;
            Some((n, if what == open { "0".to_string() } else if what == dead { "x".to_string() } else { what.strip_prefix(&format!("{fret} "))?.to_string() }))
        })
        .collect()
}

#[test]
fn the_instructions_say_every_note_once_and_the_same_in_both_languages() {
    for (name, inst, p) in cases() {
        let score = p.score(&inst);
        let (en, nb) = (instructions(&score, "en"), instructions(&score, "nb"));

        // The same structure: line for line a heading, a blank line or a line said under a heading.
        let shape = |text: &str| text.lines().skip(1).map(|l| (l.is_empty(), l.starts_with("  "))).collect::<Vec<_>>();
        assert_eq!(shape(&en), shape(&nb), "{name}\n{en}\n{nb}");
        let en_bars = bar_lines(&en, "Bar", "Pickup", "Same as bar ");
        let nb_bars = bar_lines(&nb, "Takt", "Opptakt", "Samme som takt ");
        assert_eq!(en_bars.keys().collect::<Vec<_>>(), nb_bars.keys().collect::<Vec<_>>(), "{name}");

        // Bar for bar the notes of the tab staff, where they start. A dead note has no fret said,
        // and vibrato is a word of its own.
        let want: Vec<Vec<(u8, String)>> = written(&score)
            .into_iter()
            .map(|bar| {
                let mut bar: Vec<(u8, String)> = bar.into_iter().map(|(s, t)| (s, t.trim_end_matches('~').to_string())).collect();
                bar.sort();
                bar
            })
            .collect();
        let first = if en_bars.contains_key(&0) { 0 } else { 1 };
        assert_eq!(en_bars.len(), want.len(), "{name}: a heading for every bar\n{en}");
        for (k, want) in want.iter().enumerate() {
            let number = first + k;
            let notes = |bars: &BTreeMap<usize, Vec<String>>, words: [&str; 4]| {
                let mut notes: Vec<(u8, String)> = bars[&number].iter().flat_map(|l| said(l, words[0], words[1], words[2], words[3])).collect();
                notes.sort();
                notes
            };
            assert_eq!(&notes(&en_bars, ["string", "fret", "open", "dead note"]), want, "{name}, bar {number}\n{en}");
            assert_eq!(&notes(&nb_bars, ["streng", "bånd", "løs", "dempet tone"]), want, "{name}, bar {number}\n{nb}");
        }
        // A note with no place is named where it starts.
        let no_place = p.fingering.notes.iter().filter(|n| n.string.is_none()).count();
        let named = |bars: &BTreeMap<usize, Vec<String>>, words: &str| bars.values().flatten().map(|l| l.matches(words).count()).sum::<usize>();
        assert_eq!(named(&en_bars, "no string to play it on"), no_place, "{name}\n{en}");
        assert_eq!(named(&nb_bars, "ingen streng å spille den på"), no_place, "{name}\n{nb}");
    }
}

// ---------------------------------------------------------------- wording

/// Where each line of the bars says it is: what stands before the string or the rest.
fn positions(text: &str, bar: &str) -> Vec<String> {
    text.lines().skip_while(|l| !l.starts_with(bar)).filter_map(|l| l.strip_prefix("  ")).map(|l| l.split(". ").take_while(|part| !part.starts_with("Str") && !part.ends_with("rest.") && !part.ends_with("pause.")).collect::<Vec<_>>().join(". ")).collect()
}

#[test]
fn in_six_eight_the_parts_of_a_beat_are_its_eighths_and_sixteenths_not_a_triplet() {
    let guitar = preset("guitar-standard").unwrap();
    let mut p = Passage::new();
    for k in 0..3 {
        p.placed(&guitar, 1, k as u8, 12 * k, 12, 1.0, &[]);
    }
    for k in 0..6 {
        p.placed(&guitar, 2, k as u8, 36 + 6 * k, 6, 1.0, &[]);
    }
    // The second bar: a dotted quarter, a rest of an eighth, and two eighths.
    p.placed(&guitar, 3, 0, 72, 36, 1.0, &[]);
    p.placed(&guitar, 3, 2, 120, 12, 1.0, &[]);
    p.placed(&guitar, 3, 4, 132, 12, 1.0, &[]);
    let score = p.score(&guitar).with_meter(6, 8);
    let (en, nb) = (instructions(&score, "en"), instructions(&score, "nb"));
    assert_eq!(
        positions(&en, "Bar 1"),
        [
            "Beat 1",
            "Beat 1, eighth 2",
            "Beat 1, eighth 3",
            "Beat 2",
            "Beat 2, sixteenth 2",
            "Beat 2, eighth 2",
            "Beat 2, sixteenth 4",
            "Beat 2, eighth 3",
            "Beat 2, sixteenth 6",
            "Beat 1",
            "Beat 2",
            "Beat 2, eighth 2",
            "Beat 2, eighth 3",
        ],
        "{en}"
    );
    assert_eq!(
        positions(&nb, "Takt 1"),
        [
            "Slag 1",
            "Slag 1, 2. åttendedel",
            "Slag 1, 3. åttendedel",
            "Slag 2",
            "Slag 2, 2. sekstendedel",
            "Slag 2, 2. åttendedel",
            "Slag 2, 4. sekstendedel",
            "Slag 2, 3. åttendedel",
            "Slag 2, 6. sekstendedel",
            "Slag 1",
            "Slag 2",
            "Slag 2, 2. åttendedel",
            "Slag 2, 3. åttendedel",
        ],
        "{nb}"
    );
    assert!(en.contains("\n  Beat 1, eighth 2. String 1, fret 1. Eighth note.\n") && en.contains("\n  Beat 2, sixteenth 2. String 2, fret 1. Sixteenth note.\n"), "{en}");
    assert!(en.contains("\nBar 2\n  Beat 1. String 3, open. Dotted quarter note.\n  Beat 2. Eighth rest.\n"), "{en}");
    assert!(nb.contains("\n  Slag 1, 2. åttendedel. Streng 1, bånd 1. Åttendedelsnote.\n"), "{nb}");
    for text in [&en, &nb] {
        assert!(!text.contains("triplet") && !text.contains("triol") && !text.contains("plus"), "{text}");
    }
    assert!(en.contains("\nTime signature: 6 8.\n") && nb.contains("\nTaktart: 6 åttendedeler.\n"));

    // Twelve eighths are four beats of three, nine are three.
    for (beats, last) in [(12, "Beat 4, eighth 3"), (9, "Beat 3, eighth 3")] {
        let mut p = Passage::new();
        for k in 0..beats {
            p.placed(&guitar, 1, 0, 12 * k, 12, 1.0, &[]);
        }
        let en = instructions(&p.score(&guitar).with_meter(beats, 8), "en");
        assert_eq!(positions(&en, "Bar 1").last().map(String::as_str), Some(last), "{en}");
        assert!(!en.contains("triplet"), "{en}");
    }
}

#[test]
fn a_triplet_is_only_said_where_one_is_written_and_three_eight_counts_its_eighths() {
    let guitar = preset("guitar-standard").unwrap();
    // Three eighths in the time of two, in 4/4: a triplet.
    let mut p = Passage::new();
    for k in 0..3 {
        p.placed(&guitar, 1, 0, 8 * k, 8, 1.0, &[]);
    }
    p.placed(&guitar, 1, 0, 24, 12, 1.0, &[]);
    p.placed(&guitar, 1, 0, 36, 12, 1.0, &[]);
    let en = instructions(&p.score(&guitar), "en");
    assert_eq!(positions(&en, "Bar 1"), ["Beat 1", "Beat 1, triplet 2", "Beat 1, triplet 3", "Beat 2", "Beat 2 and", "Beat 3"], "{en}");
    assert!(en.contains("  Beat 1, triplet 2. String 1, open. Eighth note in a triplet.\n"), "{en}");
    let nb = instructions(&p.score(&guitar), "nb");
    assert_eq!(positions(&nb, "Takt 1")[..5], ["Slag 1", "Slag 1, triol 2", "Slag 1, triol 3", "Slag 2", "Slag 2-og"], "{nb}");

    // 3/8 is counted in eighths: each is a beat, and a sixteenth is the "and".
    let mut p = Passage::new();
    for (k, start) in [0, 12, 18, 24].into_iter().enumerate() {
        p.placed(&guitar, 1, k as u8, start, 6, 1.0, &[]);
    }
    let en = instructions(&p.score(&guitar).with_meter(3, 8), "en");
    assert_eq!(positions(&en, "Bar 1"), ["Beat 1", "Beat 1 and", "Beat 2", "Beat 2 and", "Beat 3", "Beat 3 and"], "{en}");
}

#[test]
fn one_bar_with_many_missing_notes_is_broken_at_the_width_and_capped_too() {
    let bass = preset("bass-4-standard").unwrap();
    let mut p = Passage::new();
    for k in 0..32 {
        p.lost(k % 12, 3 * i64::from(k), 3);
    }
    let score = p.score(&bass);
    for width in [MIN_TEXT_WIDTH, TEXT_WIDTH, MAX_TEXT_WIDTH] {
        let text = tab_text(&score, width);
        let legend: Vec<&str> = text.rsplit("\n\n").next().unwrap().lines().collect();
        assert!(legend[0].starts_with("!  a note with no string"), "{text}");
        assert!(legend.iter().all(|l| l.chars().count() <= width), "width {width}\n{text}");
        let joined = legend.iter().map(|l| l.trim()).collect::<Vec<_>>().join(" ");
        let (_, notes) = joined.split_once("not in the lines: bar 1: ").unwrap();
        let (named, more) = notes.split_once("; ").unwrap();
        assert_eq!((named.split(' ').count(), more), (24, "and 8 more"), "{joined}");
        assert!(legend.iter().all(|l| !l.ends_with("1:") && !l.ends_with(" and")), "{text}");
    }
}

#[test]
fn a_tuning_is_named_in_norwegian_with_h_for_b_on_every_preset() {
    let names = [
        ("guitar-standard", "Standard", "Standard"),
        ("guitar-eb-standard", "E-flat standard", "Ess standard"),
        ("guitar-d-standard", "D standard", "D standard"),
        ("guitar-c-standard", "C standard", "C standard"),
        ("guitar-drop-d", "Drop D", "Drop D"),
        ("guitar-drop-c", "Drop C", "Drop C"),
        ("guitar-drop-b", "Drop B", "Drop H"),
        ("guitar-dadgad", "DADGAD", "DADGAD"),
        ("guitar-open-g", "Open G", "Open G"),
        ("guitar-open-d", "Open D", "Open D"),
        ("guitar-open-e", "Open E", "Open E"),
        ("guitar-7-standard", "B standard", "H standard"),
        ("guitar-7-eb-standard", "E-flat standard", "Ess standard"),
        ("guitar-8-standard", "F-sharp standard", "Fiss standard"),
        ("bass-4-standard", "Standard", "Standard"),
        ("bass-4-eb-standard", "E-flat standard", "Ess standard"),
        ("bass-4-d-standard", "D standard", "D standard"),
        ("bass-4-drop-d", "Drop D", "Drop D"),
        ("bass-4-bead", "BEAD", "HEAD"),
        ("bass-5-standard", "Standard", "Standard"),
        ("bass-5-drop-a", "Drop A", "Drop A"),
        ("bass-6-standard", "Standard", "Standard"),
        ("ukulele-high-g", "GCEA high G", "GCEA høy G"),
        ("ukulele-low-g", "GCEA low G", "GCEA lav G"),
        ("ukulele-baritone", "DGBE", "DGHE"),
        ("mandolin", "GDAE", "GDAE"),
    ];
    assert_eq!(names.iter().map(|n| n.0).collect::<Vec<_>>(), PRESET_IDS, "every preset");
    for (id, en, nb) in names {
        let inst = preset(id).unwrap();
        let mut p = Passage::new();
        p.placed(&inst, 1, 0, 0, 96, 1.0, &[]);
        let score = p.score(&inst);
        assert!(instructions(&score, "en").contains(&format!("\nTuning: {en}. Open strings from string ")), "{id}\n{}", instructions(&score, "en"));
        let said = instructions(&score, "nb");
        assert!(said.contains(&format!("\nStemming: {nb}. Løse strenger fra streng ")), "{id}\n{said}");
    }
    // A name of someone's own is kept, but for its note names and its signs.
    let mut own = preset("guitar-standard").unwrap();
    own.tuning.name = "Bob's B\u{266d} thing".into();
    let mut p = Passage::new();
    p.placed(&own, 1, 0, 0, 96, 1.0, &[]);
    assert!(instructions(&p.score(&own), "nb").contains("\nStemming: Bob's B thing. "));
    assert!(instructions(&p.score(&own), "en").contains("\nTuning: Bob's B-flat thing. "));
}

#[test]
fn time_signatures_are_said_plainly_in_each_language() {
    let bass = preset("bass-4-standard").unwrap();
    for (beats, unit, en, nb) in [
        (4, 4, "Time signature: 4 4.", "Taktart: 4 fjerdedeler."),
        (3, 4, "Time signature: 3 4.", "Taktart: 3 fjerdedeler."),
        (2, 2, "Time signature: 2 2.", "Taktart: 2 halve."),
        (1, 1, "Time signature: 1 1.", "Taktart: 1 hel."),
        (2, 1, "Time signature: 2 1.", "Taktart: 2 hele."),
        (1, 2, "Time signature: 1 2.", "Taktart: 1 halv."),
        (1, 4, "Time signature: 1 4.", "Taktart: 1 fjerdedel."),
        (6, 8, "Time signature: 6 8.", "Taktart: 6 åttendedeler."),
        (5, 16, "Time signature: 5 16.", "Taktart: 5 sekstendedeler."),
    ] {
        let score = Passage::new().score(&bass).with_meter(beats, unit);
        assert!(instructions(&score, "en").contains(&format!("\n{en}\n")), "{}", instructions(&score, "en"));
        assert!(instructions(&score, "nb").contains(&format!("\n{nb}\n")), "{}", instructions(&score, "nb"));
    }
}

#[test]
fn a_language_is_en_or_nb_with_or_without_a_region() {
    let bass = preset("bass-4-standard").unwrap();
    let score = Passage::new().score(&bass);
    let (en, nb) = (instructions(&score, "en"), instructions(&score, "nb"));
    for tag in ["EN", "en-GB", "en_US", "en-Latn-US"] {
        assert_eq!(instructions(&score, tag), en, "{tag}");
    }
    for tag in ["NB", "nb-NO", "nb_NO", "no", "no-NO", "no_NO", "NO"] {
        assert_eq!(instructions(&score, tag), nb, "{tag}");
    }
    for tag in ["", "nn", "nn-NO", "english", "norsk", "nox", "nbx", "enx", "e", "de", " en"] {
        let e = write_playing_instructions(&score, &TabOptions::default(), &text_options(TEXT_WIDTH, tag)).unwrap_err();
        assert!(e.contains("en or nb"), "{tag}: {e}");
    }
}

#[test]
fn a_mandolin_is_known_by_its_strings_not_by_what_it_is_called() {
    let said = |inst: &Instrument| {
        let mut p = Passage::new();
        p.placed(inst, 1, 2, 0, 96, 1.0, &[]);
        instructions(&p.score(inst), "en")
    };
    let mut renamed = preset("mandolin").unwrap().with_capo(2);
    renamed.name = "My F-style".into();
    assert!(said(&renamed).contains("\nMy F-style, 4 pairs of strings. Each pair is played as one string and has one number.\n"), "{}", said(&renamed));
    let mut guitar = preset("guitar-standard").unwrap();
    guitar.name = "Mandolin".into();
    assert!(said(&guitar).contains("\nMandolin, 6 strings.\n"), "{}", said(&guitar));
    let nb = {
        let inst = preset("mandolin").unwrap();
        let mut p = Passage::new();
        p.placed(&inst, 1, 2, 0, 96, 1.0, &[]);
        instructions(&p.score(&inst), "nb")
    };
    assert!(nb.contains("\nMandolin, 4 strengepar. Hvert par spilles som én streng og har ett nummer.\n"), "{nb}");
}

#[test]
fn a_slide_or_a_bend_names_the_fret_it_comes_from_only_on_its_own_string() {
    let guitar = preset("guitar-standard").unwrap();
    for (technique, mark, en_from, en_bare, nb_bare) in [(Technique::Slide, '/', "slide from fret 5", "slide", "slide"), (Technique::Bend, 'b', "bend up from fret 5", "bend up", "bend opp")] {
        // From the fifth fret to the seventh of the same string.
        let mut same = Passage::new();
        same.placed(&guitar, 2, 5, 0, 48, 1.0, &[]);
        same.placed(&guitar, 2, 7, 48, 48, 1.0, &[technique]);
        let score = same.score(&guitar);
        assert!(tab_text(&score, TEXT_WIDTH).contains(&format!("\nB|-5--{mark}7--||\n")), "{}", tab_text(&score, TEXT_WIDTH));
        assert!(instructions(&score, "en").contains(&format!("  Beat 3. String 2, fret 7, {en_from}. Half note.\n")), "{}", instructions(&score, "en"));

        // The note before is on another string, a whole step below: its fret is not where this note comes from.
        let mut other = Passage::new();
        other.placed(&guitar, 3, 9, 0, 48, 1.0, &[]);
        other.placed(&guitar, 2, 7, 48, 48, 1.0, &[technique]);
        let score = other.score(&guitar);
        let text = tab_text(&score, TEXT_WIDTH);
        assert!(text.contains(&format!("\nB|----{mark}7--||\nG|-9------||\n")), "{text}");
        let en = instructions(&score, "en");
        assert!(en.contains(&format!("  Beat 3. String 2, fret 7, {en_bare}. Half note.\n")), "{en}");
        assert!(!en.contains("from fret"), "{en}");
        let nb = instructions(&score, "nb");
        assert!(nb.contains(&format!("  Slag 3. Streng 2, bånd 7, {nb_bare}. Halvnote.\n")) && !nb.contains("fra bånd"), "{nb}");
    }
    // A slide down is drawn down only when it is known to come from above.
    let mut down = Passage::new();
    down.placed(&guitar, 2, 9, 0, 48, 1.0, &[]);
    down.placed(&guitar, 2, 7, 48, 48, 1.0, &[Technique::Slide]);
    assert!(tab_text(&down.score(&guitar), TEXT_WIDTH).contains("\nB|-9--\\7--||\n"));
}

#[test]
fn a_slide_or_a_bend_over_a_note_on_another_string_names_the_fret_it_comes_from() {
    let guitar = preset("guitar-standard").unwrap();
    for (technique, mark, en) in [(Technique::Slide, '/', "slide from fret 3"), (Technique::Bend, 'b', "bend up from fret 3")] {
        // String 1 fret 3, the open sixth string, then string 1 fret 5: the same note the MusicXML
        // links it from.
        let mut p = Passage::new();
        p.placed(&guitar, 1, 3, 0, 12, 1.0, &[]);
        p.placed(&guitar, 6, 0, 12, 12, 1.0, &[]);
        p.placed(&guitar, 1, 5, 24, 72, 1.0, &[technique]);
        let score = p.score(&guitar);
        let text = tab_text(&score, TEXT_WIDTH);
        assert!(text.contains(&format!("\nE|-3--{mark}5----------||\n")), "{text}");
        let said = instructions(&score, "en");
        assert!(said.contains(&format!("  Beat 2. String 1, fret 5, {en}. Quarter note tied to half note.\n")), "{said}");
    }
}

#[test]
fn a_title_cannot_pass_for_a_line_of_the_header() {
    let bass = preset("bass-4-standard").unwrap();
    let mut p = Passage::new();
    p.placed(&bass, 1, 2, 0, 96, 1.0, &[]);
    let title = "Song\u{2028}Capo: fret 7\u{2029}\nTempo: 300\r\u{202E}txt.exe\u{202C}\u{2066}a\u{2069}\u{200B}\u{200C}\u{200E}\u{200F}\u{061C}\u{2060}\u{00AD}\u{FEFF}";
    let mut own = bass.clone();
    own.name = "Bass\u{2028}Capo: fret 9".into();
    own.tuning.name = "Standard\u{2029}Time: 9/8\u{202E}".into();
    let hidden = |c: char| c.is_control() && c != '\n' || matches!(c, '\u{2028}' | '\u{2029}' | '\u{202A}'..='\u{202E}' | '\u{2066}'..='\u{2069}' | '\u{200B}'..='\u{200F}' | '\u{061C}' | '\u{2060}' | '\u{00AD}' | '\u{FEFF}');
    let score = TabScore::new(title, &own, &p.notes, &p.techniques, &p.fingering).unwrap();
    let text = tab_text(&score, TEXT_WIDTH);
    assert!(text.starts_with("Song Capo: fret 7 Tempo: 300 txt.exea\nBass Capo: fret 9\nTuning: Standard Time: 9/8 (E A D G), bottom line to top\nCapo: none\nTempo: 120 quarter notes per minute\nTime: 4/4\n\n"), "{text:?}");
    assert!(!text.contains(hidden), "{text:?}");
    for lang in ["en", "nb"] {
        let said = instructions(&score, lang);
        assert!(said.starts_with("Song Capo: fret 7 Tempo: 300 txt.exea\n\nBass Capo: fret 9, 4 str"), "{said:?}");
        assert!(!said.contains(hidden), "{said:?}");
        assert_eq!(said.lines().filter(|l| l.starts_with("Capo") || l.starts_with("No capo") || l.starts_with("Ingen capo")).count(), 1, "{said}");
    }
    // The joiner inside an emoji stays, so the emoji stays whole.
    let family = "Song for \u{1F469}\u{200D}\u{1F3A4}";
    let joined = TabScore::new(family, &bass, &p.notes, &p.techniques, &p.fingering).unwrap();
    assert!(tab_text(&joined, TEXT_WIDTH).starts_with(&format!("{family}\nBass\n")) && instructions(&joined, "nb").starts_with(&format!("{family}\n\n")));
    // A title of nothing but such characters is no title.
    let blank = TabScore::new("\u{200B}\u{FEFF} \u{2028}", &bass, &p.notes, &p.techniques, &p.fingering).unwrap();
    assert!(tab_text(&blank, TEXT_WIDTH).starts_with("Bass\n") && instructions(&blank, "en").starts_with("Bass, 4 strings.\n"));
}

#[test]
fn the_legend_names_missing_notes_bar_by_bar_within_the_width_and_counts_the_rest() {
    let bass = preset("bass-4-standard").unwrap();
    let mut p = Passage::new();
    p.lost(5, 0, 24);
    p.lost(7, 24, 24);
    for bar in 1..15 {
        p.lost(5 + bar as i32 % 3, 96 * bar, 48);
    }
    p.lost(7, 96 * 14 + 48, 48);
    let score = p.score(&bass);
    for width in [MIN_TEXT_WIDTH, 40, TEXT_WIDTH] {
        let text = tab_text(&score, width);
        let legend: Vec<&str> = text.rsplit("\n\n").next().unwrap().lines().collect();
        assert!(legend[0].starts_with("!  a note with no string"), "{text}");
        assert!(legend.iter().all(|l| l.chars().count() <= width), "width {width}\n{text}");
        assert!(legend[1..].iter().all(|l| l.starts_with("   ") && !l.starts_with("    ")), "the words go on under the first\n{text}");
        // A bar stays with its notes: no line ends between them.
        assert!(legend.iter().all(|l| !l.ends_with("bar") && !l.ends_with(':') || l.ends_with("lines:")), "{text}");
        assert!(legend.iter().all(|l| !l.ends_with(" and") && !l.trim().starts_with("more")), "{text}");
        let joined = legend.iter().map(|l| l.trim()).collect::<Vec<_>>().join(" ");
        assert!(joined.contains("not in the lines: bar 1: F-1 G-1; bar 2: Gb-1; bar 3: G-1; "), "{joined}");
        assert!(joined.ends_with("; bar 12: G-1; and 4 more"), "{joined}");
        assert!(!joined.contains("bar 13"), "{joined}");
    }
}

// ---------------------------------------------------------------- what is refused

#[test]
fn an_empty_passage_is_one_empty_bar() {
    let bass = preset("bass-4-standard").unwrap();
    let score = Passage::new().score(&bass);
    assert!(tab_text(&score, TEXT_WIDTH).ends_with("\n  1\nG|--------||\nD|--------||\nA|--------||\nE|--------||\n"));
    assert!(instructions(&score, "en").ends_with("\nBar 1\n  Whole-bar rest.\n"));
}

#[test]
fn a_width_or_a_language_that_cannot_be_written_is_refused() {
    let bass = preset("bass-4-standard").unwrap();
    let score = Passage::new().score(&bass);
    for width in [0, MIN_TEXT_WIDTH - 1, MAX_TEXT_WIDTH + 1, usize::MAX] {
        let e = write_tab_text(&score, &TabOptions::default(), &text_options(width, "en")).unwrap_err();
        assert!(e.contains("characters"), "{e}");
    }
    for lang in ["", "de", "sv", "nn"] {
        let e = write_playing_instructions(&score, &TabOptions::default(), &text_options(TEXT_WIDTH, lang)).unwrap_err();
        assert!(e.contains("en or nb"), "{e}");
    }
    // The doubt threshold is checked as for the MusicXML.
    let doubt = TabOptions { doubt_below: 2.0, ..TabOptions::default() };
    assert!(write_tab_text(&score, &doubt, &TextOptions::default()).is_err());
    assert!(write_playing_instructions(&score, &doubt, &TextOptions::default()).is_err());
}

fn request(notes: usize, text: &str) -> String {
    let notes: Vec<String> = (0..notes).map(|i| format!(r#"{{"pitch": 40, "start": {}, "dur": 24}}"#, 24 * i)).collect();
    format!(r#"{{"title": "Line", "instrument": {{"preset": "bass-4-standard"}}, "notes": [{}]{text}}}"#, notes.join(","))
}

#[test]
fn the_json_request_is_the_tab_request_with_text_options() {
    let text = tab_text_json(&request(4, "")).unwrap();
    assert!(text.starts_with("Line\nBass\n") && text.contains("\nD|-2-2-2-2||\n"), "{text}");
    assert!(playing_instructions_json(&request(4, "")).unwrap().contains("\nBar 1\n  Beat 1. String 2, fret 2. Quarter note.\n"));
    assert!(playing_instructions_json(&request(4, r#", "text": {"lang": "nb"}"#)).unwrap().contains("\nTakt 1\n  Slag 1. Streng 2, bånd 2. Fjerdedelsnote.\n"));
    // 12 bars on a narrow page: three bars to a line.
    let narrow = tab_text_json(&request(48, r#", "text": {"width": 32}"#)).unwrap();
    assert_eq!(systems(&narrow, 4).len(), 4, "{narrow}");
    assert!(narrow.lines().all(|l| l.chars().count() <= 32 || !l.contains('|')), "{narrow}");

    for (bad, says) in [(r#", "text": {"wide": 1}"#, "unknown field `wide`"), (r#", "text": {"width": 3}"#, "characters"), (r#", "text": {"lang": "de"}"#, "en or nb")] {
        let e = tab_text_json(&request(1, bad)).and_then(|_| playing_instructions_json(&request(1, bad))).unwrap_err();
        assert!(e.contains(says), "{bad}: {e}");
    }
}

#[test]
fn a_passage_at_the_cap_is_written_in_time_that_grows_with_its_length() {
    // 20,000 sixteenths: 1,250 bars. Written in well under a second each; a minute would mean a
    // loop over the whole passage per note or per bar.
    let notes: Vec<String> = (0..MAX_NOTES).map(|i| format!(r#"{{"pitch": {}, "start": {}, "dur": 6}}"#, 40 + (i * 7) % 12, 6 * i)).collect();
    let request = format!(r#"{{"instrument": {{"preset": "bass-5-standard"}}, "notes": [{}], "text": {{"lang": "nb"}}}}"#, notes.join(","));
    let started = std::time::Instant::now();
    let text = tab_text_json(&request).unwrap();
    let said = playing_instructions_json(&request).unwrap();
    assert!(started.elapsed().as_secs() < 60, "{:?}", started.elapsed());
    assert!(text.contains("\n  1249") && said.contains("\nTakt 1250\n"));
}

#[test]
fn more_notes_than_the_cap_are_refused() {
    let over = request(MAX_NOTES + 1, "");
    for answer in [tab_text_json(&over), playing_instructions_json(&over)] {
        assert!(answer.unwrap_err().contains("at most 20000 notes"));
    }
}
