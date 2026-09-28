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
//! A four-part lineup (the quartet) voices its two inner parts together as alto
//! and tenor with the chorale rules of [`voice_satb`]; in the layered arranger
//! strings, keys and orchestral brass become one set of harmony slots for them,
//! with no countermelody, drums or soprano doubling.
//!
//! Hard limits come from the instrument table and are never violated; anything
//! that cannot be placed is left out and reported instead.

use std::collections::{BTreeSet, HashMap};

use crate::harmony::{harmony_slots, Slot};
use crate::instruments::{brass_band, minimal_band, Lineup, Part};

/// Not a part name: the source harmony as chord context for the difficulty modes.
const HARMONY_CONTEXT: &str = " harmony";
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

/// Index after the phrase's largest leap (ties go to the later leap).
fn leap_cut(phrase: &[Note]) -> usize {
    (0..phrase.len() - 1).map(|i| ((phrase[i + 1].pitch - phrase[i].pitch).abs(), i + 1)).max().unwrap().1
}

/// Split a phrase that spans more than `width` semitones at its largest leap,
/// recursively, so each piece can take its own octave.
fn split_wide(phrase: Vec<Note>, width: i32) -> Vec<Vec<Note>> {
    let lo = phrase.iter().map(|n| n.pitch).min().unwrap_or(0);
    let hi = phrase.iter().map(|n| n.pitch).max().unwrap_or(0);
    if phrase.len() < 4 || hi - lo <= width {
        return vec![phrase];
    }
    let cut = leap_cut(&phrase);
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
        place_phrase(&phrase, part, warnings, shift_extra, prefer_low, bass_overflow_up, &mut placed, false, None);
    }
    hold_small_gaps(placed)
}

/// Place one phrase at the best single octave; returns the octave shift used (None: per note).
///
/// A tune phrase no octave fits, but no wider than the placement limit, is split at its largest
/// leap and each piece placed on its own, keeping the previous piece's shift (`keep`) wherever it
/// fits: the line changes octave only where it jumps, so its contour is kept. Bass lines
/// (`prefer_low`), wider tune phrases and tune pieces under four notes are fitted note by note at
/// the octave nearest the previous note: their wide leaps are mostly tracker octave errors or
/// jumps between voices, which this folds back together.
#[allow(clippy::too_many_arguments)]
fn place_phrase(phrase: &[Note], part: &Part, warnings: &mut Vec<String>, shift_extra: i32, prefer_low: bool,
                bass_overflow_up: bool, placed: &mut Vec<Note>, split: bool, keep: Option<i32>) -> Option<i32> {
    let inst = part.instrument;
    let (lo, hi) = inst.preferred();
    let limit = inst.placement_limit();
    let ps: Vec<i32> = phrase.iter().map(|n| n.pitch + shift_extra).collect();
    let k = match keep {
        Some(k) if ps.iter().all(|&p| limit.0 <= p + 12 * k && p + 12 * k <= limit.1) => Some(k),
        _ => best_shift(&ps, lo, hi, limit, prefer_low, placed.last().map(|n| n.pitch), bass_overflow_up),
    };
    if let Some(k) = k {
        for (n, p) in phrase.iter().zip(&ps) {
            placed.push(renote(n, p + 12 * k));
        }
        return Some(k);
    }
    let span = ps.iter().max().unwrap_or(&0) - ps.iter().min().unwrap_or(&0);
    if !prefer_low && phrase.len() >= 4 && (split || span <= limit.1 - limit.0) {
        if !split {
            warnings.push(format!("{}: phrase at tick {} split at its leaps to fit the range", part.name, phrase[0].start));
        }
        let cut = leap_cut(phrase);
        let k = place_phrase(&phrase[..cut], part, warnings, shift_extra, prefer_low, bass_overflow_up, placed, true, keep);
        return place_phrase(&phrase[cut..], part, warnings, shift_extra, prefer_low, bass_overflow_up, placed, true, k);
    }
    for (n, &p0) in phrase.iter().zip(&ps) {
        let last = placed.last().map(|n| n.pitch);
        match nearest_octave(p0, &[inst.preferred(), limit], last) {
            None => warnings.push(format!("{}: dropped {} at tick {} (no playable octave)", part.name, n.pitch, n.start)),
            Some(p) => placed.push(renote(n, p)),
        }
    }
    warnings.push(format!("{}: phrase at tick {} needed per-note octave fitting", part.name, phrase[0].start));
    None
}

/// The player's own line written for their part, in the octave they played it.
///
/// A note keeps its octave while it is inside the instrument's professional range. A note
/// outside it (almost always a tracker octave error) moves by octaves into the comfortable
/// range, else the professional range, and each move is a warning. This writes down the
/// player's notes; `place_line` arranges a heard line onto a part, which is another thing.
pub fn place_as_played(notes: &[Note], part: &Part, warnings: &mut Vec<String>) -> Vec<Note> {
    let inst = part.instrument;
    let (lo, hi) = inst.pro;
    let mut sorted: Vec<&Note> = notes.iter().collect();
    sorted.sort_by_key(|n| n.start);
    let mut placed = Vec::new();
    for n in sorted {
        let mut p = n.pitch;
        if !(lo <= p && p <= hi) {
            p = inst.fit_octave(p);
            if !(lo <= p && p <= hi) {
                warnings.push(format!("{}: dropped {} at tick {} (no playable octave)", part.name, n.pitch, n.start));
                continue;
            }
            warnings.push(format!("{}: moved {} to {} at tick {} (outside the range)", part.name, n.pitch, p, n.start));
        }
        placed.push(renote(n, p));
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
    } else if BAND_LEADS.contains(&name) {
        // The band's usual lead, with the tune on the player's part (lead "seat").
        Some("strings")
    } else if lineup.satb {
        Some("strings")
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

/// Assign one pitch per inner part (high to low) from the chord's pitch classes
/// (inside each part's reading range, or its entry in `ranges`, parallel to `parts`).
fn voice_slot(pcs: &[i32], parts: &[&Part], ceiling: i32, floor: i32, prev: &HashMap<&'static str, i32>, ranges: Option<&[(i32, i32)]>) -> Vec<(&'static str, i32)> {
    let mut chosen: Vec<(&'static str, i32)> = Vec::new();
    let mut used: Vec<i32> = Vec::new();
    let mut upper = ceiling;
    for (i, part) in parts.iter().enumerate() {
        let (lo, hi) = ranges.map(|r| r[i]).unwrap_or_else(|| part.instrument.preferred());
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

// ---------------------------------------------------------------------------
// Four-part voicing (quartet): alto and tenor chosen together per harmony slot.
// ---------------------------------------------------------------------------

/// Root of a slot's chord: the first pitch class (ascending) with the most of: a
/// triad (third and perfect fifth above it), a fifth above it, a third above it,
/// the bass on it.
pub fn chord_root(pcs: &[i32], bass_pc: Option<i32>) -> i32 {
    let mut sorted = pcs.to_vec();
    sorted.sort();
    let has = |pc: i32| pcs.contains(&pc.rem_euclid(12));
    let mut best = sorted[0];
    let mut key: Option<(i32, i32, i32, i32)> = None;
    for &r in &sorted {
        let third = has(r + 4) || has(r + 3);
        let fifth = has(r + 7);
        let k = ((third && fifth) as i32, fifth as i32, third as i32, (Some(r) == bass_pc) as i32);
        if key.is_none_or(|kk| k > kk) {
            best = r;
            key = Some(k);
        }
    }
    best
}

/// Pairs of voices (listed high to low) that move in the same direction from one
/// perfect fifth or octave (unison) to another of the same kind.
pub fn perfect_parallels(prev: &[Option<i32>], cur: &[Option<i32>]) -> usize {
    let mut n = 0;
    for i in 0..cur.len() {
        for j in i + 1..cur.len() {
            let (Some(a0), Some(b0), Some(a1), Some(b1)) = (prev[i], prev[j], cur[i], cur[j]) else { continue };
            let (iv0, iv1) = ((a0 - b0).rem_euclid(12), (a1 - b1).rem_euclid(12));
            if iv0 == iv1 && (iv0 == 0 || iv0 == 7) && a1 != a0 && b1 != b0 && (a1 > a0) == (b1 > b0) {
                n += 1;
            }
        }
    }
    n
}

/// (alto, tenor) for one harmony slot under `soprano` and over `bass`, or None
/// when no pair keeps the rules.
///
/// Hard rules: S > A >= T > B (only alto and tenor may share a note), S-A and
/// A-T at most an octave, both notes chord tones. Among the pairs that keep
/// them, the smallest of (in order):
///   1. chord tones left out (the fifth of a triad does not count)
///   2. parallel perfect fifths and octaves against the previous slot, over all voice pairs
///   3. doubling: 1 for a missing fifth, 1 per extra copy of a tone other than
///      the root and the bass's own tone
///   4. movement |dA| + |dT| from the previous slot
///   5. the higher alto, then the higher tenor
///
/// `prev` is the previous slot's [S, A, T, B]. A lead that moves during the
/// slot is given as its lowest note (`soprano`, for crossing) and its highest
/// (`soprano_top`, for spacing; default `soprano`). The same order as the
/// Python reference (arranger.voice_satb), frozen after tuning on the chorales.
pub fn voice_satb(pcs: &[i32], soprano: Option<i32>, bass: Option<i32>, prev: Option<&[Option<i32>; 4]>, alto_range: (i32, i32), tenor_range: (i32, i32), soprano_top: Option<i32>) -> Option<(i32, i32)> {
    let mut s: Vec<i32> = pcs.iter().map(|p| p.rem_euclid(12)).collect();
    s.sort();
    s.dedup();
    let top = soprano_top.or(soprano);
    let bass_pc = bass.map(|b| b.rem_euclid(12));
    let root = chord_root(&s, bass_pc);
    let fifth = Some((root + 7).rem_euclid(12)).filter(|f| s.contains(f));
    let mut best: Option<(i32, i32)> = None;
    let mut best_key: Option<(usize, usize, i64, i32, i32, i32)> = None;
    for a in alto_range.0..=alto_range.1 {
        if !s.contains(&a.rem_euclid(12)) {
            continue;
        }
        if let Some(sp) = soprano {
            if !(a < sp && top.unwrap_or(sp) - a <= 12) {
                continue;
            }
        }
        for t in tenor_range.0..=tenor_range.1 {
            if !s.contains(&t.rem_euclid(12)) || t > a || a - t > 12 || bass.is_some_and(|b| t <= b) {
                continue;
            }
            let have: Vec<i32> = [soprano, Some(a), Some(t), bass].iter().flatten().map(|v| v.rem_euclid(12)).collect();
            let missing: Vec<i32> = s.iter().copied().filter(|pc| !have.contains(pc)).collect();
            let essential = missing.iter().filter(|pc| Some(**pc) != fifth).count();
            let mut doubling: i64 = fifth.is_some_and(|f| missing.contains(&f)) as i64;
            let mut distinct = have.clone();
            distinct.sort();
            distinct.dedup();
            for pc in distinct {
                if pc != root && Some(pc) != bass_pc {
                    doubling += have.iter().filter(|h| **h == pc).count() as i64 - 1;
                }
            }
            let (par, mv) = match prev {
                Some(p) => (
                    perfect_parallels(p, &[soprano, Some(a), Some(t), bass]),
                    p[1].map(|x| (a - x).abs()).unwrap_or(0) + p[2].map(|x| (t - x).abs()).unwrap_or(0),
                ),
                None => (0, 0),
            };
            let key = (essential, par, doubling, mv, -a, -t);
            if best_key.is_none_or(|k| key < k) {
                best = Some((a, t));
                best_key = Some(key);
            }
        }
    }
    best
}

/// Alto and tenor of a four-part lineup, slot by slot (start, end, pitch classes, confidence).
fn voice_satb_slots(arr: &mut Arrangement, slots: &[(i64, i64, Vec<i32>, f64)], lead_notes: &[Note], bass_notes: &[Note], difficulty: &str) {
    let lineup = arr.lineup.clone();
    let inner = by_comfort_desc(lineup.parts.iter().filter(|p| p.name != lineup.lead && p.name != lineup.bass));
    let (alto, tenor) = (inner[0], inner[1]);
    let ra = crate::difficulty::mode_range(alto, difficulty);
    let rt = crate::difficulty::mode_range(tenor, difficulty);
    for p in &inner {
        arr.get_mut(p.name);
    }
    let mut prev: Option<[Option<i32>; 4]> = None;
    let mut prev_named: HashMap<&'static str, i32> = HashMap::new();
    for (start, end, pcs, conf) in slots {
        // The inner parts hold through the slot: keep them under the lead's lowest note in it and
        // over the bass's highest, so a moving line never crosses them.
        let top: Vec<i32> = lead_notes.iter().filter(|n| n.start < *end && n.end() > *start).map(|n| n.pitch).collect();
        let bot: Vec<i32> = bass_notes.iter().filter(|n| n.start < *end && n.end() > *start).map(|n| n.pitch).collect();
        let sop = top.iter().copied().min();
        let bas = bot.iter().copied().max();
        let (a, t) = match voice_satb(pcs, sop, bas, prev.as_ref(), ra, rt, top.iter().copied().max()) {
            Some((a, t)) => (Some(a), Some(t)),
            None => {
                arr.warnings.push(format!("{}/{}: slot at tick {} voiced without the four-part rules", alto.name, tenor.name, start));
                let v = voice_slot(pcs, &[alto, tenor], sop.unwrap_or(90), bas.unwrap_or(30), &prev_named, Some(&[ra, rt]));
                let get = |name: &str| v.iter().find(|(n, _)| *n == name).map(|(_, p)| *p);
                (get(alto.name), get(tenor.name))
            }
        };
        for (part, p) in [(alto, a), (tenor, t)] {
            if let Some(p) = p {
                arr.get_mut(part.name).push(Note::new(p, *start, end - start, *conf, vec!["arranger".into()]));
                prev_named.insert(part.name, p);
            }
        }
        prev = Some([sop, a, t, bas]);
    }
}

/// Four-part lineups: the difficulty mode applied to lead and bass before the inner
/// parts are voiced against them (so a later change to the outer parts cannot cross
/// an inner one). The 16th merges read the chord from the other outer part and the
/// source harmony.
fn outer_difficulty(arr: &mut Arrangement, difficulty: &str, harmony: &[Note]) -> Result<(), String> {
    let lineup = arr.lineup.clone();
    let names = [lineup.lead, lineup.bass];
    let mut parts: Vec<(String, Vec<Note>)> = names.iter().map(|n| (n.to_string(), arr.part_notes(n).to_vec())).collect();
    parts.push((HARMONY_CONTEXT.to_string(), harmony.to_vec()));
    let out = crate::difficulty::apply_difficulty_only(parts, &lineup, difficulty, Some(&names))?;
    for (name, notes) in out {
        if names.contains(&name.as_str()) {
            arr.set(&name, notes);
        }
    }
    Ok(())
}

/// Four-part lineups: the difficulty mode on the inner parts only (voiced in its range already).
fn inner_difficulty(arr: &mut Arrangement, difficulty: &str) -> Result<(), String> {
    let lineup = arr.lineup.clone();
    let inner: Vec<&str> = lineup.parts.iter().map(|p| p.name).filter(|n| *n != lineup.lead && *n != lineup.bass).collect();
    arr.parts = crate::difficulty::apply_difficulty_only(std::mem::take(&mut arr.parts), &lineup, difficulty, Some(&inner))?;
    Ok(())
}

pub fn arrange(comp: &Composition) -> Arrangement {
    arrange_with(comp, minimal_band())
}

pub fn arrange_with(comp: &Composition, lineup: Lineup) -> Arrangement {
    arrange_opts(comp, lineup, "faithful").expect("faithful arrangement")
}

/// Melody, bass and harmony voices arranged for `lineup`; `difficulty` as in difficulty.rs.
pub fn arrange_opts(comp: &Composition, lineup: Lineup, difficulty: &str) -> Result<Arrangement, String> {
    if !crate::difficulty::MODES.contains(&difficulty) {
        return Err(format!("difficulty must be one of {:?}", crate::difficulty::MODES));
    }
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
    if lineup.satb {
        outer_difficulty(&mut arr, difficulty, &harmony)?;
    }
    let mut satb_slots: Vec<(i64, i64, Vec<i32>, f64)> = Vec::new();
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
        let top = if tune_on_top(&lineup) { sounding_at(&lead_notes, s) } else { Vec::new() };
        let bot = sounding_at(&eb_notes, s);
        let ceiling = top.first().map(|n| n.pitch).unwrap_or(90);
        let floor = bot.first().map(|n| n.pitch).unwrap_or(30);
        let mut end = sounding.iter().map(|n| n.end()).max().unwrap();
        if let Some(&nxt) = ends.get(&s) {
            // Hold across tiny gaps (performance/MIDI release offsets) instead of writing 64th rests.
            end = if nxt - end <= MIN_REST_TICKS { nxt } else { end.min(nxt) };
        }
        let conf = sounding.iter().map(|n| n.confidence).fold(f64::INFINITY, f64::min);
        if lineup.satb {
            satb_slots.push((s, end, pcs, conf));
            continue;
        }
        let voicing = voice_slot(&pcs, &inner, ceiling, floor, &prev, None);
        for (name, p) in &voicing {
            arr.get_mut(name).push(Note::new(*p, s, end - s, conf, vec!["arranger".into()]));
        }
        prev.extend(voicing);
    }
    if lineup.satb {
        let (lead_notes, bass_notes) = (arr.part_notes(lead.name).to_vec(), arr.part_notes(eb.name).to_vec());
        voice_satb_slots(&mut arr, &satb_slots, &lead_notes, &bass_notes, difficulty);
        inner_difficulty(&mut arr, difficulty)?;
        return Ok(arr);
    }
    arr.parts = crate::difficulty::apply_difficulty(std::mem::take(&mut arr.parts), &arr.lineup, difficulty)?;
    Ok(arr)
}

/// The band lineups' own lead.
pub const BAND_LEADS: [&str; 1] = ["Solo Cornet"];

/// The part that plays the countermelody: the Euphonium, or with the tune on it, Solo Horn, then 1st Baritone.
pub fn counter_part(lineup: &Lineup) -> Option<&'static str> {
    if lineup.lead != "Euphonium" {
        return lineup.has("Euphonium").then_some("Euphonium");
    }
    ["Solo Horn", "1st Baritone"].into_iter().find(|n| lineup.has(n))
}

/// The tune's part sits on top of the band (a cornet or flugelhorn), so the inner parts go under it.
fn tune_on_top(lineup: &Lineup) -> bool {
    crate::instruments::TOP_INSTRUMENTS.contains(&lineup.lead_part().instrument.id)
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
        let voicing = voice_slot(pcs, &parts, ceiling, floor, &prev, None);
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
    if lineup.as_played {
        // A solo take for the player's seat: their own line in their octave, and nothing else.
        let placed = place_as_played(&solo, lineup.lead_part(), &mut arr.warnings);
        arr.set(lead, placed);
        arr.parts = crate::difficulty::apply_difficulty(std::mem::take(&mut arr.parts), &arr.lineup, &opts.difficulty)?;
        return Ok(arr);
    }
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
    if lineup.satb {
        // One set of harmony slots from the whole accompaniment, voiced as alto and tenor.
        let mut acc = strings.clone();
        acc.extend(keys.iter().cloned());
        acc.extend(brass.iter().cloned());
        outer_difficulty(&mut arr, &opts.difficulty, &acc)?;
        let mut slots = harmony_slots(&acc, end, 4, 0.35);
        if figuration {
            slots = figurate(&slots, &acc.iter().map(|n| n.start).collect::<Vec<_>>(), 12);
        }
        let slots: Vec<(i64, i64, Vec<i32>, f64)> = slots.into_iter().map(|(s, e, pcs)| (s, e, pcs, 0.8)).collect();
        let (lead_notes, bass_notes) = (arr.part_notes(lead).to_vec(), arr.part_notes(eb.name).to_vec());
        voice_satb_slots(&mut arr, &slots, &lead_notes, &bass_notes, &opts.difficulty);
        if !layer(comp, "drums").is_empty() {
            arr.warnings.push(format!("{}: drums left out (no percussion part)", lineup.name));
        }
        inner_difficulty(&mut arr, &opts.difficulty)?;
        return Ok(arr);
    }
    let cm = counter_part(&lineup);
    if let Some(cm) = cm {
        arr.set(cm, place_smooth(&counter, lineup.by_name(cm)));
    }

    let mut pad_src = strings.clone();
    pad_src.extend(keys.iter().cloned());
    let mut pad_slots = harmony_slots(&pad_src, end, 4, 0.35);
    if figuration {
        pad_slots = figurate(&pad_slots, &pad_src.iter().map(|n| n.start).collect::<Vec<_>>(), 12);
    }
    // With the tune on the player's part (lead "seat"), the band's own lead joins the pads, and the
    // inner parts keep under the tune only while it is on top.
    let solo_notes = if tune_on_top(&lineup) { arr.part_notes(lead).to_vec() } else { Vec::new() };
    let eb_notes = arr.part_notes(eb.name).to_vec();
    let pads: Vec<&str> = BAND_LEADS
        .iter()
        .copied()
        .filter(|p| lineup.has(p) && *p != lead)
        .chain(PAD_PARTS.iter().copied().filter(|p| lineup.has(p) && *p != lead && Some(*p) != cm))
        .collect();
    voice_layer(&mut arr, &pad_slots, &pads, &solo_notes, &eb_notes, 76, 0.8);

    let mut choir_slots = harmony_slots(&brass, end, 3, 0.35);
    if figuration {
        choir_slots = figurate(&choir_slots, &brass.iter().map(|n| n.start).collect::<Vec<_>>(), 12);
    }
    let choir: Vec<&str> = CHOIR_PARTS.iter().copied().filter(|p| lineup.has(p) && *p != lead).collect();
    voice_layer(&mut arr, &choir_slots, &choir, &solo_notes, &eb_notes, 79, 0.8);

    // Bass trombone reinforces the bass line only while the brass choir is playing.
    if lineup.has("Bass Trombone") {
        let btb = lineup.by_name("Bass Trombone");
        let tutti: Vec<Note> = bass.iter().filter(|n| choir_slots.iter().any(|(s, e, _)| *s <= n.start && n.start < *e)).cloned().collect();
        let placed = place_line(&tutti, btb, &mut arr.warnings, 0, true);
        arr.set(btb.name, placed);
    }

    if soprano && lineup.has("Soprano Cornet") && BAND_LEADS.contains(&lead) {
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

// ---------------------------------------------------------------------------
// Where each part comes from.
// ---------------------------------------------------------------------------

/// A solo take: the part carries the player's own line.
pub const YOUR_RECORDING: &str = "your-recording";
/// The part follows a line heard in a band recording.
pub const RECORDING: &str = "recording";
/// Voiced from the harmony, or doubling the tune.
pub const ARRANGED: &str = "arranged";
/// Nothing to play in this arrangement: the Percussion part of a recording without drums, the
/// Soprano Cornet when it has no climax to double (always in faithful mode). No footer.
pub const EMPTY: &str = "empty";

/// The parts of a layered band arrangement that the arranger leaves without notes (see [`EMPTY`]).
fn empty_parts(comp: &Composition, lineup: &Lineup) -> Vec<&'static str> {
    let mut out = Vec::new();
    if lineup.satb || lineup.as_played {
        return out;
    }
    if lineup.has("Percussion") && !has_notes(comp, &["drums"]) {
        out.push("Percussion");
    }
    let difficulty = arrangement_opt(comp, "difficulty").unwrap_or_else(|| "faithful".into());
    let spans = climax_spans(comp);
    let doubles = difficulty != "faithful"
        && BAND_LEADS.contains(&lineup.lead)
        && layer(comp, "solo").iter().any(|n| spans.iter().any(|(a, b)| *a <= n.start && n.start < *b));
    if lineup.has("Soprano Cornet") && !doubles {
        out.push("Soprano Cornet");
    }
    out
}

fn arrangement_opt(comp: &Composition, key: &str) -> Option<String> {
    comp.arrangement.as_ref().and_then(|a| a.get(key)).and_then(|v| v.as_str()).map(String::from)
}

/// The lineup a Composition is arranged for (as recorded in `comp.arrangement`), and whether the
/// layered arranger makes it (its voices carry layers).
pub fn composition_lineup(comp: &Composition) -> (Lineup, bool) {
    let lineup = arrangement_opt(comp, "lineup");
    let (seat, reads) = (arrangement_opt(comp, "seat"), arrangement_opt(comp, "reads"));
    let layered = comp.voices.iter().any(|v| v.layer.is_some());
    let (key, l) = if !layered {
        if lineup.as_deref() == Some("quartet") {
            ("quartet", crate::instruments::quartet())
        } else {
            ("minimal", minimal_band())
        }
    } else {
        if let Some(s) = seat.as_deref().filter(|_| is_solo_take(comp)) {
            if let Ok(l) = crate::instruments::seat_lineup(s, reads.as_deref()) {
                return (l, true);
            }
        }
        // Anything but a known lineup arranges for the band, as before lineups carried their roles.
        match crate::instruments::lineup_key(lineup.as_deref().unwrap_or("band")) {
            Ok(k) => (k, crate::instruments::lineup_by_name(k).expect("known lineup")),
            Err(_) => ("band", brass_band()),
        }
    };
    let l = match seat.as_deref().and_then(|s| Some((crate::instruments::seat_by_id(s).ok()?, crate::instruments::seat_part(key, s).ok()?))) {
        Some((s, sp)) => crate::instruments::with_reading(l, s, sp.part, reads.as_deref()),
        None => l,
    };
    let l = match seat.as_deref().filter(|_| arrangement_opt(comp, "lead").as_deref() == Some("seat")) {
        // A lineup the tune cannot move in keeps its own lead.
        Some(s) => crate::instruments::lead_lineup(l.clone(), s).unwrap_or(l),
        None => l,
    };
    (l, layered)
}

fn has_notes(comp: &Composition, layers: &[&str]) -> bool {
    comp.voices.iter().any(|v| !v.notes.is_empty() && v.layer.as_deref().is_some_and(|l| layers.contains(&l)))
}

/// A layered Composition with notes in its solo layer only: one player recorded alone.
pub fn is_solo_take(comp: &Composition) -> bool {
    comp.voices.iter().any(|v| v.layer.is_some())
        && has_notes(comp, &["solo"])
        && !comp.voices.iter().any(|v| !v.notes.is_empty() && v.layer.as_deref() != Some("solo"))
}

/// Languages of the source footer on printed parts.
pub const FOOTER_LANGS: [&str; 2] = ["en", "nb"];

/// The footer printed on a part from `source` ([`part_sources`]), in `lang` ("en" or "nb"; empty = en):
/// an arranged part says so; a part from the recording has none.
pub fn source_footer(source: &str, lang: &str) -> Option<&'static str> {
    match (source, lang) {
        (ARRANGED, "nb") => Some("Arrangert av Brasscribe ut fra harmoniene i bandet."),
        (ARRANGED, _) => Some("Arranged by Brasscribe from the band's harmony."),
        _ => None,
    }
}

/// (part name, footer) for every part of the Composition's arrangement that has one.
pub fn part_footers(comp: &Composition, lang: &str) -> Vec<(String, String)> {
    part_sources(comp).into_iter().filter_map(|(p, s)| source_footer(s, lang).map(|f| (p, f.to_string()))).collect()
}

/// Where each part of the Composition's arrangement comes from, in score order.
///
/// Derived, not stored: from the lineup's roles, the arranger that made it (layered or not) and
/// which layers have notes. `your-recording`: a solo take's line; `recording`: a line heard in the
/// recording (the tune, the bass line and its doublings, the countermelody from the strings' top
/// line, the drums); `arranged`: everything voiced from the harmony, and the Soprano Cornet's
/// doubling of the tune; `empty`: a part left without notes (no drums, no climax to double).
pub fn part_sources(comp: &Composition) -> Vec<(String, &'static str)> {
    let (lineup, layered) = composition_lineup(comp);
    let mut heard: Vec<&str> = Vec::new();
    let basses = |heard: &mut Vec<&'static str>| {
        heard.push(lineup.bass);
        if let Some(b) = lineup.second_bass {
            heard.push(b);
        }
    };
    if !layered {
        heard.push(lineup.lead);
        basses(&mut heard);
    } else if is_solo_take(comp) {
        return lineup.parts.iter().map(|p| (p.name.to_string(), if p.name == lineup.lead { YOUR_RECORDING } else { ARRANGED })).collect();
    } else {
        if has_notes(comp, &["solo"]) {
            heard.push(lineup.lead);
        }
        if has_notes(comp, &["bass"]) {
            basses(&mut heard);
            if !lineup.satb && lineup.has("Bass Trombone") {
                heard.push("Bass Trombone");
            }
        }
        if let Some(cm) = counter_part(&lineup).filter(|_| !lineup.satb && has_notes(comp, &["strings"])) {
            heard.push(cm);
        }
        if !lineup.satb && has_notes(comp, &["drums"]) && lineup.has("Percussion") {
            heard.push("Percussion");
        }
    }
    let empty = if layered { empty_parts(comp, &lineup) } else { Vec::new() };
    lineup
        .parts
        .iter()
        .map(|p| {
            let s = if heard.contains(&p.name) {
                RECORDING
            } else if empty.contains(&p.name) {
                EMPTY
            } else {
                ARRANGED
            };
            (p.name.to_string(), s)
        })
        .collect()
}
