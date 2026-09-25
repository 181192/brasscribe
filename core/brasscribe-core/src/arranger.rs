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
use crate::instruments::{brass_band, minimal_band, Lineup, Part, RangeCheck};
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

/// Octave shift that puts the most notes in [lo, hi] and none outside the pro range.
///
/// Ties go to the octave nearest the middle of the range, or the lowest one for
/// bass lines.
fn best_shift(pitches: &[i32], lo: i32, hi: i32, pro: (i32, i32), prefer_low: bool) -> Option<i32> {
    let mut best = None;
    let mut score: Option<(usize, f64)> = None;
    for k in -4..=4 {
        let shifted: Vec<i32> = pitches.iter().map(|p| p + 12 * k).collect();
        if shifted.iter().any(|&p| !(pro.0 <= p && p <= pro.1)) {
            continue;
        }
        let inside = shifted.iter().filter(|&&p| lo <= p && p <= hi).count();
        let mean = shifted.iter().map(|&p| p as i64).sum::<i64>() as f64 / shifted.len() as f64;
        let second = if prefer_low { -mean } else { -(mean - (lo + hi) as f64 / 2.0).abs() };
        let cand = (inside, second);
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

fn place_line(notes: &[Note], part: &Part, warnings: &mut Vec<String>, shift_extra: i32, prefer_low: bool) -> Vec<Note> {
    let inst = part.instrument;
    let mut placed = Vec::new();
    for phrase in phrases(notes) {
        let ps: Vec<i32> = phrase.iter().map(|n| n.pitch + shift_extra).collect();
        match best_shift(&ps, inst.comfortable.0, inst.comfortable.1, inst.pro, prefer_low) {
            None => {
                // No single octave fits the whole phrase: fall back to per-note octave fitting.
                for n in &phrase {
                    let p = inst.fit_octave(n.pitch + shift_extra);
                    if inst.check(p) == RangeCheck::Impossible {
                        warnings.push(format!("{}: dropped {} at tick {} (no playable octave)", part.name, n.pitch, n.start));
                        continue;
                    }
                    placed.push(renote(n, p));
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
        let (lo, hi) = part.instrument.comfortable;
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

    let lead = lineup.by_name("Solo Cornet");
    let placed = place_line(&melody, lead, &mut arr.warnings, 0, false);
    arr.set(lead.name, placed);

    let eb = lineup.by_name("E♭ Bass");
    let bb = lineup.by_name("B♭ Bass");
    let placed = place_line(&bass, eb, &mut arr.warnings, 0, true);
    arr.set(eb.name, placed);
    let low: Vec<Note> = arr
        .part_notes(eb.name)
        .iter()
        .map(|n| {
            let p = n.pitch - 12;
            // Octave below only where that stays comfortable.
            renote(n, if bb.instrument.check(p) == RangeCheck::Ok { p } else { n.pitch })
        })
        .collect();
    arr.set(bb.name, low);

    let inner = by_comfort_desc(lineup.parts.iter().filter(|p| ![lead.name, eb.name, bb.name].contains(&p.name)));
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
    let (lo, hi) = part.instrument.comfortable;
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

pub fn arrange_layers(comp: &Composition) -> Arrangement {
    arrange_layers_with(comp, brass_band())
}

pub fn arrange_layers_with(comp: &Composition, lineup: Lineup) -> Arrangement {
    let mut arr = Arrangement::new(lineup.clone());
    for p in &lineup.parts {
        arr.set(p.name, Vec::new());
    }
    let end = comp.end_tick();

    let solo = layer(comp, "solo");
    let placed = place_line(&solo, lineup.by_name("Solo Cornet"), &mut arr.warnings, 0, false);
    arr.set("Solo Cornet", placed);

    let bass = layer(comp, "bass");
    let eb = lineup.by_name("E♭ Bass");
    let bb = lineup.by_name("B♭ Bass");
    let placed = place_line(&bass, eb, &mut arr.warnings, 0, true);
    arr.set(eb.name, placed);
    let low: Vec<Note> = arr
        .part_notes(eb.name)
        .iter()
        .map(|n| {
            renote(n, if bb.instrument.check(n.pitch - 12) == RangeCheck::Ok { n.pitch - 12 } else { n.pitch })
        })
        .collect();
    arr.set(bb.name, low);

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
    let euph = lineup.by_name("Euphonium");
    arr.set(euph.name, place_smooth(&counter, euph));

    let mut pad_src = strings.clone();
    pad_src.extend(keys.iter().cloned());
    let pad_slots = harmony_slots(&pad_src, end, 4, 0.35);
    let solo_notes = arr.part_notes("Solo Cornet").to_vec();
    let eb_notes = arr.part_notes(eb.name).to_vec();
    voice_layer(&mut arr, &pad_slots, &PAD_PARTS, &solo_notes, &eb_notes, 76, 0.8);

    let choir_slots = harmony_slots(&brass, end, 3, 0.35);
    voice_layer(&mut arr, &choir_slots, &CHOIR_PARTS, &solo_notes, &eb_notes, 79, 0.8);

    // Bass trombone reinforces the bass line only while the brass choir is playing.
    let btb = lineup.by_name("Bass Trombone");
    let tutti: Vec<Note> = bass.iter().filter(|n| choir_slots.iter().any(|(s, e, _)| *s <= n.start && n.start < *e)).cloned().collect();
    let placed = place_line(&tutti, btb, &mut arr.warnings, 0, true);
    arr.set(btb.name, placed);

    let mut drums = layer(comp, "drums");
    if !drums.is_empty() && lineup.has("Percussion") {
        drums.sort_by_key(|n| n.start);
        arr.set("Percussion", drums);
    }
    arr
}
