//! Deterministic brass-band arrangers.
//!
//! `arrange` (minimal band) reads a Composition with voices tagged by role:
//!   melody  -> Solo Cornet (octave chosen per phrase to sit in its comfortable range)
//!   bass    -> E♭ Bass (lowest comfortable octave), B♭ Bass an octave lower where comfortable
//!   harmony -> inner parts, voiced per harmony slot from the chord tones sounding at that
//!              moment: inside each part's range, under the melody, over the bass, no
//!              crossing, least movement from the previous chord.
//!
//! `arrange_layers` (solo with band) maps textural layers to band sections:
//!   solo            -> Solo Cornet
//!   strings (line)  -> Euphonium countermelody (top moving line of the strings)
//!   strings + keys  -> sustained pads: Flugelhorn, horns, baritones
//!   orch. brass     -> brass choir: Repiano, 2nd/3rd Cornets, 1st/2nd Trombones
//!   bass            -> E♭ Bass, B♭ Bass, Bass Trombone doubling while the choir plays
//!   drums           -> Percussion (drum kit, unpitched)
//!
//! Hard limits come from the instrument table and are never violated; anything
//! that cannot be placed is left out and reported instead.

use std::collections::{BTreeSet, HashMap};

use crate::harmony::{harmony_slots, Slot};
use crate::instruments::{brass_band, minimal_band, Lineup, Part};
use crate::model::{Composition, Note, VoiceRole};

/// A rest of two beats or more starts a new phrase.
pub const PHRASE_GAP_TICKS: i64 = 48;
/// Gaps up to a 16th inside a part are held over.
pub const MIN_REST_TICKS: i64 = 6;

#[derive(Debug, Clone, PartialEq)]
pub struct Arrangement {
    pub lineup: Lineup,
    /// Concert notes per part name, in insertion order.
    pub parts: Vec<(String, Vec<Note>)>,
    pub warnings: Vec<String>,
}

impl Arrangement {
    fn new(lineup: Lineup) -> Self {
        Arrangement { lineup, parts: Vec::new(), warnings: Vec::new() }
    }

    pub fn get(&self, name: &str) -> Option<&Vec<Note>> {
        self.parts.iter().find(|(n, _)| n == name).map(|(_, v)| v)
    }

    fn get_mut(&mut self, name: &str) -> &mut Vec<Note> {
        if let Some(i) = self.parts.iter().position(|(n, _)| n == name) {
            return &mut self.parts[i].1;
        }
        self.parts.push((name.to_string(), Vec::new()));
        &mut self.parts.last_mut().unwrap().1
    }

    fn set(&mut self, name: &str, notes: Vec<Note>) {
        *self.get_mut(name) = notes;
    }

    pub fn part_notes(&self, name: &str) -> &[Note] {
        self.get(name).map(|v| v.as_slice()).unwrap_or(&[])
    }
}

fn phrases(notes: &[Note]) -> Vec<Vec<Note>> {
    let mut sorted: Vec<&Note> = notes.iter().collect();
    sorted.sort_by_key(|n| n.start);
    let mut out: Vec<Vec<Note>> = Vec::new();
    for n in sorted {
        match out.last_mut() {
            Some(ph) if n.start - ph.iter().map(|m| m.end()).max().unwrap() < PHRASE_GAP_TICKS => ph.push(n.clone()),
            _ => out.push(vec![n.clone()]),
        }
    }
    out
}

/// Bass lines centre a third of the way up the reading range.
pub const BASS_TARGET: f64 = 0.35;

/// Octave shift that puts the most notes in [lo, hi] and none outside `limit`.
///
/// Ties go to the octave nearest the middle of the range (a third of the way
/// up for bass lines) and nearest the previous phrase's last note, so the line
/// stays continuous.
///
/// With `bass_overflow_up` (bass lines of a transposed piece), notes above the
/// reading range up to the placement limit still count as inside: bass parts
/// in treble clef read up easily but go onto ledger lines below.
fn best_shift(pitches: &[i32], lo: i32, hi: i32, limit: (i32, i32), prefer_low: bool, prev: Option<i32>, bass_overflow_up: bool) -> Option<i32> {
    let target = if prefer_low { lo as f64 + BASS_TARGET * (hi - lo) as f64 } else { (lo + hi) as f64 / 2.0 };
    let mut best = None;
    let mut score: Option<(usize, f64)> = None;
    for k in -4..=4 {
        let shifted: Vec<i32> = pitches.iter().map(|p| p + 12 * k).collect();
        if shifted.iter().any(|&p| !(limit.0 <= p && p <= limit.1)) {
            continue;
        }
        let top = if prefer_low && bass_overflow_up { limit.1 } else { hi };
        let inside = shifted.iter().filter(|&&p| lo <= p && p <= top).count();
        let mean = shifted.iter().map(|&p| p as i64).sum::<i64>() as f64 / shifted.len() as f64;
        let jump = prev.map(|q| (shifted[0] - q).abs() as f64).unwrap_or(0.0);
        let cand = (inside, -((mean - target).abs() + jump));
        let better = match score {
            None => true,
            Some(s) => cand.0 > s.0 || (cand.0 == s.0 && cand.1 > s.1),
        };
        if better {
            best = Some(k);
            score = Some(cand);
        }
    }
    best
}

/// The octave of `pitch` inside the first range that has one, nearest `prev` (or the range middle).
fn nearest_octave(pitch: i32, ranges: &[(i32, i32)], prev: Option<i32>) -> Option<i32> {
    for &(lo, hi) in ranges {
        let opts: Vec<i32> = (0..11).map(|k| pitch.rem_euclid(12) + 12 * k).filter(|&x| lo <= x && x <= hi).collect();
        if !opts.is_empty() {
            let r = prev.map(|p| p as f64).unwrap_or((lo + hi) as f64 / 2.0);
            let mut best = opts[0];
            for &x in &opts[1..] {
                let (dx, db) = ((x as f64 - r).abs(), (best as f64 - r).abs());
                if dx < db || (dx == db && x < best) {
                    best = x;
                }
            }
            return Some(best);
        }
    }
    None
}

/// Split a phrase that spans more than `width` semitones at its largest leap,
/// recursively, so each piece can take its own octave.
fn split_wide(phrase: Vec<Note>, width: i32) -> Vec<Vec<Note>> {
    let lo = phrase.iter().map(|n| n.pitch).min().unwrap_or(0);
    let hi = phrase.iter().map(|n| n.pitch).max().unwrap_or(0);
    if phrase.len() < 4 || hi - lo <= width {
        return vec![phrase];
    }
    // largest leap; ties go to the later one
    let cut = (0..phrase.len() - 1).map(|i| ((phrase[i + 1].pitch - phrase[i].pitch).abs(), i + 1)).max().unwrap().1;
    let rest = phrase[cut..].to_vec();
    let mut out = split_wide(phrase[..cut].to_vec(), width);
    out.extend(split_wide(rest, width));
    out
}

fn place_line(notes: &[Note], part: &Part, warnings: &mut Vec<String>, shift_extra: i32, prefer_low: bool) -> Vec<Note> {
    place_line_with(notes, part, warnings, shift_extra, prefer_low, false)
}

fn place_line_with(notes: &[Note], part: &Part, warnings: &mut Vec<String>, shift_extra: i32, prefer_low: bool, bass_overflow_up: bool) -> Vec<Note> {
    let inst = part.instrument;
    let (lo, hi) = inst.preferred();
    let mut placed: Vec<Note> = Vec::new();
    let mut all = phrases(notes);
    if bass_overflow_up {
        all = all.into_iter().flat_map(|ph| split_wide(ph, hi - lo)).collect();
    }
    for phrase in all {
        let prev = placed.last().map(|n| n.pitch);
        let ps: Vec<i32> = phrase.iter().map(|n| n.pitch + shift_extra).collect();
        match best_shift(&ps, lo, hi, inst.placement_limit(), prefer_low, prev, bass_overflow_up) {
            None => {
                // No single octave fits the whole phrase: per note, the octave nearest the previous note.
                for n in &phrase {
                    let last = placed.last().map(|n| n.pitch);
                    match nearest_octave(n.pitch + shift_extra, &[inst.preferred(), inst.placement_limit()], last) {
                        None => {
                            warnings.push(format!("{}: dropped {} at tick {} (no playable octave)", part.name, n.pitch, n.start));
                        }
                        Some(p) => placed.push(renote(n, p)),
                    }
                }
                warnings.push(format!("{}: phrase at tick {} needed per-note octave fitting", part.name, phrase[0].start));
            }
            Some(k) => {
                for n in &phrase {
                    placed.push(renote(n, n.pitch + shift_extra + 12 * k));
                }
            }
        }
    }
    hold_small_gaps(placed)
}

/// Inside the instrument's preferred (reading) range.
fn readable(inst: &crate::instruments::Instrument, pitch: i32) -> bool {
    let (lo, hi) = inst.preferred();
    lo <= pitch && pitch <= hi
}

/// Which source layer a part of `lineup` plays in the layered arrangement (for its dynamics).
pub fn layer_of_part(lineup: &Lineup, name: &str) -> Option<&'static str> {
    if name == lineup.lead {
        Some("solo")
    } else if name == lineup.bass || Some(name) == lineup.second_bass {
        Some("bass")
    } else if PAD_PARTS.contains(&name) || name == "Euphonium" {
        Some("strings")
    } else if CHOIR_PARTS.contains(&name) {
        Some("brass")
    } else if name == "Bass Trombone" {
        Some("bass")
    } else if name == "Percussion" {
        Some("drums")
    } else {
        None
    }
}

/// Copy of a source note at another pitch (timing, confidence and articulations kept).
fn renote(n: &Note, pitch: i32) -> Note {
    Note { pitch, ..n.clone() }
}

fn hold_small_gaps(mut notes: Vec<Note>) -> Vec<Note> {
    notes.sort_by_key(|n| n.start);
    for i in 0..notes.len().saturating_sub(1) {
        let (bs, ae) = (notes[i + 1].start, notes[i].end());
        if 0 < bs - ae && bs - ae <= MIN_REST_TICKS {
            notes[i].dur = bs - notes[i].start;
        }
    }
    notes
}

fn sounding_at(notes: &[Note], tick: i64) -> Vec<&Note> {
    notes.iter().filter(|n| n.start <= tick && tick < n.end()).collect()
}

/// Assign one pitch per inner part (high to low) from the chord's pitch classes.
fn voice_slot(pcs: &[i32], parts: &[&Part], ceiling: i32, floor: i32, prev: &HashMap<&'static str, i32>) -> Vec<(&'static str, i32)> {
    let mut chosen: Vec<(&'static str, i32)> = Vec::new();
    let mut used: Vec<i32> = Vec::new();
    let mut upper = ceiling;
    for part in parts {
        let (lo, hi) = part.instrument.preferred();
        let hi = hi.min(upper - 1);
        let lo = lo.max(floor + 1);
        let options: Vec<i32> = (lo..=hi).filter(|p| pcs.contains(&p.rem_euclid(12))).collect();
        if options.is_empty() {
            continue;
        }
        let used_pcs: BTreeSet<i32> = used.iter().map(|u| u.rem_euclid(12)).collect();
        let missing: Vec<i32> = options.iter().copied().filter(|p| !used_pcs.contains(&p.rem_euclid(12))).collect();
        // When every chord tone is taken, double in another octave rather than at the unison.
        let not_used: Vec<i32> = options.iter().copied().filter(|p| !used.contains(p)).collect();
        let pool = if !missing.is_empty() {
            missing
        } else if !not_used.is_empty() {
            not_used
        } else {
            options
        };
        // Close position: start just under the part above; afterwards follow the part's own previous note.
        let target = *prev.get(part.name).unwrap_or(&if upper < 200 { hi.min(upper - 3) } else { (lo + hi).div_euclid(2) });
        let p = *pool.iter().min_by_key(|&&x| ((x - target).abs(), -x)).unwrap();
        chosen.push((part.name, p));
        used.push(p);
        upper = p + 1; // next part may double at the unison but not cross above
    }
    chosen
}

fn by_comfort_desc<'a>(parts: impl Iterator<Item = &'a Part>) -> Vec<&'a Part> {
    let mut v: Vec<&Part> = parts.collect();
    v.sort_by_key(|p| -(p.instrument.comfortable.0 + p.instrument.comfortable.1));
    v
}

pub fn arrange(comp: &Composition) -> Arrangement {
    arrange_with(comp, minimal_band())
}

pub fn arrange_with(comp: &Composition, lineup: Lineup) -> Arrangement {
    let mut arr = Arrangement::new(lineup.clone());
    let melody: Vec<Note> = comp.voices_with(VoiceRole::Melody).flat_map(|v| v.notes.iter().cloned()).collect();
    let bass: Vec<Note> = comp.voices_with(VoiceRole::Bass).flat_map(|v| v.notes.iter().cloned()).collect();
    let harmony: Vec<Note> = comp
        .voices
        .iter()
        .filter(|v| matches!(v.role, VoiceRole::Harmony | VoiceRole::Countermelody))
        .flat_map(|v| v.notes.iter().cloned())
        .collect();

    let lead = lineup.lead_part();
    let placed = place_line(&melody, lead, &mut arr.warnings, 0, false);
    arr.set(lead.name, placed);

    let eb = lineup.bass_part();
    let placed = place_line(&bass, eb, &mut arr.warnings, 0, true);
    arr.set(eb.name, placed);
    if let Some(bb) = lineup.second_bass_part() {
        let low: Vec<Note> = arr
            .part_notes(eb.name)
            .iter()
            .map(|n| {
                let p = n.pitch - 12;
                // Octave below only where that stays readable.
                renote(n, if readable(bb.instrument, p) { p } else { n.pitch })
            })
            .collect();
        arr.set(bb.name, low);
    }

    let inner = by_comfort_desc(lineup.parts.iter().filter(|p| p.name != lead.name && p.name != eb.name && Some(p.name) != lineup.second_bass));
    for p in &inner {
        arr.set(p.name, Vec::new());
    }
    let mut slots: Vec<i64> = harmony.iter().map(|n| n.start).collect();
    slots.sort();
    slots.dedup();
    let ends: HashMap<i64, i64> = slots.windows(2).map(|w| (w[0], w[1])).collect();
    let mut prev: HashMap<&'static str, i32> = HashMap::new();
    let lead_notes = arr.part_notes(lead.name).to_vec();
    let eb_notes = arr.part_notes(eb.name).to_vec();
    for &s in &slots {
        let mut sounding: Vec<&Note> = sounding_at(&harmony, s);
        if sounding.is_empty() {
            sounding = harmony.iter().filter(|n| n.start == s).collect();
        }
        let mut pcs: BTreeSet<i32> = sounding.iter().map(|n| n.pitch.rem_euclid(12)).collect();
        pcs.extend(sounding_at(&melody, s).iter().map(|n| n.pitch.rem_euclid(12)));
        pcs.extend(sounding_at(&bass, s).iter().map(|n| n.pitch.rem_euclid(12)));
        let pcs: Vec<i32> = pcs.into_iter().collect();
        let top = sounding_at(&lead_notes, s);
        let bot = sounding_at(&eb_notes, s);
        let ceiling = top.first().map(|n| n.pitch).unwrap_or(90);
        let floor = bot.first().map(|n| n.pitch).unwrap_or(30);
        let mut end = sounding.iter().map(|n| n.end()).max().unwrap();
        if let Some(&nxt) = ends.get(&s) {
            // Hold across tiny gaps (performance/MIDI release offsets) instead of writing 64th rests.
            end = if nxt - end <= MIN_REST_TICKS { nxt } else { end.min(nxt) };
        }
        let conf = sounding.iter().map(|n| n.confidence).fold(f64::INFINITY, f64::min);
        let voicing = voice_slot(&pcs, &inner, ceiling, floor, &prev);
        for (name, p) in &voicing {
            arr.get_mut(name).push(Note::new(*p, s, end - s, conf, vec!["arranger".into()]));
        }
        prev.extend(voicing);
    }
    arr
}

pub const PAD_PARTS: [&str; 6] = ["Flugelhorn", "Solo Horn", "1st Horn", "2nd Horn", "1st Baritone", "2nd Baritone"];
pub const CHOIR_PARTS: [&str; 5] = ["Repiano Cornet", "2nd Cornet", "3rd Cornet", "1st Trombone", "2nd Trombone"];
/// A strings note shorter than this many beats counts as melodic movement.
pub const COUNTER_MIN_MOVE: i64 = 2;

fn layer(comp: &Composition, name: &str) -> Vec<Note> {
    comp.voices.iter().filter(|v| v.layer.as_deref() == Some(name)).flat_map(|v| v.notes.iter().cloned()).collect()
}

#[allow(clippy::too_many_arguments)]
fn voice_layer(arr: &mut Arrangement, slots: &[Slot], part_names: &[&str], ceiling_notes: &[Note], floor_notes: &[Note], default_ceiling: i32, conf: f64) {
    let lineup = arr.lineup.clone();
    let parts = by_comfort_desc(part_names.iter().map(|n| lineup.by_name(n)));
    let mut prev: HashMap<&'static str, i32> = HashMap::new();
    for p in &parts {
        arr.get_mut(p.name);
    }
    for (start, end, pcs) in slots {
        let top = sounding_at(ceiling_notes, *start);
        let bot = sounding_at(floor_notes, *start);
        let ceiling = top.first().map(|n| n.pitch).unwrap_or(default_ceiling);
        // Pads may sit below a bass line that climbs into the tenor register.
        let floor = bot.first().map(|n| n.pitch.min(43)).unwrap_or(30);
        let voicing = voice_slot(pcs, &parts, ceiling, floor, &prev);
        for (name, p) in &voicing {
            arr.get_mut(name).push(Note::new(*p, *start, end - start, conf, vec!["arranger".into()]));
        }
        prev.extend(voicing);
    }
}

/// Octave per note nearest the previous note (inside the comfortable range).
///
/// Used for lines pulled from a dense texture, where the source hops between
/// voices and a single octave shift per phrase would leave large leaps.
fn place_smooth(notes: &[Note], part: &Part) -> Vec<Note> {
    let (lo, hi) = part.instrument.preferred();
    let mut prev = (lo + hi).div_euclid(2);
    let mut out = Vec::new();
    let mut sorted: Vec<&Note> = notes.iter().collect();
    sorted.sort_by_key(|n| n.start);
    for n in sorted {
        let opts: Vec<i32> = (0..11).map(|k| n.pitch.rem_euclid(12) + 12 * k).filter(|&p| lo <= p && p <= hi).collect();
        if opts.is_empty() {
            continue;
        }
        let p = *opts.iter().min_by_key(|&&x| (x - prev).abs()).unwrap();
        out.push(renote(n, p));
        prev = p;
    }
    hold_small_gaps(out)
}

/// Split harmony slots at the source's own attacks, so the pads play its rhythm:
/// a slot is re-attacked at every source onset inside it on the 8th grid, at
/// least `min_len` ticks from the previous attack and from the slot end.
fn figurate(slots: &[Slot], onsets: &[i64], min_len: i64) -> Vec<Slot> {
    let on: BTreeSet<i64> = onsets.iter().copied().filter(|o| o.rem_euclid(12) == 0).collect();
    let mut out = Vec::new();
    for (s, e, pcs) in slots {
        let mut cut = *s;
        for &o in &on {
            if *s < o && o < *e && o - cut >= min_len && e - o >= min_len {
                out.push((cut, o, pcs.clone()));
                cut = o;
            }
        }
        out.push((cut, *e, pcs.clone()));
    }
    out
}

/// Tick spans where the solo is at its loudest (ff) while the orchestra plays f or louder.
fn climax_spans(comp: &Composition) -> Vec<(i64, i64)> {
    let timeline = |layer: &str| {
        let mut v: Vec<(i64, String)> = comp.dynamics.iter().filter(|d| d.layer == layer).map(|d| (d.tick, d.mark.clone())).collect();
        v.sort();
        v
    };
    let mark_at = |tl: &[(i64, String)], t: i64| -> Option<String> { tl.iter().filter(|(tick, _)| *tick <= t).last().map(|(_, m)| m.clone()) };
    let (solo, strings) = (timeline("solo"), timeline("strings"));
    let mut edges: BTreeSet<i64> = solo.iter().chain(strings.iter()).map(|(t, _)| *t).collect();
    edges.insert(comp.end_tick());
    let edges: Vec<i64> = edges.into_iter().collect();
    let mut spans: Vec<(i64, i64)> = Vec::new();
    for w in edges.windows(2) {
        let (a, b) = (w[0], w[1]);
        let (ms, mo) = (mark_at(&solo, a), mark_at(&strings, a));
        if ms.as_deref() == Some("ff") && matches!(mo.as_deref(), Some("f") | Some("ff")) {
            match spans.last_mut() {
                Some(last) if last.1 == a => last.1 = b,
                _ => spans.push((a, b)),
            }
        }
    }
    spans
}

/// Soprano Cornet doubles the solo an octave up at climaxes (at the unison when the octave is too high).
fn soprano_doubling(solo: &[Note], part: &Part, spans: &[(i64, i64)]) -> Vec<Note> {
    let (lo, hi) = part.instrument.preferred();
    solo.iter()
        .filter(|n| spans.iter().any(|(a, b)| *a <= n.start && n.start < *b))
        .filter_map(|n| {
            let p = if lo <= n.pitch + 12 && n.pitch + 12 <= hi {
                Some(n.pitch + 12)
            } else if lo <= n.pitch && n.pitch <= hi {
                Some(n.pitch)
            } else {
                None
            };
            p.map(|p| renote(n, p))
        })
        .collect()
}

/// Options of the layered arrangement.
#[derive(Debug, Clone, PartialEq)]
pub struct LayersArrangeOptions {
    /// faithful, standard or easier (see difficulty.rs).
    pub difficulty: String,
    /// Soprano Cornet doubles the solo at climaxes (default: on unless faithful).
    pub soprano: Option<bool>,
    /// Pads re-attacked with the source's rhythm (default: on unless faithful).
    pub figuration: Option<bool>,
}

impl Default for LayersArrangeOptions {
    fn default() -> Self {
        LayersArrangeOptions { difficulty: "faithful".into(), soprano: None, figuration: None }
    }
}

pub fn arrange_layers(comp: &Composition) -> Arrangement {
    arrange_layers_with(comp, brass_band())
}

pub fn arrange_layers_with(comp: &Composition, lineup: Lineup) -> Arrangement {
    arrange_layers_opts(comp, lineup, &LayersArrangeOptions::default()).expect("faithful arrangement")
}

/// Layered solo-with-band arrangement with options. Parts missing from
/// `lineup` are not written.
pub fn arrange_layers_opts(comp: &Composition, lineup: Lineup, opts: &LayersArrangeOptions) -> Result<Arrangement, String> {
    let faithful = opts.difficulty == "faithful";
    let soprano = opts.soprano.unwrap_or(!faithful);
    let figuration = opts.figuration.unwrap_or(!faithful);
    let mut arr = Arrangement::new(lineup.clone());
    for p in &lineup.parts {
        arr.set(p.name, Vec::new());
    }
    let end = comp.end_tick();

    let lead = lineup.lead;
    let solo = layer(comp, "solo");
    let placed = place_line(&solo, lineup.lead_part(), &mut arr.warnings, 0, false);
    arr.set(lead, placed);

    let bass = layer(comp, "bass");
    let eb = lineup.bass_part();
    // A transposed piece re-fits its bass lines (phrases split at their largest
    // leap, spilling above the range rather than below); untransposed
    // arrangements keep their established placement.
    let refit = comp.arrangement.as_ref().and_then(|a| a.get("transpose_semitones")).is_some_and(|t| t.as_f64().is_some_and(|x| x != 0.0));
    let placed = place_line_with(&bass, eb, &mut arr.warnings, 0, true, refit);
    arr.set(eb.name, placed);
    if let Some(bb) = lineup.second_bass_part() {
        let low: Vec<Note> = arr
            .part_notes(eb.name)
            .iter()
            .map(|n| renote(n, if readable(bb.instrument, n.pitch - 12) { n.pitch - 12 } else { n.pitch }))
            .collect();
        arr.set(bb.name, low);
    }

    let strings = layer(comp, "strings");
    let keys = layer(comp, "keys");
    let brass = layer(comp, "brass");

    // Countermelody: the top strings line where it moves (long held tops belong to the pad).
    let mut sorted: Vec<&Note> = strings.iter().collect();
    sorted.sort_by_key(|n| n.start);
    let mut top: Vec<Note> = Vec::new();
    for n in sorted {
        if let Some(last) = top.last_mut() {
            if n.start - last.start < 6 {
                if n.pitch > last.pitch {
                    *last = n.clone();
                }
                continue;
            }
        }
        top.push(n.clone());
    }
    let counter: Vec<Note> = top.into_iter().filter(|n| n.dur < COUNTER_MIN_MOVE * comp.ticks_per_beat).collect();
    if lineup.has("Euphonium") {
        let euph = lineup.by_name("Euphonium");
        arr.set(euph.name, place_smooth(&counter, euph));
    }

    let mut pad_src = strings.clone();
    pad_src.extend(keys.iter().cloned());
    let mut pad_slots = harmony_slots(&pad_src, end, 4, 0.35);
    if figuration {
        pad_slots = figurate(&pad_slots, &pad_src.iter().map(|n| n.start).collect::<Vec<_>>(), 12);
    }
    let solo_notes = arr.part_notes(lead).to_vec();
    let eb_notes = arr.part_notes(eb.name).to_vec();
    let pads: Vec<&str> = PAD_PARTS.iter().copied().filter(|p| lineup.has(p)).collect();
    voice_layer(&mut arr, &pad_slots, &pads, &solo_notes, &eb_notes, 76, 0.8);

    let mut choir_slots = harmony_slots(&brass, end, 3, 0.35);
    if figuration {
        choir_slots = figurate(&choir_slots, &brass.iter().map(|n| n.start).collect::<Vec<_>>(), 12);
    }
    let choir: Vec<&str> = CHOIR_PARTS.iter().copied().filter(|p| lineup.has(p)).collect();
    voice_layer(&mut arr, &choir_slots, &choir, &solo_notes, &eb_notes, 79, 0.8);

    // Bass trombone reinforces the bass line only while the brass choir is playing.
    if lineup.has("Bass Trombone") {
        let btb = lineup.by_name("Bass Trombone");
        let tutti: Vec<Note> = bass.iter().filter(|n| choir_slots.iter().any(|(s, e, _)| *s <= n.start && n.start < *e)).cloned().collect();
        let placed = place_line(&tutti, btb, &mut arr.warnings, 0, true);
        arr.set(btb.name, placed);
    }

    if soprano && lineup.has("Soprano Cornet") {
        let sop = soprano_doubling(arr.part_notes(lead), lineup.by_name("Soprano Cornet"), &climax_spans(comp));
        arr.set("Soprano Cornet", sop);
    }

    let mut drums = layer(comp, "drums");
    if !drums.is_empty() && lineup.has("Percussion") {
        drums.sort_by_key(|n| n.start);
        arr.set("Percussion", drums);
    }
    arr.parts = crate::difficulty::apply_difficulty(std::mem::take(&mut arr.parts), &arr.lineup, &opts.difficulty)?;
    Ok(arr)
}
