//! Note-level consensus across transcription sources.
//!
//! A source is one (model, stem) note stream. Notes from different sources that
//! share a pitch and start within `ONSET_TOL` are clustered into one candidate.
//! Each candidate's confidence is `1 - prod(1 - precision_s)` over its
//! supporting model families, so agreement between independent models raises
//! confidence and one reliable source alone can still carry a note.

use std::collections::{BTreeSet, HashMap};

use crate::midi::RawNote;
use crate::py;

pub const ONSET_TOL: f64 = 0.10;

#[derive(Debug, Clone, PartialEq)]
pub struct Candidate {
    pub pitch: i32,
    pub onsets: Vec<f64>,
    pub offsets: Vec<f64>,
    pub sources: BTreeSet<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct VotedNote {
    pub pitch: i32,
    pub onset: f64,
    pub offset: f64,
    pub confidence: f64,
    pub sources: Vec<String>,
}

impl VotedNote {
    pub fn raw(&self) -> RawNote {
        RawNote { pitch: self.pitch, onset: self.onset, offset: self.offset, confidence: Some(self.confidence) }
    }
}

impl Candidate {
    pub fn median_onset(&self) -> f64 {
        py::median(&self.onsets)
    }

    pub fn median_offset(&self) -> f64 {
        py::median(&self.offsets)
    }

    pub fn to_note(&self, confidence: f64) -> VotedNote {
        VotedNote {
            pitch: self.pitch,
            onset: self.median_onset(),
            offset: self.median_offset(),
            confidence: py::py_round(confidence, 3),
            sources: self.sources.iter().cloned().collect(),
        }
    }
}

/// Sources in the order given; each is a label and its notes.
pub type Sources = Vec<(String, Vec<RawNote>)>;

pub fn cluster(sources: &Sources) -> Vec<Candidate> {
    let mut events: Vec<(f64, i32, f64, &str)> =
        sources.iter().flat_map(|(s, notes)| notes.iter().map(move |n| (n.onset, n.pitch, n.offset, s.as_str()))).collect();
    events.sort_by(|a, b| {
        a.0.partial_cmp(&b.0).unwrap().then(a.1.cmp(&b.1)).then(a.2.partial_cmp(&b.2).unwrap()).then(a.3.cmp(b.3))
    });
    let mut done: Vec<Candidate> = Vec::new();
    // open candidates per pitch, as indices into `done`
    let mut open: HashMap<i32, Vec<usize>> = HashMap::new();
    for (onset, pitch, offset, src) in events {
        let bucket = open.entry(pitch).or_default();
        let mut target = None;
        for &ci in bucket.iter() {
            let c = &done[ci];
            if onset - c.onsets[0] <= ONSET_TOL && !c.sources.contains(src) {
                target = Some(ci);
                break;
            }
        }
        let ti = match target {
            Some(t) => t,
            None => {
                done.push(Candidate { pitch, onsets: Vec::new(), offsets: Vec::new(), sources: BTreeSet::new() });
                bucket.push(done.len() - 1);
                done.len() - 1
            }
        };
        let c = &mut done[ti];
        c.onsets.push(onset);
        c.offsets.push(offset);
        c.sources.insert(src.to_string());
        bucket.retain(|&ci| onset - done[ci].onsets[0] <= ONSET_TOL);
    }
    done
}

/// Stems of one model share a precision estimate unless given explicitly.
pub fn source_family(source: &str) -> &str {
    source.split('/').next().unwrap_or(source)
}

/// (accepted, alternatives); precision is keyed by source or family.
pub fn consensus(sources: &Sources, precision: &[(&str, f64)], threshold: f64) -> (Vec<VotedNote>, Vec<VotedNote>) {
    let prec = |k: &str| precision.iter().find(|(n, _)| *n == k).map(|(_, p)| *p);
    let mut accepted = Vec::new();
    let mut alternatives = Vec::new();
    for c in cluster(sources) {
        // Each model family votes once, with its most reliable supporting stem.
        let mut best: Vec<(String, f64)> = Vec::new();
        for s in &c.sources {
            let p = prec(s).or_else(|| prec(source_family(s))).unwrap_or(0.3);
            let fam = source_family(s).to_string();
            match best.iter_mut().find(|(f, _)| *f == fam) {
                Some(e) => e.1 = e.1.max(p),
                None => best.push((fam, 0.0f64.max(p))),
            }
        }
        let mut miss = 1.0;
        for (_, p) in &best {
            miss *= 1.0 - p;
        }
        let note = c.to_note(1.0 - miss);
        if note.confidence >= threshold {
            accepted.push(note);
        } else {
            alternatives.push(note);
        }
    }
    accepted.sort_by(|a, b| a.onset.partial_cmp(&b.onset).unwrap().then(a.pitch.cmp(&b.pitch)));
    (accepted, alternatives)
}
