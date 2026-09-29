//! Quantized parts -> MusicXML.
//!
//! Notes sharing a start tick within a part become a chord (clipped to the
//! shortest member); overlaps within a part are cut at the next onset, so every
//! part is a single voice. Values are split into tied pieces that show the
//! beat; transposing parts are written at written pitch with a <transpose>
//! element; every part names its MuseScore <instrument-sound>.

use crate::arranger::{layer_of_part, Arrangement};
use crate::model::Composition;
use crate::quantize::QNote;

pub use crate::notation::parts::split_parts;
pub use crate::notation::score::{write_score, FreeSpan, PartSpec, ScoreSpec};

/// Arrangement (concert notes per band part) -> transposing score in lineup order.
/// QNote articulation "trill:<semitones>" (Note::trill) inside the writer.
pub const TRILL: &str = "trill:";

pub fn band_score(arr: &Arrangement, comp: &Composition) -> ScoreSpec {
    let parts = arr
        .lineup
        .parts
        .iter()
        .map(|part| {
            let notes = arr
                .part_notes(part.name)
                .iter()
                .map(|n| QNote {
                    pitch: n.pitch,
                    start: n.start,
                    end: n.end(),
                    onset_s: n.onset_s.unwrap_or(0.0),
                    offset_s: n.offset_s.unwrap_or(0.0),
                    confidence: n.confidence,
                    articulations: n.articulations.iter().cloned().chain(n.trill.map(|t| format!("{TRILL}{t}"))).collect(),
                })
                .collect();
            let layer = layer_of_part(&arr.lineup, part.name);
            let dynamics = comp.dynamics.iter().filter(|d| Some(d.layer.as_str()) == layer).map(|d| (d.tick, d.mark.clone())).collect();
            PartSpec {
                name: part.name.to_string(),
                notes,
                clef: part.instrument.clef.as_str().to_string(),
                instrument: Some(part.instrument),
                abbreviation: Some(part.abbreviation().to_string()),
                dynamics,
            }
        })
        .collect();
    ScoreSpec {
        parts,
        beats_per_bar: comp.meters.first().map(|m| m.beats).unwrap_or(4),
        bpm: comp.bpm(),
        title: comp.title.clone(),
        pickup_ticks: 0,
        low_confidence: crate::confidence::Model::load().mark_below(),
        very_below: crate::confidence::Model::load().very_below(),
        key_fifths: comp.keys.first().map(|k| k.fifths),
        sounds: band_sounds(arr),
        free_spans: comp.free_regions.iter().map(|r| FreeSpan { start: r.start, end: r.end, bpm: r.tempo_bpm, label: r.label.clone() }).collect(),
        key_changes: comp.keys.iter().skip(1).map(|k| (k.tick, k.fifths)).collect(),
        rehearsal: comp.sections.iter().map(|s| (s.tick, s.label.clone())).collect(),
        encoding_date: String::new(),
    }
}

pub fn band_sounds(arr: &Arrangement) -> Vec<(String, String)> {
    arr.lineup.parts.iter().filter(|p| !p.instrument.sound.is_empty()).map(|p| (p.name.to_string(), p.instrument.sound.to_string())).collect()
}
