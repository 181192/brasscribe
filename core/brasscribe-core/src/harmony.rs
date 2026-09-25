//! Reduce dense accompaniment notes to a harmonic rhythm of pitch-class sets.
//!
//! Per beat, each pitch class is weighted by sounding duration x confidence;
//! the strongest few are kept and consecutive beats with the same set merge
//! into one harmony slot.

use crate::model::{Note, TICKS_PER_BEAT};

/// (start, end, pitch classes)
pub type Slot = (i64, i64, Vec<i32>);

pub fn harmony_slots(notes: &[Note], end_tick: i64, max_pcs: usize, rel_threshold: f64) -> Vec<Slot> {
    harmony_slots_beat(notes, end_tick, max_pcs, rel_threshold, TICKS_PER_BEAT)
}

pub fn harmony_slots_beat(notes: &[Note], end_tick: i64, max_pcs: usize, rel_threshold: f64, beat: i64) -> Vec<Slot> {
    let mut slots: Vec<Slot> = Vec::new();
    let mut t = 0;
    while t < end_tick {
        let mut w = [0.0f64; 12];
        for n in notes {
            let overlap = n.end().min(t + beat) - n.start.max(t);
            if overlap > 0 {
                w[n.pitch.rem_euclid(12) as usize] += overlap as f64 * n.confidence;
            }
        }
        let top = w.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        let pcs: Vec<i32> = if top <= 0.0 {
            Vec::new()
        } else {
            let mut ranked: Vec<usize> = (0..12).collect();
            ranked.sort_by(|&a, &b| (-w[a]).partial_cmp(&-w[b]).unwrap());
            let mut v: Vec<i32> = ranked.iter().take(max_pcs).filter(|&&pc| w[pc] >= rel_threshold * top).map(|&pc| pc as i32).collect();
            v.sort();
            v
        };
        match slots.last_mut() {
            Some(last) if last.2 == pcs && last.1 == t => last.1 = t + beat,
            _ => slots.push((t, t + beat, pcs)),
        }
        t += beat;
    }
    slots.into_iter().filter(|s| !s.2.is_empty()).collect()
}

/// One middle-register note per pitch class per slot (the arranger re-voices them anyway).
pub fn slots_to_notes(slots: &[Slot], confidence: f64) -> Vec<Note> {
    slots
        .iter()
        .flat_map(|(s, e, pcs)| pcs.iter().map(move |pc| Note::new(48 + pc, *s, e - s, confidence, vec!["harmony".into()])))
        .collect()
}
