//! `brasscribe-core`: file-based entry points of the Rust core, mirroring the
//! Python reference scripts so the two can be run on identical inputs.
//!
//! ```text
//! brasscribe-core arrange-layers --layers DIR --beats FILE --out DIR [--title T] [--solo-contour NPZ] [--no-free-time] [--free-tempo BPM]
//!                               [--no-gate] [--no-beat-cleanup] [--single-key] [--lineup band|full|minimal|quartet]
//!                               [--difficulty faithful|standard|easier] [--trills] [--key KEY | --transpose N]
//!                               [--seat SEAT] [--reads treble|bass] [--lead lineup|seat] [--lang en|nb] [--kit band|pop]
//! brasscribe-core arrange-song --beats FILE --melody MID [--melody-support MID] --bass MID --harmony MID... --out DIR [--title T]
//!                               [--lineup minimal|quartet] [--seat SEAT] [--reads treble|bass] [--lead lineup|seat] [--kit band|pop]
//! brasscribe-core lead-sheet --beats FILE --melody MID [--melody-support MID] --bass MID --out FILE [--title T]
//! brasscribe-core arrange-reference --reference JSON --out DIR [--title T] [--lineup minimal|quartet]
//! brasscribe-core quantize --reference JSON --beats FILE --out FILE
//! brasscribe-core musicxml --composition JSON --out FILE      (arrange an existing composition.json)
//! brasscribe-core meter --beats FILE --notes JSON --out FILE     (beats per bar and bar phase; notes [{onset, offset}])
//! brasscribe-core humanize --notes JSON --part P --player K [--seed S] [--composition JSON] [--timing score|performed] --out FILE
//! brasscribe-core talking-score --musicxml FILE [--composition JSON] [--json FILE] [--json-utf8 FILE] [--text FILE] [--html FILE]
//!                               [--lang en|nb] [--verbosity brief|standard|full] [--pitch-mode written|concert] [--octave-style scientific|helmholtz]
//! brasscribe-core fret --request JSON --out FILE     (a string and fret for every note: target-fretted's JSON request and response)
//! ```

use std::collections::HashMap;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use brasscribe_core::durations::Contour;
use brasscribe_core::energy::Audio;
use brasscribe_core::midi::MidiFile;
use brasscribe_core::model::Composition;
use brasscribe_core::musicxml::{band_score, write_score};
use brasscribe_core::pipeline::{self, Beats, Layers, LayersOptions, SongInputs};
use serde_json::{json, Value};

type R<T> = Result<T, String>;

struct Args {
    flags: HashMap<String, Vec<String>>,
}

impl Args {
    fn parse(argv: &[String]) -> Args {
        let mut flags: HashMap<String, Vec<String>> = HashMap::new();
        let mut key: Option<String> = None;
        for a in argv {
            if let Some(k) = a.strip_prefix("--") {
                flags.entry(k.to_string()).or_default();
                key = Some(k.to_string());
            } else if let Some(k) = &key {
                flags.get_mut(k).unwrap().push(a.clone());
            }
        }
        Args { flags }
    }
    fn one(&self, k: &str) -> R<String> {
        self.opt(k).ok_or_else(|| format!("missing --{k}"))
    }
    fn opt(&self, k: &str) -> Option<String> {
        self.flags.get(k).and_then(|v| v.first().cloned())
    }
    fn many(&self, k: &str) -> Vec<String> {
        self.flags.get(k).cloned().unwrap_or_default()
    }
    fn has(&self, k: &str) -> bool {
        self.flags.contains_key(k)
    }
}

fn read(p: &Path) -> R<Vec<u8>> {
    fs::read(p).map_err(|e| format!("{}: {e}", p.display()))
}

fn midi(p: &Path) -> R<MidiFile> {
    MidiFile::parse(&read(p)?).map_err(|e| format!("{}: {e}", p.display()))
}

/// A layer's MIDI; no notes when the file is absent (a solo take has only a solo layer).
fn midi_if(p: &Path) -> R<MidiFile> {
    if !p.exists() {
        return Ok(MidiFile { resolution: 480, instruments: Vec::new() });
    }
    midi(p)
}

fn beats(p: &Path) -> R<Beats> {
    Beats::parse(&String::from_utf8_lossy(&read(p)?))
}

fn write(p: &Path, s: &str) -> R<()> {
    if let Some(d) = p.parent() {
        fs::create_dir_all(d).map_err(|e| e.to_string())?;
    }
    fs::write(p, s).map_err(|e| format!("{}: {e}", p.display()))
}

/// Today's date (UTC) as YYYY-MM-DD.
fn today() -> String {
    let secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0) as i64;
    let z = secs.div_euclid(86400) + 719468;
    let era = z.div_euclid(146097);
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + if m <= 2 { 1 } else { 0 };
    format!("{y:04}-{m:02}-{d:02}")
}

fn stamp(xml: String) -> String {
    xml.replacen("<encoding>\n", &format!("<encoding>\n      <encoding-date>{}</encoding-date>\n", today()), 1)
}

/// Arrays of a NumPy .npz archive (float32/float64 1-D arrays).
fn load_npz(p: &Path) -> R<HashMap<String, Vec<f64>>> {
    let f = fs::File::open(p).map_err(|e| format!("{}: {e}", p.display()))?;
    let mut z = zip::ZipArchive::new(f).map_err(|e| format!("{}: {e}", p.display()))?;
    let mut out = HashMap::new();
    for i in 0..z.len() {
        let mut entry = z.by_index(i).map_err(|e| e.to_string())?;
        let name = entry.name().trim_end_matches(".npy").to_string();
        let mut buf = Vec::new();
        entry.read_to_end(&mut buf).map_err(|e| e.to_string())?;
        out.insert(name, parse_npy(&buf)?);
    }
    Ok(out)
}

fn parse_npy(b: &[u8]) -> R<Vec<f64>> {
    if b.len() < 10 || &b[..6] != b"\x93NUMPY" {
        return Err("not a .npy array".into());
    }
    let (hlen, start) = if b[6] == 1 { (u16::from_le_bytes([b[8], b[9]]) as usize, 10) } else { (u32::from_le_bytes([b[8], b[9], b[10], b[11]]) as usize, 12) };
    let header = String::from_utf8_lossy(&b[start..start + hlen]).to_string();
    let data = &b[start + hlen..];
    let descr = header.split("'descr':").nth(1).and_then(|s| s.split('\'').nth(1)).ok_or("npy header without descr")?;
    let v = match descr {
        "<f4" => data.as_chunks::<4>().0.iter().map(|c| f32::from_le_bytes(*c) as f64).collect(),
        "<f8" => data.as_chunks::<8>().0.iter().map(|c| f64::from_le_bytes(*c)).collect(),
        other => return Err(format!("unsupported npy dtype {other}")),
    };
    Ok(v)
}

fn contour(p: &Path) -> R<Contour> {
    let mut a = load_npz(p)?;
    let t = a.remove("t").ok_or("contour without t")?;
    let hz = a.remove("pitch_hz").ok_or("contour without pitch_hz")?;
    let db = a.remove("loudness_db").ok_or("contour without loudness_db")?;
    let c = Contour::from_hz(t, &hz, db).with_confidence(a.remove("confidence"));
    c.check().map_err(|e| format!("{}: {e}", p.display()))?;
    Ok(c)
}

fn out_band(dir: &Path, r: &pipeline::BandResult) -> R<()> {
    write(&dir.join("composition.json"), &r.composition.to_json_string())?;
    if let Some(s) = &r.separation_check {
        write(&dir.join("separation-check.json"), s)?;
    }
    write(&dir.join("brass-band.musicxml"), &stamp(r.musicxml.clone()))?;
    for (name, xml) in &r.parts {
        write(&dir.join("parts").join(name), &stamp(xml.clone()))?;
    }
    Ok(())
}

fn wav_if(p: &Path) -> R<Option<Audio>> {
    if !p.exists() {
        return Ok(None);
    }
    Audio::from_wav(&read(p)?).map(Some).map_err(|e| format!("{}: {e}", p.display()))
}


fn run(cmd: &str, a: &Args) -> R<()> {
    let title = a.opt("title").unwrap_or_else(|| "Draft".into());
    match cmd {
        "arrange-layers" => {
            let l = PathBuf::from(a.one("layers")?);
            let layers = Layers {
                solo_sw: midi_if(&l.join("solo-sw.mid"))?,
                solo_mus: midi_if(&l.join("solo-mus.mid"))?,
                solo_bp: midi_if(&l.join("solo-bp.mid"))?,
                bass: midi_if(&l.join("bass-mus.mid"))?,
                orchestra: midi_if(&l.join("orchestra-mus.mid"))?,
                drums: midi_if(&l.join("drums-mus.mid"))?,
                solo_audio: wav_if(&l.join("solo.wav"))?,
                bass_audio: wav_if(&l.join("bass.wav"))?,
                drums_audio: wav_if(&l.join("drums.wav"))?,
                orchestra_audio: wav_if(&l.join("orchestra.wav"))?,
            };
            let contour_path = a.opt("solo-contour").map(PathBuf::from).or_else(|| Some(l.join("solo-sw.contour.npz")).filter(|p| p.exists()));
            let opts = LayersOptions {
                solo_contour: contour_path.map(|p| contour(&p)).transpose()?,
                no_free_time: a.has("no-free-time"),
                free_tempo: a.opt("free-tempo").map(|s| s.parse::<f64>().map_err(|e| e.to_string())).transpose()?,
                no_gate: a.has("no-gate"),
                no_beat_cleanup: a.has("no-beat-cleanup"),
                single_key: a.has("single-key"),
                lineup: a.opt("lineup").unwrap_or_default(),
                difficulty: a.opt("difficulty").unwrap_or_default(),
                trills: a.has("trills"),
                key: a.opt("key"),
                transpose: a.opt("transpose").map(|s| s.parse::<i32>().map_err(|e| e.to_string())).transpose()?,
                seat: a.opt("seat"),
                reads: a.opt("reads"),
                lead: a.opt("lead").unwrap_or_default(),
                lang: a.opt("lang").unwrap_or_default(),
                kit: a.opt("kit").unwrap_or_default(),
            };
            let bt = Beats::parse_any(&String::from_utf8_lossy(&read(Path::new(&a.one("beats")?))?))?;
            let r = pipeline::arrange_layers_song(&layers, &bt, &title, &opts)?;
            out_band(Path::new(&a.one("out")?), &r)
        }
        "arrange-song" => {
            let inp = SongInputs {
                melody: midi(Path::new(&a.one("melody")?))?,
                melody_support: a.opt("melody-support").map(|p| midi(Path::new(&p))).transpose()?,
                bass: midi(Path::new(&a.one("bass")?))?,
                harmony: a.many("harmony").iter().map(|p| midi(Path::new(p))).collect::<R<Vec<_>>>()?,
            };
            let opts = pipeline::SongOptions {
                lineup: a.opt("lineup").unwrap_or_default(),
                seat: a.opt("seat"),
                reads: a.opt("reads"),
                lead: a.opt("lead").unwrap_or_default(),
                kit: a.opt("kit").unwrap_or_default(),
            };
            let r = pipeline::arrange_song_opts(&inp, &beats(Path::new(&a.one("beats")?))?, &title, &opts)?;
            out_band(Path::new(&a.one("out")?), &r)
        }
        "lead-sheet" => {
            let support = a.opt("melody-support").map(|p| midi(Path::new(&p))).transpose()?;
            let xml = pipeline::lead_sheet(
                &midi(Path::new(&a.one("melody")?))?,
                support.as_ref(),
                &midi(Path::new(&a.one("bass")?))?,
                &beats(Path::new(&a.one("beats")?))?,
                &title,
            )?;
            write(Path::new(&a.one("out")?), &stamp(xml))
        }
        "arrange-reference" => {
            let v: Value = serde_json::from_slice(&read(Path::new(&a.one("reference")?))?).map_err(|e| e.to_string())?;
            let r = pipeline::arrange_reference_with(&v, &title, &a.opt("lineup").unwrap_or_default())?;
            out_band(Path::new(&a.one("out")?), &r)
        }
        "quantize" => {
            let v: Value = serde_json::from_slice(&read(Path::new(&a.one("reference")?))?).map_err(|e| e.to_string())?;
            let q = pipeline::quantize_reference(&v, &beats(Path::new(&a.one("beats")?))?);
            let rows: Vec<Value> = q
                .iter()
                .map(|x| json!({"pitch": x.pitch, "start": x.start, "end": x.end, "onset_s": x.onset_s, "offset_s": x.offset_s, "confidence": x.confidence}))
                .collect();
            write(Path::new(&a.one("out")?), &brasscribe_core::pyjson::dumps(&Value::Array(rows)))
        }
        "musicxml" => {
            let comp = Composition::from_json_str(&String::from_utf8_lossy(&read(Path::new(&a.one("composition")?))?)).map_err(|e| e.to_string())?;
            let arr = pipeline::arrange_composition(&comp)?;
            write(Path::new(&a.one("out")?), &stamp(write_score(&band_score(&arr, &comp))))
        }
        "normalize" => {
            let comp = Composition::from_json_str(&String::from_utf8_lossy(&read(Path::new(&a.one("composition")?))?)).map_err(|e| e.to_string())?;
            write(Path::new(&a.one("out")?), &comp.to_json_string())
        }
        "meter" => {
            let b = beats(Path::new(&a.one("beats")?))?;
            let notes: Value = serde_json::from_slice(&read(Path::new(&a.one("notes")?))?).map_err(|e| e.to_string())?;
            let notes = notes.as_array().cloned().unwrap_or_default();
            let on: Vec<f64> = notes.iter().map(|n| n["onset"].as_f64().unwrap_or(0.0)).collect();
            let du: Vec<f64> = notes.iter().map(|n| n["offset"].as_f64().unwrap_or(0.0) - n["onset"].as_f64().unwrap_or(0.0)).collect();
            let down: Vec<bool> = b.positions.iter().map(|&p| p == 1).collect();
            let m = brasscribe_core::beats::meter_of(&b.times, &down, &on, &du, Some(&b.positions));
            let v = json!({"beats_per_bar": m.beats_per_bar, "first_downbeat": m.first_downbeat, "from_labels": m.from_labels,
                           "compound": m.compound, "strength": m.strength, "times": m.times});
            write(Path::new(&a.one("out")?), &brasscribe_core::pyjson::dumps_compact(&v))
        }
        "humanize" => {
            use brasscribe_core::humanize::{humanize, Performance, ScoreNote, Timing};
            let notes: Vec<ScoreNote> = serde_json::from_slice(&read(Path::new(&a.one("notes")?))?).map_err(|e| e.to_string())?;
            let perf = match a.opt("composition") {
                Some(c) => Some(Performance::from_json_str(&String::from_utf8_lossy(&read(Path::new(&c))?))?),
                None => None,
            };
            let timing = match a.opt("timing").as_deref() {
                None | Some("score") => Timing::Score,
                Some("performed") => Timing::Performed,
                Some(t) => return Err(format!("unknown timing {t}")),
            };
            let player = a.one("player")?.parse::<i64>().map_err(|e| e.to_string())?;
            let seed = a.opt("seed").unwrap_or_else(|| "brasscribe".into());
            let h = humanize(&notes, &a.one("part")?, player, &seed, perf.as_ref(), timing)?;
            write(Path::new(&a.one("out")?), &h.to_json_string())
        }
        "talking-score" => {
            use brasscribe_core::talking_score as ts;
            let xml = String::from_utf8_lossy(&read(Path::new(&a.one("musicxml")?))?).into_owned();
            let comp: Option<Value> = match a.opt("composition") {
                Some(c) => Some(serde_json::from_slice(&read(Path::new(&c))?).map_err(|e| e.to_string())?),
                None => None,
            };
            let doc = ts::build(&xml, comp.as_ref())?;
            let d = ts::Settings::default();
            let settings = ts::Settings {
                lang: a.opt("lang").unwrap_or(d.lang),
                pitch_mode: a.opt("pitch-mode").unwrap_or(d.pitch_mode),
                verbosity: a.opt("verbosity").unwrap_or(d.verbosity),
                octave_style: a.opt("octave-style").unwrap_or(d.octave_style),
                announce_confident: a.has("announce-confident"),
            };
            if let Some(p) = a.opt("json") {
                write(Path::new(&p), &brasscribe_core::pyjson::dumps(&doc))?;
            }
            if let Some(p) = a.opt("json-utf8") {
                write(Path::new(&p), &brasscribe_core::pyjson::dumps_utf8(&doc))?;
            }
            if let Some(p) = a.opt("text") {
                write(Path::new(&p), &ts::to_text(&doc, &settings, None))?;
            }
            if let Some(p) = a.opt("html") {
                write(Path::new(&p), &ts::to_html(&doc, &settings, None))?;
            }
            Ok(())
        }
        "fret" => {
            // The request and the response are target-fretted's own JSON, passed through unchanged.
            let request = String::from_utf8(read(Path::new(&a.one("request")?))?).map_err(|e| format!("the request is not UTF-8: {e}"))?;
            write(Path::new(&a.one("out")?), &target_fretted::json::solve_json(&request)?)
        }
        "version" => {
            println!("brasscribe-core {}", brasscribe_core::VERSION);
            Ok(())
        }
        _ => Err(format!("unknown command {cmd}")),
    }
}

fn main() -> ExitCode {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let Some(cmd) = argv.first() else {
        eprintln!("usage: brasscribe-core <arrange-layers|arrange-song|lead-sheet|arrange-reference|quantize|musicxml|meter|humanize|talking-score|fret|version> ...");
        return ExitCode::from(2);
    };
    match run(cmd, &Args::parse(&argv[1..])) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("brasscribe-core: {e}");
            ExitCode::FAILURE
        }
    }
}
