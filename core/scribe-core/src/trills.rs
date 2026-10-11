//! Trill notation: a sustained two-pitch alternation written as one note with a trill mark.
//!
//! A trill is a run of at least [`MIN_NOTES`] notes (three full cycles) that alternate between
//! exactly two pitches a semitone or a whole tone apart, each following the previous one without a
//! gap and within [`MAX_STEP`] seconds, at a median IOI of [`MAX_IOI`] or less. A held last note is
//! where the trill resolves, not part of it. It is written as one note on the lower (main) pitch,
//! with `Note::trill` the semitones up to the auxiliary; the writers spell the auxiliary from the
//! written key. Playback plays the main note.
//!
//! [`with_trills`] writes them in the transcription at standard and easier (on the simpler line,
//! from the contour-split notes); [`collapse_trills`] in the arrangement (written-out alternations,
//! at standard and easier, and at faithful when asked for). Mirrors `brasscribe_music.trills`.

use crate::midi::RawNote;
use crate::model::Note;
use crate::py;

pub const MIN_NOTES: usize = 7;
pub const MAX_IOI: f64 = 0.15;
pub const MAX_STEP: f64 = 0.2;
pub const MAX_GAP: f64 = 0.05;
pub const MAX_IOI_TICKS: i64 = 6;
pub const MAX_GAP_TICKS: i64 = 6;

fn is_step(d: i32) -> bool {
    d.abs() == 1 || d.abs() == 2
}

/// Trill runs `(i, j)` (inclusive): maximal A B A B ... runs of at least MIN_NOTES notes a
/// semitone or a whole tone apart. `linked[i]`: note i + 1 follows note i fast enough and without
/// a gap; `held[i]`: note i lasts longer than a trill note. A note the quantizer dropped leaves two
/// neighbours on one pitch: at most two linked notes in a row on one pitch are one turn, and the
/// run needs MIN_NOTES - 1 turns.
pub fn runs(pitches: &[i32], linked: &[bool], held: &[bool]) -> Vec<(usize, usize)> {
    let n = pitches.len();
    let mut turns: Vec<(usize, usize)> = Vec::new();
    for k in 0..n {
        match turns.last_mut() {
            Some(t) if pitches[k] == pitches[t.1] && linked[k - 1] && t.1 - t.0 < 1 => t.1 = k,
            _ => turns.push((k, k)),
        }
    }
    let mut out = Vec::new();
    let mut t = 0;
    while t + 1 < turns.len() {
        let (a, b) = (turns[t], turns[t + 1]);
        if !is_step(pitches[a.0] - pitches[b.0]) || !linked[a.1] {
            t += 1;
            continue;
        }
        let mut u = t + 1;
        while u + 1 < turns.len() && pitches[turns[u + 1].0] == pitches[turns[u - 1].0] && linked[turns[u].1] {
            u += 1;
        }
        let mut j = turns[u].1;
        if held[j] {
            if turns[u].0 == j {
                u -= 1;
            }
            j -= 1;
        }
        let i = turns[t].0;
        if u + 1 - t >= MIN_NOTES - 1 && j + 1 - i >= MIN_NOTES {
            out.push((i, j));
            t = u + 1;
        } else {
            t += 1;
        }
    }
    out
}

/// The median IOI of notes i..=j (the upper one of an even count) is at most MAX_IOI.
pub fn fast(onsets: &[f64], i: usize, j: usize) -> bool {
    let mut d: Vec<f64> = (i..j).map(|k| onsets[k + 1] - onsets[k]).collect();
    d.sort_by(py::fcmp);
    d[d.len() / 2] <= MAX_IOI
}

/// [`runs`] on performed notes in seconds.
pub fn timed_runs(pitches: &[i32], onsets: &[f64], offsets: &[f64]) -> Vec<(usize, usize)> {
    let k = pitches.len();
    let mut linked: Vec<bool> = (0..k.saturating_sub(1)).map(|i| onsets[i + 1] - onsets[i] <= MAX_STEP && onsets[i + 1] - offsets[i] <= MAX_GAP).collect();
    linked.push(false);
    let held: Vec<bool> = (0..k).map(|i| offsets[i] - onsets[i] > MAX_STEP).collect();
    runs(pitches, &linked, &held).into_iter().filter(|&(i, j)| fast(onsets, i, j)).collect()
}

/// `line` with each trill run of `split` (the same notes split on the contour) as one note on the
/// lower pitch (`trill` set). A note of `line` inside a run goes; the parts of it before and after
/// the run stay.
pub fn with_trills(line: &[RawNote], split: &[RawNote]) -> Vec<RawNote> {
    let mut s = split.to_vec();
    s.sort_by(|a, b| py::fcmp(&a.onset, &b.onset).then(a.pitch.cmp(&b.pitch)));
    let p: Vec<i32> = s.iter().map(|n| n.pitch).collect();
    let on: Vec<f64> = s.iter().map(|n| n.onset).collect();
    let off: Vec<f64> = s.iter().map(|n| n.offset).collect();
    let found = timed_runs(&p, &on, &off);
    if found.is_empty() {
        return line.to_vec();
    }
    let spans: Vec<RawNote> = found
        .iter()
        .map(|&(i, j)| {
            // the run's two pitches (its first two notes can be one turn on the same pitch)
            let (lo, hi) = s[i..=j].iter().fold((i32::MAX, i32::MIN), |(lo, hi), n| (lo.min(n.pitch), hi.max(n.pitch)));
            RawNote { pitch: lo, onset: s[i].onset, offset: s[j].offset, confidence: None, split: false, trill: hi - lo }
        })
        .collect();
    let mut out: Vec<RawNote> = Vec::new();
    for n in line {
        let mut pieces = vec![n.clone()];
        for t in &spans {
            let mut nxt = Vec::new();
            for q in pieces {
                if q.offset <= t.onset || q.onset >= t.offset {
                    nxt.push(q);
                    continue;
                }
                if q.onset < t.onset {
                    nxt.push(RawNote { offset: t.onset, ..q.clone() });
                }
                if q.offset > t.offset {
                    nxt.push(RawNote { onset: t.offset, ..q.clone() });
                }
            }
            pieces = nxt;
        }
        out.extend(pieces);
    }
    out.extend(spans);
    out.sort_by(|a, b| py::fcmp(&a.onset, &b.onset).then(a.pitch.cmp(&b.pitch)));
    out
}

/// Written notes with each trill run as one note on the lower pitch; with, for each output note,
/// its index in `notes` when it is an unchanged input note (the reference keeps those objects).
///
/// The notes touch on the page (within a 16th), each at most a 16th long but a held last one. The
/// rate comes from the performed onsets where every note has one, else from the written grid.
/// Notes sharing an onset (chords) are left alone (None: unchanged).
pub fn collapse_trills_indexed(notes: &[Note]) -> Option<Vec<(Note, Option<usize>)>> {
    let mut ns: Vec<(usize, &Note)> = notes.iter().enumerate().collect();
    ns.sort_by(|a, b| a.1.start.cmp(&b.1.start).then(a.1.pitch.cmp(&b.1.pitch)));
    if ns.len() < MIN_NOTES {
        return None;
    }
    if ns.windows(2).any(|w| w[0].1.start == w[1].1.start) {
        return None;
    }
    let k = ns.len();
    let pitches: Vec<i32> = ns.iter().map(|x| x.1.pitch).collect();
    let touch: Vec<bool> = (0..k - 1).map(|i| ns[i + 1].1.start - ns[i].1.end() <= MAX_GAP_TICKS).collect();
    let held: Vec<bool> = ns.iter().map(|x| x.1.dur > MAX_IOI_TICKS).collect();
    let found = if ns.iter().all(|x| x.1.onset_s.is_some()) {
        let on: Vec<f64> = ns.iter().map(|x| x.1.onset_s.unwrap()).collect();
        let mut linked: Vec<bool> = (0..k - 1).map(|i| touch[i] && on[i + 1] - on[i] <= MAX_STEP).collect();
        linked.push(false);
        runs(&pitches, &linked, &held).into_iter().filter(|&(i, j)| fast(&on, i, j)).collect::<Vec<_>>()
    } else {
        let mut linked: Vec<bool> = (0..k - 1).map(|i| touch[i] && ns[i + 1].1.start - ns[i].1.start <= MAX_IOI_TICKS).collect();
        linked.push(false);
        runs(&pitches, &linked, &held)
    };
    if found.is_empty() {
        return None;
    }
    let mut out: Vec<(Note, Option<usize>)> = Vec::new();
    let mut at = 0;
    for (i, j) in found {
        out.extend(ns[at..i].iter().map(|x| (x.1.clone(), Some(x.0))));
        let run: Vec<&Note> = ns[i..=j].iter().map(|x| x.1).collect();
        let (first, last) = (run[0], run[run.len() - 1]);
        // a first turn can repeat one pitch
        let (lo, hi) = run.iter().fold((i32::MAX, i32::MIN), |(lo, hi), n| (lo.min(n.pitch), hi.max(n.pitch)));
        let conf = run.iter().map(|n| n.confidence).fold(f64::NEG_INFINITY, f64::max);
        let performed = match (first.performed_dur, last.performed_dur) {
            (Some(_), Some(p)) => Some(last.start + p - first.start),
            _ => None,
        };
        out.push((
            Note {
                pitch: lo,
                dur: last.end() - first.start,
                confidence: conf,
                offset_s: last.offset_s,
                performed_dur: performed,
                articulations: last.articulations.iter().filter(|a| a.as_str() == "fermata").cloned().collect(),
                trill: Some(hi - lo),
                ..first.clone()
            },
            None,
        ));
        at = j + 1;
    }
    out.extend(ns[at..].iter().map(|x| (x.1.clone(), Some(x.0))));
    Some(out)
}

/// [`collapse_trills_indexed`] without the indices; the notes unchanged when there is no trill.
pub fn collapse_trills(notes: &[Note]) -> Vec<Note> {
    match collapse_trills_indexed(notes) {
        Some(v) => v.into_iter().map(|(n, _)| n).collect(),
        None => notes.to_vec(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // C C D C D C D C: the first two Cs are one turn (a dropped note), the trill is C to D
    const PITCHES: [i32; 8] = [60, 60, 62, 60, 62, 60, 62, 60];

    #[test]
    fn a_first_turn_on_one_pitch_still_names_both_pitches() {
        let written: Vec<Note> = PITCHES.iter().enumerate().map(|(i, &p)| Note::new(p, i as i64 * 6, 6, 1.0, vec![])).collect();
        let out = collapse_trills(&written);
        assert_eq!(out.iter().map(|n| (n.pitch, n.start, n.dur, n.trill)).collect::<Vec<_>>(), [(60, 0, 48, Some(2))]);
        let performed: Vec<RawNote> = PITCHES
            .iter()
            .enumerate()
            .map(|(i, &p)| RawNote { pitch: p, onset: 1.0 + i as f64 * 0.1, offset: 1.1 + i as f64 * 0.1, confidence: None, split: false, trill: 0 })
            .collect();
        let out = with_trills(&performed, &performed);
        assert_eq!(out.iter().map(|n| (n.pitch, n.trill)).collect::<Vec<_>>(), [(60, 2)]);
    }
}
