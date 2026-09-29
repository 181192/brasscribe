//! Score building and MusicXML export.
//!
//! The pipeline mirrors the reference's `build_score` + `write_musicxml`:
//! events per part -> ensemble pitch spelling at concert pitch -> measures ->
//! accidentals -> ties at bar lines -> tuplet completion -> beams and stems ->
//! tuplet brackets -> written pitch for transposing parts -> splitting of
//! values that need several tied notes -> MusicXML.

use std::collections::{BTreeMap, HashMap, HashSet};

use super::beams::{get_beams, BDir, BeamInput, BeamSequence, Beams, BT};
use super::duration::{DType, Dur, Rat, TupletType};
use super::pitch::{altered_names, transpose, transpose_key, update_accidental_display, Acc, P};
use super::xml::El as X;
use crate::rhythm_spelling::{is_value, pieces};
use crate::instruments::Instrument;
use crate::quantize::QNote;
use crate::spelling::{key_of, spell};

pub const DIVISIONS: i64 = 10080;
const TPB: i64 = 24;

#[derive(Clone, Debug)]
pub struct PartSpec {
    pub name: String,
    pub notes: Vec<QNote>,
    /// "treble" | "bass"
    pub clef: String,
    /// Transposing band instrument; None = concert-pitch part.
    pub instrument: Option<&'static Instrument>,
    /// Staff label after the first system (default: the instrument's).
    pub abbreviation: Option<String>,
    /// (tick, marking) changes of this part's layer.
    pub dynamics: Vec<(i64, String)>,
}

impl PartSpec {
    pub fn concert(name: &str, notes: Vec<QNote>, clef: &str) -> PartSpec {
        PartSpec { name: name.into(), notes, clef: clef.into(), instrument: None, abbreviation: None, dynamics: Vec::new() }
    }
}

/// A free-time passage for the score: [start, end) ticks, notated at `bpm`.
#[derive(Clone, Debug, PartialEq)]
pub struct FreeSpan {
    pub start: i64,
    pub end: i64,
    pub bpm: f64,
    pub label: String,
}

#[derive(Clone, Debug)]
pub struct ScoreSpec {
    pub parts: Vec<PartSpec>,
    pub beats_per_bar: i64,
    pub bpm: f64,
    pub title: String,
    pub pickup_ticks: i64,
    /// Notes below this confidence are marked "?" (grouped with their neighbours).
    pub low_confidence: f64,
    /// Marks of groups with a note below this confidence are boxed.
    pub very_below: f64,
    pub key_fifths: Option<i32>,
    /// Part name -> MusicXML <instrument-sound>.
    pub sounds: Vec<(String, String)>,
    pub free_spans: Vec<FreeSpan>,
    /// Key changes after the first key: (tick, fifths), at bar lines.
    pub key_changes: Vec<(i64, i32)>,
    /// Rehearsal marks (tick, label), shown on the top part.
    pub rehearsal: Vec<(i64, String)>,
    pub encoding_date: String,
    /// Text above the first tempo mark (musicxml::TEMPO_ESTIMATED when the beat grid is a guess).
    pub tempo_note: Option<String>,
    /// The drum kit a percussion part plays: its 0-based bank 128 program (instruments::KITS), written
    /// as <midi-program> when it is not the band kit (0).
    pub kit_program: i64,
}

// ---------------------------------------------------------------------------
// elements

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Tie {
    Start,
    Continue,
    Stop,
}

#[derive(Clone, Copy, Debug)]
pub struct Unp {
    pub step: u8,
    pub octave: i32,
    pub head: &'static str,
    pub tie: Option<Tie>,
}

#[derive(Clone, Debug)]
pub enum Kind {
    Rest,
    Note(P, Option<Tie>),
    Chord(Vec<(P, Option<Tie>)>),
    Unp(Unp),
    PChord(Vec<Unp>),
}

#[derive(Clone, Debug)]
pub struct Elem {
    pub id: u64,
    pub off: Rat,
    pub dur: Dur,
    pub kind: Kind,
    pub beams: Beams,
    /// Some(true) = up.
    pub stem: Option<bool>,
    /// Colour of an uncertain note (on its attack).
    pub color: Option<&'static str>,
    pub staccato: bool,
    pub fermata: bool,
    /// A trill mark: semitones up to the auxiliary, and the accidental mark the auxiliary needs in
    /// the written key (set once the part is at written pitch).
    pub trill: Option<(i32, Option<Acc>)>,
    /// The wavy line of a trill that goes on through ties: "start" (on the trill) or "stop".
    pub wavy: Option<&'static str>,
}

impl Elem {
    fn is_rest(&self) -> bool {
        matches!(self.kind, Kind::Rest)
    }

    fn end(&self) -> Rat {
        self.off + self.dur.ql
    }

    fn pitches(&self) -> Vec<P> {
        match &self.kind {
            Kind::Note(p, _) => vec![*p],
            Kind::Chord(v) => v.iter().map(|(p, _)| *p).collect(),
            _ => Vec::new(),
        }
    }

    /// Tie of a single note, or the first tie in a chord.
    fn tie(&self) -> Option<Tie> {
        match &self.kind {
            Kind::Note(_, t) => *t,
            Kind::Chord(v) => v.iter().find_map(|(_, t)| *t),
            Kind::Unp(u) => u.tie,
            _ => None,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
enum Dir {
    /// Text; (placement above, boxed).
    Words(String, bool, bool),
    Metro(i64),
    Rehearsal(String),
    Dynamic(String),
}

impl Dir {
    /// Class sort order of the corresponding notation object.
    fn class_order(&self) -> i32 {
        match self {
            Dir::Words(..) | Dir::Rehearsal(_) => -30,
            Dir::Metro(_) => 1,
            Dir::Dynamic(_) => 10,
        }
    }
}

#[derive(Clone, Debug)]
struct Measure {
    els: Vec<Elem>,
    dirs: Vec<(Rat, Dir)>,
    barline: Option<&'static str>,
    tuplets: Option<bool>,
    /// Key signature at the start of this measure (the first measure, and key changes).
    key: Option<i32>,
}

impl Measure {
    fn tuplets_made(&self) -> bool {
        match self.tuplets {
            Some(v) => v,
            None => have_tuplet_brackets(self.els.iter()).unwrap_or(true),
        }
    }
}

fn have_tuplet_brackets<'a>(els: impl Iterator<Item = &'a Elem>) -> Option<bool> {
    let mut found = false;
    for e in els {
        if let Some(t) = e.dur.tuplets.first() {
            found = true;
            if t.typ.is_some() {
                return Some(true);
            }
        }
    }
    if found {
        Some(false)
    } else {
        None
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum ClefKind {
    Treble,
    Bass,
    Percussion,
}

#[derive(Clone, Debug)]
struct Part {
    name: String,
    abbreviation: Option<String>,
    inst: Option<&'static Instrument>,
    clef: ClefKind,
    fifths: Option<i32>,
    measures: Vec<Measure>,
    /// Dashed brackets over review groups: (first element id, last element id), in insertion order.
    lines: Vec<(u64, u64)>,
}

impl Part {
    fn is_drums(&self) -> bool {
        self.clef == ClefKind::Percussion
    }

    /// Sounding minus written: (staff steps, semitones), for transposing instruments.
    fn transposition(&self) -> Option<(i32, i32)> {
        self.inst.filter(|i| i.chromatic != 0 && !i.is_percussion()).map(|i| (i.diatonic, i.chromatic))
    }

    fn all_els(&self) -> impl Iterator<Item = &Elem> {
        self.measures.iter().flat_map(|m| m.els.iter())
    }
}

struct Ids(u64);

impl Ids {
    fn next(&mut self) -> u64 {
        self.0 += 1;
        self.0
    }
}

// ---------------------------------------------------------------------------
// score construction (events, spelling)

struct Event {
    start: i64,
    end: i64,
    pitches: Vec<i32>,
    conf: f64,
    arts: HashSet<String>,
}

/// Snap an end tick to the nearest 16th (6) or triplet-8th (8) position after start.
fn notatable_end(start: i64, end: i64) -> i64 {
    let mut cands: Vec<i64> = Vec::new();
    for g in [6i64, 8] {
        cands.push(g * crate::py::round_int(end as f64 / g as f64));
    }
    for g in [6i64, 8] {
        cands.push(g * (end.div_euclid(g) + 1));
    }
    cands.into_iter().filter(|&c| c > start).min_by_key(|&c| ((c - end).abs(), c)).unwrap()
}

/// [a, b) splits into plain, dotted or triplet values within each beat (no
/// 2-tick fragments, which can only be written as nested tuplets).
fn clean_span(a: i64, b: i64) -> bool {
    b > a && pieces(a, b, TPB).iter().all(|&(x, y)| is_value(y - x))
}

/// The end nearest `end` for which the note and the rest after it are both clean spans.
fn clean_end(start: i64, end: i64, nxt: Option<i64>) -> i64 {
    let ok = |e: i64| clean_span(start, e) && (nxt.is_none() || nxt == Some(e) || clean_span(e, nxt.unwrap()));
    if ok(end) {
        return end;
    }
    let hi = nxt.unwrap_or(end + TPB);
    let mut cands: Vec<i64> = Vec::new();
    for g in [6i64, 8] {
        let mut e = g * (crate::py::floordiv(start, g) + 1);
        while e <= hi {
            cands.push(e);
            e += g;
        }
    }
    if let Some(n) = nxt {
        if n != 0 {
            cands.push(n);
        }
    }
    cands.sort();
    cands.dedup();
    cands.sort_by_key(|&e| ((e - end).abs(), -e));
    cands.into_iter().find(|&e| ok(e)).unwrap_or(end)
}

/// Group by start tick; make the line non-overlapping.
fn events(notes: &[QNote]) -> Vec<Event> {
    let mut groups: BTreeMap<i64, Vec<&QNote>> = BTreeMap::new();
    for q in notes {
        groups.entry(q.start).or_default().push(q);
    }
    let starts: Vec<i64> = groups.keys().copied().collect();
    let mut out = Vec::new();
    for (i, s) in starts.iter().enumerate() {
        let g = &groups[s];
        let mut end = g.iter().map(|q| q.end).min().unwrap();
        end = notatable_end(*s, end);
        let nxt = starts.get(i + 1).copied();
        if let Some(n) = nxt {
            end = end.min(n);
        }
        end = clean_end(*s, end, nxt);
        let mut ps: Vec<i32> = g.iter().map(|q| q.pitch).collect();
        ps.sort();
        ps.dedup();
        let conf = g.iter().map(|q| q.confidence).fold(f64::INFINITY, f64::min);
        let arts: HashSet<String> = g.iter().flat_map(|q| q.articulations.iter().cloned()).collect();
        out.push(Event { start: *s, end: end.max(s + 1), pitches: ps, conf, arts });
    }
    out
}

/// General MIDI drum number -> (display step, octave, notehead) on a 5-line percussion staff.
fn drum(p: i32) -> (u8, i32, &'static str) {
    // steps: C=0 D=1 E=2 F=3 G=4 A=5 B=6
    match p {
        35 | 36 => (3, 4, "normal"),
        37 => (0, 5, "x"),
        38 | 40 => (0, 5, "normal"),
        41 | 43 => (5, 4, "normal"),
        45 | 47 => (1, 5, "normal"),
        48 | 50 => (2, 5, "normal"),
        42 => (4, 5, "x"),
        44 => (1, 4, "x"),
        46 => (4, 5, "circle-x"),
        49 | 52 | 55 | 57 => (5, 5, "x"),
        51 | 59 => (3, 5, "x"),
        53 => (3, 5, "diamond"),
        _ => (6, 5, "x"),
    }
}

fn py_round_bpm(bpm: f64) -> i64 {
    crate::py::round_int(bpm)
}

/// Uncertainty encoding: colour plus a "?" above the attack, boxed below VERY_UNCERTAIN.
pub const UNCERTAIN_COLOUR: &str = "#0063A6";
pub const VERY_UNCERTAIN_COLOUR: &str = "#B04A00";
pub const VERY_UNCERTAIN: f64 = 0.4;
/// A part re-entering after this many empty bars gets its dynamic again.
pub const RESTATE_AFTER_BARS: i64 = 2;

/// The layer's dynamics on this part's notes: at the first note at or after each
/// change, and again when the part re-enters after RESTATE_AFTER_BARS empty bars.
fn place_dynamics(spec: &PartSpec, bar: i64) -> Vec<(i64, String)> {
    if spec.dynamics.is_empty() || spec.notes.is_empty() {
        return Vec::new();
    }
    let mut starts: Vec<i64> = spec.notes.iter().map(|q| q.start).collect();
    starts.sort();
    starts.dedup();
    let mut ends: HashMap<i64, i64> = HashMap::new();
    for q in &spec.notes {
        let e = ends.entry(q.start).or_insert(q.start);
        *e = (*e).max(q.end);
    }
    let mut changes = spec.dynamics.clone();
    changes.sort();
    let mark_at = |tick: i64| -> Option<String> {
        let mut m = None;
        for (t, mk) in &changes {
            if *t <= tick {
                m = Some(mk.clone());
            }
        }
        m
    };
    let mut placed: BTreeMap<i64, String> = BTreeMap::new();
    for (i, (t, mk)) in changes.iter().enumerate() {
        let nxt = changes.get(i + 1).map(|c| c.0);
        if let Some(&first) = starts.iter().find(|&&s| s >= *t && nxt.map_or(true, |n| s < n)) {
            placed.insert(first, mk.clone());
        }
    }
    if !placed.contains_key(&starts[0]) {
        placed.insert(starts[0], mark_at(starts[0]).unwrap_or_else(|| changes[0].1.clone()));
    }
    let mut prev_end: Option<i64> = None;
    for &s in &starts {
        if let Some(pe) = prev_end {
            if s - pe >= RESTATE_AFTER_BARS * bar && !placed.contains_key(&s) {
                if let Some(m) = mark_at(s) {
                    placed.insert(s, m);
                }
            }
        }
        prev_end = Some(prev_end.unwrap_or(0).max(ends[&s]));
    }
    placed.into_iter().collect()
}

fn build_parts(spec: &ScoreSpec, ids: &mut Ids) -> (Vec<Part>, i64) {
    let is_drums = |p: &PartSpec| p.instrument.is_some_and(|i| i.is_percussion());
    let part_events: Vec<Vec<Event>> = spec.parts.iter().map(|p| events(&p.notes)).collect();
    // Spell every note from the whole ensemble at concert pitch, and pick the key.
    let mut flat: Vec<(usize, i64, i64, i32)> = Vec::new();
    for (pi, p) in spec.parts.iter().enumerate() {
        if is_drums(p) {
            continue;
        }
        for ev in &part_events[pi] {
            for &m in &ev.pitches {
                flat.push((pi, ev.start, ev.end, m));
            }
        }
    }
    let mut spelled: HashMap<(usize, i64, i32), P> = HashMap::new();
    let mut fifths = 0;
    if !flat.is_empty() {
        let on: Vec<f64> = flat.iter().map(|x| x.1 as f64 / TPB as f64).collect();
        let du: Vec<f64> = flat.iter().map(|x| (x.2 - x.1) as f64 / TPB as f64).collect();
        let ps: Vec<i32> = flat.iter().map(|x| x.3).collect();
        for (x, s) in flat.iter().zip(spell(&on, &ps)) {
            let step = super::pitch::STEPS.iter().position(|&c| c == s.step).unwrap() as u8;
            spelled.insert((x.0, x.1, x.3), P::new(step, s.alter, s.octave));
        }
        fifths = key_of(&du, &ps).1;
    }
    if let Some(k) = spec.key_fifths {
        fifths = k;
    }

    // Every part spans the same whole bars.
    let bar = spec.beats_per_bar * TPB;
    let last = spec.parts.iter().flat_map(|p| p.notes.iter().map(|q| q.end)).max().unwrap_or(0) - spec.pickup_ticks;
    let total = -((-last.max(bar)).div_euclid(bar)) * bar;
    let opens_free = spec.free_spans.iter().any(|sp| sp.start - spec.pickup_ticks == 0);

    let mut parts = Vec::new();
    for (pi, p) in spec.parts.iter().enumerate() {
        let drums = is_drums(p);
        // (tick, class order, insertion) -> direction
        let mut dirs: Vec<(i64, i32, usize, Dir)> = Vec::new();
        let push = |dirs: &mut Vec<(i64, i32, usize, Dir)>, t: i64, d: Dir| {
            let n = dirs.len();
            dirs.push((t, d.class_order(), n, d));
        };
        let mut key_changes: Vec<(i64, i32)> = Vec::new();
        if !drums {
            for &(tick, f) in &spec.key_changes {
                if tick - spec.pickup_ticks > 0 {
                    key_changes.push((tick - spec.pickup_ticks, f));
                }
            }
        }
        if pi == 0 {
            if let Some(t) = &spec.tempo_note {
                push(&mut dirs, 0, Dir::Words(t.clone(), false, false));
            }
        }
        if pi == 0 && !opens_free {
            push(&mut dirs, 0, Dir::Metro(py_round_bpm(spec.bpm)));
        }
        for sp in &spec.free_spans {
            let (a, b) = (sp.start - spec.pickup_ticks, sp.end - spec.pickup_ticks);
            if a >= 0 {
                push(&mut dirs, a, Dir::Words(sp.label.clone(), false, false));
                if pi == 0 {
                    push(&mut dirs, a, Dir::Metro(py_round_bpm(sp.bpm)));
                }
            }
            if 0 <= b && b < total {
                push(&mut dirs, b, Dir::Words("a tempo".into(), false, false));
                if pi == 0 {
                    push(&mut dirs, b, Dir::Metro(py_round_bpm(spec.bpm)));
                }
            }
        }
        if pi == 0 {
            for (tick, label) in &spec.rehearsal {
                if 0 <= tick - spec.pickup_ticks && tick - spec.pickup_ticks < total {
                    push(&mut dirs, tick - spec.pickup_ticks, Dir::Rehearsal(label.clone()));
                }
            }
        }
        for (s, mk) in place_dynamics(p, bar) {
            if s - spec.pickup_ticks >= 0 {
                push(&mut dirs, s - spec.pickup_ticks, Dir::Dynamic(mk));
            }
        }

        let mut flat_els: Vec<Elem> = Vec::new();
        let rest = |ids: &mut Ids, out: &mut Vec<Elem>, from: i64, to: i64| {
            for (x, y) in pieces(from, to, bar) {
                out.push(Elem {
                    id: ids.next(),
                    off: Rat::new(x, TPB),
                    dur: Dur::from_ql(Rat::new(y - x, TPB)),
                    kind: Kind::Rest,
                    beams: Vec::new(),
                    stem: None,
                    color: None,
                    staccato: false,
                    fermata: false,
                    trill: None,
                    wavy: None,
                });
            }
        };
        // Review groups: neighbouring marked notes share one "?" (at the group's first
        // note, boxed when any member is very unsure) and a dashed bracket over the group.
        let groups = if drums {
            Vec::new()
        } else {
            let ns: Vec<(i64, i64, f64)> = part_events[pi].iter().map(|e| (e.start, e.end, e.conf)).collect();
            crate::confidence::review_groups(&ns, bar, spec.low_confidence, spec.very_below)
        };
        let mut firsts: Vec<(i64, u64)> = Vec::new();
        let mut lasts: Vec<(i64, u64)> = Vec::new();
        let mut cursor = 0i64;
        for ev in &part_events[pi] {
            let tick = ev.start;
            let start = ev.start - spec.pickup_ticks;
            let mut end = ev.end - spec.pickup_ticks;
            if start < 0 {
                continue;
            }
            if start > cursor {
                rest(ids, &mut flat_els, cursor, start);
            }
            let mut segs = pieces(start, end, bar);
            if drums {
                // A drum hit has no meaningful length: its first readable value, then rest.
                segs.truncate(1);
                end = segs[0].1;
            }
            let n = segs.len();
            for (i, &(a, b)) in segs.iter().enumerate() {
                let tie = if n > 1 { Some(if i == 0 { Tie::Start } else if i == n - 1 { Tie::Stop } else { Tie::Continue }) } else { None };
                let kind = if drums {
                    let mut heads: Vec<i32> = ev.pitches.clone();
                    heads.sort();
                    heads.dedup();
                    let us: Vec<Unp> = heads
                        .iter()
                        .map(|&m| {
                            let (step, octave, head) = drum(m);
                            Unp { step, octave, head, tie: None }
                        })
                        .collect();
                    if us.len() == 1 {
                        Kind::Unp(us[0])
                    } else {
                        Kind::PChord(us)
                    }
                } else {
                    let sp: Vec<P> = ev.pitches.iter().map(|&m| spelled[&(pi, tick, m)]).collect();
                    if sp.len() == 1 {
                        Kind::Note(sp[0], tie)
                    } else {
                        Kind::Chord(sp.into_iter().map(|p| (p, tie)).collect())
                    }
                };
                let mut color = None;
                if i == 0 {
                    if let Some(g) = groups.iter().find(|g| g.start == tick) {
                        color = Some(if g.very { VERY_UNCERTAIN_COLOUR } else { UNCERTAIN_COLOUR });
                        push(&mut dirs, a, Dir::Words("?".into(), true, g.very));
                    }
                }
                let id = ids.next();
                if !drums {
                    if i == 0 {
                        match firsts.iter_mut().find(|f| f.0 == tick) {
                            Some(f) => f.1 = id,
                            None => firsts.push((tick, id)),
                        }
                    }
                    match lasts.iter_mut().find(|f| f.0 == tick) {
                        Some(f) => f.1 = id,
                        None => lasts.push((tick, id)),
                    }
                }
                flat_els.push(Elem {
                    id,
                    off: Rat::new(a, TPB),
                    dur: Dur::from_ql(Rat::new(b - a, TPB)),
                    kind,
                    beams: Vec::new(),
                    stem: None,
                    color,
                    staccato: !drums && i == 0 && ev.arts.contains("staccato"),
                    fermata: !drums && i == n - 1 && ev.arts.contains("fermata"),
                    trill: if !drums && i == 0 && ev.pitches.len() == 1 { trill_of(&ev.arts).map(|t| (t, None)) } else { None },
                    wavy: None,
                });
            }
            cursor = end;
        }
        if cursor < total {
            rest(ids, &mut flat_els, cursor, total);
        }
        let mut lines: Vec<(u64, u64)> = Vec::new();
        for g in groups.iter().filter(|g| g.notes > 1) {
            let ticks: Vec<i64> = firsts.iter().map(|f| f.0).filter(|&t| g.start <= t && t < g.end).collect();
            if let (Some(&lo), Some(&hi)) = (ticks.iter().min(), ticks.iter().max()) {
                if lo != hi {
                    let first = firsts.iter().find(|f| f.0 == lo).unwrap().1;
                    let last = lasts.iter().find(|f| f.0 == hi).unwrap().1;
                    lines.push((first, last));
                }
            }
        }
        // stable: offset, then class order, then insertion
        dirs.sort_by_key(|d| (d.0, d.1, d.2));

        // measures (bar lines every `bar`, at least one bar, up to the last element)
        let bar_ql = Rat::int(spec.beats_per_bar);
        let o_max = flat_els
            .iter()
            .map(|e| e.end())
            .chain(dirs.iter().map(|d| Rat::new(d.0, TPB)))
            .chain(key_changes.iter().map(|k| Rat::new(k.0, TPB)))
            .max()
            .unwrap_or(Rat::ZERO);
        let mut n_measures = 1usize;
        let mut o = bar_ql;
        while o < o_max {
            n_measures += 1;
            o = o + bar_ql;
        }
        let mut measures: Vec<Measure> =
            (0..n_measures).map(|_| Measure { els: Vec::new(), dirs: Vec::new(), barline: None, tuplets: None, key: None }).collect();
        let index = |off: Rat| -> usize { ((off / bar_ql).n.div_euclid((off / bar_ql).d)) as usize };
        for mut e in flat_els {
            let k = index(e.off);
            // makeNotation works on a deep copy, but these durations have not been
            // expanded into components yet, so they keep counting as inferred.
            e.off = e.off - bar_ql * Rat::int(k as i64);
            measures[k].els.push(e);
        }
        for (t, _, _, d) in dirs {
            let off = Rat::new(t, TPB);
            let k = index(off);
            measures[k].dirs.push((off - bar_ql * Rat::int(k as i64), d));
        }
        if !drums {
            measures[0].key = Some(fifths);
            for (t, f) in key_changes {
                // key changes sit on bar lines
                let k = index(Rat::new(t, TPB));
                measures[k].key = Some(f);
            }
        }
        measures.last_mut().unwrap().barline = Some("final");
        let clef = if drums {
            ClefKind::Percussion
        } else if p.clef == "bass" {
            ClefKind::Bass
        } else {
            ClefKind::Treble
        };
        parts.push(Part {
            name: p.name.clone(),
            abbreviation: p.abbreviation.clone(),
            inst: p.instrument,
            clef,
            fifths: if drums { None } else { Some(fifths) },
            measures,
            lines,
        });
    }
    (parts, total)
}

// ---------------------------------------------------------------------------
// accidentals

fn name_with_octave(p: &P) -> (u8, i32, i32) {
    (p.step, p.alter(), p.octave)
}

fn tie_pitch_set(e: &Elem) -> Option<HashSet<(u8, i32, i32)>> {
    match &e.kind {
        Kind::Rest => None,
        Kind::Note(p, t) => Some(t.filter(|t| *t != Tie::Stop).map(|_| name_with_octave(p)).into_iter().collect()),
        Kind::Chord(v) => Some(v.iter().filter(|(_, t)| t.is_some_and(|t| t != Tie::Stop)).map(|(p, _)| name_with_octave(p)).collect()),
        Kind::Unp(_) | Kind::PChord(_) => Some(HashSet::new()),
    }
}

/// (step, alter) names of the major scale of a key signature.
fn scale_names(fifths: i32) -> Vec<(u8, i32)> {
    let altered = altered_names(fifths);
    (0..7u8).map(|st| altered.iter().rev().find(|(s, _)| *s == st).copied().unwrap_or((st, 0))).collect()
}

fn make_accidentals(part: &mut Part) {
    let mut ks_last: Option<i32> = None;
    let mut tie_set: Option<HashSet<(u8, i32, i32)>> = None;
    let mut past_measure: Vec<P> = Vec::new();
    for i in 0..part.measures.len() {
        let mkey = part.measures[i].key;
        if i > 0 {
            let prev: Vec<P> = part.measures[i - 1].els.iter().flat_map(|e| e.pitches()).collect();
            if mkey.is_none() {
                past_measure = prev;
            } else if let Some(last) = ks_last {
                // Only the chromatic pitches of the previous measure carry over a key change.
                let diatonic = scale_names(last);
                past_measure = prev.into_iter().filter(|p| !diatonic.contains(&p.name())).collect();
            }
            if let Some(last) = part.measures[i - 1].els.iter().rev().find(|e| !e.is_rest()) {
                tie_set = tie_pitch_set(last);
                if tie_set.is_some() && mkey.is_some() {
                    // The reference compares names with octave against names without: nothing survives.
                    tie_set = Some(HashSet::new());
                }
            }
        }
        if mkey.is_some() {
            ks_last = mkey;
        }
        let altered = ks_last.map(altered_names).unwrap_or_default();
        let mut ts = tie_set.take().unwrap_or_default();
        let mut past: Vec<P> = Vec::new();
        for e in part.measures[i].els.iter_mut() {
            match &mut e.kind {
                Kind::Note(p, t) => {
                    let tied = ts.contains(&name_with_octave(p));
                    update_accidental_display(p, &past, &past_measure, &[], &altered, tied);
                    past.push(*p);
                    ts.clear();
                    if t.is_some_and(|t| t != Tie::Stop) {
                        ts.insert(name_with_octave(p));
                    }
                }
                Kind::Chord(v) => {
                    let mut seen = HashSet::new();
                    for k in 0..v.len() {
                        let tied = ts.contains(&name_with_octave(&v[k].0));
                        let others: Vec<P> = v.iter().enumerate().filter(|(j, _)| *j != k).map(|(_, (p, _))| *p).collect();
                        let mut p = v[k].0;
                        update_accidental_display(&mut p, &past, &past_measure, &others, &altered, tied);
                        v[k].0 = p;
                        if v[k].1.is_some_and(|t| t != Tie::Stop) {
                            seen.insert(name_with_octave(&p));
                        }
                    }
                    ts = seen;
                    past.extend(v.iter().map(|(p, _)| *p));
                }
                _ => ts.clear(),
            }
        }
        tie_set = Some(ts);
    }
}

fn have_accidentals_been_made(part: &Part) -> bool {
    part.all_els().flat_map(|e| e.pitches()).any(|p| p.acc.is_some_and(|a| a.display.is_some()))
}

// ---------------------------------------------------------------------------
// splitting

/// Split an element at `ql` into (first, remainder), with ties and hidden
/// accidentals on the tied continuation; staccato and fermata go to the remainder.
fn split_at(e: &mut Elem, ql: Rat, ids: &mut Ids) -> Option<Elem> {
    let mut rem = e.clone();
    rem.id = ids.next();
    let len_end = e.dur.ql - ql;
    e.dur = Dur::from_ql(ql);
    rem.dur = Dur::from_ql(len_end);
    rem.off = e.off + ql;
    let force = |t: &mut Option<Tie>| -> Tie {
        match *t {
            Some(Tie::Start) => Tie::Continue,
            Some(Tie::Stop) => {
                *t = Some(Tie::Continue);
                Tie::Stop
            }
            Some(Tie::Continue) => Tie::Continue,
            None => {
                *t = Some(Tie::Start);
                Tie::Stop
            }
        }
    };
    match (&mut e.kind, &mut rem.kind) {
        (Kind::Note(_, t), Kind::Note(_, rt)) => *rt = Some(force(t)),
        (Kind::Unp(u), Kind::Unp(ru)) => ru.tie = Some(force(&mut u.tie)),
        (Kind::Chord(v), Kind::Chord(rv)) => {
            for (a, b) in v.iter_mut().zip(rv.iter_mut()) {
                b.1 = Some(force(&mut a.1));
            }
        }
        _ => {}
    }
    match (&e.kind, &mut rem.kind) {
        (Kind::Note(p, _), Kind::Note(rp, _)) => {
            if p.acc.is_some() {
                if let Some(a) = rp.acc.as_mut() {
                    a.display = Some(false);
                }
            }
        }
        (Kind::Chord(v), Kind::Chord(rv)) => {
            for (a, b) in v.iter().zip(rv.iter_mut()) {
                if a.0.acc.is_some() {
                    if let Some(x) = b.0.acc.as_mut() {
                        x.display = Some(false);
                    }
                }
            }
        }
        _ => {}
    }
    e.staccato = false;
    e.fermata = false;
    rem.trill = None; // a trill stays on the first piece (the writer draws its wavy line)
    rem.wavy = None;
    if rem.dur.ql > Rat::ZERO {
        Some(rem)
    } else {
        None
    }
}

fn make_ties(part: &mut Part, bar: Rat, ids: &mut Ids) {
    let n = part.measures.len();
    for mi in 0..n {
        let mut k = 0;
        while k < part.measures[mi].els.len() {
            let (off, end) = {
                let e = &part.measures[mi].els[k];
                (e.off, e.end())
            };
            if end > bar && off < bar {
                let mut e = part.measures[mi].els[k].clone();
                let rem = split_at(&mut e, bar - off, ids);
                part.measures[mi].els[k] = e;
                if let Some(mut r) = rem {
                    r.off = Rat::ZERO;
                    if mi + 1 < n {
                        part.measures[mi + 1].els.insert(0, r);
                    }
                }
            }
            k += 1;
        }
    }
}

/// Split notes or rests where doing so completes an incomplete tuplet.
fn split_to_complete_tuplets(m: &mut Measure, ids: &mut Ids) {
    let snapshot: Vec<u64> = m.els.iter().map(|e| e.id).collect();
    let mut last: Option<super::duration::Tuplet> = None;
    let mut partial = Rat::ZERO;
    for id in snapshot {
        let Some(i) = m.els.iter().position(|e| e.id == id) else { continue };
        let gn = &m.els[i];
        let t0 = gn.dur.tuplets.first().copied();
        if t0.is_some() && gn.dur.inferred && (last.is_none() || last == t0) {
            last = t0;
            partial = gn.dur.ql + partial;
        } else {
            last = None;
            partial = Rat::ZERO;
            continue;
        }
        let to_complete = t0.unwrap().total_length() - partial;
        if to_complete.is_zero() {
            last = None;
            partial = Rat::ZERO;
            continue;
        }
        if i + 1 >= m.els.len() {
            continue;
        }
        let gn_end = gn.end();
        let next = &m.els[i + 1];
        if next.off != gn_end {
            continue;
        }
        if next.dur.inferred && Rat::ZERO < to_complete && to_complete < next.dur.ql {
            let mut e = m.els[i + 1].clone();
            if let Some(r) = split_at(&mut e, to_complete, ids) {
                m.els[i + 1] = e;
                m.els.insert(i + 2, r);
            }
        }
    }
}

/// Replace consecutive tied notes (or rests) that fill a whole tuplet by one plain value.
fn consolidate_tuplets(m: &mut Measure) {
    // search state
    let mut to_consolidate: Vec<Option<u64>> = Vec::new();
    let mut partial = Rat::ZERO;
    let mut last: Option<super::duration::Tuplet> = None;
    let mut target: Option<Rat> = None;
    let reset = |tc: &mut Vec<Option<u64>>, partial: &mut Rat, last: &mut Option<super::duration::Tuplet>, target: &mut Option<Rat>| {
        tc.clear();
        *partial = Rat::ZERO;
        *last = None;
        *target = None;
    };
    let ids: Vec<u64> = m.els.iter().map(|e| e.id).collect();
    for id in ids {
        let Some(i) = m.els.iter().position(|e| e.id == id) else { continue };
        partial = partial + m.els[i].dur.ql;
        let gn = &m.els[i];
        let should_test = if to_consolidate.is_empty() {
            true
        } else if i == 0 {
            false
        } else {
            let prev = &m.els[i - 1];
            // Pitches compare as music21's do: spelling, octave and accidental, not whether it is shown.
            let spelled = |e: &Elem| -> Vec<(u8, i32, Option<i32>)> { e.pitches().iter().map(|p| (p.step, p.octave, p.acc.map(|a| a.alter))).collect() };
            let same = (gn.is_rest() && prev.is_rest()) || (!gn.is_rest() && !prev.is_rest() && spelled(gn) == spelled(prev));
            same && prev.end() == gn.off && gn.dur.tuplets.len() == 1 && Some(gn.dur.tuplets[0]) == last
        };
        if should_test {
            if !to_consolidate.is_empty() {
                to_consolidate.push(Some(id));
            } else {
                partial = gn.dur.ql;
                if let Some(t) = gn.dur.tuplets.first() {
                    last = Some(*t);
                    target = Some(t.total_length());
                    to_consolidate.push(Some(id));
                }
            }
        } else if !to_consolidate.is_empty() {
            to_consolidate.push(None);
        }
        if Some(partial) == target {
            let reexpressible = |x: &Option<u64>| -> bool {
                let Some(id) = x else { return false };
                let Some(e) = m.els.iter().find(|e| e.id == *id) else { return false };
                e.dur.inferred && e.dur.tuplets.len() < 2 && (e.is_rest() || e.tie().is_some())
            };
            if to_consolidate.iter().all(reexpressible) && !to_consolidate.is_empty() {
                m.tuplets = Some(false);
                let first = to_consolidate[0].unwrap();
                let others: Vec<u64> = to_consolidate[1..].iter().map(|x| x.unwrap()).collect();
                m.els.retain(|e| !others.contains(&e.id));
                let t = target.unwrap();
                if let Some(e) = m.els.iter_mut().find(|e| e.id == first) {
                    let mut d = Dur::from_ql(t);
                    d.inferred = true;
                    e.dur = d;
                }
            }
            reset(&mut to_consolidate, &mut partial, &mut last, &mut target);
        }
    }
}

fn make_tuplet_brackets(m: &mut Measure) {
    let n = m.els.len();
    let mut completion = Rat::ZERO;
    let mut target: Option<Rat> = None;
    let mut prev_has = false;
    for i in 0..n {
        let has = m.els[i].dur.tuplets.len() == 1;
        let next_has = i + 1 < n && m.els[i + 1].dur.tuplets.len() == 1;
        if has {
            let ql = m.els[i].dur.ql;
            let t = &mut m.els[i].dur.tuplets[0];
            completion = completion + ql;
            if !prev_has || target.is_none() {
                if !next_has {
                    t.typ = Some(TupletType::StartStop);
                    t.bracket = false;
                    completion = Rat::ZERO;
                } else {
                    t.typ = Some(TupletType::Start);
                    target = Some(t.total_length());
                }
            } else if !next_has || completion >= target.unwrap() {
                t.typ = Some(TupletType::Stop);
                target = None;
                completion = Rat::ZERO;
            } else {
                t.typ = None;
            }
        }
        prev_has = has;
    }
    m.tuplets = Some(true);
}

fn split_at_durations(m: &mut Measure, bar: Rat, ids: &mut Ids, lines: &mut [(u64, u64)]) {
    let mut out: Vec<Elem> = Vec::with_capacity(m.els.len());
    for e in std::mem::take(&mut m.els) {
        let full_rest = e.is_rest() && e.dur.ql == bar;
        if !e.dur.is_complex() || full_rest {
            out.push(e);
            continue;
        }
        let atm = e.dur.aggregate_multiplier();
        let qls: Vec<Rat> = e.dur.comps.iter().map(|c| c.ql * atm).collect();
        let mut cur = e.clone();
        cur.dur = cur.dur.deep_copied();
        for q in &qls[..qls.len() - 1] {
            let rem = split_at(&mut cur, *q, ids);
            out.push(cur);
            match rem {
                Some(r) => cur = r,
                None => {
                    cur = Elem { dur: Dur::from_ql(Rat::ZERO), ..e.clone() };
                    break;
                }
            }
        }
        if cur.dur.ql > Rat::ZERO {
            out.push(cur);
        }
        // A bracket that ends on the split element ends on its last piece.
        let last_piece = out.last().map(|x| x.id).unwrap_or(e.id);
        for l in lines.iter_mut().filter(|l| l.1 == e.id) {
            l.1 = last_piece;
        }
    }
    m.els = out;
}

// ---------------------------------------------------------------------------
// beams and stems

fn make_beams(part: &mut Part, seq: &BeamSequence) {
    for m in part.measures.iter_mut() {
        if m.els.len() <= 1 {
            continue;
        }
        let input: Vec<BeamInput> = m
            .els
            .iter()
            .map(|e| BeamInput { offset: e.off, ql: e.dur.ql, typ: e.dur.typ(), notrest: !e.is_rest() })
            .collect();
        let beams = get_beams(&input, seq);
        for (e, b) in m.els.iter_mut().zip(beams) {
            e.beams = b;
        }
    }
    // stems per beam group
    let midline = match part.clef {
        ClefKind::Bass => 19 + 4,
        _ => 31 + 4,
    };
    let mut group: Vec<(usize, usize)> = Vec::new();
    let mut in_group = false;
    let mut groups: Vec<Vec<(usize, usize)>> = Vec::new();
    for (mi, m) in part.measures.iter().enumerate() {
        for (ei, e) in m.els.iter().enumerate() {
            if e.is_rest() {
                continue;
            }
            let first = e.beams.iter().find(|b| b.number == 1).and_then(|b| b.typ.map(|t| (t, b.dir)));
            if first == Some((BT::Start, None)) {
                in_group = true;
            }
            if in_group {
                group.push((mi, ei));
            }
            if first == Some((BT::Stop, None)) {
                groups.push(std::mem::take(&mut group));
                in_group = false;
            }
        }
    }
    if !group.is_empty() {
        groups.push(group);
    }
    for g in groups {
        let pitches: Vec<P> = g.iter().flat_map(|&(mi, ei)| part.measures[mi].els[ei].pitches()).collect();
        if pitches.is_empty() {
            continue;
        }
        let rel: Vec<P> = if pitches.len() > 1 { vec![pitches[0], pitches[pitches.len() - 1]] } else { pitches };
        let diff: i32 = rel.iter().map(|p| p.diatonic_note_num() - midline).sum();
        let up = diff < 0;
        for &(mi, ei) in &g {
            part.measures[mi].els[ei].stem = Some(up);
        }
    }
}

// ---------------------------------------------------------------------------
// transposition

fn to_written(part: &mut Part) {
    let Some((steps, semis)) = part.transposition() else { return };
    let (steps, semis) = (-steps, -semis);
    if let Some(f) = part.fifths {
        part.fifths = Some(transpose_key(f, steps, semis));
    }
    for m in part.measures.iter_mut() {
        if let Some(f) = m.key {
            m.key = Some(transpose_key(f, steps, semis));
        }
        for e in m.els.iter_mut() {
            match &mut e.kind {
                Kind::Note(p, _) => *p = transpose(p, steps, semis),
                Kind::Chord(v) => {
                    for (p, _) in v.iter_mut() {
                        *p = transpose(p, steps, semis);
                    }
                }
                _ => {}
            }
        }
    }
}

fn trill_of(arts: &HashSet<String>) -> Option<i32> {
    let mut v: Vec<&String> = arts.iter().filter(|a| a.starts_with(crate::musicxml::TRILL)).collect();
    v.sort();
    v.first().and_then(|a| a[crate::musicxml::TRILL.len()..].parse().ok())
}

/// The auxiliary of each trill, spelled from the written part's key: the next letter up at the
/// trill's size; an accidental mark only where the key signature does not give that note
/// (accidentals earlier in the bar are not considered).
fn trill_accidentals(part: &mut Part) {
    let altered = |f: i32, step: u8| altered_names(f).iter().find(|(s, _)| *s == step).map(|(_, a)| *a).unwrap_or(0);
    let mut fifths = part.fifths.unwrap_or(0);
    for m in part.measures.iter_mut() {
        if let Some(f) = m.key {
            fifths = f;
        }
        for e in m.els.iter_mut() {
            let (Some((size, _)), Kind::Note(p, _)) = (e.trill, &e.kind) else { continue };
            let (step, octave) = if p.step == 6 { (0u8, p.octave + 1) } else { (p.step + 1, p.octave) };
            let alter = p.ps() + size - P::new(step, 0, octave).ps();
            e.trill = Some((size, if alter != altered(fifths, step) { Some(Acc { alter, display: Some(true) }) } else { None }));
        }
    }
}

/// A wavy line over a trill that goes on through ties: from the trill to the last tied note.
fn trill_lines(part: &mut Part) {
    let mut open = false;
    for m in part.measures.iter_mut() {
        for e in m.els.iter_mut() {
            let Kind::Note(_, tie) = e.kind else { continue };
            if e.trill.is_some() && tie == Some(Tie::Start) {
                e.wavy = Some("start");
                open = true;
            } else if open && tie == Some(Tie::Stop) {
                e.wavy = Some("stop");
                open = false;
            }
        }
    }
}

fn deep_copy(parts: &mut [Part]) {
    for p in parts {
        for m in p.measures.iter_mut() {
            for e in m.els.iter_mut() {
                e.dur = e.dur.deep_copied();
            }
        }
    }
}

// ---------------------------------------------------------------------------
// XML

/// Written E#, B#, Fb, Cb and double accidentals become the plain enharmonic
/// (flats stay flats, sharps sharps): spelling runs at concert pitch, and
/// transposing a part can turn a sensible name into F## or E# on the page.
fn plain_spellings(part: &mut Part) {
    const SHARP: [(u8, i32); 12] = [(0, 0), (0, 1), (1, 0), (2, -1), (2, 0), (3, 0), (3, 1), (4, 0), (5, -1), (5, 0), (6, -1), (6, 0)];
    const FLAT: [(u8, i32); 12] = [(0, 0), (1, -1), (1, 0), (2, -1), (2, 0), (3, 0), (4, -1), (4, 0), (5, -1), (5, 0), (6, -1), (6, 0)];
    let fix = |p: &mut P| {
        let alter = p.alter();
        let awkward = matches!((p.step, alter), (2, 1) | (6, 1) | (3, -1) | (0, -1));
        if alter.abs() >= 2 || awkward {
            let midi = p.ps();
            let (step, a) = (if alter < 0 { FLAT } else { SHARP })[midi.rem_euclid(12) as usize];
            let mut q = P::new(step, a, crate::py::floordiv(midi as i64, 12) as i32 - 1);
            q.octave += crate::py::floordiv((midi - q.ps()) as i64, 12) as i32;
            *p = q;
        }
    };
    for m in part.measures.iter_mut() {
        for e in m.els.iter_mut() {
            match &mut e.kind {
                Kind::Note(p, _) => fix(p),
                Kind::Chord(v) => {
                    for (p, _) in v.iter_mut() {
                        fix(p);
                    }
                }
                _ => {}
            }
        }
    }
}

fn duration_el(ql: Rat) -> X {
    X::text("duration", (Rat::int(DIVISIONS) * ql).round_even().to_string())
}

fn tie_els(t: Tie) -> Vec<X> {
    match t {
        Tie::Start => vec![X::new("tie").attr("type", "start")],
        Tie::Stop => vec![X::new("tie").attr("type", "stop")],
        Tie::Continue => vec![X::new("tie").attr("type", "stop"), X::new("tie").attr("type", "start")],
    }
}

fn tied_els(t: Tie) -> Vec<X> {
    match t {
        Tie::Start => vec![X::new("tied").attr("type", "start")],
        Tie::Stop => vec![X::new("tied").attr("type", "stop")],
        Tie::Continue => vec![X::new("tied").attr("type", "stop"), X::new("tied").attr("type", "start")],
    }
}

fn tuplet_els(e: &Elem) -> Vec<X> {
    let Some(t) = e.dur.tuplets.first() else { return Vec::new() };
    if e.dur.tuplets.len() != 1 {
        return Vec::new();
    }
    let types: Vec<&str> = match t.typ {
        None => return Vec::new(),
        Some(TupletType::Start) => vec!["start"],
        Some(TupletType::Stop) => vec!["stop"],
        Some(TupletType::StartStop) => vec!["start", "stop"],
    };
    types
        .into_iter()
        .map(|ty| {
            let mut x = X::new("tuplet").attr("type", ty).attr("number", "1");
            if ty == "start" {
                x.set("bracket", if t.bracket { "yes" } else { "no" });
                x.set("placement", "above");
                let mut a = X::new("tuplet-actual").child(X::text("tuplet-number", t.actual.to_string()));
                if let Some(d) = t.dur_actual {
                    a.push(X::text("tuplet-type", d.typ.musicxml()));
                    for _ in 0..d.dots {
                        a.push(X::new("tuplet-dot"));
                    }
                }
                let mut nrm = X::new("tuplet-normal").child(X::text("tuplet-number", t.normal.to_string()));
                if let Some(d) = t.dur_normal {
                    nrm.push(X::text("tuplet-type", d.typ.musicxml()));
                    for _ in 0..d.dots {
                        nrm.push(X::new("tuplet-dot"));
                    }
                }
                x.push(a);
                x.push(nrm);
            }
            x
        })
        .collect()
}

fn time_modification(e: &Elem) -> Option<X> {
    match e.dur.tuplets.len() {
        0 => None,
        1 => {
            let t = &e.dur.tuplets[0];
            let mut x = X::new("time-modification")
                .child(X::text("actual-notes", t.actual.to_string()))
                .child(X::text("normal-notes", t.normal.to_string()));
            if let Some(d) = t.dur_normal {
                x.push(X::text("normal-type", d.typ.musicxml()));
                for _ in 0..d.dots {
                    x.push(X::new("normal-dot"));
                }
            }
            Some(x)
        }
        _ => {
            let m = e.dur.aggregate_multiplier();
            Some(X::new("time-modification").child(X::text("actual-notes", m.d.to_string())).child(X::text("normal-notes", m.n.to_string())))
        }
    }
}

fn beam_els(b: &Beams) -> Vec<X> {
    b.iter()
        .filter_map(|x| {
            let text = match (x.typ?, x.dir) {
                (BT::Start, _) => "begin",
                (BT::Continue, _) => "continue",
                (BT::Stop, _) => "end",
                (BT::Partial, Some(BDir::Left)) => "backward hook",
                (BT::Partial, _) => "forward hook",
            };
            Some(X::text("beam", text).attr("number", x.number.to_string()))
        })
        .collect()
}

enum Head<'a> {
    Pitch(&'a P),
    Unp(&'a Unp),
    Rest,
}

/// One <note> element (index > 0 inside a chord gets <chord/>).
fn note_xml(e: &Elem, head: Head, tie: Option<Tie>, index: usize, full_rest: bool, member_notehead: &'static str) -> X {
    let mut n = X::new("note");
    if let Some(c) = e.color {
        n.set("color", c);
    }
    if index > 0 {
        n.push(X::new("chord"));
    }
    match &head {
        Head::Pitch(p) => {
            let mut px = X::new("pitch").child(X::text("step", p.step_char().to_string()));
            if let Some(a) = p.acc {
                px.push(X::text("alter", a.alter.to_string()));
            }
            px.push(X::text("octave", p.octave.to_string()));
            n.push(px);
        }
        Head::Unp(u) => {
            n.push(
                X::new("unpitched")
                    .child(X::text("display-step", super::pitch::STEPS[u.step as usize].to_string()))
                    .child(X::text("display-octave", u.octave.to_string())),
            );
        }
        Head::Rest => {
            let mut r = X::new("rest");
            if full_rest {
                r.set("measure", "yes");
            }
            n.push(r);
        }
    }
    n.push(duration_el(e.dur.ql));
    if let Some(t) = tie {
        for x in tie_els(t) {
            n.push(x);
        }
    }
    if !full_rest {
        if let Some(t) = e.dur.typ() {
            n.push(X::text("type", t.musicxml()));
        }
        for _ in 0..e.dur.dots() {
            n.push(X::new("dot"));
        }
    }
    if let Head::Pitch(p) = &head {
        if let Some(a) = p.acc {
            if a.display != Some(false) {
                n.push(X::text("accidental", a.musicxml_name()));
            }
        }
    }
    if let Some(tm) = time_modification(e) {
        n.push(tm);
    }
    if index == 0 && !matches!(head, Head::Rest) {
        if let Some(up) = e.stem {
            n.push(X::text("stem", if up { "up" } else { "down" }));
        }
    }
    if !matches!(head, Head::Rest) && (member_notehead != "normal" || e.color.is_some()) {
        let mut nh = X::text("notehead", member_notehead).attr("parentheses", "no");
        if let Some(c) = e.color {
            nh.set("color", c);
        }
        n.push(nh);
    }
    if index == 0 && !matches!(head, Head::Rest) {
        for b in beam_els(&e.beams) {
            n.push(b);
        }
    }
    let mut notations: Vec<X> = Vec::new();
    if index == 0 && e.fermata {
        notations.push(X::new("fermata").attr("type", "inverted"));
    }
    if let Some(t) = tie {
        notations.extend(tied_els(t));
    }
    if index == 0 && e.staccato {
        notations.push(X::new("articulations").child(X::new("staccato")));
    }
    if index == 0 {
        if let Some((_, mark)) = e.trill {
            let mut o = X::new("ornaments").child(X::new("trill-mark").attr("placement", "above"));
            if let Some(a) = mark {
                o.push(X::text("accidental-mark", a.musicxml_name()).attr("placement", "above"));
            }
            if e.wavy == Some("start") {
                o.push(X::new("wavy-line").attr("type", "start").attr("number", "1"));
            }
            notations.push(o);
        } else if e.wavy == Some("stop") {
            notations.push(X::new("ornaments").child(X::new("wavy-line").attr("type", "stop").attr("number", "1")));
        }
    }
    if index == 0 {
        notations.extend(tuplet_els(e));
    }
    if !notations.is_empty() {
        let mut nx = X::new("notations");
        nx.children = notations;
        n.push(nx);
    }
    n
}

fn elem_xml(e: &Elem, bar: Rat, out: &mut Vec<X>) {
    match &e.kind {
        Kind::Rest => out.push(note_xml(e, Head::Rest, None, 0, e.dur.ql == bar, "normal")),
        Kind::Note(p, t) => out.push(note_xml(e, Head::Pitch(p), *t, 0, false, "normal")),
        Kind::Chord(v) => {
            for (i, (p, t)) in v.iter().enumerate() {
                out.push(note_xml(e, Head::Pitch(p), *t, i, false, "normal"));
            }
        }
        Kind::Unp(u) => out.push(note_xml(e, Head::Unp(u), u.tie, 0, false, u.head)),
        Kind::PChord(v) => {
            for (i, u) in v.iter().enumerate() {
                out.push(note_xml(e, Head::Unp(u), u.tie, i, false, u.head));
            }
        }
    }
}

/// A <direction>; `offset` in divisions when it does not sit at the current position.
fn dir_xml(d: &Dir, offset: Option<i64>) -> X {
    let off = |x: &mut X, sound: bool| {
        if let Some(o) = offset {
            let mut e = X::text("offset", o.to_string());
            if sound {
                e.set("sound", "yes");
            }
            x.push(e);
        }
    };
    match d {
        Dir::Words(w, above, boxed) => {
            let mut words = X::text("words", w.clone());
            if *boxed {
                words.set("enclosure", "rectangle");
            }
            let mut x = X::new("direction").child(X::new("direction-type").child(words));
            if *above {
                x.set("placement", "above");
            }
            off(&mut x, false);
            x
        }
        Dir::Metro(n) => {
            let mut x = X::new("direction").child(
                X::new("direction-type").child(
                    X::new("metronome")
                        .attr("parentheses", "no")
                        .child(X::text("beat-unit", "quarter"))
                        .child(X::text("per-minute", n.to_string())),
                ),
            );
            off(&mut x, true);
            x.push(X::new("sound").attr("tempo", n.to_string()));
            x
        }
        Dir::Rehearsal(l) => {
            let mut x = X::new("direction").child(
                X::new("direction-type").child(X::text("rehearsal", l.clone()).attr("halign", "center").attr("valign", "middle")),
            );
            off(&mut x, true);
            x
        }
        Dir::Dynamic(m) => {
            let volume = match m.as_str() {
                "pppppp" => 0.02,
                "ppppp" => 0.05,
                "pppp" => 0.1,
                "ppp" => 0.15,
                "pp" => 0.25,
                "p" => 0.35,
                "mp" => 0.45,
                "mf" => 0.55,
                "f" => 0.7,
                "ff" => 0.85,
                "fff" => 0.9,
                "ffff" => 0.95,
                _ => 0.99,
            };
            let mut x = X::new("direction").child(
                X::new("direction-type").child(X::new("dynamics").attr("default-x", "-36").attr("default-y", "-80").child(X::new(m))),
            );
            off(&mut x, true);
            x.push(X::new("sound").attr("dynamics", ((volume * 127.0) as i64).to_string()));
            x
        }
    }
}

fn transpose_xml(diatonic: i32, chromatic: i32) -> X {
    let generic = if diatonic >= 0 { diatonic + 1 } else { diatonic - 1 };
    let a = generic.abs() - 1;
    let (mut oct, mut dia) = (a / 7, a % 7);
    let mut chrom = chromatic.abs() % 12;
    if generic < 0 {
        dia = -dia;
        oct = -oct;
        chrom = -chrom;
    }
    let mut x = X::new("transpose").child(X::text("diatonic", dia.to_string())).child(X::text("chromatic", chrom.to_string()));
    if oct != 0 {
        x.push(X::text("octave-change", oct.to_string()));
    }
    x
}

/// `line_base`: review brackets in the parts before this one (the reference numbers them 1..6 across the
/// whole score, in part order).
fn part_xml(part: &Part, idx: usize, bpb: i64, line_base: usize) -> X {
    let bar = Rat::int(bpb);
    let mut px = X::new("part").attr("id", format!("P{}", idx + 1));
    for (mi, m) in part.measures.iter().enumerate() {
        let mut mx = X::new("measure").attr("implicit", "no").attr("number", (mi + 1).to_string());
        if mi > 0 {
            if let Some(f) = m.key {
                mx.push(X::new("attributes").child(X::new("key").child(X::text("fifths", f.to_string()))));
            }
        }
        if mi == 0 {
            let mut at = X::new("attributes").child(X::text("divisions", DIVISIONS.to_string()));
            if let Some(f) = m.key {
                at.push(X::new("key").child(X::text("fifths", f.to_string())));
            }
            at.push(X::new("time").child(X::text("beats", bpb.to_string())).child(X::text("beat-type", "4")));
            at.push(match part.clef {
                ClefKind::Treble => X::new("clef").child(X::text("sign", "G")).child(X::text("line", "2")),
                ClefKind::Bass => X::new("clef").child(X::text("sign", "F")).child(X::text("line", "4")),
                ClefKind::Percussion => X::new("clef").child(X::text("sign", "percussion")),
            });
            if let Some((d, c)) = part.transposition() {
                at.push(transpose_xml(d, c));
            }
            mx.push(at);
        }
        // offset groups: directions first, then notes
        let mut offsets: Vec<Rat> = m.els.iter().map(|e| e.off).chain(m.dirs.iter().map(|d| d.0)).collect();
        offsets.sort();
        offsets.dedup();
        let mut children = Vec::new();
        let mut cur = Rat::ZERO;
        // The reference exporter (music21) tracks the position in the measure as a float sum of the
        // written lengths, and writes a direction's <offset> whenever its exact offset differs from that
        // sum: after tuplets the float drifts, and a zero <offset> appears.
        let mut cur_f = 0.0f64;
        for o in offsets {
            if o > cur && m.els.iter().any(|e| e.off == o) {
                let fwd = (Rat::int(DIVISIONS) * (o - cur)).round_even();
                children.push(X::new("forward").child(X::text("duration", fwd.to_string())));
                cur_f += (o - cur).to_f64();
                cur = o;
            }
            for (_, d) in m.dirs.iter().filter(|d| d.0 == o) {
                let exact = o.d & (o.d - 1) == 0 && o.to_f64() == cur_f;
                let off = if exact { None } else { Some(((o.to_f64() - cur_f) * DIVISIONS as f64) as i64) };
                children.push(dir_xml(d, off));
            }
            for e in m.els.iter().filter(|e| e.off == o) {
                for (k, l) in part.lines.iter().enumerate() {
                    if l.0 == e.id {
                        children.push(bracket_xml(line_base + k, "start"));
                    }
                }
                elem_xml(e, bar, &mut children);
                for (k, l) in part.lines.iter().enumerate() {
                    if l.1 == e.id {
                        children.push(bracket_xml(line_base + k, "stop"));
                    }
                }
                cur = cur + e.dur.ql;
                cur_f += e.dur.ql.to_f64();
            }
        }
        mx.children.extend(children);
        if let Some(b) = m.barline {
            let style = if b == "final" { "light-heavy" } else { b };
            mx.push(X::new("barline").attr("location", "right").child(X::text("bar-style", style)));
        }
        px.push(mx);
    }
    px
}

/// A dashed review bracket (spanner number: its index in the score, cycling 1..6).
fn bracket_xml(k: usize, typ: &str) -> X {
    X::new("direction").attr("placement", "above").child(
        X::new("direction-type").child(
            X::new("bracket").attr("number", ((k % 6) + 1).to_string()).attr("line-type", "dashed").attr("type", typ).attr("line-end", "down"),
        ),
    )
}

/// Assign MIDI channels as the reference exporter does: in part order, skipping
/// the percussion channel, and falling back to channel 1 once 15 are used.
fn midi_channels(parts: &[Part]) -> Vec<i64> {
    let mut used: Vec<Option<i64>> = Vec::new();
    let auto = |used: &[Option<i64>], perc: bool| -> Result<i64, ()> {
        let set: HashSet<Option<i64>> = used.iter().copied().collect();
        if perc && !set.contains(&Some(9)) {
            return Ok(9);
        }
        if set.is_empty() {
            return Ok(0);
        }
        if set.len() >= 15 {
            return Err(());
        }
        for ch in 0..16 {
            if set.contains(&Some(ch)) || ch % 16 == 9 {
                continue;
            }
            return Ok(ch);
        }
        Ok(0)
    };
    let mut assigned: Vec<(Option<i64>, bool)> = Vec::new();
    for p in parts {
        let perc = p.is_drums();
        let mut ch: Option<i64> = if perc { Some(9) } else { None };
        if ch.is_none() || used.contains(&ch) {
            ch = auto(&used, perc).ok();
        }
        used.push(ch);
        assigned.push((ch, perc));
    }
    assigned.into_iter().map(|(c, perc)| c.unwrap_or_else(|| auto(&used, perc).unwrap_or(0))).collect()
}

fn score_part_xml(part: &Part, idx: usize, channel: i64, sounds: &[(String, String)]) -> X {
    let mut sp = X::new("score-part").attr("id", format!("P{}", idx + 1)).child(X::text("part-name", part.name.clone()));
    if let Some(inst) = part.inst {
        sp.push(X::text("part-abbreviation", part.abbreviation.clone().unwrap_or_else(|| inst.short.to_string())));
        let iid = format!("I{}", idx + 1);
        let mut si = X::new("score-instrument").attr("id", iid.clone()).child(X::text("instrument-name", inst.name));
        if inst.is_percussion() {
            si.push(X::text("instrument-abbreviation", "Perc"));
        }
        if let Some((_, s)) = sounds.iter().find(|(n, _)| *n == part.name) {
            si.push(X::text("instrument-sound", s.clone()));
        }
        sp.push(si);
        let mut mi = X::new("midi-instrument").attr("id", iid).child(X::text("midi-channel", (channel + 1).to_string()));
        if !inst.is_percussion() {
            mi.push(X::text("midi-program", (inst.gm_program + 1).to_string()));
        }
        sp.push(mi);
    }
    sp
}

pub const XML_HEAD: &str = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<!DOCTYPE score-partwise  PUBLIC \"-//Recordare//DTD MusicXML 4.0 Partwise//EN\" \"http://www.musicxml.org/dtds/partwise.dtd\">\n";

pub fn to_string(root: &X) -> String {
    let mut out = String::from(XML_HEAD);
    root.write(0, &mut out);
    out
}

/// Build the score and write it as MusicXML (written pitch for transposing parts).
pub fn write_score(spec: &ScoreSpec) -> String {
    to_string(&build_score_xml(spec))
}

/// The score and its individual parts ((file name, MusicXML) in score order), with a footer on
/// each part named in `footers` ((part name, text)).
pub fn write_score_with_parts(spec: &ScoreSpec, footers: &[(String, String)]) -> (String, Vec<(String, String)>) {
    let root = build_score_xml(spec);
    let parts = super::parts::split_parts_with_footers(&root, footers).into_iter().map(|(n, d)| (n, to_string(&d))).collect();
    (to_string(&root), parts)
}

/// Build the score as an element tree.
pub fn build_score_xml(spec: &ScoreSpec) -> X {
    let mut ids = Ids(0);
    let (mut parts, _total) = build_parts(spec, &mut ids);
    let bar = Rat::int(spec.beats_per_bar);
    let seq = BeamSequence::for_quarters(spec.beats_per_bar);

    // notation at concert pitch
    for part in parts.iter_mut() {
        make_accidentals(part);
        make_ties(part, bar, &mut ids);
        for m in part.measures.iter_mut() {
            split_to_complete_tuplets(m, &mut ids);
            consolidate_tuplets(m);
        }
        make_beams(part, &seq);
        for m in part.measures.iter_mut() {
            if !m.tuplets_made() {
                make_tuplet_brackets(m);
            }
        }
    }
    // dashed bar lines inside free-time passages
    if !spec.free_spans.is_empty() {
        let bar_ticks = spec.beats_per_bar * TPB;
        for part in parts.iter_mut() {
            for (k, m) in part.measures.iter_mut().enumerate() {
                let end = (k as i64 + 1) * bar_ticks + spec.pickup_ticks;
                if spec.free_spans.iter().any(|sp| sp.start < end && end < sp.end) {
                    m.barline = Some("dashed");
                }
            }
        }
    }
    // written pitch (a copy)
    if parts.iter().any(|p| p.transposition().is_some()) {
        deep_copy(&mut parts);
        for part in parts.iter_mut() {
            to_written(part);
        }
    }
    for part in parts.iter_mut() {
        plain_spellings(part);
        trill_accidentals(part);
    }
    // export: the exporter's own copy and notation pass
    deep_copy(&mut parts);
    for part in parts.iter_mut() {
        for m in part.measures.iter_mut() {
            split_to_complete_tuplets(m, &mut ids);
            consolidate_tuplets(m);
            if !m.tuplets_made() {
                make_tuplet_brackets(m);
            }
        }
        for m in part.measures.iter_mut() {
            split_at_durations(m, bar, &mut ids, &mut part.lines);
        }
        if !have_accidentals_been_made(part) {
            make_accidentals(part);
        }
        let part_tuplets = have_tuplet_brackets(part.all_els()).unwrap_or(true);
        if !part_tuplets {
            for m in part.measures.iter_mut() {
                make_tuplet_brackets(m);
            }
        }
    }

    for part in parts.iter_mut() {
        trill_lines(part);
    }
    let channels = midi_channels(&parts);
    let mut root = X::new("score-partwise").attr("version", "4.0");
    // No <movement-title>: it would repeat the work title, and readers show it as a subtitle.
    root.push(X::new("work").child(X::text("work-title", spec.title.clone())));
    let mut encoding = X::new("encoding");
    if !spec.encoding_date.is_empty() {
        encoding.push(X::text("encoding-date", spec.encoding_date.clone()));
    }
    encoding.push(X::text("software", format!("brasscribe-core {}", env!("CARGO_PKG_VERSION"))));
    for el in ["beam", "stem", "accidental"] {
        encoding.push(X::new("supports").attr("element", el).attr("type", "yes"));
    }
    root.push(X::new("identification").child(X::text("creator", "arr. Brasscribe").attr("type", "composer")).child(encoding));
    root.push(X::new("defaults").child(X::new("scaling").child(X::text("millimeters", "7")).child(X::text("tenths", "40"))));
    let mut pl = X::new("part-list");
    for (i, p) in parts.iter().enumerate() {
        pl.push(score_part_xml(p, i, channels[i], &spec.sounds));
    }
    root.push(pl);
    let mut line_base = 0;
    for (i, p) in parts.iter().enumerate() {
        root.push(part_xml(p, i, spec.beats_per_bar, line_base));
        line_base += p.lines.len();
    }
    if !spec.sounds.is_empty() {
        band_midi(&mut root, spec.kit_program);
    }
    root
}

#[allow(dead_code)]
fn _unused(_: DType) {}

// ---------------------------------------------------------------------------
// MIDI setup for the band SoundFont

/// Percussion instruments by written position and notehead, as General MIDI notes.
const DRUM_SOUNDS: [(&str, &str, i64, &str); 13] = [
    ("F4", "normal", 36, "Bass Drum"),
    ("C5", "normal", 38, "Snare Drum"),
    ("C5", "x", 37, "Side Stick"),
    ("A4", "normal", 43, "Floor Tom"),
    ("D5", "normal", 47, "Low-Mid Tom"),
    ("E5", "normal", 50, "High Tom"),
    ("G5", "x", 42, "Closed Hi-Hat"),
    ("D4", "x", 44, "Pedal Hi-Hat"),
    ("G5", "circle-x", 46, "Open Hi-Hat"),
    ("A5", "x", 49, "Crash Cymbal"),
    ("F5", "x", 51, "Ride Cymbal"),
    ("F5", "diamond", 53, "Ride Bell"),
    ("B5", "x", 54, "Tambourine"),
];
const DRUM_CHANNEL: i64 = 10;

fn drum_sound(pos: &str, head: &str) -> (i64, &'static str) {
    let hit = DRUM_SOUNDS.iter().find(|d| d.0 == pos && d.1 == head).unwrap_or(&DRUM_SOUNDS[12]);
    (hit.2, hit.3)
}

fn attr_of<'a>(e: &'a X, k: &str) -> Option<&'a str> {
    e.attrs.iter().find(|(n, _)| n == k).map(|(_, v)| v.as_str())
}

fn child_text(e: &X, tag: &str) -> Option<String> {
    e.children.iter().find(|c| c.name == tag).map(|c| c.text.clone().unwrap_or_default())
}

fn has_descendant(e: &X, tag: &str) -> bool {
    e.children.iter().any(|c| c.name == tag || has_descendant(c, tag))
}

/// Every drum note gets `<instrument id>`; returns the GM notes used with their names.
fn tag_drum_notes(e: &mut X, base: &str, used: &mut Vec<(i64, &'static str)>) {
    for c in e.children.iter_mut() {
        if c.name == "note" {
            if let Some(u) = c.children.iter().find(|x| x.name == "unpitched") {
                let pos = format!("{}{}", child_text(u, "display-step").unwrap_or_else(|| "None".into()), child_text(u, "display-octave").unwrap_or_else(|| "None".into()));
                let head = child_text(c, "notehead").filter(|h| !h.is_empty()).unwrap_or_else(|| "normal".into());
                let (gm, label) = drum_sound(&pos, &head);
                match used.iter_mut().find(|(g, _)| *g == gm) {
                    Some(x) => x.1 = label,
                    None => used.push((gm, label)),
                }
                // Schema order: ..., duration, tie*, instrument, voice, type, ...
                let after = c.children.iter().rposition(|x| ["unpitched", "duration", "tie", "chord", "grace", "cue"].contains(&x.name.as_str()));
                let at = after.map(|i| i + 1).unwrap_or(0);
                c.children.insert(at, X::new("instrument").attr("id", format!("{base}-{gm}")));
            }
        }
        tag_drum_notes(c, base, used);
    }
}

/// Pitched parts: their preset's <midi-bank> and a channel of their own in
/// score order, skipping the drum channel; past 15 parts the channels continue
/// on MIDI port 2. Percussion: one score-instrument per drum sound used, on
/// channel 10 with <midi-unpitched> = GM note + 1, and an <instrument id> on
/// every note; a kit other than the band kit (`kit_program`, 0-based: the pop
/// kit is 1) as <midi-program> on each of those.
fn band_midi(root: &mut X, kit_program: i64) {
    let banks: Vec<(&'static str, i64)> = crate::instruments::part_banks();
    let channels: Vec<i64> = (1..=16).filter(|&c| c != DRUM_CHANNEL).collect();
    let Some(pl) = root.children.iter().position(|c| c.name == "part-list") else { return };
    let mut k = 0usize;
    for si in 0..root.children[pl].children.len() {
        if root.children[pl].children[si].name != "score-part" {
            continue;
        }
        let pid = attr_of(&root.children[pl].children[si], "id").unwrap_or("").to_string();
        let part_idx = root.children.iter().position(|c| c.name == "part" && attr_of(c, "id") == Some(pid.as_str()));
        if let Some(pi) = part_idx.filter(|&pi| has_descendant(&root.children[pi], "unpitched")) {
            let sp = &root.children[pl].children[si];
            let base = sp.children.iter().find(|c| c.name == "score-instrument").and_then(|c| attr_of(c, "id")).unwrap_or("").to_string();
            let mut used = Vec::new();
            tag_drum_notes(&mut root.children[pi], &base, &mut used);
            used.sort_by_key(|u| u.0);
            let sp = &mut root.children[pl].children[si];
            sp.children.retain(|c| !["score-instrument", "midi-instrument", "midi-device"].contains(&c.name.as_str()));
            for (gm, label) in &used {
                sp.push(X::new("score-instrument").attr("id", format!("{base}-{gm}")).child(X::text("instrument-name", *label)).child(X::text("instrument-sound", "drum.group.set")));
            }
            for (gm, _) in &used {
                let mut mi = X::new("midi-instrument").attr("id", format!("{base}-{gm}")).child(X::text("midi-channel", DRUM_CHANNEL.to_string()));
                if kit_program != 0 {
                    mi.push(X::text("midi-program", (kit_program + 1).to_string()));
                }
                sp.push(mi.child(X::text("midi-unpitched", (gm + 1).to_string())));
            }
            continue;
        }
        let sp = &mut root.children[pl].children[si];
        let name = child_text(sp, "part-name").unwrap_or_default().trim().to_string();
        let Some(mi) = sp.children.iter().position(|c| c.name == "midi-instrument") else { continue };
        let (port, channel) = (k / channels.len(), k % channels.len());
        k += 1;
        let mi_id = attr_of(&sp.children[mi], "id").unwrap_or("").to_string();
        {
            let m = &mut sp.children[mi];
            match m.children.iter().position(|c| c.name == "midi-channel") {
                Some(ci) => m.children[ci].text = Some(channels[channel].to_string()),
                None => m.children.insert(0, X::text("midi-channel", channels[channel].to_string())),
            }
            if let Some((_, bank)) = banks.iter().find(|(n, _)| *n == name) {
                if !m.children.iter().any(|c| c.name == "midi-bank") {
                    let after = m.children.iter().rposition(|c| c.name == "midi-channel" || c.name == "midi-name");
                    m.children.insert(after.map(|i| i + 1).unwrap_or(0), X::text("midi-bank", bank.to_string()));
                }
            }
        }
        if port > 0 {
            sp.children.insert(mi, X::new("midi-device").attr("id", mi_id).attr("port", (port + 1).to_string()));
        }
    }
}
