//! Playability check: the hard rules a fingering must never break, independent of the solver.

use scribe_core::model::Note;
use serde::{Deserialize, Serialize};

use crate::instrument::{Instrument, Position};
use crate::solve::{Fingering, Options};
use crate::technique::{per_note, previous_notes, string_link, Technique};

/// A hard playability violation. Note numbers are indices into the input.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "kebab-case")]
pub enum Violation {
    /// Two different notes starting together on one string.
    SharedString { string: u8, notes: Vec<usize> },
    /// Notes starting together whose fretted span is over the hand limit.
    SpanTooWide { notes: Vec<usize>, span_mm: f64 },
    /// A string or fret that does not exist on the instrument.
    FretOutOfRange { note: usize, string: u8, fret: u8 },
    /// A position that sounds another pitch than the note's.
    WrongPitch { note: usize, string: u8, fret: u8 },
    /// A pinned note that is not on its pinned string.
    PinNotHonoured { note: usize, string: u8 },
    /// A note the instrument can play that was left without a position (more notes start together
    /// than there are strings), or an out-of-range flag that does not match the instrument.
    NoString { note: usize },
    /// A slide, hammer-on, pull-off or bend on another string than the note it comes from.
    TechniqueString { note: usize, previous: usize },
    /// A slide, hammer-on or pull-off farther from the note it comes from than the hand can play it
    /// (12 frets for a slide, 5 for a hammer-on or pull-off).
    TechniqueReach { note: usize, previous: usize, frets: i32 },
    /// A bend on an open string.
    BendOnOpenString { note: usize },
    /// A note on a string that a let-ring note, started earlier, still reserves.
    RingCut { string: u8, ringing: usize, note: usize },
}

/// Whether two notes of one onset are one sounding note (a doubling) rather than two.
pub fn same_sound(a_pitch: i32, a: Position, b_pitch: i32, b: Position) -> bool {
    a_pitch == b_pitch && a == b
}

/// Every hard violation in `fingering` for `notes` on `inst`. Empty means playable.
pub fn check(inst: &Instrument, notes: &[Note], fingering: &Fingering, opts: &Options) -> Vec<Violation> {
    check_with_techniques(inst, notes, &[], fingering, opts)
}

/// [`check`] with playing techniques, one list per note (or none at all; a list of another length
/// counts as none).
pub fn check_with_techniques(inst: &Instrument, notes: &[Note], techniques: &[Vec<Technique>], fingering: &Fingering, opts: &Options) -> Vec<Violation> {
    let techniques = per_note(techniques, notes.len()).unwrap_or_else(|_| vec![Vec::new(); notes.len()]);
    let mut out = Vec::new();
    let mut placed: Vec<(usize, Position, i32)> = Vec::new();
    for (i, (note, place)) in notes.iter().zip(&fingering.notes).enumerate() {
        match place.position() {
            None => {
                if place.out_of_range != inst.positions(note.pitch).is_empty() || !place.out_of_range {
                    out.push(Violation::NoString { note: i });
                }
            }
            Some(pos) => {
                match inst.pitch_at(pos) {
                    None => out.push(Violation::FretOutOfRange { note: i, string: pos.string, fret: pos.fret }),
                    Some(p) if p != note.pitch => out.push(Violation::WrongPitch { note: i, string: pos.string, fret: pos.fret }),
                    Some(_) => placed.push((i, pos, inst.neck_fret(pos).unwrap_or(0))),
                }
                if place.out_of_range {
                    out.push(Violation::NoString { note: i });
                }
            }
        }
        if let Some(string) = opts.pin_for(i) {
            if place.string != Some(string) {
                out.push(Violation::PinNotHonoured { note: i, string });
            }
        }
    }

    let string_of = |i: usize| fingering.notes.get(i).and_then(|p| p.string);
    let neck_of = |i: usize| fingering.notes.get(i).and_then(|p| p.position()).and_then(|p| inst.neck_fret(p));
    let previous = previous_notes(notes);
    for (i, t) in techniques.iter().enumerate() {
        if let (Some(reach), Some(j)) = (string_link(t), previous[i]) {
            if let (Some(s), Some(sj)) = (string_of(i), string_of(j)) {
                // On one string, frets apart equal semitones apart; a jump too far to play legato
                // is reported as such whichever strings were chosen.
                let frets = if s == sj { neck_of(i).zip(neck_of(j)).map_or(0, |(a, b)| (a - b).abs()) } else { (notes[i].pitch - notes[j].pitch).abs() };
                if frets > reach {
                    out.push(Violation::TechniqueReach { note: i, previous: j, frets });
                } else if s != sj {
                    out.push(Violation::TechniqueString { note: i, previous: j });
                }
            }
        }
        if t.iter().any(|t| t.needs_fret()) && fingering.notes.get(i).and_then(|p| p.fret) == Some(0) {
            out.push(Violation::BendOnOpenString { note: i });
        }
    }
    // Notes that overlap in time: a let-ring note keeps its string until it ends.
    for (r, t) in techniques.iter().enumerate() {
        let Some(string) = string_of(r).filter(|_| t.contains(&Technique::LetRing)) else { continue };
        let (start, end) = (notes[r].start, notes[r].end());
        for (k, n) in notes.iter().enumerate() {
            if k != r && n.start > start && n.start < end && string_of(k) == Some(string) {
                out.push(Violation::RingCut { string, ringing: r, note: k });
            }
        }
    }

    placed.sort_by_key(|&(i, _, _)| (notes[i].start, i));
    for event in placed.chunk_by(|a, b| notes[a.0].start == notes[b.0].start) {
        let mut strings: Vec<u8> = event.iter().map(|x| x.1.string).collect();
        strings.sort_unstable();
        strings.dedup();
        for s in strings {
            let on: Vec<&(usize, Position, i32)> = event.iter().filter(|x| x.1.string == s).collect();
            let first = on[0];
            if on.iter().any(|x| !same_sound(notes[first.0].pitch, first.1, notes[x.0].pitch, x.1)) {
                out.push(Violation::SharedString { string: s, notes: on.iter().map(|x| x.0).collect() });
            }
        }
        let fretted: Vec<i32> = event.iter().map(|x| x.2).filter(|&n| n > 0).collect();
        if let (Some(&lo), Some(&hi)) = (fretted.iter().min(), fretted.iter().max()) {
            let span = inst.fret_mm(hi) - inst.fret_mm(lo);
            if span > opts.hand.max_mm + 1e-9 {
                out.push(Violation::SpanTooWide { notes: event.iter().map(|x| x.0).collect(), span_mm: span });
            }
        }
    }
    out
}
