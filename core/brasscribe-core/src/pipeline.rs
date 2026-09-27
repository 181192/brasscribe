//! End-to-end entry points, mirroring the reference scripts:
//!
//! * [`arrange_layers_song`]: layer transcriptions + beats -> solo-with-band score
//! * [`arrange_song`]: melody/support/bass/harmony transcriptions + beats -> minimal band score
//! * [`lead_sheet`]: melody/support/bass transcriptions + beats -> two-stave concert lead sheet
//! * [`composition_from_reference`]: notated reference notes -> Composition (arranger benchmark)
//!
//! Inputs are in-memory (parsed MIDI files, beat tables); nothing here touches the file system.

use std::collections::{HashMap, HashSet};

use serde_json::Value;

use crate::arranger::{arrange, Arrangement};
use crate::beats::clean_beats_gated;
use crate::consensus::{cluster, consensus, Sources};
use crate::durations::{apply_written_with, contour_offsets, Contour, WriteOptions, SEPARATED_STEM};
use crate::dynamics::{layer_dynamics, Bar};
use crate::energy::{gate, Audio, Envelope, GATE_DB};
use crate::freetime::{clip_to_regions, mark_fermatas, plan_free_time, unstable_runs, FreeTimePlan};
use crate::harmony::{harmony_slots, slots_to_notes};
use crate::keys::{key_plan, CHANGE_PENALTY};
use crate::lines::{line, MIN_DUR};
use crate::midi::{MidiFile, RawNote};
use crate::model::{Composition, Dynamic, KeySig, Meter, Note, Section, Voice, VoiceRole, TICKS_PER_BEAT};
use crate::musicxml::{band_score, write_score, PartSpec, ScoreSpec};
use crate::notation::score::write_score_with_parts;
use crate::py;
use crate::quantize::{choose_level, fill_gaps, quantize, quantize_coarse, BeatMap, QNote};
use crate::separation::{check_stem, FAIL_DB as SEPARATION_FAIL_DB};
use crate::spelling::key_of;
use crate::structure::{bar_features, letters, section_starts};

/// A beat table as written by the beat tracker: time in seconds and position in the bar (1 = downbeat).
#[derive(Debug, Clone, PartialEq)]
pub struct Beats {
    pub times: Vec<f64>,
    pub positions: Vec<i64>,
}

impl Beats {
    /// Parse whitespace-separated rows `time position` (as `np.loadtxt` reads them).
    pub fn parse(text: &str) -> Result<Beats, String> {
        let mut times = Vec::new();
        let mut positions = Vec::new();
        for (i, raw) in text.lines().enumerate() {
            let l = raw.split('#').next().unwrap_or("").trim();
            if l.is_empty() {
                continue;
            }
            let cols: Vec<&str> = l.split_whitespace().collect();
            if cols.len() < 2 {
                return Err(format!("beats line {}: expected two columns", i + 1));
            }
            let t: f64 = cols[0].parse().map_err(|e| format!("beats line {}: {e}", i + 1))?;
            let p: f64 = cols[1].parse().map_err(|e| format!("beats line {}: {e}", i + 1))?;
            times.push(t);
            positions.push(p.trunc() as i64);
        }
        if times.len() < 2 {
            return Err("need at least two beats".into());
        }
        Ok(Beats { times, positions })
    }

    /// Most common distance between downbeats (first seen wins a tie).
    pub fn beats_per_bar(&self) -> Result<i64, String> {
        let downs: Vec<usize> = self.positions.iter().enumerate().filter(|(_, &p)| p == 1).map(|(i, _)| i).collect();
        let mut counts: Vec<(i64, usize)> = Vec::new();
        for w in downs.windows(2) {
            let d = (w[1] - w[0]) as i64;
            match counts.iter_mut().find(|(k, _)| *k == d) {
                Some(e) => e.1 += 1,
                None => counts.push((d, 1)),
            }
        }
        let mut best: Option<(i64, usize)> = None;
        for &(k, c) in &counts {
            if best.map_or(true, |(_, bc)| c > bc) {
                best = Some((k, c));
            }
        }
        best.map(|b| b.0).ok_or_else(|| "fewer than two downbeats in the beat table".to_string())
    }

    /// Index of the first downbeat (0 when there is none).
    pub fn first_downbeat(&self) -> i64 {
        self.positions.iter().position(|&p| p == 1).unwrap_or(0) as i64
    }
}

fn to_notes(qnotes: &[QNote], pickup: i64, source: &str) -> Vec<Note> {
    qnotes
        .iter()
        .map(|q| Note::new(q.pitch, q.start - pickup, q.end - q.start, q.confidence, vec![source.to_string()]).with_times(Some(q.onset_s), Some(q.offset_s)))
        .collect()
}

/// Metrical level and bar origin shared by the song entry points: fix the level
/// once from all onsets, then put tick 0 on the downbeat at or before the earliest note.
fn grid(beats: &Beats, onsets: &[f64]) -> Result<(Vec<f64>, i64, i64), String> {
    let mut bpb = beats.beats_per_bar()?;
    let mut first_down = beats.first_downbeat();
    let times = choose_level(&beats.times, onsets);
    if times.len() != beats.times.len() {
        bpb *= 2;
        first_down *= 2;
    }
    let min_on = onsets.iter().cloned().fold(f64::INFINITY, f64::min);
    let earliest = BeatMap::new(&times)?.to_beats(min_on);
    while first_down as f64 > earliest + 1e-6 {
        first_down -= bpb;
    }
    Ok((times, bpb, first_down))
}

fn tonal_key(notes: &[&Note]) -> i32 {
    let du: Vec<f64> = notes.iter().map(|n| n.dur as f64 / TICKS_PER_BEAT as f64).collect();
    let ps: Vec<i32> = notes.iter().map(|n| n.pitch).collect();
    key_of(&du, &ps).1
}

#[derive(Debug, Clone)]
pub struct BandResult {
    pub composition: Composition,
    pub arrangement: Arrangement,
    pub musicxml: String,
    /// Individual parts: (file name, MusicXML), for the layered arrangement.
    pub parts: Vec<(String, String)>,
    /// `separation-check.json` text, when the layer audio was given.
    pub separation_check: Option<String>,
}

/// Transcribed layers of one recording, with the layers' audio where available.
#[derive(Debug, Clone)]
pub struct Layers {
    pub solo_sw: MidiFile,
    pub solo_mus: MidiFile,
    pub solo_bp: MidiFile,
    pub bass: MidiFile,
    pub orchestra: MidiFile,
    pub drums: MidiFile,
    pub solo_audio: Option<Audio>,
    pub bass_audio: Option<Audio>,
    pub drums_audio: Option<Audio>,
    pub orchestra_audio: Option<Audio>,
}

/// (hits, lines): short notes sharing an attack with >= 2 others are chordal hits.
pub fn split_orchestra(notes: Vec<Note>) -> (Vec<Note>, Vec<Note>) {
    let mut by_start: HashMap<i64, usize> = HashMap::new();
    for n in &notes {
        *by_start.entry(n.start).or_default() += 1;
    }
    let (hits, lines): (Vec<Note>, Vec<Note>) = notes.into_iter().partition(|n| by_start[&n.start] >= 3 && n.dur <= TICKS_PER_BEAT);
    (hits, lines)
}

/// Options of the solo-with-band arrangement.
#[derive(Debug, Clone, Default)]
pub struct LayersOptions {
    /// Frame-level SwiftF0 contour of the solo stem: where sustained solo notes really end.
    pub solo_contour: Option<Contour>,
    /// Keep the beat grid through free-time passages.
    pub no_free_time: bool,
    /// Notate free-time passages at this BPM instead of estimating one.
    pub free_tempo: Option<f64>,
    /// Keep layer notes where the layer's audio is silent.
    pub no_gate: bool,
    /// Use the tracked beats as they are.
    pub no_beat_cleanup: bool,
    /// One key signature for the whole piece.
    pub single_key: bool,
    /// "band" (= "full", the 18-part contest band) or "minimal" (8 parts); empty = band.
    pub lineup: String,
    /// "faithful" (default when empty), "standard" or "easier".
    pub difficulty: String,
    /// Target concert key of the first key signature: Bb, F#, Am or FIFTHS[:MODE].
    pub key: Option<String>,
    /// Transpose the whole arrangement by this many semitones (instead of `key`).
    pub transpose: Option<i32>,
}

/// Detached notes are written as (staccato) 8ths in band parts, not 16ths and rests.
pub const PART_HOLD_WITHIN: i64 = TICKS_PER_BEAT / 2;

/// One voice with written durations from its performed lengths (held vs detached, staccato).
fn written_line(qnotes: Vec<QNote>, times: &[f64], pickup: i64, source: &str) -> Result<Vec<Note>, String> {
    let bm = BeatMap::new(times)?;
    let o = WriteOptions { hold_within: PART_HOLD_WITHIN, min_detached: PART_HOLD_WITHIN };
    Ok(apply_written_with(qnotes, Some(&bm), o)
        .into_iter()
        .map(|(q, w)| {
            let mut n = to_notes(std::slice::from_ref(&q), pickup, source).remove(0);
            n.performed_dur = Some(py::round_int(w.performed));
            if w.staccato {
                n.articulations.push("staccato".into());
            }
            n
        })
        .collect())
}

/// Solo stem against the mix of all layers (the orchestra is the residual, so they sum to it).
fn separation(l: &Layers) -> Option<String> {
    let (s, b, d, o) = (l.solo_audio.as_ref()?, l.bass_audio.as_ref()?, l.drums_audio.as_ref()?, l.orchestra_audio.as_ref()?);
    let all = [s, b, d, o];
    let n_min = all.iter().map(|a| a.frames()).min().unwrap();
    let ch = s.channels;
    if all.iter().any(|a| a.channels != ch) {
        return None;
    }
    let take = |a: &Audio| Audio { samples: a.samples[..n_min * ch].to_vec(), channels: ch, sample_rate: a.sample_rate };
    let mut mix = take(s);
    for a in [b, d, o] {
        for (m, v) in mix.samples.iter_mut().zip(a.samples[..n_min * ch].iter()) {
            *m += *v;
        }
    }
    let c = check_stem(&take(s).mono(), &mix.mono(), s.sample_rate, SEPARATION_FAIL_DB);
    Some(c.to_json_string())
}

/// Solo-with-band arrangement from textural layers.
///
/// Order: energy gate of the layer notes, separation check, gated beat cleanup,
/// metrical level, free time, written durations (solo contour), key plan,
/// dynamics, rehearsal marks, clipping and fermatas, arrangement, score, parts.
///
/// The solo is SwiftF0's line (notes without SwiftF0 are dropped); each note's
/// confidence is the calibrated probability that it is right (confidence.rs).
/// The orchestra residual is split by what the notes do: short notes attacked
/// together with two or more others are brass-choir hits, the rest strings.
pub fn arrange_layers_song(layers: &Layers, beats: &Beats, title: &str, opts: &LayersOptions) -> Result<BandResult, String> {
    let difficulty = if opts.difficulty.is_empty() { "faithful" } else { opts.difficulty.as_str() };
    if !crate::difficulty::MODES.contains(&difficulty) {
        return Err(format!("difficulty must be one of {:?}", crate::difficulty::MODES));
    }
    let lineup_name = crate::instruments::lineup_key(&opts.lineup)?;
    if opts.key.is_some() && opts.transpose.is_some() {
        return Err("give a key or a transposition, not both".into());
    }
    let solo_mus = layers.solo_mus.pitched();
    let solo_bp = layers.solo_bp.pitched();
    let mut bass_raw = layers.bass.pitched();
    let mut orch_raw = layers.orchestra.pitched();
    let mut drum_raw = layers.drums.drums();
    let solo_sw = layers.solo_sw.pitched();
    if !opts.no_gate {
        // Drop notes a layer's transcriber found where that layer is (nearly) silent.
        for (raw, audio) in [(&mut bass_raw, &layers.bass_audio), (&mut orch_raw, &layers.orchestra_audio), (&mut drum_raw, &layers.drums_audio)] {
            if let Some(a) = audio {
                let (kept, _) = gate(std::mem::take(raw), &Envelope::of(a), GATE_DB);
                *raw = kept;
            }
        }
    }
    let separation_check = separation(layers);

    // Most common gap between labelled downbeats (1 when there are none).
    let label_bpb = beats.beats_per_bar().ok();
    let mut bpb = label_bpb.unwrap_or(1);
    let onsets: Vec<f64> = solo_sw.iter().chain(bass_raw.iter()).chain(orch_raw.iter()).map(|n| n.onset).collect();
    let mut down: Vec<bool> = beats.positions.iter().map(|&p| p == 1).collect();
    let mut raw_times = beats.times.clone();
    let mut first_down;
    if !opts.no_beat_cleanup {
        // Restore missed and remove inserted beats (outside free time); the bar phase
        // follows the majority of the tracker's downbeat labels.
        let cb = clean_beats_gated(&raw_times, &down, bpb, &unstable_runs(&raw_times), Some(&onsets));
        first_down = cb.phase(bpb);
        raw_times = cb.times;
        down = cb.downbeat;
    } else {
        first_down = down.iter().position(|&d| d).unwrap_or(0) as i64;
    }
    let mut times = choose_level(&raw_times, &onsets);
    let mut doubled = times.len() != raw_times.len();
    if doubled {
        bpb *= 2;
        first_down *= 2;
    }
    if label_bpb.is_none_or(|g| g < 2) {
        // The tracker's downbeat labels give no bars (one instrument labelled a
        // downbeat on most beats): infer the meter and bar phase on the final
        // grid from the labels' periodicity and the solo's note accents, unless
        // the evidence is too weak (then the grid's own bars stay).
        let solo_notes = if solo_sw.is_empty() { layers.solo_mus.pitched() } else { solo_sw.clone() };
        let grid_pos = crate::beats::labels_on(&times, &beats.times, &beats.positions, 0);
        let grid_down: Vec<bool> = grid_pos.iter().map(|&p| p == 1).collect();
        let m = crate::beats::solo_meter(
            &times,
            &grid_down,
            &grid_pos,
            bpb,
            first_down,
            &solo_notes.iter().map(|n| n.onset).collect::<Vec<_>>(),
            &solo_notes.iter().map(|n| n.offset - n.onset).collect::<Vec<_>>(),
        );
        if !m.from_labels {
            times = m.times.clone().unwrap_or(times);
            bpb = m.beats_per_bar;
            first_down = m.first_downbeat;
            down = (0..times.len() as i64).map(|i| (i - first_down).rem_euclid(bpb) == 0).collect();
            doubled = false; // the labels are replaced by the inferred bars
        }
    }
    let mut plan: Option<FreeTimePlan> = None;
    if !opts.no_free_time {
        let sw_onsets: Vec<f64> = solo_sw.iter().map(|n| n.onset).collect();
        let p = plan_free_time(&times, &onsets, bpb, first_down, if doubled { None } else { Some(&down) }, opts.free_tempo, Some(&sw_onsets));
        times = p.beat_times.clone();
        first_down = p.first_downbeat;
        plan = Some(p);
    }
    let coarse: Option<Vec<(f64, f64)>> = plan.as_ref().map(|p| p.beat_ranges());
    let coarse = coarse.as_deref();
    let min_on = onsets.iter().cloned().fold(f64::INFINITY, f64::min);
    let earliest = BeatMap::new(&times)?.to_beats(min_on);
    while first_down as f64 > earliest + 1e-6 {
        first_down -= bpb;
    }
    let pickup = first_down * TICKS_PER_BEAT;
    let half = TICKS_PER_BEAT / 2;

    let votes: Sources = vec![
        ("sw".into(), line(&solo_sw, 52, 88, true, MIN_DUR)),
        ("mus".into(), line(&solo_mus, 52, 88, true, MIN_DUR)),
        ("bp".into(), line(&solo_bp, 52, 88, true, MIN_DUR)),
    ];
    // Basic Pitch standing in for MuScriptor (the solo path) is one vote for the
    // confidence, not two; the clustering is unchanged.
    let key_set = |v: &[RawNote]| {
        let mut k: Vec<(f64, i32)> = v.iter().map(|n| (n.onset, n.pitch)).collect();
        k.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap().then(a.1.cmp(&b.1)));
        k
    };
    let mus_is_bp = key_set(&solo_mus) == key_set(&solo_bp);
    let separated = layers.bass_audio.is_some() || layers.drums_audio.is_some() || layers.orchestra_audio.is_some();
    let model = crate::confidence::Model::load();
    let cand: Vec<RawNote> = cluster(&votes)
        .into_iter()
        .filter(|c| c.sources.contains("sw"))
        .map(|c| {
            let (on, off) = (c.median_onset(), c.median_offset());
            let mut src = c.sources.clone();
            if mus_is_bp {
                src.remove("mus");
            }
            let sup = crate::confidence::support(opts.solo_contour.as_ref(), on, c.pitch);
            let x = crate::confidence::features(&src, off - on, sup, separated);
            RawNote { pitch: c.pitch, onset: on, offset: off, confidence: Some(py::py_round(crate::confidence::p_correct(&x, &model), 3)) }
        })
        .collect();
    let mut solo_line = line(&cand, 52, 88, true, MIN_DUR);
    if let Some(c) = &opts.solo_contour {
        // Where the note really ends: the SwiftF0 contour, or the longest confirming model offset.
        let keys: Vec<(f64, i32)> = solo_line.iter().map(|n| (n.onset, n.pitch)).collect();
        let ends = contour_offsets(c, &keys, SEPARATED_STEM);
        for (n, e) in solo_line.iter_mut().zip(ends) {
            if e > n.offset {
                n.offset = e;
            }
        }
    }
    let mut solo = written_line(quantize_coarse(&solo_line, &times, true, false, coarse), &times, pickup, "solo")?;
    let mut bass = written_line(quantize_coarse(&line(&bass_raw, 24, 55, false, MIN_DUR), &times, true, false, coarse), &times, pickup, "bass")?;

    let solo_keys: HashSet<(u64, i32)> = solo_line.iter().map(|n| (py::py_round(n.onset, 1).to_bits(), n.pitch)).collect();
    let orch: Vec<RawNote> = orch_raw
        .iter()
        // Solo onsets are Python floats (medians), orchestra onsets NumPy scalars: they round differently.
        .filter(|n| 36 <= n.pitch && n.pitch <= 88 && !solo_keys.contains(&(py::np_round(n.onset, 1).to_bits(), n.pitch)))
        .cloned()
        .collect();
    let orch_q: Vec<Note> =
        to_notes(&quantize_coarse(&orch, &times, false, false, coarse), pickup, "orchestra").into_iter().filter(|n| n.start >= 0).collect();
    let (mut hits, mut lines) = split_orchestra(orch_q);

    let dq = quantize_coarse(&drum_raw, &times, false, false, coarse);
    let mut starts: Vec<i64> = dq.iter().map(|q| q.start).collect();
    starts.sort();
    starts.dedup();
    let nxt: HashMap<i64, i64> = starts.windows(2).map(|w| (w[0], w[1])).collect();
    let mut drums: Vec<Note> = dq
        .iter()
        .filter(|q| q.start - pickup >= 0)
        .map(|q| {
            let d = (nxt.get(&q.start).copied().unwrap_or(q.start + half) - q.start).min(TICKS_PER_BEAT);
            Note::new(q.pitch, q.start - pickup, d, 1.0, vec!["drums".into()])
        })
        .collect();

    let regions = plan.as_ref().map(|p| p.regions(first_down)).unwrap_or_default();
    for v in [&mut solo, &mut bass, &mut lines, &mut hits, &mut drums] {
        clip_to_regions(v, &regions);
    }
    mark_fermatas(&mut solo, &regions);

    let voice = |id: &str, role, notes: Vec<Note>, hint: &str, layer: &str| Voice {
        id: id.into(),
        role,
        notes,
        instrument_hint: Some(hint.into()),
        layer: Some(layer.into()),
    };
    let tonal: Vec<&Note> = solo.iter().chain(bass.iter()).chain(lines.iter()).collect();
    let fifths = tonal_key(&tonal);
    let bar_ticks = bpb * TICKS_PER_BEAT;
    let keys = if opts.single_key {
        vec![KeySig { tick: 0, fifths, mode: "major".into() }]
    } else {
        // Key changes where the music modulates (a change must pay for itself over several bars).
        let mut sl: Vec<Note> = solo.clone();
        sl.extend(lines.iter().cloned());
        let penalty = crate::difficulty::key_change_penalty(difficulty).unwrap_or(CHANGE_PENALTY);
        key_plan(&sl, bar_ticks, penalty, &bass).keys
    };
    let mut comp = Composition {
        title: title.into(),
        voices: vec![
            voice("solo", VoiceRole::Melody, solo.clone(), "trumpet/cornet", "solo"),
            voice("bass", VoiceRole::Bass, bass.clone(), "electric bass", "bass"),
            voice("strings", VoiceRole::Harmony, lines.clone(), "orchestra", "strings"),
            voice("brass", VoiceRole::Harmony, hits, "orchestra hits", "brass"),
            voice("drums", VoiceRole::Rhythm, drums, "drum kit", "drums"),
        ],
        meters: vec![Meter { tick: 0, beats: bpb, beat_unit: 4 }],
        keys,
        beat_times: times,
        first_downbeat: first_down,
        ticks_per_beat: TICKS_PER_BEAT,
        free_regions: regions,
        dynamics: Vec::new(),
        sections: Vec::new(),
        review: Vec::new(),
        arrangement: None,
    };
    // Dynamics per layer from its own loudness, per bar.
    let bm = BeatMap::new(&comp.beat_times)?;
    let n_bars = py::floordiv(comp.end_tick(), bar_ticks) + 1;
    let edges: Vec<f64> = (0..=n_bars).map(|k| bm.to_seconds((k * bpb + first_down) as f64)).collect();
    let bars: Vec<Bar> = (0..n_bars as usize).map(|k| (k as i64 * bar_ticks, edges[k], edges[k + 1])).collect();
    let envs: Vec<(&str, Envelope)> = [("solo", &layers.solo_audio), ("orchestra", &layers.orchestra_audio), ("bass", &layers.bass_audio), ("drums", &layers.drums_audio)]
        .into_iter()
        .filter_map(|(n, a)| a.as_ref().map(|a| (n, Envelope::of(a))))
        .collect();
    for (layer, wav) in [("solo", "solo"), ("strings", "orchestra"), ("brass", "orchestra"), ("bass", "bass"), ("drums", "drums")] {
        if let Some((_, env)) = envs.iter().find(|(n, _)| *n == wav) {
            comp.dynamics.extend(layer_dynamics(env, &bars).into_iter().map(|(t, m)| Dynamic { tick: t, layer: layer.into(), mark: m }));
        }
    }
    // Rehearsal letters where the layers' energy changes, and where free time ends.
    if !envs.is_empty() {
        let e: Vec<&Envelope> = envs.iter().map(|(_, e)| e).collect();
        let forced: Vec<i64> = comp.free_regions.iter().map(|r| py::floordiv(r.end, bar_ticks)).collect();
        let starts = section_starts(&bar_features(&e, &bars), &forced);
        comp.sections = starts.iter().zip(letters(starts.len())).map(|(b, l)| Section { tick: b * bar_ticks, label: l }).collect();
    }
    // Arrangement options: lineup, difficulty, transposition to a concert key.
    let shift = match (&opts.transpose, &opts.key) {
        (Some(t), _) => *t,
        (None, Some(k)) => crate::keys::semitones_to(&comp.keys[0], k)?,
        _ => 0,
    };
    if shift != 0 {
        comp = comp.transposed(shift);
    }
    if lineup_name != "band" || difficulty != "faithful" || shift != 0 {
        let mut a = serde_json::Map::new();
        a.insert("lineup".into(), lineup_name.into());
        a.insert("difficulty".into(), difficulty.into());
        a.insert("transpose_semitones".into(), shift.into());
        comp.arrangement = Some(serde_json::Value::Object(a));
    }
    // Review groups: neighbouring uncertain notes in one bar are one review item for the apps.
    let bar_ticks = bpb * TICKS_PER_BEAT;
    comp.review = comp
        .voices
        .iter()
        .filter(|v| v.layer.as_deref() != Some("drums"))
        .flat_map(|v| {
            let notes: Vec<(i64, i64, f64)> = v.notes.iter().map(|n| (n.start, n.end(), n.confidence)).collect();
            crate::confidence::review_groups(&notes, bar_ticks, model.mark_below(), model.very_below())
                .into_iter()
                .map(|g| crate::model::ReviewItem { voice: v.id.clone(), start: g.start, end: g.end, notes: g.notes, very: g.very })
                .collect::<Vec<_>>()
        })
        .collect();
    let lineup = crate::instruments::lineup_by_name(lineup_name)?;
    let arrangement = crate::arranger::arrange_layers_opts(&comp, lineup, &crate::arranger::LayersArrangeOptions { difficulty: difficulty.into(), ..Default::default() })?;
    let (musicxml, parts) = write_score_with_parts(&band_score(&arrangement, &comp));
    Ok(BandResult { composition: comp, arrangement, musicxml, parts, separation_check })
}

/// Arrange an existing Composition the way it was made: the layered arranger
/// when its voices carry layers (with the lineup and difficulty recorded in
/// `arrangement`), else the minimal arranger.
pub fn arrange_composition(comp: &Composition) -> Result<Arrangement, String> {
    if !comp.voices.iter().any(|v| v.layer.is_some()) {
        return Ok(arrange(comp));
    }
    let opt = |k: &str| comp.arrangement.as_ref().and_then(|a| a.get(k)).and_then(|v| v.as_str()).map(String::from);
    // Anything but a known lineup arranges for the band, as before lineups carried their roles.
    let lineup = crate::instruments::lineup_by_name(opt("lineup").as_deref().unwrap_or("band")).unwrap_or_else(|_| crate::instruments::brass_band());
    let difficulty = opt("difficulty").unwrap_or_else(|| "faithful".into());
    crate::arranger::arrange_layers_opts(comp, lineup, &crate::arranger::LayersArrangeOptions { difficulty, ..Default::default() })
}

#[derive(Debug, Clone)]
pub struct SongInputs {
    pub melody: MidiFile,
    pub melody_support: Option<MidiFile>,
    pub bass: MidiFile,
    pub harmony: Vec<MidiFile>,
}

fn melody_votes(melody: &MidiFile, support: Option<&MidiFile>) -> Vec<RawNote> {
    let mut sources: Sources = vec![("mus".into(), melody.pitched())];
    if let Some(s) = support {
        sources.push(("bp".into(), s.pitched()));
    }
    let (cand, _) = consensus(&sources, &[("mus", 0.6), ("bp", 0.4)], 0.5);
    cand.iter().map(|c| c.raw()).collect()
}

/// Minimal brass-band arrangement: melody (MuScriptor confirmed by Basic Pitch),
/// bass line, and the accompaniment reduced to a per-beat harmonic rhythm.
pub fn arrange_song(inp: &SongInputs, beats: &Beats, title: &str) -> Result<BandResult, String> {
    let mel_all = inp.melody.pitched();
    let bass_all = inp.bass.pitched();
    let harm_all: Vec<Vec<RawNote>> = inp.harmony.iter().map(|m| m.pitched()).collect();
    let all_onsets: Vec<f64> = mel_all.iter().chain(bass_all.iter()).chain(harm_all.iter().flatten()).map(|n| n.onset).collect();
    let (times, bpb, first_down) = grid(beats, &all_onsets)?;
    let pickup = first_down * TICKS_PER_BEAT;
    let half = TICKS_PER_BEAT / 2;

    let cand = melody_votes(&inp.melody, inp.melody_support.as_ref());
    let mel_raw = line(&cand, 52, 88, true, MIN_DUR);
    let melody = to_notes(&fill_gaps(quantize(&mel_raw, &times, true, false), half, 0.0), pickup, "melody");
    let bass = to_notes(&fill_gaps(quantize(&line(&bass_all, 28, 55, false, MIN_DUR), &times, true, false), half, 0.0), pickup, "bass");

    let mel_keys: HashSet<(u64, i32)> = mel_raw.iter().map(|n| (py::py_round(n.onset, 2).to_bits(), n.pitch)).collect();
    let acc: Vec<RawNote> = harm_all
        .iter()
        .flatten()
        .filter(|n| 40 <= n.pitch && n.pitch <= 84 && !mel_keys.contains(&(py::np_round(n.onset, 2).to_bits(), n.pitch)))
        .cloned()
        .collect();
    let acc_q = to_notes(&quantize(&acc, &times, false, false), pickup, "accompaniment");
    let end = melody.iter().chain(bass.iter()).chain(acc_q.iter()).map(|n| n.end()).max().ok_or("no notes")?;
    let harm = slots_to_notes(&harmony_slots(&acc_q, end, 4, 0.35), 0.8);

    let plain = |id: &str, role, notes: Vec<Note>| Voice { id: id.into(), role, notes, instrument_hint: None, layer: None };
    let tonal: Vec<&Note> = melody.iter().chain(bass.iter()).chain(harm.iter()).collect();
    let fifths = tonal_key(&tonal);
    let comp = Composition {
        title: title.into(),
        voices: vec![plain("melody", VoiceRole::Melody, melody.clone()), plain("bass", VoiceRole::Bass, bass.clone()), plain("harmony", VoiceRole::Harmony, harm.clone())],
        meters: vec![Meter { tick: 0, beats: bpb, beat_unit: 4 }],
        keys: vec![KeySig { tick: 0, fifths, mode: "major".into() }],
        beat_times: times,
        first_downbeat: first_down,
        ticks_per_beat: TICKS_PER_BEAT,
        free_regions: Vec::new(),
        dynamics: Vec::new(),
        sections: Vec::new(),
        review: Vec::new(),
        arrangement: None,
    };
    let arrangement = arrange(&comp);
    let musicxml = write_score(&band_score(&arrangement, &comp));
    Ok(BandResult { composition: comp, arrangement, musicxml, parts: Vec::new(), separation_check: None })
}

/// Draft lead sheet: melody + bass lines as concert-pitch staves, first downbeat at bar 1.
pub fn lead_sheet(melody: &MidiFile, support: Option<&MidiFile>, bass: &MidiFile, beats: &Beats, title: &str) -> Result<String, String> {
    let bpb = beats.beats_per_bar()?;
    let diffs: Vec<f64> = beats.times.windows(2).map(|w| w[1] - w[0]).collect();
    let bpm = 60.0 / py::median(&diffs);
    let pickup = beats.first_downbeat() * TICKS_PER_BEAT;
    let half = TICKS_PER_BEAT / 2;
    let cand = melody_votes(melody, support);
    let mel = fill_gaps(quantize(&line(&cand, 52, 86, true, MIN_DUR), &beats.times, true, true), half, 0.0);
    let bas = fill_gaps(quantize(&line(&bass.pitched(), 28, 55, false, MIN_DUR), &beats.times, true, true), half, 0.0);
    let spec = ScoreSpec {
        parts: vec![PartSpec::concert("Melody", mel, "treble"), PartSpec::concert("Bass", bas, "bass")],
        beats_per_bar: bpb,
        bpm,
        title: title.into(),
        pickup_ticks: pickup,
        low_confidence: 0.7,
        very_below: crate::notation::score::VERY_UNCERTAIN,
        key_fifths: None,
        sounds: Vec::new(),
        free_spans: Vec::new(),
        key_changes: Vec::new(),
        rehearsal: Vec::new(),
        encoding_date: String::new(),
    };
    Ok(write_score(&spec))
}

/// Reference notes with notated positions -> Composition (SATB or numbered parts).
pub fn composition_from_reference(reference: &Value, title: &str) -> Result<Composition, String> {
    let notes = match reference {
        Value::Object(m) => m.get("notes").and_then(|v| v.as_array()).ok_or("reference has no notes")?,
        Value::Array(a) => a,
        _ => return Err("reference must be an object or array".into()),
    };
    let refs: Vec<&serde_json::Map<String, Value>> = notes.iter().filter_map(|v| v.as_object()).filter(|o| o.contains_key("quarter")).collect();
    let f = |o: &serde_json::Map<String, Value>, k: &str| o.get(k).and_then(|v| v.as_f64()).unwrap_or(0.0);
    let mut names: Vec<String> = refs.iter().filter_map(|o| o.get("part").and_then(|v| v.as_str()).map(String::from)).collect();
    names.sort();
    names.dedup();
    let roles: Vec<(String, VoiceRole)> = if names.len() == 4 && ["S", "A", "T", "B"].iter().all(|p| names.iter().any(|n| n == p)) {
        vec![("S".into(), VoiceRole::Melody), ("A".into(), VoiceRole::Harmony), ("T".into(), VoiceRole::Harmony), ("B".into(), VoiceRole::Bass)]
    } else {
        let mut ordered = names.clone();
        let num = |p: &String| p.split('-').next().and_then(|x| x.parse::<i64>().ok()).unwrap_or(0);
        ordered.sort_by_key(num);
        let n = ordered.len();
        ordered
            .into_iter()
            .enumerate()
            .map(|(i, p)| {
                let role = if i + 1 == n { VoiceRole::Bass } else if i == 0 { VoiceRole::Melody } else { VoiceRole::Harmony };
                (p, role)
            })
            .collect()
    };
    let mut voices = Vec::new();
    for (part, role) in roles {
        let mut vn: Vec<Note> = refs
            .iter()
            .filter(|o| o.get("part").and_then(|v| v.as_str()) == Some(part.as_str()))
            .map(|o| {
                let start = py::round_int(f(o, "quarter") * TICKS_PER_BEAT as f64);
                let dur = py::round_int(f(o, "dur_quarter") * TICKS_PER_BEAT as f64).max(1);
                Note::new(o.get("pitch").and_then(|v| v.as_i64()).unwrap_or(0) as i32, start, dur, 1.0, vec!["reference".into()])
                    .with_times(Some(f(o, "onset")), Some(f(o, "offset")))
            })
            .collect();
        vn.sort_by_key(|n| n.start);
        voices.push(Voice { id: part.clone(), role, notes: vn, instrument_hint: Some(part.clone()), layer: None });
    }
    let ts = refs.iter().find_map(|o| o.get("time_sig").and_then(|v| v.as_str()).filter(|s| !s.is_empty()).map(String::from));
    let beats = ts.and_then(|t| t.split('/').next().and_then(|x| x.trim().parse::<i64>().ok())).unwrap_or(4);
    let all: Vec<&Note> = voices.iter().flat_map(|v| v.notes.iter()).collect();
    let fifths = tonal_key(&all);
    Ok(Composition {
        title: title.into(),
        voices,
        meters: vec![Meter { tick: 0, beats, beat_unit: 4 }],
        keys: vec![KeySig { tick: 0, fifths, mode: "major".into() }],
        beat_times: Vec::new(),
        first_downbeat: 0,
        ticks_per_beat: TICKS_PER_BEAT,
        free_regions: Vec::new(),
        dynamics: Vec::new(),
        sections: Vec::new(),
        review: Vec::new(),
        arrangement: None,
    })
}

/// Arranger benchmark path: reference -> Composition -> minimal band score.
pub fn arrange_reference(reference: &Value, title: &str) -> Result<BandResult, String> {
    let comp = composition_from_reference(reference, title)?;
    let arrangement = arrange(&comp);
    let musicxml = write_score(&band_score(&arrangement, &comp));
    Ok(BandResult { composition: comp, arrangement, musicxml, parts: Vec::new(), separation_check: None })
}

/// Reference notes (with "quarter") quantized on a beat table, as rows for comparison.
pub fn quantize_reference(reference: &Value, beats: &Beats) -> Vec<QNote> {
    let notes = match reference {
        Value::Object(m) => m.get("notes").and_then(|v| v.as_array()).cloned().unwrap_or_default(),
        Value::Array(a) => a.clone(),
        _ => Vec::new(),
    };
    let raw: Vec<RawNote> = notes
        .iter()
        .filter_map(|v| v.as_object())
        .filter(|o| o.contains_key("quarter"))
        .map(|o| RawNote {
            pitch: o.get("pitch").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
            onset: o.get("onset").and_then(|v| v.as_f64()).unwrap_or(0.0),
            offset: o.get("offset").and_then(|v| v.as_f64()).unwrap_or(0.0),
            confidence: o.get("confidence").and_then(|v| v.as_f64()),
        })
        .collect();
    quantize(&raw, &beats.times, false, true)
}
