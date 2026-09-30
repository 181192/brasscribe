//! String and fret assignment: a Viterbi search over hand states, one onset at a time.
//!
//! Notes that start together form an event. Each event has voicings (every note on its own string)
//! and each voicing is paired with a hand position `p` (the neck fret under the index finger). The
//! cheapest path through these states minimises the per-state cost (span, height on the neck, open
//! strings) plus the per-transition cost (moving the hand, dropping a melody note far below the
//! hand). A second pass pulls repeated pitch sequences onto the fingering of their first
//! occurrence. See the crate README for the cost model.

use std::collections::HashMap;

use brasscribe_core::model::{Note, TICKS_PER_BEAT};
use serde::{Deserialize, Serialize};

use crate::instrument::{Instrument, Position};

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
pub struct Pin {
    /// Index of the note in the input.
    pub note: usize,
    pub string: u8,
}

#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
#[serde(default)]
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
    /// Per mm of voicing span (lowest to highest fretted note).
    span_mm: f64,
    /// Per mm squared the reach from the index finger exceeds the comfortable span.
    stretch_sq: f64,
    /// For a repeated passage fingered differently from its first occurrence.
    repeat: f64,
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
            span_mm: 0.01,
            stretch_sq: 0.01,
            repeat: 25.0,
        },
        Style::AsPlayed => Weights {
            height: 0.01,
            open_chord: -0.5,
            open_melodic: 0.0,
            shift_mm: 0.03,
            shift_fixed: 1.5,
            drop_mm: 0.04,
            span_mm: 0.01,
            stretch_sq: 0.01,
            repeat: 25.0,
        },
        Style::Lead => Weights {
            height: 0.002,
            open_chord: 0.0,
            open_melodic: 3.0,
            shift_mm: 0.06,
            shift_fixed: 3.0,
            drop_mm: 0.06,
            span_mm: 0.01,
            stretch_sq: 0.01,
            repeat: 25.0,
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
}

#[derive(Debug)]
struct Voicing {
    /// Candidate index per group; None when the group has no string left.
    place: Vec<Option<usize>>,
    lo: i32,
    hi: i32,
    fretted: bool,
    opens: i32,
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
        c
    }
}

/// Choose a string and fret for every note. Notes starting on the same tick are played together;
/// pitches never change, and notes no position can sound are flagged `out_of_range`.
pub fn assign(inst: &Instrument, notes: &[Note], opts: &Options) -> Result<Fingering, String> {
    inst.validate()?;
    opts.validate(inst, notes.len())?;
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

    let mut events = build_events(&ctx, notes, opts, &mut out);
    for ev in events.iter_mut() {
        build_states(&ctx, ev);
    }
    let mut path = viterbi(&ctx, &events, &HashMap::new());
    let refs = repeats(&events);
    if !refs.is_empty() {
        // Later occurrences and the first one itself keep the first occurrence's fingering.
        let chosen = |r: usize| events[r].positions(events[r].states[path[r]].v);
        let targets: HashMap<usize, Vec<Option<Position>>> = refs.iter().flat_map(|(&e, &r)| [(e, chosen(r)), (r, chosen(r))]).collect();
        path = viterbi(&ctx, &events, &targets);
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

fn build_events(ctx: &Ctx, notes: &[Note], opts: &Options, out: &mut [NotePlace]) -> Vec<Event> {
    let mut order: Vec<usize> = (0..notes.len()).collect();
    order.sort_by_key(|&i| (notes[i].start, notes[i].pitch, i));
    let mut events: Vec<Event> = Vec::new();
    let mut k = 0;
    while k < order.len() {
        let start = notes[order[k]].start;
        let mut groups: Vec<Group> = Vec::new();
        while k < order.len() && notes[order[k]].start == start {
            let i = order[k];
            k += 1;
            let pitch = notes[i].pitch;
            // Notes of one pitch at one onset (doublings from several voices) sound as one note.
            if let Some(g) = groups.iter_mut().find(|g| g.pitch == pitch) {
                g.notes.push(i);
                continue;
            }
            if ctx.inst.positions(pitch).is_empty() {
                out[i].out_of_range = true;
                continue;
            }
            groups.push(Group { pitch, notes: vec![i], cands: Vec::new() });
        }
        for g in groups.iter_mut() {
            let pin = g.notes.iter().find_map(|&i| opts.pin_for(i));
            let all: Vec<Cand> = ctx.inst.positions(g.pitch).into_iter().map(|pos| Cand { pos, neck: ctx.inst.neck_fret(pos).unwrap_or(0) }).collect();
            let pinned: Vec<Cand> = all.iter().copied().filter(|c| Some(c.pos.string) == pin).collect();
            // A pin that no position honours is dropped here and reported by the playability check.
            g.cands = if pinned.is_empty() { all } else { pinned };
        }
        if !groups.is_empty() {
            events.push(Event { start, groups, voicings: Vec::new(), states: Vec::new() });
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
            Voicing {
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

/// The cheapest state per event. `targets` maps an event to the positions it should repeat.
fn viterbi(ctx: &Ctx, events: &[Event], targets: &HashMap<usize, Vec<Option<Position>>>) -> Vec<usize> {
    if events.is_empty() {
        return Vec::new();
    }
    let bias = |e: usize, s: &State| -> f64 {
        match targets.get(&e) {
            Some(t) if *t != events[e].positions(s.v) => ctx.w.repeat,
            _ => 0.0,
        }
    };
    let mut cost: Vec<f64> = events[0].states.iter().map(|s| s.cost + bias(0, s)).collect();
    let mut back: Vec<Vec<usize>> = vec![Vec::new()];
    for e in 1..events.len() {
        let (a, b) = (&events[e - 1], &events[e]);
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
            next.push(best.0 + sb.cost + bias(e, sb));
            from.push(best.1);
        }
        cost = next;
        back.push(from);
    }
    let mut last = 0;
    for (i, c) in cost.iter().enumerate() {
        if *c < cost[last] {
            last = i;
        }
    }
    let mut path = vec![0; events.len()];
    path[events.len() - 1] = last;
    for e in (1..events.len()).rev() {
        path[e - 1] = back[e][path[e]];
    }
    path
}

/// Events that repeat an earlier passage: event -> the event whose fingering it should reuse.
/// A passage is this many consecutive events with the same pitches.
const REPEAT_EVENTS: usize = 4;

fn repeats(events: &[Event]) -> HashMap<usize, usize> {
    let keys: Vec<Vec<i32>> = events.iter().map(|e| e.groups.iter().map(|g| g.pitch).collect()).collect();
    let mut first: HashMap<&[Vec<i32>], usize> = HashMap::new();
    let mut refs: HashMap<usize, usize> = HashMap::new();
    if events.len() < REPEAT_EVENTS {
        return refs;
    }
    for i in 0..=events.len() - REPEAT_EVENTS {
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
    refs
}

type Neighbour<'a> = Option<(&'a Event, &'a State)>;

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
