//! Tab fingering for fretted instruments (`target-fretted`): its JSON requests in, its JSON answers
//! out, both unchanged, as the command line's `fret` and `tab` pass them.
//!
//! Everything the crate refuses is something the request said (JSON that is not a request, an
//! unknown preset, a pin on a note or string that does not exist, a note that cannot be written),
//! so every error is invalid input.

use crate::{invalid, CoreError};

/// A string and a fret for every note. `request` is `target-fretted`'s fingering request:
/// `{"instrument": {"preset": "bass-4-standard", "capo": 0} | {full instrument},
///   "notes": [{"pitch", "start", "dur", "confidence"?, "techniques"?: ["slide", ...]}...],
///   "options": {"style": "open-position" | "as-played" | "lead", "tempo_bpm", "hand",
///               "pins": [{"note": index, "string": number}]}}` (`options` and each of its fields
/// may be left out). Answers with
/// `{"instrument": {the instrument used}, "fingering": {"notes": [{"pitch", "string", "fret",
///   "alternatives": [{"string", "fret"}...], "out_of_range", "pinned"}...]},
///   "violations": [{"kind": "pin-not-honoured", ...}...], "tuning_suggestions": [...]}`:
/// one place per note in the order of the request, the hard playability violations, and for a
/// preset instrument the tunings of its family ranked by fit.
/// A pin on a string that cannot sound the note's pitch is not an error: the note is placed
/// elsewhere and the pin is listed in `violations`.
#[uniffi::export]
pub fn fretted_fingering_json(request: String) -> Result<String, CoreError> {
    target_fretted::json::solve_json(&request).map_err(invalid)
}

/// Tablature as MusicXML. `request` is `target-fretted`'s tab request: the fingering request plus
/// `title`, `tempo_bpm`, `meter`, `key`, `tab` (layout, capo encoding, clef, doubt threshold) and,
/// to write a fingering as it is instead of solving, `fingering`. Answers with
/// `{"musicxml": "...", "adjusted_notes": 0}`.
#[uniffi::export]
pub fn fretted_tab_json(request: String) -> Result<String, CoreError> {
    target_fretted::json::tab_json(&request).map_err(invalid)
}
