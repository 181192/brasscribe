//! Monophonic line extraction from a note list.

use crate::midi::RawNote;

/// Highest (or lowest) note among candidates starting within 50 ms of each
/// other, inside a pitch window, ignoring notes shorter than `min_dur` seconds.
pub fn line(notes: &[RawNote], lo: i32, hi: i32, top: bool, min_dur: f64) -> Vec<RawNote> {
    let mut cand: Vec<&RawNote> =
        notes.iter().filter(|n| lo <= n.pitch && n.pitch <= hi && n.offset - n.onset >= min_dur).collect();
    cand.sort_by(|a, b| a.onset.partial_cmp(&b.onset).unwrap());
    let mut out: Vec<RawNote> = Vec::new();
    for n in cand {
        if let Some(last) = out.last_mut() {
            if n.onset - last.onset < 0.05 {
                let better = if top { n.pitch > last.pitch } else { n.pitch < last.pitch };
                if better {
                    *last = n.clone();
                }
                continue;
            }
        }
        out.push(n.clone());
    }
    out
}

pub const MIN_DUR: f64 = 0.06;
