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
use super::pitch::{altered_names, transpose, transpose_key, update_accidental_display, P};
use super::xml::El as X;
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
}

impl PartSpec {
    pub fn concert(name: &str, notes: Vec<QNote>, clef: &str) -> PartSpec {
        PartSpec { name: name.into(), notes, clef: clef.into(), instrument: None }
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
    pub low_confidence: f64,
    pub key_fifths: Option<i32>,
    /// Part name -> MusicXML <instrument-sound>.
    pub sounds: Vec<(String, String)>,
    pub free_spans: Vec<FreeSpan>,
    pub encoding_date: String,
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
    pub color: bool,
    pub staccato: bool,
    pub fermata: bool,
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
    Words(String),
    Metro(i64),
}

#[derive(Clone, Debug)]
struct Measure {
    els: Vec<Elem>,
    dirs: Vec<(Rat, Dir)>,
    barline: Option<&'static str>,
    tuplets: Option<bool>,
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
    inst: Option<&'static Instrument>,
    clef: ClefKind,
    fifths: Option<i32>,
    measures: Vec<Measure>,
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
        if i + 1 < starts.len() {
            end = end.min(starts[i + 1]);
        }
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
        let mut dirs: Vec<(i64, u8, Dir)> = Vec::new();
        if pi == 0 && !opens_free {
            dirs.push((0, 1, Dir::Metro(py_round_bpm(spec.bpm))));
        }
        for sp in &spec.free_spans {
            let (a, b) = (sp.start - spec.pickup_ticks, sp.end - spec.pickup_ticks);
            if a >= 0 {
                dirs.push((a, 0, Dir::Words(sp.label.clone())));
                if pi == 0 {
                    dirs.push((a, 1, Dir::Metro(py_round_bpm(sp.bpm))));
                }
            }
            if 0 <= b && b < total {
                dirs.push((b, 0, Dir::Words("a tempo".into())));
                if pi == 0 {
                    dirs.push((b, 1, Dir::Metro(py_round_bpm(spec.bpm))));
                }
            }
        }
        // stable: offset, then class order (text before tempo), then insertion
        dirs.sort_by_key(|d| (d.0, d.1));

        let mut flat_els: Vec<Elem> = Vec::new();
        let rest = |ids: &mut Ids, from: i64, to: i64| Elem {
            id: ids.next(),
            off: Rat::new(from, TPB),
            dur: Dur::from_ql(Rat::new(to - from, TPB)),
            kind: Kind::Rest,
            beams: Vec::new(),
            stem: None,
            color: false,
            staccato: false,
            fermata: false,
        };
        let mut cursor = 0i64;
        for ev in &part_events[pi] {
            let tick = ev.start;
            let start = ev.start - spec.pickup_ticks;
            let end = ev.end - spec.pickup_ticks;
            if start < 0 {
                continue;
            }
            if start > cursor {
                flat_els.push(rest(ids, cursor, start));
            }
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
                    Kind::Note(sp[0], None)
                } else {
                    Kind::Chord(sp.into_iter().map(|p| (p, None)).collect())
                }
            };
            flat_els.push(Elem {
                id: ids.next(),
                off: Rat::new(start, TPB),
                dur: Dur::from_ql(Rat::new(end - start, TPB)),
                kind,
                beams: Vec::new(),
                stem: None,
                color: ev.conf < spec.low_confidence,
                staccato: !drums && ev.arts.contains("staccato"),
                fermata: !drums && ev.arts.contains("fermata"),
            });
            cursor = end;
        }
        if cursor < total {
            flat_els.push(rest(ids, cursor, total));
        }

        // measures (bar lines every `bar`, at least one bar, up to the last element)
        let bar_ql = Rat::int(spec.beats_per_bar);
        let o_max = flat_els.iter().map(|e| e.end()).chain(dirs.iter().map(|d| Rat::new(d.0, TPB))).max().unwrap_or(Rat::ZERO);
        let mut n_measures = 1usize;
        let mut o = bar_ql;
        while o < o_max {
            n_measures += 1;
            o = o + bar_ql;
        }
        let mut measures: Vec<Measure> =
            (0..n_measures).map(|_| Measure { els: Vec::new(), dirs: Vec::new(), barline: None, tuplets: None }).collect();
        for mut e in flat_els {
            let k = ((e.off / bar_ql).n.div_euclid((e.off / bar_ql).d)) as usize;
            // makeNotation works on a deep copy, but these durations have not been
            // expanded into components yet, so they keep counting as inferred.
            e.off = e.off - bar_ql * Rat::int(k as i64);
            measures[k].els.push(e);
        }
        for (t, _, d) in dirs {
            let off = Rat::new(t, TPB);
            let k = ((off / bar_ql).n.div_euclid((off / bar_ql).d)) as usize;
            measures[k].dirs.push((off - bar_ql * Rat::int(k as i64), d));
        }
        measures.last_mut().unwrap().barline = Some("final");
        let clef = if drums {
            ClefKind::Percussion
        } else if p.clef == "bass" {
            ClefKind::Bass
        } else {
            ClefKind::Treble
        };
        parts.push(Part { name: p.name.clone(), inst: p.instrument, clef, fifths: if drums { None } else { Some(fifths) }, measures });
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

fn make_accidentals(part: &mut Part) {
    let altered = part.fifths.map(altered_names).unwrap_or_default();
    let mut tie_set: Option<HashSet<(u8, i32, i32)>> = None;
    let mut past_measure: Vec<P> = Vec::new();
    for i in 0..part.measures.len() {
        if i > 0 {
            past_measure = part.measures[i - 1].els.iter().flat_map(|e| e.pitches()).collect();
            if let Some(last) = part.measures[i - 1].els.iter().rev().find(|e| !e.is_rest()) {
                tie_set = tie_pitch_set(last);
            }
        }
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
            let same = (gn.is_rest() && prev.is_rest()) || (!gn.is_rest() && !prev.is_rest() && gn.pitches() == prev.pitches());
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

fn split_at_durations(m: &mut Measure, bar: Rat, ids: &mut Ids) {
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

const COLOR: &str = "#D0021B";

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
    if e.color {
        n.set("color", COLOR);
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
    if !matches!(head, Head::Rest) && (member_notehead != "normal" || e.color) {
        let mut nh = X::text("notehead", member_notehead).attr("parentheses", "no");
        if e.color {
            nh.set("color", COLOR);
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

fn dir_xml(d: &Dir) -> X {
    match d {
        Dir::Words(w) => X::new("direction").child(X::new("direction-type").child(X::text("words", w.clone()))),
        Dir::Metro(n) => X::new("direction")
            .child(
                X::new("direction-type").child(
                    X::new("metronome")
                        .attr("parentheses", "no")
                        .child(X::text("beat-unit", "quarter"))
                        .child(X::text("per-minute", n.to_string())),
                ),
            )
            .child(X::new("sound").attr("tempo", n.to_string())),
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

fn part_xml(part: &Part, idx: usize, bpb: i64) -> X {
    let bar = Rat::int(bpb);
    let mut px = X::new("part").attr("id", format!("P{}", idx + 1));
    for (mi, m) in part.measures.iter().enumerate() {
        let mut mx = X::new("measure").attr("implicit", "no").attr("number", (mi + 1).to_string());
        if mi == 0 {
            let mut at = X::new("attributes").child(X::text("divisions", DIVISIONS.to_string()));
            if let Some(f) = part.fifths {
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
        for o in offsets {
            for (_, d) in m.dirs.iter().filter(|d| d.0 == o) {
                children.push(dir_xml(d));
            }
            for e in m.els.iter().filter(|e| e.off == o) {
                elem_xml(e, bar, &mut children);
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
        sp.push(X::text("part-abbreviation", inst.short));
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

/// Build the score and write it as MusicXML (written pitch for transposing parts).
pub fn write_score(spec: &ScoreSpec) -> String {
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
            split_at_durations(m, bar, &mut ids);
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

    let channels = midi_channels(&parts);
    let mut root = X::new("score-partwise").attr("version", "4.0");
    root.push(X::new("work").child(X::text("work-title", spec.title.clone())));
    root.push(X::text("movement-title", spec.title.clone()));
    let mut encoding = X::new("encoding");
    if !spec.encoding_date.is_empty() {
        encoding.push(X::text("encoding-date", spec.encoding_date.clone()));
    }
    encoding.push(X::text("software", format!("brasscribe-core {}", env!("CARGO_PKG_VERSION"))));
    for el in ["beam", "stem", "accidental"] {
        encoding.push(X::new("supports").attr("element", el).attr("type", "yes"));
    }
    root.push(X::new("identification").child(X::text("creator", "arr. brasscribe").attr("type", "composer")).child(encoding));
    root.push(X::new("defaults").child(X::new("scaling").child(X::text("millimeters", "7")).child(X::text("tenths", "40"))));
    let mut pl = X::new("part-list");
    for (i, p) in parts.iter().enumerate() {
        pl.push(score_part_xml(p, i, channels[i], &spec.sounds));
    }
    root.push(pl);
    for (i, p) in parts.iter().enumerate() {
        root.push(part_xml(p, i, spec.beats_per_bar));
    }
    let mut out = String::from(
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<!DOCTYPE score-partwise  PUBLIC \"-//Recordare//DTD MusicXML 4.0 Partwise//EN\" \"http://www.musicxml.org/dtds/partwise.dtd\">\n",
    );
    root.write(0, &mut out);
    out
}

#[allow(dead_code)]
fn _unused(_: DType) {}
