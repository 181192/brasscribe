//! String and fret assignment: a Viterbi search over hand states, one onset at a time.
//!
//! Notes that start together form an event. Each event has voicings (every note on its own string)
//! and each voicing is paired with a hand position `p` (the neck fret under the index finger). The
//! cheapest path through these states minimises the per-state cost (span, height on the neck, open
//! strings) plus the per-transition cost (moving the hand, dropping a melody note far below the
//! hand). Stray notes and short fills are set aside first and reached from the line afterwards. A
//! second pass pulls repeated pitch sequences onto the fingering most of their occurrences got.
//! See the crate README for the cost model.

use std::collections::{BTreeMap, HashMap};

use brasscribe_core::model::{check_span, Note, TICKS_PER_BEAT};
use serde::{Deserialize, Serialize};

use crate::instrument::{Instrument, Position};
use crate::shapes::{is_power_chord, open_shapes};
use crate::technique::{per_note, previous_note, string_link, Technique};

/// How a passage should sit on the neck.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Style {
    /// Low positions and open strings where they fit: folk, pop, first chords.
    OpenPosition,
    /// Neutral: the cheapest playable fingering with only a mild pull towards the nut.
    #[default]
    AsPlayed,
    /// Solo lines: keeps a phrase in one position and avoids open strings in melodic lines.
    Lead,
}

/// Hand span limits, measured between the lowest and highest fretted note in millimetres.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct HandLimits {
    /// Spans up to this are free.
    pub comfortable_mm: f64,
    /// Spans beyond this are not played.
    pub max_mm: f64,
}

impl Default for HandLimits {
    fn default() -> Self {
        HandLimits { comfortable_mm: 100.0, max_mm: 140.0 }
    }
}

/// Fix the string of one note; the solver treats it as a hard constraint.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Pin {
    /// Index of the note in the input.
    pub note: usize,
    pub string: u8,
}

#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Options {
    pub style: Style,
    /// Tempo for turning ticks into seconds; None counts in beats (as at 120 BPM).
    pub tempo_bpm: Option<f64>,
    pub hand: HandLimits,
    pub pins: Vec<Pin>,
}

impl Options {
    pub fn validate(&self, instrument: &Instrument, notes: usize) -> Result<(), String> {
        if let Some(t) = self.tempo_bpm {
            if !(t.is_finite() && t > 0.0) {
                return Err(format!("the tempo must be a positive number of beats per minute, not {t}"));
            }
        }
        let h = self.hand;
        if !(h.comfortable_mm.is_finite() && h.max_mm.is_finite() && h.comfortable_mm > 0.0 && h.max_mm >= h.comfortable_mm) {
            return Err(format!("hand limits must be positive with the maximum at least the comfortable span, not {} and {}", h.comfortable_mm, h.max_mm));
        }
        for pin in &self.pins {
            if pin.note >= notes {
                return Err(format!("a pin names note {} of {notes}", pin.note));
            }
            if pin.string == 0 || usize::from(pin.string) > instrument.string_count() {
                return Err(format!("a pin names string {} of {}", pin.string, instrument.string_count()));
            }
        }
        Ok(())
    }

    /// The string pinned for note `i`, the first pin naming it.
    pub fn pin_for(&self, i: usize) -> Option<u8> {
        self.pins.iter().find(|p| p.note == i).map(|p| p.string)
    }
}

/// Where one input note is played.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct NotePlace {
    /// The input pitch, unchanged.
    pub pitch: i32,
    pub string: Option<u8>,
    /// Relative to the capo; 0 = open.
    pub fret: Option<u8>,
    /// Other positions that sound the same pitch, cheapest first.
    pub alternatives: Vec<Position>,
    /// No position on this instrument sounds the pitch.
    pub out_of_range: bool,
    /// The caller pinned this note's string.
    pub pinned: bool,
}

impl NotePlace {
    pub fn position(&self) -> Option<Position> {
        Some(Position { string: self.string?, fret: self.fret? })
    }
}

/// One [`NotePlace`] per input note, in input order.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Fingering {
    pub notes: Vec<NotePlace>,
}

/// Cost weights of one style. Distances are millimetres on the neck.
#[derive(Debug, Clone, Copy)]
struct Weights {
    /// Per mm of hand position above the nut (or capo), for states with fretted notes.
    height: f64,
    /// Per open string in a chord (negative: a bonus).
    open_chord: f64,
    /// Per open string in a single-note line.
    open_melodic: f64,
    /// Per mm the hand moves between events.
    shift_mm: f64,
    /// Per move of the hand, however small.
    shift_fixed: f64,
    /// Per mm a melody note sits below a neighbouring hand position by more than a hand's width.
    drop_mm: f64,
    /// Excursions (stray notes, short fills) are set aside while the rest of the line is placed,
    /// then reached from it.
    excursions: bool,
    /// Per mm of voicing span (lowest to highest fretted note).
    span_mm: f64,
    /// Per mm squared the reach from the index finger exceeds the comfortable span.
    stretch_sq: f64,
    /// For a repeated passage fingered differently from its other occurrences.
    repeat: f64,
    /// For a power chord from the shape table (negative: a bonus).
    power: f64,
    /// For a strummed chord played as its open shape from the shape table (negative: a bonus).
    open_shape: f64,
}

fn weights(style: Style) -> Weights {
    match style {
        Style::OpenPosition => Weights {
            height: 0.015,
            open_chord: -2.0,
            open_melodic: -1.0,
            shift_mm: 0.03,
            shift_fixed: 1.5,
            drop_mm: 0.03,
            excursions: true,
            span_mm: 0.01,
            stretch_sq: 0.01,
            repeat: 25.0,
            power: -6.0,
            open_shape: -6.0,
        },
        Style::AsPlayed => Weights {
            height: 0.01,
            open_chord: -0.5,
            open_melodic: 0.0,
            shift_mm: 0.03,
            shift_fixed: 3.0,
            drop_mm: 0.04,
            excursions: true,
            span_mm: 0.01,
            stretch_sq: 0.01,
            repeat: 25.0,
            power: -4.0,
            open_shape: -4.0,
        },
        Style::Lead => Weights {
            height: 0.002,
            open_chord: 0.0,
            open_melodic: 3.0,
            shift_mm: 0.06,
            shift_fixed: 3.0,
            drop_mm: 0.06,
            excursions: false,
            span_mm: 0.01,
            stretch_sq: 0.01,
            repeat: 25.0,
            power: -4.0,
            open_shape: 0.0,
        },
    }
}

/// Time for a shift at which its cost doubles, in seconds.
const SHIFT_TIME_S: f64 = 0.25;
/// Frets under the hand besides the index finger's: a note more than this below the hand needs it
/// to move.
const HAND_FRETS: i32 = 3;
/// Most voicings kept per event (the cheapest).
const MAX_VOICINGS: usize = 64;
/// Most leaves the voicing search visits per pass, so huge clusters stay bounded.
const LEAF_CAP: usize = 50_000;
/// Most notes in a row that can be an excursion: a bar of eighths.
const EXCURSION_NOTES: usize = 8;
/// Most notes in a row that are stray notes; a longer excursion is a fill.
const STRAY_NOTES: usize = 2;
/// Fewest semitones between a stray note and the notes on either side of the excursion.
const STRAY_LEAP: i32 = 7;
/// The same for every note of a fill: more than an octave, so that an arpeggio over its root or a
/// phrase an octave up is not taken for one.
const FILL_LEAP: i32 = 13;
/// Most semitones between the notes on either side of an excursion.
const EXCURSION_RETURN: i32 = 5;
/// The cost of breaking a technique constraint: the search only does it when nothing else fits.
const HARD: f64 = 1e6;
/// Most re-solves that move notes off strings reserved by a let-ring note.
const RING_PASSES: usize = 8;

#[derive(Debug, Clone, Copy)]
struct Cand {
    pos: Position,
    /// Neck fret; 0 when open.
    neck: i32,
}

#[derive(Debug)]
struct Group {
    pitch: i32,
    notes: Vec<usize>,
    cands: Vec<Cand>,
    pin: Option<u8>,
    /// A bend: fretted positions only.
    bend: bool,
    /// Strings this group may not use (reserved by a ringing note).
    forbid: Vec<u8>,
    /// Group in the previous event whose string this one must keep (slide, hammer-on, pull-off,
    /// bend), and the most frets it may be from it there.
    link: Option<(usize, i32)>,
    /// Tick until which a let-ring note of this group reserves its string.
    ring_until: Option<i64>,
}

impl Group {
    fn new(pitch: i32, note: usize) -> Self {
        Group { pitch, notes: vec![note], cands: Vec::new(), pin: None, bend: false, forbid: Vec::new(), link: None, ring_until: None }
    }

    /// Candidates honouring the pin, the bend and the reserved strings. A constraint no position
    /// meets is dropped here and reported by the playability check.
    fn refresh(&mut self, inst: &Instrument) {
        let mut cands: Vec<Cand> = inst.positions(self.pitch).into_iter().map(|pos| Cand { pos, neck: inst.neck_fret(pos).unwrap_or(0) }).collect();
        let mut keep = |f: &dyn Fn(&Cand) -> bool| {
            let kept: Vec<Cand> = cands.iter().copied().filter(|c| f(c)).collect();
            if !kept.is_empty() {
                cands = kept;
            }
        };
        if let Some(pin) = self.pin {
            keep(&|c| c.pos.string == pin);
        }
        if self.bend {
            keep(&|c| c.neck > 0);
        }
        if !self.forbid.is_empty() {
            let forbid = self.forbid.clone();
            keep(&move |c| !forbid.contains(&c.pos.string));
        }
        self.cands = cands;
    }
}

#[derive(Debug)]
struct Voicing {
    /// Candidate index per group; None when the group has no string left.
    place: Vec<Option<usize>>,
    lo: i32,
    hi: i32,
    fretted: bool,
    opens: i32,
    /// String per group.
    strings: Vec<Option<u8>>,
}

#[derive(Debug, Clone, Copy)]
struct State {
    v: usize,
    p: i32,
    cost: f64,
}

#[derive(Debug)]
struct Event {
    start: i64,
    groups: Vec<Group>,
    voicings: Vec<Voicing>,
    states: Vec<State>,
    /// The open shape these notes form, as sorted positions.
    shape: Option<Vec<Position>>,
    /// Some group keeps the string of a note in the previous event.
    linked: bool,
    /// Some group has a let-ring note.
    rings: bool,
}

impl Event {
    fn melodic(&self) -> bool {
        self.groups.len() == 1
    }

    /// Neck fret of the single note of a melodic state (the capo for an open string).
    fn melody_fret(&self, s: &State, capo: i32) -> Option<i32> {
        if !self.melodic() {
            return None;
        }
        let c = self.groups[0].cands[self.voicings[s.v].place[0]?];
        Some(if c.neck == 0 { capo } else { c.neck })
    }

    fn positions(&self, v: usize) -> Vec<Option<Position>> {
        self.voicings[v].place.iter().zip(&self.groups).map(|(c, g)| c.map(|c| g.cands[c].pos)).collect()
    }
}

struct Ctx<'a> {
    inst: &'a Instrument,
    w: Weights,
    hand: HandLimits,
    mm: Vec<f64>,
    capo: i32,
    frets: i32,
    sec_per_tick: f64,
}

impl Ctx<'_> {
    fn mm(&self, neck: i32) -> f64 {
        self.mm[neck.clamp(0, self.frets) as usize]
    }

    fn span_mm(&self, lo: i32, hi: i32) -> f64 {
        self.mm(hi) - self.mm(lo)
    }

    fn state_cost(&self, ev: &Event, v: &Voicing, p: i32) -> f64 {
        let w = &self.w;
        let mut c = 0.0;
        if v.fretted {
            c += w.height * (self.mm(p) - self.mm(self.capo));
            c += w.span_mm * self.span_mm(v.lo, v.hi);
            let over = self.span_mm(p, v.hi) - self.hand.comfortable_mm;
            if over > 0.0 {
                c += w.stretch_sq * over * over;
            }
        }
        if !ev.melodic() && v.strings.iter().all(Option::is_some) {
            if (2..=3).contains(&ev.groups.len()) {
                let notes: Vec<(i32, u8)> = ev.groups.iter().zip(&v.strings).filter_map(|(g, s)| Some((g.pitch, (*s)?))).collect();
                if is_power_chord(&notes) {
                    c += w.power;
                }
            }
            if let Some(shape) = &ev.shape {
                let mut pos: Vec<Position> = v.place.iter().zip(&ev.groups).filter_map(|(c, g)| c.map(|c| g.cands[c].pos)).collect();
                pos.sort_unstable();
                if pos == *shape {
                    c += w.open_shape;
                }
            }
        }
        let open_w = if ev.melodic() { w.open_melodic } else { w.open_chord };
        c + open_w * f64::from(v.opens)
    }

    fn transition(&self, a: &Event, sa: &State, b: &Event, sb: &State) -> f64 {
        let w = &self.w;
        let dt = ((b.start - a.start) as f64 * self.sec_per_tick).max(0.02);
        let urgency = 1.0 + SHIFT_TIME_S / dt;
        let mut c = 0.0;
        if sa.p != sb.p {
            c += (w.shift_fixed + w.shift_mm * (self.mm(sa.p) - self.mm(sb.p)).abs()) * urgency;
        }
        // A melody note far below the neighbouring hand position: the open-string or low-fret
        // rendering of a line that is being played up the neck.
        if let Some(q) = b.melody_fret(sb, self.capo) {
            if q + HAND_FRETS < sa.p {
                c += w.drop_mm * (self.mm(sa.p) - self.mm(q));
            }
        }
        if let Some(q) = a.melody_fret(sa, self.capo) {
            if q + HAND_FRETS < sb.p {
                c += w.drop_mm * (self.mm(sb.p) - self.mm(q));
            }
        }
        let (va, vb) = (&a.voicings[sa.v], &b.voicings[sb.v]);
        if b.linked {
            for (gb, g) in b.groups.iter().enumerate() {
                let Some((ga, reach)) = g.link else { continue };
                let (Some(ca), Some(cb)) = (va.place[ga], vb.place[gb]) else { continue };
                let (from, to) = (a.groups[ga].cands[ca], g.cands[cb]);
                if from.pos.string != to.pos.string || (from.neck - to.neck).abs() > reach {
                    c += HARD;
                }
            }
        }
        if a.rings {
            for (ga, g) in a.groups.iter().enumerate() {
                if g.ring_until.is_some_and(|t| t > b.start) && va.strings[ga].is_some_and(|s| vb.strings.contains(&Some(s))) {
                    c += HARD;
                }
            }
        }
        c
    }
}

/// Choose a string and fret for every note. Notes starting on the same tick are played together;
/// pitches never change, and notes no position can sound are flagged `out_of_range`.
pub fn assign(inst: &Instrument, notes: &[Note], opts: &Options) -> Result<Fingering, String> {
    assign_with_techniques(inst, notes, &[], opts)
}

/// [`assign`] with playing techniques: one list per note (or none at all). Slides, hammer-ons,
/// pull-offs and bends keep the string of the note they come from; let ring reserves its string
/// until the note ends.
pub fn assign_with_techniques(inst: &Instrument, notes: &[Note], techniques: &[Vec<Technique>], opts: &Options) -> Result<Fingering, String> {
    inst.validate()?;
    let techniques = per_note(techniques, notes.len())?;
    opts.validate(inst, notes.len())?;
    for (i, n) in notes.iter().enumerate() {
        if !(0..=127).contains(&n.pitch) {
            return Err(format!("note {i}: pitch {} is outside MIDI 0-127", n.pitch));
        }
        check_span(n.start, n.start.saturating_add(n.dur.max(0))).map_err(|e| format!("note {i}: {e}"))?;
    }
    let bpm = opts.tempo_bpm.unwrap_or(120.0);
    let frets = i32::from(inst.frets);
    let ctx = Ctx {
        inst,
        w: weights(opts.style),
        hand: opts.hand,
        mm: (0..=frets).map(|f| inst.fret_mm(f)).collect(),
        capo: i32::from(inst.capo),
        frets,
        sec_per_tick: 60.0 / bpm / TICKS_PER_BEAT as f64,
    };

    let mut out: Vec<NotePlace> = notes
        .iter()
        .enumerate()
        .map(|(i, n)| NotePlace {
            pitch: n.pitch,
            string: None,
            fret: None,
            alternatives: Vec::new(),
            out_of_range: false,
            pinned: opts.pin_for(i).is_some(),
        })
        .collect();

    let mut events = build_events(&ctx, notes, opts, &techniques, &mut out);
    for ev in events.iter_mut() {
        build_states(&ctx, ev);
    }
    let mut path = solve_path(&ctx, &events);
    // A let-ring note reserves its string past the next event too; the search only sees
    // neighbouring events, so notes placed on a reserved string further on are moved and re-solved.
    for _ in 0..RING_PASSES {
        let mut changed = false;
        for (e, g, string) in ring_conflicts(&events, &path) {
            let group = &mut events[e].groups[g];
            if !group.forbid.contains(&string) {
                group.forbid.push(string);
                group.refresh(ctx.inst);
                build_states(&ctx, &mut events[e]);
                changed = true;
            }
        }
        if !changed {
            break;
        }
        path = solve_path(&ctx, &events);
    }

    for (e, ev) in events.iter().enumerate() {
        let chosen = ev.states[path[e]];
        let prev = e.checked_sub(1).map(|p| (&events[p], &events[p].states[path[p]]));
        let next = events.get(e + 1).map(|n| (n, &n.states[path[e + 1]]));
        for (g, group) in ev.groups.iter().enumerate() {
            let pos = ev.voicings[chosen.v].place[g].map(|c| group.cands[c].pos);
            let alternatives = rank_alternatives(&ctx, ev, g, pos, prev, next);
            for &i in &group.notes {
                let place = &mut out[i];
                place.string = pos.map(|p| p.string);
                place.fret = pos.map(|p| p.fret);
                place.alternatives = alternatives.clone();
            }
        }
    }
    Ok(Fingering { notes: out })
}

type Neighbour<'a> = Option<(&'a Event, &'a State)>;

/// The state chosen for every event. Excursions are left out while the rest of the line is solved,
/// so the notes around one sit where they would without it; each excursion is then solved on its
/// own between its neighbours, which stay where they are.
fn solve_path(ctx: &Ctx, events: &[Event]) -> Vec<usize> {
    let away = if ctx.w.excursions { excursions(events) } else { vec![false; events.len()] };
    let line: Vec<usize> = (0..events.len()).filter(|&e| !away[e]).collect();
    let mut path = vec![0; events.len()];
    for (&e, state) in line.iter().zip(solve_line(ctx, events, &line)) {
        path[e] = state;
    }
    let mut e = 0;
    while e < events.len() {
        if !away[e] {
            e += 1;
            continue;
        }
        let end = (e..events.len()).find(|&k| !away[k]).unwrap_or(events.len());
        let run: Vec<usize> = (e..end).collect();
        let before = e.checked_sub(1).map(|b| (&events[b], &events[b].states[path[b]]));
        let after = events.get(end).map(|a| (a, &a.states[path[end]]));
        for (&k, state) in run.iter().zip(viterbi(ctx, events, &run, &HashMap::new(), before, after)) {
            path[k] = state;
        }
        e = end;
    }
    path
}

/// Which events are excursions: up to [`EXCURSION_NOTES`] single notes in a row that the line
/// leaps to and straight back from, such as a stray note an octave up or a short fill.
///
/// - Every note of the excursion is far from the notes on both sides of it, and on the same side
///   of both: at least [`STRAY_LEAP`] semitones for one or two stray notes, [`FILL_LEAP`] for a
///   longer fill.
/// - Those two notes are within [`EXCURSION_RETURN`] semitones of each other: the line carries on
///   where it was.
///
/// A run that climbs and stays, the top of an arpeggio and a line that moves by step are not
/// excursions. Notes tied to a neighbour by a technique are never set aside.
fn excursions(events: &[Event]) -> Vec<bool> {
    let n = events.len();
    let mut away = vec![false; n];
    let pitch = |e: usize| events[e].groups[0].pitch;
    let mut e = 1;
    while e < n {
        let len = (1..=EXCURSION_NOTES).find(|&len| {
            let (before, after) = (e - 1, e + len);
            if after >= n || !(before..=after).all(|k| events[k].melodic()) {
                return false;
            }
            if (e..=after).any(|k| events[k].linked) || (before..after).any(|k| events[k].rings) {
                return false;
            }
            let (lo, hi) = (pitch(before).min(pitch(after)), pitch(before).max(pitch(after)));
            let leap = if len <= STRAY_NOTES { STRAY_LEAP } else { FILL_LEAP };
            hi - lo <= EXCURSION_RETURN && ((e..after).all(|k| pitch(k) - hi >= leap) || (e..after).all(|k| lo - pitch(k) >= leap))
        });
        match len {
            Some(len) => {
                away[e..e + len].fill(true);
                // The note after the excursion belongs to the line.
                e += len + 1;
            }
            None => e += 1,
        }
    }
    away
}

/// The cheapest states for the events `line`, with repeated passages pulled onto one fingering:
/// each event of a repeated passage takes the positions most of its occurrences got on their own;
/// on a tie the cheaper ones, then the earliest. One occurrence in an odd context then follows the
/// others, not the other way round.
fn solve_line(ctx: &Ctx, events: &[Event], line: &[usize]) -> Vec<usize> {
    let path = viterbi(ctx, events, line, &HashMap::new(), None, None);
    let refs = repeats(events, line);
    if refs.is_empty() {
        return path;
    }
    let at: HashMap<usize, usize> = line.iter().enumerate().map(|(k, &e)| (e, k)).collect();
    let state = |e: usize| &events[e].states[path[at[&e]]];
    let mut occurrences: BTreeMap<usize, Vec<usize>> = BTreeMap::new();
    for (&e, &first) in &refs {
        occurrences.entry(first).or_insert_with(|| vec![first]).push(e);
    }
    let mut targets: HashMap<usize, Vec<Option<Position>>> = HashMap::new();
    for mut same in occurrences.into_values() {
        same.sort_unstable();
        // Per fingering: its votes, its lowest cost and the first event that got it.
        let mut votes: HashMap<Vec<Option<Position>>, (usize, f64, usize)> = HashMap::new();
        for &e in &same {
            let vote = votes.entry(events[e].positions(state(e).v)).or_insert((0, f64::INFINITY, e));
            vote.0 += 1;
            vote.1 = vote.1.min(state(e).cost);
        }
        let best = votes.into_iter().max_by(|(_, a), (_, b)| a.0.cmp(&b.0).then(b.1.total_cmp(&a.1)).then(b.2.cmp(&a.2))).map(|(f, _)| f).unwrap_or_default();
        for &e in &same {
            targets.insert(e, best.clone());
        }
    }
    viterbi(ctx, events, line, &targets, None, None)
}

/// Notes on a string a let-ring note still reserves: (event, group, string).
fn ring_conflicts(events: &[Event], path: &[usize]) -> Vec<(usize, usize, u8)> {
    let mut out = Vec::new();
    for (ea, a) in events.iter().enumerate().filter(|(_, a)| a.rings) {
        let va = &a.voicings[a.states[path[ea]].v];
        for (ga, g) in a.groups.iter().enumerate() {
            let (Some(until), Some(string)) = (g.ring_until, va.strings[ga]) else { continue };
            for (eb, b) in events.iter().enumerate().skip(ea + 1).take_while(|(_, b)| b.start < until) {
                let vb = &b.voicings[b.states[path[eb]].v];
                for (gb, s) in vb.strings.iter().enumerate() {
                    if *s == Some(string) {
                        out.push((eb, gb, string));
                    }
                }
            }
        }
    }
    out
}

fn build_events(ctx: &Ctx, notes: &[Note], opts: &Options, techniques: &[Vec<Technique>], out: &mut [NotePlace]) -> Vec<Event> {
    let shapes = if ctx.w.open_shape != 0.0 { open_shapes(ctx.inst) } else { Vec::new() };
    let mut order: Vec<usize> = (0..notes.len()).collect();
    order.sort_by_key(|&i| (notes[i].start, notes[i].pitch, i));
    let mut events: Vec<Event> = Vec::new();
    let mut loc: Vec<Option<(usize, usize)>> = vec![None; notes.len()];
    let mut k = 0;
    while k < order.len() {
        let start = notes[order[k]].start;
        let mut playable = Vec::new();
        while k < order.len() && notes[order[k]].start == start {
            let i = order[k];
            k += 1;
            if ctx.inst.positions(notes[i].pitch).is_empty() {
                out[i].out_of_range = true;
            } else {
                playable.push(i);
            }
        }
        let mut pitches: Vec<i32> = playable.iter().map(|&i| notes[i].pitch).collect();
        pitches.sort_unstable();
        let shape = shapes
            .iter()
            .find(|(_, pos)| {
                let mut sounding: Vec<i32> = pos.iter().filter_map(|&p| ctx.inst.pitch_at(p)).collect();
                sounding.sort_unstable();
                sounding == pitches
            })
            .map(|(_, pos)| {
                let mut pos = pos.clone();
                pos.sort_unstable();
                pos
            });
        let mut groups: Vec<Group> = Vec::new();
        for &i in &playable {
            let pitch = notes[i].pitch;
            // Notes of one pitch at one onset (doublings from several voices) sound as one note,
            // unless together they are an open shape that plays the doubled pitch on two strings.
            if shape.is_none() {
                if let Some(g) = groups.iter_mut().find(|g| g.pitch == pitch) {
                    g.notes.push(i);
                    continue;
                }
            }
            groups.push(Group::new(pitch, i));
        }
        let e = events.len();
        for (gi, g) in groups.iter_mut().enumerate() {
            g.pin = g.notes.iter().find_map(|&i| opts.pin_for(i));
            g.bend = g.notes.iter().any(|&i| techniques[i].iter().any(|t| t.needs_fret()));
            g.ring_until = g.notes.iter().filter(|&&i| techniques[i].contains(&Technique::LetRing)).map(|&i| notes[i].end()).max();
            g.refresh(ctx.inst);
            for &i in &g.notes {
                loc[i] = Some((e, gi));
            }
        }
        if !groups.is_empty() {
            let rings = groups.iter().any(|g| g.ring_until.is_some());
            events.push(Event { start, groups, voicings: Vec::new(), states: Vec::new(), shape, linked: false, rings });
        }
    }
    for i in 0..notes.len() {
        let Some(reach) = string_link(&techniques[i]) else { continue };
        let (Some((e, g)), Some(j)) = (loc[i], previous_note(notes, i)) else { continue };
        if let Some((pe, pg)) = loc[j] {
            if pe + 1 == e && events[e].groups[g].link.is_none() {
                events[e].groups[g].link = Some((pg, reach));
                events[e].linked = true;
            }
        }
    }
    events
}

struct Search<'a> {
    groups: &'a [Group],
    ctx: &'a Ctx<'a>,
    limit: Option<f64>,
    allow_skip: bool,
    best_placed: usize,
    leaves: usize,
    found: Vec<(usize, Vec<Option<usize>>)>,
}

impl Search<'_> {
    fn run(&mut self, g: usize, used: u32, lo: i32, hi: i32, placed: usize, cur: &mut Vec<Option<usize>>) {
        if self.leaves >= LEAF_CAP {
            return;
        }
        if placed + (self.groups.len() - g) < self.best_placed {
            return;
        }
        if g == self.groups.len() {
            self.leaves += 1;
            self.best_placed = self.best_placed.max(placed);
            self.found.push((placed, cur.clone()));
            return;
        }
        for (ci, c) in self.groups[g].cands.iter().enumerate() {
            let bit = 1u32 << c.pos.string;
            if used & bit != 0 {
                continue;
            }
            let (nlo, nhi) = if c.neck > 0 { (lo.min(c.neck), hi.max(c.neck)) } else { (lo, hi) };
            if let Some(limit) = self.limit {
                if nhi > 0 && self.ctx.span_mm(nlo, nhi) > limit {
                    continue;
                }
            }
            cur.push(Some(ci));
            self.run(g + 1, used | bit, nlo, nhi, placed + 1, cur);
            cur.pop();
        }
        if self.allow_skip {
            cur.push(None);
            self.run(g + 1, used, lo, hi, placed, cur);
            cur.pop();
        }
    }
}

fn enumerate(ctx: &Ctx, groups: &[Group], limit: Option<f64>, allow_skip: bool) -> Vec<Vec<Option<usize>>> {
    let mut s = Search { groups, ctx, limit, allow_skip, best_placed: 0, leaves: 0, found: Vec::new() };
    s.run(0, 0, i32::MAX, 0, 0, &mut Vec::new());
    let best = s.best_placed;
    s.found.into_iter().filter(|(p, _)| *p == best).map(|(_, v)| v).collect()
}

fn build_states(ctx: &Ctx, ev: &mut Event) {
    // Complete voicings within the hand limit; failing that, complete voicings of any span; failing
    // that (more notes than strings), the voicings that place the most notes.
    let mut places = enumerate(ctx, &ev.groups, Some(ctx.hand.max_mm), false);
    if places.is_empty() {
        places = enumerate(ctx, &ev.groups, None, false);
    }
    if places.is_empty() {
        places = enumerate(ctx, &ev.groups, Some(ctx.hand.max_mm), true);
        if places.iter().all(|p| p.iter().all(Option::is_none)) {
            places = enumerate(ctx, &ev.groups, None, true);
        }
    }
    let mut voicings: Vec<Voicing> = places
        .into_iter()
        .map(|place| {
            let necks: Vec<i32> = place.iter().zip(&ev.groups).filter_map(|(c, g)| c.map(|c| g.cands[c].neck)).collect();
            let fretted: Vec<i32> = necks.iter().copied().filter(|&n| n > 0).collect();
            let strings = place.iter().zip(&ev.groups).map(|(c, g)| c.map(|c| g.cands[c].pos.string)).collect();
            Voicing {
                strings,
                lo: fretted.iter().copied().min().unwrap_or(0),
                hi: fretted.iter().copied().max().unwrap_or(0),
                fretted: !fretted.is_empty(),
                opens: (necks.len() - fretted.len()) as i32,
                place,
            }
        })
        .collect();

    let hand_positions = |v: &Voicing| -> Vec<i32> {
        if !v.fretted {
            return (ctx.capo + 1..=ctx.frets).collect();
        }
        let ps: Vec<i32> = ((v.lo - HAND_FRETS).max(ctx.capo + 1)..=v.lo).filter(|&p| ctx.span_mm(p, v.hi) <= ctx.hand.max_mm).collect();
        if ps.is_empty() {
            vec![v.lo]
        } else {
            ps
        }
    };

    if voicings.len() > MAX_VOICINGS {
        let mut scored: Vec<(f64, Voicing)> = voicings
            .into_iter()
            .map(|v| {
                let best = hand_positions(&v).into_iter().map(|p| ctx.state_cost(ev, &v, p)).fold(f64::INFINITY, f64::min);
                (best, v)
            })
            .collect();
        scored.sort_by(|a, b| a.0.total_cmp(&b.0).then_with(|| a.1.place.cmp(&b.1.place)));
        scored.truncate(MAX_VOICINGS);
        voicings = scored.into_iter().map(|(_, v)| v).collect();
    }

    let mut states = Vec::new();
    for (vi, v) in voicings.iter().enumerate() {
        for p in hand_positions(v) {
            states.push(State { v: vi, p, cost: ctx.state_cost(ev, v, p) });
        }
    }
    ev.voicings = voicings;
    ev.states = states;
}

/// The cheapest state for each of the events `line`, taken one after another. `targets` maps an
/// event to the positions it should repeat. `before` and `after` are events on either side whose
/// states are already chosen.
fn viterbi(ctx: &Ctx, events: &[Event], line: &[usize], targets: &HashMap<usize, Vec<Option<Position>>>, before: Neighbour, after: Neighbour) -> Vec<usize> {
    if line.is_empty() {
        return Vec::new();
    }
    let bias = |e: usize, s: &State| -> f64 {
        match targets.get(&e) {
            Some(t) if *t != events[e].positions(s.v) => ctx.w.repeat,
            _ => 0.0,
        }
    };
    let lead_in = |s: &State| before.map_or(0.0, |(b, sb)| ctx.transition(b, sb, &events[line[0]], s));
    let mut cost: Vec<f64> = events[line[0]].states.iter().map(|s| lead_in(s) + s.cost + bias(line[0], s)).collect();
    let mut back: Vec<Vec<usize>> = vec![Vec::new()];
    for k in 1..line.len() {
        let (a, b) = (&events[line[k - 1]], &events[line[k]]);
        let mut next = Vec::with_capacity(b.states.len());
        let mut from = Vec::with_capacity(b.states.len());
        for sb in &b.states {
            let mut best = (f64::INFINITY, 0);
            for (ia, sa) in a.states.iter().enumerate() {
                let c = cost[ia] + ctx.transition(a, sa, b, sb);
                if c < best.0 {
                    best = (c, ia);
                }
            }
            next.push(best.0 + sb.cost + bias(line[k], sb));
            from.push(best.1);
        }
        cost = next;
        back.push(from);
    }
    if let Some((a, sa)) = after {
        let end = &events[line[line.len() - 1]];
        for (c, s) in cost.iter_mut().zip(&end.states) {
            *c += ctx.transition(end, s, a, sa);
        }
    }
    let mut last = 0;
    for (i, c) in cost.iter().enumerate() {
        if *c < cost[last] {
            last = i;
        }
    }
    let mut path = vec![0; line.len()];
    path[line.len() - 1] = last;
    for k in (1..line.len()).rev() {
        path[k - 1] = back[k][path[k]];
    }
    path
}

/// Events of `line` that repeat an earlier passage: event -> the first event with its place in the
/// passage. A passage is this many events in a row with the same pitches.
const REPEAT_EVENTS: usize = 4;

fn repeats(events: &[Event], line: &[usize]) -> HashMap<usize, usize> {
    let keys: Vec<Vec<i32>> = line.iter().map(|&e| events[e].groups.iter().map(|g| g.pitch).collect()).collect();
    let mut first: HashMap<&[Vec<i32>], usize> = HashMap::new();
    // By place in `line`.
    let mut refs: HashMap<usize, usize> = HashMap::new();
    if line.len() < REPEAT_EVENTS {
        return refs;
    }
    for i in 0..=line.len() - REPEAT_EVENTS {
        let key = &keys[i..i + REPEAT_EVENTS];
        match first.get(key) {
            Some(&j) => {
                for k in 0..REPEAT_EVENTS {
                    if refs.contains_key(&(i + k)) {
                        continue;
                    }
                    let mut root = j + k;
                    while let Some(&r) = refs.get(&root) {
                        root = r;
                    }
                    if root != i + k {
                        refs.insert(i + k, root);
                    }
                }
            }
            None => {
                first.insert(key, i);
            }
        }
    }
    refs.into_iter().map(|(e, r)| (line[e], line[r])).collect()
}

fn rank_alternatives(ctx: &Ctx, ev: &Event, g: usize, chosen: Option<Position>, prev: Neighbour, next: Neighbour) -> Vec<Position> {
    let group = &ev.groups[g];
    let mut ranked: Vec<(f64, Position)> = ctx
        .inst
        .positions(group.pitch)
        .into_iter()
        .filter(|p| Some(*p) != chosen)
        .map(|alt| {
            let best = ev
                .states
                .iter()
                .filter(|s| ev.voicings[s.v].place[g].map(|c| group.cands[c].pos) == Some(alt))
                .map(|s| {
                    let mut c = s.cost;
                    if let Some((pe, ps)) = prev {
                        c += ctx.transition(pe, ps, ev, s);
                    }
                    if let Some((ne, ns)) = next {
                        c += ctx.transition(ev, s, ne, ns);
                    }
                    c
                })
                .fold(f64::INFINITY, f64::min);
            (best, alt)
        })
        .collect();
    ranked.sort_by(|a, b| a.0.total_cmp(&b.0).then_with(|| a.1.cmp(&b.1)));
    ranked.into_iter().map(|(_, p)| p).collect()
}
