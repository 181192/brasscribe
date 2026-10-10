//! Standard MIDI File reading with the note semantics of `pretty_midi`
//! (as used by the reference to load transcriptions):
//! tempo map from track 0, notes closed in note-off order, a note-off that
//! coincides with a note-on at the same tick keeps that new note open, and
//! instruments keyed by (program, channel, track) in order of first note.

use std::collections::HashMap;

#[derive(Debug, Clone, PartialEq)]
pub struct MidiNote {
    pub pitch: i32,
    pub velocity: i32,
    pub start: f64,
    pub end: f64,
}

#[derive(Debug, Clone)]
pub struct MidiInstrument {
    pub program: i32,
    pub is_drum: bool,
    pub name: String,
    pub notes: Vec<MidiNote>,
}

#[derive(Debug, Clone)]
pub struct MidiFile {
    pub resolution: u32,
    pub instruments: Vec<MidiInstrument>,
}

#[derive(Debug)]
pub struct MidiError(pub String);

impl std::fmt::Display for MidiError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "MIDI: {}", self.0)
    }
}

impl std::error::Error for MidiError {}

#[derive(Debug, Clone)]
enum Kind {
    NoteOn { ch: u8, note: u8, vel: u8 },
    NoteOff { ch: u8, note: u8 },
    Program { ch: u8, program: u8 },
    Tempo(u32),
    TrackName(String),
    Other,
}

#[derive(Debug, Clone)]
struct Event {
    tick: u64,
    kind: Kind,
}

struct Reader<'a> {
    b: &'a [u8],
    i: usize,
}

impl<'a> Reader<'a> {
    fn u8(&mut self) -> Result<u8, MidiError> {
        let v = *self.b.get(self.i).ok_or_else(|| MidiError("unexpected end of data".into()))?;
        self.i += 1;
        Ok(v)
    }
    fn bytes(&mut self, n: usize) -> Result<&'a [u8], MidiError> {
        if self.i + n > self.b.len() {
            return Err(MidiError("unexpected end of data".into()));
        }
        let s = &self.b[self.i..self.i + n];
        self.i += n;
        Ok(s)
    }
    fn u16(&mut self) -> Result<u16, MidiError> {
        let s = self.bytes(2)?;
        Ok(u16::from_be_bytes([s[0], s[1]]))
    }
    fn u32(&mut self) -> Result<u32, MidiError> {
        let s = self.bytes(4)?;
        Ok(u32::from_be_bytes([s[0], s[1], s[2], s[3]]))
    }
    fn vlq(&mut self) -> Result<u64, MidiError> {
        let mut v: u64 = 0;
        for _ in 0..4 {
            let b = self.u8()?;
            v = (v << 7) | (b & 0x7f) as u64;
            if b & 0x80 == 0 {
                return Ok(v);
            }
        }
        Ok(v)
    }
}

fn latin1(b: &[u8]) -> String {
    b.iter().map(|&c| c as char).collect()
}

fn parse_track(data: &[u8]) -> Result<Vec<Event>, MidiError> {
    let mut r = Reader { b: data, i: 0 };
    let mut tick = 0u64;
    let mut running: Option<u8> = None;
    let mut out = Vec::new();
    while r.i < data.len() {
        tick += r.vlq()?;
        let mut status = r.u8()?;
        let first_data;
        if status < 0x80 {
            first_data = Some(status);
            status = running.ok_or_else(|| MidiError("running status without status".into()))?;
        } else {
            first_data = None;
        }
        let kind = match status {
            0xff => {
                let t = r.u8()?;
                let len = r.vlq()? as usize;
                let d = r.bytes(len)?;
                match t {
                    0x51 if len >= 3 => Kind::Tempo(((d[0] as u32) << 16) | ((d[1] as u32) << 8) | d[2] as u32),
                    0x03 => Kind::TrackName(latin1(d)),
                    0x2f => {
                        out.push(Event { tick, kind: Kind::Other });
                        break;
                    }
                    _ => Kind::Other,
                }
            }
            0xf0 | 0xf7 => {
                let len = r.vlq()? as usize;
                r.bytes(len)?;
                Kind::Other
            }
            s if s >= 0x80 && s < 0xf0 => {
                running = Some(s);
                let ch = s & 0x0f;
                let next = |r: &mut Reader, fd: &mut Option<u8>| -> Result<u8, MidiError> {
                    match fd.take() {
                        Some(v) => Ok(v),
                        None => r.u8(),
                    }
                };
                let mut fd = first_data;
                match s & 0xf0 {
                    0x80 => {
                        let note = next(&mut r, &mut fd)?;
                        let _vel = next(&mut r, &mut fd)?;
                        Kind::NoteOff { ch, note }
                    }
                    0x90 => {
                        let note = next(&mut r, &mut fd)?;
                        let vel = next(&mut r, &mut fd)?;
                        Kind::NoteOn { ch, note, vel }
                    }
                    0xa0 | 0xb0 | 0xe0 => {
                        next(&mut r, &mut fd)?;
                        next(&mut r, &mut fd)?;
                        Kind::Other
                    }
                    0xc0 => {
                        let program = next(&mut r, &mut fd)?;
                        Kind::Program { ch, program }
                    }
                    _ => {
                        next(&mut r, &mut fd)?;
                        Kind::Other
                    }
                }
            }
            _ => {
                // System common/realtime messages carry no data we use.
                Kind::Other
            }
        };
        out.push(Event { tick, kind });
    }
    Ok(out)
}

impl MidiFile {
    pub fn parse(bytes: &[u8]) -> Result<MidiFile, MidiError> {
        let mut r = Reader { b: bytes, i: 0 };
        let mut tracks: Vec<Vec<Event>> = Vec::new();
        let mut resolution = 0u32;
        while r.i + 8 <= bytes.len() {
            let id = r.bytes(4)?;
            let len = r.u32()? as usize;
            let body = r.bytes(len.min(bytes.len() - r.i))?;
            if id == b"MThd" {
                let mut h = Reader { b: body, i: 0 };
                let _format = h.u16()?;
                let _ntracks = h.u16()?;
                let div = h.u16()?;
                if div & 0x8000 != 0 {
                    return Err(MidiError("SMPTE time division is not supported".into()));
                }
                resolution = div as u32;
            } else if id == b"MTrk" {
                tracks.push(parse_track(body)?);
            }
        }
        if resolution == 0 || tracks.is_empty() {
            return Err(MidiError("no header or tracks".into()));
        }
        Ok(Self::from_tracks(resolution, &tracks))
    }

    fn from_tracks(resolution: u32, tracks: &[Vec<Event>]) -> MidiFile {
        let res = resolution as f64;
        // Tempo map (track 0 only).
        let mut scales: Vec<(u64, f64)> = vec![(0, 60.0 / (120.0 * res))];
        for e in &tracks[0] {
            if let Kind::Tempo(t) = e.kind {
                if e.tick == 0 {
                    let bpm = 6e7 / t as f64;
                    scales = vec![(0, 60.0 / (bpm * res))];
                } else {
                    let last = scales.last().unwrap().1;
                    let ts = 60.0 / ((6e7 / t as f64) * res);
                    if ts != last {
                        scales.push((e.tick, ts));
                    }
                }
            }
        }
        // Segment start times, as the reference's tick->time table builds them.
        let mut seg_start_time = vec![0.0f64; scales.len()];
        let mut last_end = 0.0f64;
        for i in 0..scales.len().saturating_sub(1) {
            let (s, sc) = scales[i];
            let (e, _) = scales[i + 1];
            seg_start_time[i] = last_end;
            last_end = last_end + sc * ((e - s) as f64);
        }
        if let Some(l) = seg_start_time.last_mut() {
            *l = last_end;
        }
        let time_of = |tick: u64| -> f64 {
            // the last segment whose start <= tick; boundary ticks belong to the later segment
            let mut k = 0;
            for (i, (s, _)) in scales.iter().enumerate() {
                if *s <= tick {
                    k = i;
                }
            }
            let (s, sc) = scales[k];
            seg_start_time[k] + sc * ((tick - s) as f64)
        };

        let mut instruments: Vec<MidiInstrument> = Vec::new();
        let mut index: HashMap<(i32, u8, usize), usize> = HashMap::new();
        let mut track_names: HashMap<usize, String> = HashMap::new();
        for (ti, track) in tracks.iter().enumerate() {
            let mut last_on: HashMap<(u8, u8), Vec<(u64, u8)>> = HashMap::new();
            let mut current = [0i32; 16];
            for e in track {
                match &e.kind {
                    Kind::TrackName(n) => {
                        track_names.insert(ti, n.clone());
                    }
                    Kind::Program { ch, program } => current[*ch as usize] = *program as i32,
                    Kind::NoteOn { ch, note, vel } if *vel > 0 => {
                        last_on.entry((*ch, *note)).or_default().push((e.tick, *vel));
                    }
                    Kind::NoteOn { ch, note, .. } | Kind::NoteOff { ch, note } => {
                        let key = (*ch, *note);
                        if let Some(open) = last_on.get(&key).cloned() {
                            let end_tick = e.tick;
                            let close: Vec<_> = open.iter().filter(|(s, _)| *s != end_tick).cloned().collect();
                            let keep: Vec<_> = open.iter().filter(|(s, _)| *s == end_tick).cloned().collect();
                            for (s, v) in &close {
                                let program = current[*ch as usize];
                                let k = (program, *ch, ti);
                                let idx = *index.entry(k).or_insert_with(|| {
                                    instruments.push(MidiInstrument {
                                        program,
                                        is_drum: *ch == 9,
                                        name: track_names.get(&ti).cloned().unwrap_or_default(),
                                        notes: Vec::new(),
                                    });
                                    instruments.len() - 1
                                });
                                instruments[idx].notes.push(MidiNote {
                                    pitch: *note as i32,
                                    velocity: *v as i32,
                                    start: time_of(*s),
                                    end: time_of(end_tick),
                                });
                            }
                            if !close.is_empty() && !keep.is_empty() {
                                last_on.insert(key, keep);
                            } else {
                                last_on.remove(&key);
                            }
                        }
                    }
                    _ => {}
                }
            }
        }
        MidiFile { resolution, instruments }
    }
}

/// A note as a plain record: what the reference passes around as a dict.
#[derive(Debug, Clone, PartialEq)]
pub struct RawNote {
    pub pitch: i32,
    pub onset: f64,
    pub offset: f64,
    pub confidence: Option<f64>,
    /// A pitch-change onset from the contour (onsets.rs): the solo line keeps it down to 30 ms.
    pub split: bool,
    /// A trill (trills.rs): semitones up to the auxiliary; 0 = none.
    pub trill: i32,
}

impl RawNote {
    pub fn new(pitch: i32, onset: f64, offset: f64) -> Self {
        RawNote { pitch, onset, offset, confidence: None, split: false, trill: 0 }
    }
}

impl MidiFile {
    /// Notes of all pitched (non-drum) instruments, in instrument order.
    pub fn pitched(&self) -> Vec<RawNote> {
        self.instruments.iter().filter(|i| !i.is_drum).flat_map(|i| i.notes.iter()).map(|n| RawNote::new(n.pitch, n.start, n.end)).collect()
    }

    /// Notes of all drum instruments, in instrument order.
    pub fn drums(&self) -> Vec<RawNote> {
        self.instruments.iter().filter(|i| i.is_drum).flat_map(|i| i.notes.iter()).map(|n| RawNote::new(n.pitch, n.start, n.end)).collect()
    }
}
