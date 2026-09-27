//! Difficulty modes for an arrangement: faithful, standard, easier.
//!
//! * faithful: the arrangement as the arranger wrote it (no change).
//! * standard: 16th runs merged into 8ths where the harmony allows (the
//!   dropped note is not a chord tone), every part folded into its reading range.
//! * easier: non-solo parts at most 8th-note rhythm (16th runs merged, keeping
//!   the chord tone), every part in its easy range (the reading range with the
//!   top EASY_TOP_TRIM semitones cut), and the solo's 16th runs merged too,
//!   keeping the notes that shape the contour (turning points).
//!
//! Key changes are thinned for easier in the key plan ([`key_change_penalty`]).
//! All transforms run on the arranged parts (concert pitch, ticks).

use std::collections::{BTreeMap, HashSet};

use crate::instruments::{Clef, Lineup, Part};
use crate::model::Note;

pub const MODES: [&str; 3] = ["faithful", "standard", "easier"];
/// Semitones taken off the top of the reading range.
pub const EASY_TOP_TRIM: i32 = 4;
pub const SIXTEENTH: i64 = 6;
pub const EIGHTH: i64 = 12;
/// The band lineups' lead; `apply_difficulty` reads `lineup.lead`.
pub const SOLO_PART: &str = "Solo Cornet";

/// Key-plan change penalty of a mode (None: the key plan's default).
pub fn key_change_penalty(mode: &str) -> Option<f64> {
    (mode == "easier").then_some(1.0)
}

pub fn easy_range(part: &Part) -> (i32, i32) {
    let (lo, hi) = part.instrument.preferred();
    (lo, (lo + 12).max(hi - EASY_TOP_TRIM))
}

fn harmony_at(parts: &[(String, Vec<Note>)], tick: i64, exclude: &str) -> HashSet<i32> {
    parts
        .iter()
        .filter(|(name, _)| name != exclude && name != "Percussion")
        .flat_map(|(_, notes)| notes.iter())
        .filter(|n| n.start <= tick && tick < n.end())
        .map(|n| n.pitch.rem_euclid(12))
        .collect()
}

/// Stable sort by start, keeping each note's index in `notes`.
fn sorted_by_start(notes: &[Note]) -> Vec<(usize, Note)> {
    let mut v: Vec<(usize, Note)> = notes.iter().cloned().enumerate().collect();
    v.sort_by_key(|(_, n)| n.start);
    v
}

/// Merge 16th pairs (onsets x and x+6 inside one 8th) into one 8th.
///
/// The kept pitch: the turning point of the line when `keep_contour`, else
/// the chord tone, else the first. Unless `always`, a pair is merged only when
/// the dropped note is not a chord tone. Afterwards a note that runs into the
/// next onset is clipped; a clipped note that was kept as it was is clipped in
/// `source` too (the reference shares those note objects with the parts it
/// reads the harmony from).
fn merge_sixteenths(source: &mut [Note], chord_at: &dyn Fn(&[Note], i64) -> HashSet<i32>, always: bool, keep_contour: bool) -> Vec<Note> {
    let notes = sorted_by_start(source);
    // (note, index in `source` when it is an unchanged source note)
    let mut out: Vec<(Note, Option<usize>)> = Vec::new();
    let mut i = 0;
    while i < notes.len() {
        let (ai, a) = &notes[i];
        let b = notes.get(i + 1).map(|x| &x.1);
        let pair = b.is_some_and(|b| a.start.rem_euclid(EIGHTH) == 0 && b.start == a.start + SIXTEENTH && a.dur <= SIXTEENTH);
        if !pair {
            out.push((a.clone(), Some(*ai)));
            i += 1;
            continue;
        }
        let b = b.unwrap();
        let chord = chord_at(source, a.start);
        let prev = out.last().map(|(n, _)| n.pitch);
        let nxt = notes.get(i + 2).map(|x| x.1.pitch);
        let turning = |n: &Note| match (prev, nxt) {
            (Some(p), Some(q)) => (n.pitch - p) * (q - n.pitch) < 0,
            _ => false,
        };
        let (keep, drop) = if keep_contour && (turning(a) || turning(b)) {
            if turning(b) && !turning(a) {
                (b, a)
            } else {
                (a, b)
            }
        } else if chord.contains(&a.pitch.rem_euclid(12)) || !chord.contains(&b.pitch.rem_euclid(12)) {
            (a, b)
        } else {
            (b, a)
        };
        if !always && chord.contains(&drop.pitch.rem_euclid(12)) && drop.pitch.rem_euclid(12) != keep.pitch.rem_euclid(12) {
            out.push((a.clone(), Some(*ai)));
            i += 1;
            continue;
        }
        let end = a.end().max(b.end()).max(a.start + EIGHTH);
        out.push((Note { start: a.start, dur: end - a.start, ..keep.clone() }, None));
        i += 2;
    }
    for k in 0..out.len().saturating_sub(1) {
        let ys = out[k + 1].0.start;
        if out[k].0.end() > ys {
            let d = ys - out[k].0.start;
            out[k].0.dur = d;
            if let Some(si) = out[k].1 {
                source[si].dur = d;
            }
        }
    }
    out.into_iter().map(|(n, _)| n).collect()
}

/// Every note at least an 8th long and on the 8th grid (merging notes that land on one 8th).
fn min_eighth(notes: &[Note]) -> Vec<Note> {
    let mut by_slot: BTreeMap<i64, Note> = BTreeMap::new();
    for (_, n) in sorted_by_start(notes) {
        let slot = n.start.div_euclid(EIGHTH) * EIGHTH;
        by_slot.entry(slot).or_insert_with(|| Note { start: slot, dur: EIGHTH.max(n.end() - slot), ..n.clone() });
    }
    let mut out: Vec<Note> = by_slot.into_values().collect();
    for k in 0..out.len().saturating_sub(1) {
        let ys = out[k + 1].start;
        if out[k].end() > ys {
            out[k].dur = ys - out[k].start;
        }
    }
    out
}

/// Octave-fold notes outside [lo, hi] to the octave inside it nearest the previous note.
fn fold(notes: &[Note], lo: i32, hi: i32) -> Vec<Note> {
    let mut out = Vec::new();
    let mut prev: Option<i32> = None;
    for (_, n) in sorted_by_start(notes) {
        let mut p = n.pitch;
        if !(lo <= p && p <= hi) {
            let r = prev.map(|x| x as f64).unwrap_or((lo + hi) as f64 / 2.0);
            let opts = (0..11).map(|k| p.rem_euclid(12) + 12 * k).filter(|&x| lo <= x && x <= hi);
            if let Some(best) = opts.min_by(|x, y| ((*x as f64 - r).abs(), *x).partial_cmp(&((*y as f64 - r).abs(), *y)).unwrap()) {
                p = best;
            }
        }
        out.push(Note { pitch: p, ..n });
        prev = Some(p);
    }
    out
}

/// Parts rewritten for a difficulty mode (faithful returns them unchanged).
pub fn apply_difficulty(parts: Vec<(String, Vec<Note>)>, lineup: &Lineup, mode: &str) -> Result<Vec<(String, Vec<Note>)>, String> {
    if !MODES.contains(&mode) {
        return Err(format!("difficulty must be one of {MODES:?}"));
    }
    if mode == "faithful" {
        return Ok(parts);
    }
    let mut source = parts; // the notes the harmony is read from
    let mut out: Vec<(String, Vec<Note>)> = source.clone();
    for part in &lineup.parts {
        let name = part.name;
        let Some(pi) = source.iter().position(|(n, _)| n == name) else { continue };
        if source[pi].1.is_empty() || part.instrument.clef == Clef::Percussion {
            continue;
        }
        let solo = name == lineup.lead;
        // The chord at a tick, from every other part as it currently stands.
        let others: Vec<(String, Vec<Note>)> = source.iter().enumerate().filter(|(k, _)| *k != pi).map(|(_, x)| x.clone()).collect();
        let chord_at = |mine: &[Note], t: i64| -> HashSet<i32> {
            let _ = mine; // the part's own notes never count (excluded by name)
            harmony_at(&others, t, name)
        };
        let mut mine = std::mem::take(&mut source[pi].1);
        let notes = if mode == "standard" {
            let m = merge_sixteenths(&mut mine, &chord_at, false, false);
            let (lo, hi) = part.instrument.preferred();
            fold(&m, lo, hi)
        } else {
            let mut m = merge_sixteenths(&mut mine, &chord_at, true, solo);
            if !solo {
                m = min_eighth(&m);
            }
            let (lo, hi) = easy_range(part);
            fold(&m, lo, hi)
        };
        source[pi].1 = mine;
        if let Some(o) = out.iter_mut().find(|(n, _)| n == name) {
            o.1 = notes;
        }
    }
    Ok(out)
}
