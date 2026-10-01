//! Tablature as MusicXML 4.0: a tab staff, a notation staff, or both, from a solved fingering.
//!
//! [`TabScore`] holds what is written: the title, the instrument, tempo, meter and key, and each
//! note with its string and fret. [`write_tab_musicxml`] turns it into one partwise document.
//! The same input always gives the same text.
//!
//! One rhythmic voice is written. Notes that start together are a chord; a chord lasts until its
//! longest note ends or the next note starts, whichever comes first.

use brasscribe_core::model::{check_span, Composition, Note, TICKS_PER_BEAT};
use brasscribe_core::notation::xml::El;
use brasscribe_core::rhythm_spelling::{is_value, pieces};
use brasscribe_core::spelling::{spell, Spelled};
use serde::{Deserialize, Serialize};

use crate::instrument::Instrument;
use crate::solve::Fingering;
use crate::technique::{per_note, previous_note, Technique};

/// Notes below this confidence are marked as doubtful unless [`TabOptions::doubt_below`] says
/// otherwise.
pub const DOUBT_BELOW: f64 = 0.4;
/// Colour of a doubtful note.
pub const DOUBT_COLOR: &str = "#9A5200";
/// Target of the processing instruction that carries a doubtful note's confidence, as the last
/// child of its `<note>`: `<?brasscribe-confidence 0.31?>`.
pub const CONFIDENCE: &str = "brasscribe-confidence";
/// Divisions per quarter note: durations are written in the model's ticks.
const DIVISIONS: i64 = TICKS_PER_BEAT;
/// Ticks of a whole note.
const WHOLE: i64 = 4 * TICKS_PER_BEAT;
/// Ticks of a dotted quarter: the beat of compound time.
const DOTTED_QUARTER: i64 = 36;
/// The largest bend written, in semitones.
const MAX_BEND: i32 = 4;

/// Which staves are written.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Layout {
    /// A tab staff alone, with stems and beams so the rhythm can be drawn under it.
    Tab,
    /// One part with two staves: notation above, tab below, the same notes on both.
    #[default]
    TabAndNotation,
    /// A notation staff alone.
    Notation,
}

/// The clef of the notation staff. Pitches are written as they sound; the `8vb` clefs carry the
/// octave an instrument is written above its sound.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum NotationClef {
    Treble,
    /// Treble clef sounding an octave lower: guitar.
    #[serde(rename = "treble-8vb")]
    Treble8vb,
    /// Bass clef sounding an octave lower: bass guitar.
    #[serde(rename = "bass-8vb")]
    Bass8vb,
}

impl NotationClef {
    /// The clef an instrument is usually written in, from its open strings: bass clef 8vb when
    /// the highest open string is below E3, treble 8vb when the lowest is below C3, else treble
    /// at pitch.
    pub fn for_instrument(inst: &Instrument) -> NotationClef {
        let open = || inst.tuning.strings.iter().map(|s| s.open_pitch);
        match (open().min(), open().max()) {
            (_, Some(hi)) if hi < 52 => NotationClef::Bass8vb,
            (Some(lo), _) if lo < 48 => NotationClef::Treble8vb,
            _ => NotationClef::Treble,
        }
    }
}

/// How a capo is written on the tab staff. Frets are relative to the capo either way, and the
/// header names it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum CapoEncoding {
    /// `<staff-tuning>` holds the tuning without the capo, and `<capo>` the capo fret.
    #[default]
    Element,
    /// `<staff-tuning>` holds the open strings as they sound with the capo on, and there is no
    /// `<capo>`: for readers that ignore the element.
    Tuning,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct TabOptions {
    pub layout: Layout,
    /// A note with a confidence below this is marked as doubtful. 0 marks none.
    pub doubt_below: f64,
    /// The notation staff's clef; None picks [`NotationClef::for_instrument`].
    pub clef: Option<NotationClef>,
    pub capo: CapoEncoding,
}

impl Default for TabOptions {
    fn default() -> Self {
        TabOptions { layout: Layout::default(), doubt_below: DOUBT_BELOW, clef: None, capo: CapoEncoding::default() }
    }
}

/// One note as it is written: the sounding pitch, where it is played and how.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TabNote {
    /// Concert MIDI pitch.
    pub pitch: i32,
    /// Ticks from the first downbeat; negative in a pickup.
    pub start: i64,
    pub dur: i64,
    pub confidence: f64,
    /// 1 = the highest tab line. None when the note has no place on the instrument.
    pub string: Option<u8>,
    /// Relative to the capo; 0 = open.
    pub fret: Option<u8>,
    /// No string of the instrument can sound the pitch.
    pub out_of_range: bool,
    pub techniques: Vec<Technique>,
}

/// Everything one tablature document holds.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TabScore {
    pub title: String,
    pub instrument: Instrument,
    /// Quarter notes per minute.
    pub tempo_bpm: f64,
    /// Time signature: `beats` over `beat_unit`.
    pub beats: i64,
    pub beat_unit: i64,
    /// Key signature: sharps (positive) or flats (negative).
    pub fifths: i32,
    /// "major" or "minor"; anything else is left out of the file.
    pub mode: String,
    pub notes: Vec<TabNote>,
}

impl TabScore {
    /// A score in 4/4, C major, at 120 BPM from the solver's input and output. `techniques` is
    /// empty or one list per note; `fingering` has one place per note.
    pub fn new(title: &str, instrument: &Instrument, notes: &[Note], techniques: &[Vec<Technique>], fingering: &Fingering) -> Result<TabScore, String> {
        instrument.validate()?;
        let techniques = per_note(techniques, notes.len())?;
        if fingering.notes.len() != notes.len() {
            return Err(format!("the fingering places {} notes, not the {} notes of the passage", fingering.notes.len(), notes.len()));
        }
        let strings = instrument.string_count();
        let mut out = Vec::with_capacity(notes.len());
        for (i, ((n, place), techniques)) in notes.iter().zip(&fingering.notes).zip(techniques).enumerate() {
            check_span(n.start, n.end()).map_err(|e| format!("note {i}: {e}"))?;
            if !(0..=127).contains(&n.pitch) {
                return Err(format!("note {i}: pitch {} is outside MIDI 0-127", n.pitch));
            }
            if place.pitch != n.pitch {
                return Err(format!("note {i}: the fingering is for pitch {}, the note is {}", place.pitch, n.pitch));
            }
            let position = place.position();
            if let Some(p) = position {
                if p.string == 0 || usize::from(p.string) > strings {
                    return Err(format!("note {i}: string {} is not on an instrument with {strings} strings", p.string));
                }
            }
            out.push(TabNote {
                pitch: n.pitch,
                start: n.start,
                dur: n.dur,
                confidence: n.confidence,
                string: position.map(|p| p.string),
                fret: position.map(|p| p.fret),
                out_of_range: place.out_of_range,
                techniques,
            });
        }
        Ok(TabScore { title: title.into(), instrument: instrument.clone(), tempo_bpm: 120.0, beats: 4, beat_unit: 4, fifths: 0, mode: "major".into(), notes: out })
    }

    pub fn with_tempo(mut self, bpm: f64) -> Self {
        self.tempo_bpm = bpm;
        self
    }

    pub fn with_meter(mut self, beats: i64, beat_unit: i64) -> Self {
        self.beats = beats;
        self.beat_unit = beat_unit;
        self
    }

    pub fn with_key(mut self, fifths: i32, mode: &str) -> Self {
        self.fifths = fifths;
        self.mode = mode.into();
        self
    }

    /// Tempo, first time signature and first key of a composition. Later meter and key changes are
    /// not written.
    pub fn with_composition(mut self, comp: &Composition) -> Self {
        self.tempo_bpm = comp.bpm();
        if let Some(m) = comp.meters.first() {
            self.beats = m.beats;
            self.beat_unit = m.beat_unit;
        }
        if let Some(k) = comp.keys.first() {
            self.fifths = k.fifths;
            self.mode = k.mode.clone();
        }
        self
    }
}

/// A slur-like link between a note and the note it leads to.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Link {
    HammerOn,
    PullOff,
    Slide,
    /// A bend of this many semitones, written on the note it starts from.
    Bend(i32),
    /// The arc that joins a bent note to the note it was bent from.
    BendArc,
}

impl Link {
    /// Drawn as a slur.
    fn is_arc(self) -> bool {
        matches!(self, Link::HammerOn | Link::PullOff | Link::BendArc)
    }
}

/// One written note of a chord, after notes that sound as one are merged.
#[derive(Debug, Clone)]
struct Written {
    pitch: i32,
    confidence: f64,
    place: Option<(u8, u8)>,
    vibrato: bool,
    let_ring: bool,
    dead: bool,
    /// Links that start here, with their number.
    starts: Vec<(Link, u8)>,
    /// Links that end here.
    stops: Vec<(Link, u8)>,
    spelled: Spelled,
}

/// Notes that start together, low to high.
#[derive(Debug, Clone)]
struct Event {
    start: i64,
    end: i64,
    notes: Vec<Written>,
}

/// A note, chord or rest as written: one symbol.
#[derive(Debug, Clone)]
struct Symbol {
    start: i64,
    end: i64,
    /// None for a rest.
    event: Option<usize>,
    /// First and last symbol of its event (a tied note has several).
    first: bool,
    last: bool,
    /// A rest that fills its measure.
    whole_measure: bool,
    tuplet_start: bool,
    tuplet_stop: bool,
    beams: Vec<&'static str>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Staff {
    Notation,
    Tab,
}

/// Written type, dots and whether it is a triplet value, for a length in ticks.
fn value(len: i64) -> Option<(&'static str, u8, bool)> {
    Some(match len {
        96 => ("whole", 0, false),
        72 => ("half", 1, false),
        48 => ("half", 0, false),
        36 => ("quarter", 1, false),
        24 => ("quarter", 0, false),
        18 => ("eighth", 1, false),
        12 => ("eighth", 0, false),
        9 => ("16th", 1, false),
        6 => ("16th", 0, false),
        3 => ("32nd", 0, false),
        16 => ("quarter", 0, true),
        8 => ("eighth", 0, true),
        4 => ("16th", 0, true),
        _ => return None,
    })
}

/// Readable (start, end) pieces of [start, end) in compound time, where the beat is a dotted
/// quarter: split at bar lines, and at the beat unless the value starts on a beat and fills whole
/// beats.
fn compound_pieces(start: i64, end: i64, bar: i64) -> Vec<(i64, i64)> {
    let mut out = Vec::new();
    let mut at = start;
    while at < end {
        let in_bar = at.rem_euclid(bar);
        let left = (end - at).min(bar - in_bar);
        let in_beat = in_bar % DOTTED_QUARTER;
        // On a beat a value may fill whole beats; anywhere it may stay inside its beat.
        let fits = |n: i64| n <= left && is_value(n) && if in_beat == 0 { n <= DOTTED_QUARTER || n % DOTTED_QUARTER == 0 } else { in_beat + n <= DOTTED_QUARTER };
        let reach = if in_beat == 0 { left } else { left.min(DOTTED_QUARTER - in_beat) };
        let len = (1..=reach).rev().find(|&n| fits(n)).unwrap_or(reach);
        out.push((at, at + len));
        at += len;
    }
    out
}

/// Beams a written type carries: 1 for an eighth, 2 for a 16th, 3 for a 32nd.
fn beam_levels(len: i64) -> usize {
    match value(len).map(|v| v.0) {
        Some("eighth") => 1,
        Some("16th") => 2,
        Some("32nd") => 3,
        _ => 0,
    }
}

/// A tempo as text: a whole number without a fraction, any other with two decimals.
fn number(x: f64) -> String {
    if x.fract() == 0.0 {
        format!("{x:.0}")
    } else {
        format!("{x:.2}")
    }
}

const SHARP_NAMES: [(char, i32); 12] = [('C', 0), ('C', 1), ('D', 0), ('D', 1), ('E', 0), ('F', 0), ('F', 1), ('G', 0), ('G', 1), ('A', 0), ('A', 1), ('B', 0)];
const FLAT_NAMES: [(char, i32); 12] = [('C', 0), ('D', -1), ('D', 0), ('E', -1), ('E', 0), ('F', 0), ('G', -1), ('G', 0), ('A', -1), ('A', 0), ('B', -1), ('B', 0)];

/// Whether a tuning's open strings are named with flats. A tuning named with a flat or sharp sign
/// decides it; otherwise the side whose accidentals come earlier in the order of key signatures
/// wins, and sharps on a tie.
fn uses_flats(name: &str, open_pitches: &[i32]) -> bool {
    if name.contains('\u{266d}') {
        return true;
    }
    if name.contains('\u{266f}') {
        return false;
    }
    // Position of each black key in the order sharps (F C G D A) and flats (B E A D G) are added.
    const SHARP_RANK: [i32; 12] = [0, 2, 0, 4, 0, 0, 1, 0, 3, 0, 5, 0];
    const FLAT_RANK: [i32; 12] = [0, 4, 0, 2, 0, 0, 5, 0, 3, 0, 1, 0];
    let worst = |rank: &[i32; 12]| open_pitches.iter().map(|p| rank[p.rem_euclid(12) as usize]).max().unwrap_or(0);
    worst(&FLAT_RANK) < worst(&SHARP_RANK)
}

/// Step, alter and octave of an open string.
fn open_name(pitch: i32, flats: bool) -> (char, i32, i32) {
    let (step, alter) = if flats { FLAT_NAMES } else { SHARP_NAMES }[pitch.rem_euclid(12) as usize];
    (step, alter, pitch.div_euclid(12) - 1)
}

/// The open strings from the bottom tab line to the top, for the header: "E A D G B E".
fn tuning_text(inst: &Instrument) -> String {
    let open: Vec<i32> = inst.tuning.strings.iter().map(|s| s.open_pitch).collect();
    let flats = uses_flats(&inst.tuning.name, &open);
    let names: Vec<String> = open
        .iter()
        .rev()
        .map(|&p| {
            let (step, alter, _) = open_name(p, flats);
            match alter {
                1 => format!("{step}\u{266f}"),
                -1 => format!("{step}\u{266d}"),
                _ => step.to_string(),
            }
        })
        .collect();
    names.join(" ")
}

/// The header line: tuning name, open strings low line to high, and the capo when set.
pub fn header_text(inst: &Instrument) -> String {
    let mut text = format!("{}: {}", inst.tuning.name, tuning_text(inst));
    if inst.capo > 0 {
        text.push_str(&format!(", Capo {}", inst.capo));
    }
    text
}

/// What the writer needs, with out-of-bounds values replaced by ones that can be written.
struct Plan<'a> {
    score: &'a TabScore,
    opts: &'a TabOptions,
    clef: NotationClef,
    bar: i64,
    /// 3/8, 6/8, 9/8, 12/8: the beat is a dotted quarter.
    compound: bool,
    /// Ticks of one beam group: the beat.
    beam_group: i64,
    events: Vec<Event>,
    /// (start, end, number, implicit) per measure.
    measures: Vec<(i64, i64, usize, bool)>,
    symbols: Vec<Symbol>,
}

fn doubtful(n: &Written, opts: &TabOptions) -> bool {
    n.confidence < opts.doubt_below
}

/// Group the notes into chords, merge notes that sound as one, and pair up the techniques.
fn events(score: &TabScore) -> Vec<Event> {
    let notes = &score.notes;
    let kept: Vec<usize> = {
        let mut k: Vec<usize> = (0..notes.len()).filter(|&i| notes[i].dur > 0).collect();
        k.sort_by_key(|&i| (notes[i].start, notes[i].pitch, i));
        k
    };
    let place = |i: usize| notes[i].string.zip(notes[i].fret).filter(|_| !notes[i].out_of_range);
    // Where each kept note ends up: (event, note in event).
    let mut slot: Vec<Option<(usize, usize)>> = vec![None; notes.len()];
    let mut events: Vec<Event> = Vec::new();
    for &i in &kept {
        let n = &notes[i];
        if events.last().is_none_or(|e| e.start != n.start) {
            events.push(Event { start: n.start, end: n.start, notes: Vec::new() });
        }
        let e = events.len() - 1;
        let ev = &mut events[e];
        ev.end = ev.end.max(n.start + n.dur);
        let has = |t: Technique| n.techniques.contains(&t);
        // Two notes of one pitch on one position sound as one note.
        if let Some(k) = ev.notes.iter().position(|w| w.pitch == n.pitch && w.place == place(i)) {
            let w = &mut ev.notes[k];
            w.confidence = w.confidence.max(n.confidence);
            w.vibrato |= has(Technique::Vibrato);
            w.let_ring |= has(Technique::LetRing);
            w.dead |= has(Technique::DeadNote);
            slot[i] = Some((e, k));
            continue;
        }
        slot[i] = Some((e, ev.notes.len()));
        ev.notes.push(Written {
            pitch: n.pitch,
            confidence: n.confidence,
            place: place(i),
            vibrato: has(Technique::Vibrato),
            let_ring: has(Technique::LetRing),
            dead: has(Technique::DeadNote),
            starts: Vec::new(),
            stops: Vec::new(),
            spelled: Spelled { step: 'C', alter: 0, octave: 4 },
        });
    }
    for i in 0..events.len() {
        if let Some(next) = events.get(i + 1).map(|e| e.start) {
            events[i].end = events[i].end.min(next);
        }
    }

    // Pitch spelling over the written notes, in order.
    let flat: Vec<(usize, usize)> = events.iter().enumerate().flat_map(|(e, ev)| (0..ev.notes.len()).map(move |k| (e, k))).collect();
    let onsets: Vec<f64> = flat.iter().map(|&(e, _)| events[e].start as f64 / TICKS_PER_BEAT as f64).collect();
    let pitches: Vec<i32> = flat.iter().map(|&(e, k)| events[e].notes[k].pitch).collect();
    for (&(e, k), s) in flat.iter().zip(spell(&onsets, &pitches)) {
        events[e].notes[k].spelled = s;
    }

    // A slide, hammer-on, pull-off or bend links the note it comes from to the note that has it.
    let model: Vec<Note> = notes.iter().map(|n| Note::new(n.pitch, n.start, n.dur, n.confidence, Vec::new())).collect();
    for &i in &kept {
        let Some(to) = slot[i] else { continue };
        for &t in &notes[i].techniques {
            if !t.keeps_string() {
                continue;
            }
            let Some(from) = previous_note(&model, i).and_then(|j| slot[j]) else { continue };
            let links: &[Link] = match t {
                Technique::HammerOn => &[Link::HammerOn],
                Technique::PullOff => &[Link::PullOff],
                Technique::Slide => &[Link::Slide],
                Technique::Bend => {
                    let up = notes[i].pitch - events[from.0].notes[from.1].pitch;
                    if (1..=MAX_BEND).contains(&up) {
                        &[Link::Bend(up), Link::BendArc]
                    } else {
                        continue;
                    }
                }
                _ => continue,
            };
            for &link in links {
                if events[from.0].notes[from.1].starts.iter().any(|&(l, _)| l == link) {
                    continue;
                }
                // Arcs that leave the same chord are numbered apart, and so are slides.
                let number = match link {
                    Link::Bend(_) => 1,
                    _ => 1 + events[from.0].notes.iter().flat_map(|w| &w.starts).filter(|&&(l, _)| !matches!(l, Link::Bend(_)) && l.is_arc() == link.is_arc()).count().min(5) as u8,
                };
                events[from.0].notes[from.1].starts.push((link, number));
                events[to.0].notes[to.1].stops.push((link, number));
            }
        }
    }
    events
}

impl<'a> Plan<'a> {
    fn new(score: &'a TabScore, opts: &'a TabOptions) -> Plan<'a> {
        let beat_unit = if [1, 2, 4, 8, 16].contains(&score.beat_unit) { score.beat_unit } else { 4 };
        let beats = score.beats.clamp(1, 32);
        let bar = beats * WHOLE / beat_unit;
        let compound = beat_unit == 8 && beats % 3 == 0;
        let beam_group = if compound { DOTTED_QUARTER } else { TICKS_PER_BEAT };
        let events = events(score);

        let first = events.first().map_or(0, |e| e.start);
        let last = events.last().map_or(0, |e| e.end);
        let mut measures = Vec::new();
        let mut at = if first < 0 { first.div_euclid(bar) * bar } else { 0 };
        if first < 0 && -first < bar {
            // A pickup shorter than a bar: an unnumbered measure before measure 1.
            measures.push((first, 0, 0, true));
            at = 0;
        }
        let mut n = 1;
        while at < last || n == 1 {
            measures.push((at, at + bar, n, false));
            at += bar;
            n += 1;
        }

        let mut plan = Plan { score, opts, clef: opts.clef.unwrap_or_else(|| NotationClef::for_instrument(&score.instrument)), bar, compound, beam_group, events, measures, symbols: Vec::new() };
        plan.lay_out();
        plan
    }

    /// A span as tied values that show the beat.
    fn split(&self, start: i64, end: i64) -> Vec<(i64, i64)> {
        if self.compound {
            compound_pieces(start, end, self.bar)
        } else {
            pieces(start, end, self.bar)
        }
    }

    fn rest(&mut self, from: i64, to: i64) {
        let spans: Vec<(i64, i64)> = self.measures.iter().map(|&(a, b, _, _)| (a.max(from), b.min(to))).filter(|(a, b)| a < b).collect();
        for (a, b) in spans {
            let whole = self.measures.iter().any(|&(ma, mb, _, _)| (ma, mb) == (a, b));
            let parts = if whole { vec![(a, b)] } else { self.split(a, b) };
            for (s, e) in parts {
                self.symbols.push(Symbol { start: s, end: e, event: None, first: true, last: true, whole_measure: whole, tuplet_start: false, tuplet_stop: false, beams: Vec::new() });
            }
        }
    }

    /// Notes and rests in time order, split into tied values that show the beat, then tuplets and
    /// beams per measure.
    fn lay_out(&mut self) {
        let mut at = self.measures[0].0;
        for e in 0..self.events.len() {
            let (start, end) = (self.events[e].start, self.events[e].end);
            self.rest(at, start);
            let parts = self.split(start, end);
            let count = parts.len();
            for (k, (s, e2)) in parts.into_iter().enumerate() {
                self.symbols.push(Symbol { start: s, end: e2, event: Some(e), first: k == 0, last: k + 1 == count, whole_measure: false, tuplet_start: false, tuplet_stop: false, beams: Vec::new() });
            }
            at = end;
        }
        let end = self.measures.last().map_or(at, |m| m.1);
        self.rest(at, end);

        let (bar, group) = (self.bar, self.beam_group);
        let measure_of = |s: &Symbol| s.start.div_euclid(bar);
        let n = self.symbols.len();
        // Triplets: a bracket from the first triplet value to the one that ends on a beat.
        let triplet = |s: &Symbol| value(s.end - s.start).is_some_and(|v| v.2);
        let mut open = false;
        for i in 0..n {
            if !triplet(&self.symbols[i]) {
                continue;
            }
            if !open {
                self.symbols[i].tuplet_start = true;
                open = true;
            }
            let next_joins = i + 1 < n && triplet(&self.symbols[i + 1]) && measure_of(&self.symbols[i + 1]) == measure_of(&self.symbols[i]);
            if self.symbols[i].end.rem_euclid(TICKS_PER_BEAT) == 0 || !next_joins {
                self.symbols[i].tuplet_stop = true;
                open = false;
            }
        }
        // Beams: runs of notes shorter than a quarter inside one beat.
        let levels: Vec<usize> = self.symbols.iter().map(|s| if s.event.is_some() { beam_levels(s.end - s.start) } else { 0 }).collect();
        let cell = |s: &Symbol| (measure_of(s), (s.start - measure_of(s) * bar).div_euclid(group));
        let joined = |a: usize, b: usize, k: usize| levels[a] >= k && levels[b] >= k && cell(&self.symbols[a]) == cell(&self.symbols[b]);
        let mut beams: Vec<Vec<&'static str>> = vec![Vec::new(); n];
        for i in 0..n {
            let before = |k: usize| i > 0 && joined(i - 1, i, k);
            let after = |k: usize| i + 1 < n && joined(i, i + 1, k);
            if !before(1) && !after(1) {
                continue;
            }
            for k in 1..=levels[i] {
                beams[i].push(match (before(k), after(k)) {
                    (false, true) => "begin",
                    (true, true) => "continue",
                    (true, false) => "end",
                    (false, false) if before(1) => "backward hook",
                    (false, false) => "forward hook",
                });
            }
        }
        for (s, b) in self.symbols.iter_mut().zip(beams) {
            s.beams = b;
        }
    }

    fn has_tab(&self) -> bool {
        self.opts.layout != Layout::Notation
    }

    fn two_staves(&self) -> bool {
        self.opts.layout == Layout::TabAndNotation
    }

    /// The staff that carries the techniques and the "?" and "!" marks: the tab staff when there
    /// is one.
    fn marks_on(&self, staff: Staff) -> bool {
        staff == Staff::Tab || !self.has_tab()
    }

    fn staff_number(&self, staff: Staff) -> Option<u8> {
        self.two_staves().then_some(if staff == Staff::Tab { 2 } else { 1 })
    }

    fn words(&self, text: &str, staff: Staff) -> El {
        let mut d = El::new("direction").attr("placement", "above").child(El::new("direction-type").child(El::text("words", text)));
        if let Some(n) = self.staff_number(staff) {
            d.push(El::text("staff", n.to_string()));
        }
        d
    }

    fn attributes(&self) -> El {
        let score = self.score;
        let inst = &score.instrument;
        let mut a = El::new("attributes").child(El::text("divisions", DIVISIONS.to_string()));
        let mut key = El::new("key").child(El::text("fifths", score.fifths.clamp(-7, 7).to_string()));
        if score.mode == "major" || score.mode == "minor" {
            key.push(El::text("mode", score.mode.as_str()));
        }
        a.push(key);
        let beat_unit = if [1, 2, 4, 8, 16].contains(&score.beat_unit) { score.beat_unit } else { 4 };
        a.push(El::new("time").child(El::text("beats", score.beats.clamp(1, 32).to_string())).child(El::text("beat-type", beat_unit.to_string())));
        if self.two_staves() {
            a.push(El::text("staves", "2"));
        }
        let numbered = |el: El, staff: Staff| match self.staff_number(staff) {
            Some(n) => el.attr("number", n.to_string()),
            None => el,
        };
        if self.opts.layout != Layout::Tab {
            let (sign, line) = if self.clef == NotationClef::Bass8vb { ("F", "4") } else { ("G", "2") };
            let mut clef = numbered(El::new("clef"), Staff::Notation).child(El::text("sign", sign)).child(El::text("line", line));
            if self.clef != NotationClef::Treble {
                clef.push(El::text("clef-octave-change", "-1"));
            }
            a.push(clef);
        }
        if self.has_tab() {
            a.push(numbered(El::new("clef"), Staff::Tab).child(El::text("sign", "TAB")).child(El::text("line", "5")));
            let strings = &inst.tuning.strings;
            let mut details = numbered(El::new("staff-details"), Staff::Tab).child(El::text("staff-lines", strings.len().to_string()));
            let baked = self.opts.capo == CapoEncoding::Tuning;
            // String 1 first, as the instrument has them.
            let open: Vec<i32> = strings.iter().enumerate().map(|(i, s)| inst.open_pitch(i as u8 + 1).filter(|_| baked).unwrap_or(s.open_pitch)).collect();
            let flats = uses_flats(if baked && inst.capo > 0 { "" } else { &inst.tuning.name }, &open);
            // Line 1 is the bottom line: the last string in tab order.
            for (line, &pitch) in open.iter().rev().enumerate() {
                let (step, alter, octave) = open_name(pitch, flats);
                let mut t = El::new("staff-tuning").attr("line", (line + 1).to_string()).child(El::text("tuning-step", step.to_string()));
                if alter != 0 {
                    t.push(El::text("tuning-alter", alter.to_string()));
                }
                t.push(El::text("tuning-octave", octave.to_string()));
                details.push(t);
            }
            if inst.capo > 0 && !baked {
                details.push(El::text("capo", inst.capo.to_string()));
            }
            a.push(details);
        }
        a
    }

    /// Tempo and the tuning header, at the start of the first measure.
    fn opening(&self, out: &mut El) {
        let top = if self.opts.layout == Layout::Tab { Staff::Tab } else { Staff::Notation };
        out.push(self.words(&header_text(&self.score.instrument), top));
        let bpm = if self.score.tempo_bpm.is_finite() && self.score.tempo_bpm > 0.0 { self.score.tempo_bpm.clamp(10.0, 600.0) } else { 120.0 };
        let mut d = El::new("direction")
            .attr("placement", "above")
            .child(El::new("direction-type").child(El::new("metronome").child(El::text("beat-unit", "quarter")).child(El::text("per-minute", number(bpm)))));
        if let Some(n) = self.staff_number(top) {
            d.push(El::text("staff", n.to_string()));
        }
        d.push(El::new("sound").attr("tempo", number(bpm)));
        out.push(d);
    }

    /// The symbols of one measure on one staff.
    fn staff(&self, range: (i64, i64), staff: Staff, out: &mut El) {
        let marks = self.marks_on(staff);
        let voice = if staff == Staff::Tab && self.two_staves() { "5" } else { "1" };
        // Rhythm is drawn on the notation staff, or under the tab when it stands alone.
        let rhythm = !(staff == Staff::Tab && self.two_staves());
        for sym in self.symbols.iter().filter(|s| range.0 <= s.start && s.start < range.1) {
            let len = sym.end - sym.start;
            let written = value(len);
            let event = sym.event.map(|e| &self.events[e]);
            if let (Some(ev), true, true) = (event, marks, sym.first) {
                if ev.notes.iter().any(|n| n.place.is_none()) {
                    out.push(self.words("!", staff));
                }
                if ev.notes.iter().any(|n| doubtful(n, self.opts)) {
                    out.push(self.words("?", staff));
                }
                let rings = |e: &Event| e.notes.iter().any(|n| n.let_ring);
                let ringing_before = sym.event.and_then(|e| e.checked_sub(1)).is_some_and(|p| rings(&self.events[p]) && self.events[p].end == ev.start);
                if rings(ev) && !ringing_before {
                    out.push(self.words("let ring", staff));
                }
            }
            let chord: Vec<Option<&Written>> = match event {
                Some(ev) => ev.notes.iter().map(Some).collect(),
                None => vec![None],
            };
            for (k, w) in chord.into_iter().enumerate() {
                let mut note = El::new("note");
                if w.is_some_and(|w| doubtful(w, self.opts)) {
                    note.set("color", DOUBT_COLOR);
                }
                match w {
                    Some(w) => {
                        if k > 0 {
                            note.push(El::new("chord"));
                        }
                        let mut pitch = El::new("pitch").child(El::text("step", w.spelled.step.to_string()));
                        if w.spelled.alter != 0 {
                            pitch.push(El::text("alter", w.spelled.alter.to_string()));
                        }
                        pitch.push(El::text("octave", w.spelled.octave.to_string()));
                        note.push(pitch);
                    }
                    None if sym.whole_measure => note.push(El::new("rest").attr("measure", "yes")),
                    None => note.push(El::new("rest")),
                }
                note.push(El::text("duration", len.to_string()));
                if w.is_some() {
                    if !sym.first {
                        note.push(El::new("tie").attr("type", "stop"));
                    }
                    if !sym.last {
                        note.push(El::new("tie").attr("type", "start"));
                    }
                }
                note.push(El::text("voice", voice));
                if let (Some((typ, dots, triplet)), false) = (written, sym.whole_measure) {
                    note.push(El::text("type", typ));
                    for _ in 0..dots {
                        note.push(El::new("dot"));
                    }
                    if triplet {
                        note.push(El::new("time-modification").child(El::text("actual-notes", "3")).child(El::text("normal-notes", "2")));
                    }
                }
                if let Some(w) = w {
                    if staff == Staff::Tab {
                        note.push(El::text("stem", if rhythm && len < WHOLE { "down" } else { "none" }));
                    }
                    let doubt = doubtful(w, self.opts);
                    if w.dead || doubt {
                        let mut head = El::text("notehead", if w.dead { "x" } else { "normal" });
                        if doubt {
                            head.set("color", DOUBT_COLOR);
                        }
                        note.push(head);
                    }
                }
                if let Some(n) = self.staff_number(staff) {
                    note.push(El::text("staff", n.to_string()));
                }
                if w.is_some() && rhythm && k == 0 {
                    for (level, b) in sym.beams.iter().enumerate() {
                        note.push(El::text("beam", *b).attr("number", (level + 1).to_string()));
                    }
                }
                let mut notations = El::new("notations");
                if let Some(w) = w {
                    self.notations(w, sym, staff, &mut notations);
                }
                if k == 0 && rhythm && (sym.tuplet_start || sym.tuplet_stop) {
                    if sym.tuplet_stop && !sym.tuplet_start {
                        notations.children.insert(0, El::new("tuplet").attr("type", "stop"));
                    } else if sym.tuplet_start && !sym.tuplet_stop {
                        notations.children.insert(0, El::new("tuplet").attr("type", "start").attr("bracket", "yes"));
                    }
                }
                if !notations.children.is_empty() {
                    note.push(notations);
                }
                if let Some(w) = w.filter(|w| sym.first && doubtful(w, self.opts)) {
                    note.push(El::text(CONFIDENCE, format!("{:.2}", w.confidence.clamp(0.0, 1.0))));
                }
                out.push(note);
            }
        }
    }

    /// Ties, techniques, string and fret.
    fn notations(&self, w: &Written, sym: &Symbol, staff: Staff, out: &mut El) {
        let marks = self.marks_on(staff);
        if !sym.first {
            out.push(El::new("tied").attr("type", "stop"));
        }
        if !sym.last {
            out.push(El::new("tied").attr("type", "start"));
        } else if w.let_ring && marks {
            out.push(El::new("tied").attr("type", "let-ring"));
        }
        // Arcs on the second staff of a pair are numbered apart from the first's.
        let offset = if staff == Staff::Tab && self.two_staves() { 6 } else { 0 };
        let stops = || w.stops.iter().filter(|_| sym.first);
        let starts = || w.starts.iter().filter(|_| sym.last);
        for &(_, n) in stops().filter(|(l, _)| l.is_arc()) {
            out.push(El::new("slur").attr("type", "stop").attr("number", (n + offset).to_string()));
        }
        for &(_, n) in starts().filter(|(l, _)| l.is_arc()) {
            out.push(El::new("slur").attr("type", "start").attr("number", (n + offset).to_string()));
        }
        if marks {
            for &(_, n) in stops().filter(|(l, _)| *l == Link::Slide) {
                out.push(El::new("slide").attr("type", "stop").attr("number", n.to_string()));
            }
            for &(_, n) in starts().filter(|(l, _)| *l == Link::Slide) {
                out.push(El::new("slide").attr("type", "start").attr("line-type", "solid").attr("number", n.to_string()));
            }
            if w.vibrato && sym.first {
                out.push(El::new("ornaments").child(El::new("wavy-line").attr("type", "start").attr("number", "1")).child(El::new("wavy-line").attr("type", "stop").attr("number", "1")));
            }
        }
        let mut technical = El::new("technical");
        if staff == Staff::Tab {
            if let Some((string, fret)) = w.place {
                technical.push(El::text("string", string.to_string()));
                technical.push(El::text("fret", fret.to_string()));
            }
        }
        if marks {
            let legato = |l: Link| match l {
                Link::HammerOn => Some(("hammer-on", "H")),
                Link::PullOff => Some(("pull-off", "P")),
                _ => None,
            };
            for &(l, n) in stops() {
                if let Some((name, _)) = legato(l) {
                    technical.push(El::new(name).attr("type", "stop").attr("number", n.to_string()));
                }
            }
            for &(l, n) in starts() {
                if let Some((name, text)) = legato(l) {
                    technical.push(El::text(name, text).attr("type", "start").attr("number", n.to_string()));
                }
                if let Link::Bend(up) = l {
                    technical.push(El::new("bend").child(El::text("bend-alter", up.to_string())));
                }
            }
        }
        if !technical.children.is_empty() {
            out.push(technical);
        }
    }

    fn document(&self) -> String {
        let score = self.score;
        let mut root = El::new("score-partwise").attr("version", "4.0");
        if !score.title.is_empty() {
            root.push(El::new("work").child(El::text("work-title", score.title.as_str())));
        }
        root.push(El::new("identification").child(El::new("encoding").child(El::text("software", "Brasscribe"))));
        root.push(El::new("part-list").child(El::new("score-part").attr("id", "P1").child(El::text("part-name", score.instrument.name.as_str()))));
        let mut part = El::new("part").attr("id", "P1");
        let count = self.measures.len();
        for (m, &(a, b, number, implicit)) in self.measures.iter().enumerate() {
            let mut measure = El::new("measure").attr("number", number.to_string());
            if implicit {
                measure.set("implicit", "yes");
            }
            if m == 0 {
                measure.push(self.attributes());
                self.opening(&mut measure);
            }
            match self.opts.layout {
                Layout::Tab => self.staff((a, b), Staff::Tab, &mut measure),
                Layout::Notation => self.staff((a, b), Staff::Notation, &mut measure),
                Layout::TabAndNotation => {
                    self.staff((a, b), Staff::Notation, &mut measure);
                    measure.push(El::new("backup").child(El::text("duration", (b - a).to_string())));
                    self.staff((a, b), Staff::Tab, &mut measure);
                }
            }
            if m + 1 == count {
                measure.push(El::new("barline").attr("location", "right").child(El::text("bar-style", "light-heavy")));
            }
            part.push(measure);
        }
        root.push(part);
        let mut out = String::from("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE score-partwise PUBLIC \"-//Recordare//DTD MusicXML 4.0 Partwise//EN\" \"http://www.musicxml.org/dtds/partwise.dtd\">\n");
        root.write(0, &mut out);
        // The confidence is a processing instruction, which the element tree cannot hold.
        out.replace(&format!("<{CONFIDENCE}>"), &format!("<?{CONFIDENCE} ")).replace(&format!("</{CONFIDENCE}>"), "?>")
    }
}

/// The score as a MusicXML 4.0 partwise document.
pub fn write_tab_musicxml(score: &TabScore, opts: &TabOptions) -> String {
    Plan::new(score, opts).document()
}
