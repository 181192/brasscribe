//! Talking score: the text form of a score (docs/accessibility/talking-score-spec.md).
//!
//! * [`build`] reads partwise MusicXML (spelled written pitch, types, ties,
//!   tuplets) plus the Composition (confidence, sources, performed time, free
//!   regions) into the TalkingScore JSON shape (spec §6).
//! * [`announce`] produces one announcement string (spec §4).
//! * [`part_lines`], [`to_text`] and [`to_html`] walk a part note by note the
//!   way a reader does: a heading per part, a sub-heading per bar, one line per
//!   event.
//!
//! Events are JSON objects with the field names of spec §6. The conformance
//! vectors (docs/accessibility/talking-score-vectors.json) are the reference.
//! Output never depends on the process locale.

use std::collections::HashMap;

use roxmltree::{Document, Node, ParsingOptions};
use serde_json::{json, Map, Value};

use crate::py::floordiv;

pub const TICKS_PER_QUARTER: i64 = 10080;
pub const UNCERTAIN_BELOW: f64 = 0.7;
pub const VERY_UNCERTAIN_BELOW: f64 = 0.4;
/// Confidence of a note the MusicXML colours as uncertain, with no Composition match.
pub const COLOUR_ONLY_CONFIDENCE: f64 = 0.55;
/// The number of a pickup (anacrusis): spoken as "pickup", never as a bar number (spec §4.10).
pub const PICKUP_BAR: i64 = 0;

pub fn round_half_up(x: f64) -> i64 {
    (x + 0.5).floor() as i64
}

pub fn round_half(x: f64) -> f64 {
    (x * 2.0 + 0.5).floor() / 2.0
}

const STEPS: &str = "CDEFGAB";

fn step_pc(step: &str) -> i64 {
    match step {
        "C" => 0,
        "D" => 2,
        "E" => 4,
        "F" => 5,
        "G" => 7,
        "A" => 9,
        "B" => 11,
        _ => 0,
    }
}

fn gi(v: &Value, k: &str, default: i64) -> i64 {
    v.get(k).and_then(|x| x.as_i64()).unwrap_or(default)
}

fn gs<'a>(v: &'a Value, k: &str) -> Option<&'a str> {
    v.get(k).and_then(|x| x.as_str())
}

fn gf(v: &Value, k: &str) -> Option<f64> {
    v.get(k).and_then(|x| x.as_f64())
}

/// Python truthiness of a JSON value (absent = false).
fn truthy(v: Option<&Value>) -> bool {
    match v {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64().map(|x| x != 0.0).unwrap_or(true),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
    }
}

fn present(v: Option<&Value>) -> Option<&Value> {
    v.filter(|x| !x.is_null())
}

/// MIDI number of a spelled pitch object.
pub fn midi(p: &Value) -> i64 {
    (gi(p, "octave", 0) + 1) * 12 + step_pc(gs(p, "step").unwrap_or("")) + gi(p, "alter", 0)
}

/// Key signature in concert pitch: the written key moved by the part's transposition.
pub fn concert_key(written_fifths: i64, transpose: Option<&Value>) -> i64 {
    let chrom = transpose.map(|t| gi(t, "chromatic", 0)).unwrap_or(0);
    if chrom.rem_euclid(12) == 0 {
        return written_fifths;
    }
    let mut shift = (chrom * 7).rem_euclid(12);
    if shift > 6 {
        shift -= 12;
    }
    let k = written_fifths.saturating_add(shift);
    if k > 7 {
        k - 12
    } else if k < -7 {
        k + 12
    } else {
        k
    }
}

pub fn source_name(s: &str) -> String {
    match s.to_lowercase().as_str() {
        "swiftf0" | "swift-f0" | "sw" => "SwiftF0".into(),
        "muscriptor" | "mus" => "MuScriptor".into(),
        "basic-pitch" | "basicpitch" | "bp" => "Basic Pitch".into(),
        "mega53" | "mega-53" => "Mega-53".into(),
        "beat-this" => "Beat This".into(),
        _ => s.to_string(),
    }
}

// ---------------------------------------------------------------------------
// announcement inputs

#[derive(Debug, Clone, PartialEq)]
pub struct Settings {
    pub lang: String,
    /// "written" | "concert"
    pub pitch_mode: String,
    /// "brief" | "standard" | "full"
    pub verbosity: String,
    /// "scientific" | "helmholtz" (nb)
    pub octave_style: String,
    pub announce_confident: bool,
}

impl Default for Settings {
    fn default() -> Self {
        Settings { lang: "en".into(), pitch_mode: "written".into(), verbosity: "standard".into(), octave_style: "scientific".into(), announce_confident: false }
    }
}

impl Settings {
    pub fn nb(&self) -> bool {
        let l = self.lang.to_lowercase();
        l.starts_with("nb") || l.starts_with("no")
    }
}

/// What the previous announcement left behind; decides which parts get repeated.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Context {
    pub part: Option<String>,
    pub bar: Option<i64>,
    pub pitch_mode: Option<String>,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct Part {
    pub name: String,
    pub name_nb: Option<String>,
    pub instrument: Option<String>,
    pub instrument_nb: Option<String>,
    /// {"chromatic", "diatonic", "octave"}
    pub transpose: Option<Value>,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct Bar {
    pub number: i64,
    pub key_fifths: i64,
    pub key_changed: bool,
    /// {"beats", "beat_type"} when the time signature changes here.
    pub time_changed: Option<Value>,
    pub tempo_marked: Option<f64>,
    pub rehearsal: Option<String>,
    /// The free-time region this bar is in.
    pub free_region: Option<Value>,
    pub entering_region: bool,
    pub a_tempo: bool,
    pub total_bars: i64,
}

// ---------------------------------------------------------------------------
// lexicons

fn reduce(num: i64, den: i64) -> (i64, i64) {
    fn gcd(a: i64, b: i64) -> i64 {
        if b == 0 {
            a
        } else {
            gcd(b, a % b)
        }
    }
    let g = gcd(num.abs(), den.abs());
    if g != 0 {
        (floordiv(num, g), floordiv(den, g))
    } else {
        (num, den)
    }
}

fn key_alters(step: &str, fifths: i64) -> bool {
    let n = fifths.unsigned_abs().min(7) as usize;
    if fifths > 0 {
        return "FCGDAEB"[..n].contains(step);
    }
    fifths < 0 && "BEADGCF"[..n].contains(step)
}

fn fmt_num(x: &Value) -> String {
    match x.as_i64() {
        Some(i) => i.to_string(),
        None => crate::py::float_repr(x.as_f64().unwrap_or(0.0)),
    }
}

struct Lex {
    nb: bool,
}

const EN_TYPES: [(&str, &str, &str); 8] = [
    ("breve", "double whole note", "double whole"),
    ("whole", "whole note", "whole"),
    ("half", "half note", "half"),
    ("quarter", "quarter note", "quarter"),
    ("eighth", "eighth note", "eighth"),
    ("16th", "sixteenth note", "sixteenth"),
    ("32nd", "thirty-second note", "thirty-second"),
    ("64th", "sixty-fourth note", "sixty-fourth"),
];
const NB_TYPES: [(&str, &str, &str, &str); 8] = [
    ("breve", "brevis", "brevis", "brevispause"),
    ("whole", "helnote", "hel", "helpause"),
    ("half", "halvnote", "halv", "halvpause"),
    ("quarter", "fjerdedelsnote", "fjerdedel", "fjerdedelspause"),
    ("eighth", "åttendedelsnote", "åttendedel", "åttendedelspause"),
    ("16th", "sekstendedelsnote", "sekstendedel", "sekstendedelspause"),
    ("32nd", "trettitodelsnote", "trettitodel", "trettitodelspause"),
    ("64th", "sekstifiredelsnote", "sekstifiredel", "sekstifiredelspause"),
];

impl Lex {
    fn of(s: &Settings) -> Lex {
        Lex { nb: s.nb() }
    }

    fn decimal(&self) -> &'static str {
        if self.nb {
            ","
        } else {
            "."
        }
    }

    fn t<'a>(&self, en: &'a str, nb: &'a str) -> &'a str {
        if self.nb {
            nb
        } else {
            en
        }
    }

    fn number(&self, x: f64) -> String {
        let r = (x * 10.0 + 0.5).floor() / 10.0;
        if (r - r.round_ties_even()).abs() < 1e-9 {
            return format!("{}", r.round_ties_even() as i64);
        }
        format!("{r:.1}").replace('.', self.decimal())
    }

    fn join_and(&self, items: &[String]) -> String {
        match items.len() {
            0 => String::new(),
            1 => items[0].clone(),
            n => format!("{} {} {}", items[..n - 1].join(", "), self.t("and", "og"), items[n - 1]),
        }
    }

    fn dynamic(&self, d: &str) -> String {
        match d {
            "ppp" => "pianississimo",
            "pp" => "pianissimo",
            "p" => "piano",
            "mp" => "mezzo-piano",
            "mf" => "mezzo-forte",
            "f" => "forte",
            "ff" => "fortissimo",
            "fff" => "fortississimo",
            "sfz" => "sforzando",
            "fp" => "forte-piano",
            other => other,
        }
        .to_string()
    }

    fn of_word(&self) -> &'static str {
        self.t(" of ", " av ")
    }

    fn pickup(&self) -> &'static str {
        self.t("pickup", "opptakt")
    }

    fn bar(&self, n: i64) -> String {
        if n == PICKUP_BAR {
            return self.pickup().to_string();
        }
        format!("{} {n}", self.t("bar", "takt"))
    }

    /// A rest over `n` bars from the pickup on: the pickup is named, and is not one of the bars counted.
    fn pickup_rest(&self, n: i64) -> String {
        let after = n - 1;
        let and = self.t("and", "og");
        let rest = self.t("rest", "pause");
        match after {
            i64::MIN..=0 => format!("{}: {rest}", self.pickup()),
            1 => format!("{} {and} {}: {rest}", self.pickup(), self.bar(1)),
            _ => format!("{} {and} {}: {}", self.pickup(), self.bars_range(1, after), self.rest_bars(after)),
        }
    }

    fn bars_range(&self, a: i64, b: i64) -> String {
        if self.nb {
            format!("takt {a} til {b}")
        } else {
            format!("bars {a} to {b}")
        }
    }

    fn rest_bars(&self, n: i64) -> String {
        if self.nb {
            format!("pause, {n} takter")
        } else {
            format!("rest, {n} bars")
        }
    }

    fn position(&self, p: &Value) -> String {
        format!("{} {}", self.t("beat", "slag"), self.position_brief(p))
    }

    fn position_brief(&self, p: &Value) -> String {
        let (num, den) = reduce(gi(p, "num", 0), gi(p, "den", 1));
        let b = p.get("beat").map(fmt_num).unwrap_or_default();
        // In compound time the beat is a dotted quarter: in sixths of it, the even ones are its three
        // eighths and all six its sixteenths; none is a triplet.
        let compound = p.get("compound").and_then(Value::as_bool).unwrap_or(false);
        if let Some(k) = (compound && num > 0 && 6 % den == 0).then(|| num * 6 / den) {
            return match (k % 2 == 0, self.nb) {
                (true, false) => format!("{b}, eighth {}", k / 2 + 1),
                (false, false) => format!("{b}, sixteenth {}", k + 1),
                (true, true) => format!("{b}, {}. åttendedel", k / 2 + 1),
                (false, true) => format!("{b}, {}. sekstendedel", k + 1),
            };
        }
        let named = match ((num, den), self.nb) {
            ((1, 2), false) => Some(format!("{b} and")),
            ((1, 4), false) => Some(format!("{b} e")),
            ((3, 4), false) => Some(format!("{b} a")),
            ((1, 3), false) => Some(format!("{b}, triplet 2")),
            ((2, 3), false) => Some(format!("{b}, triplet 3")),
            ((1, 2), true) => Some(format!("{b}-og")),
            ((1, 4), true) => Some(format!("{b}, 2. av 4")),
            ((3, 4), true) => Some(format!("{b}, 4. av 4")),
            ((1, 3), true) => Some(format!("{b}, triol 2")),
            ((2, 3), true) => Some(format!("{b}, triol 3")),
            _ => None,
        };
        named.unwrap_or_else(|| if num == 0 { b } else { format!("{b} {} {num}/{den}", self.t("plus", "pluss")) })
    }

    fn nb_name(step: &str, alter: i64) -> String {
        let letter = if step == "B" { "H" } else { step };
        match (step, alter) {
            ("B", -1) => return "B".into(),
            ("E", -1) => return "Ess".into(),
            ("A", -1) => return "Ass".into(),
            _ => {}
        }
        match alter {
            -1 => format!("{letter}ess"),
            1 => format!("{letter}iss"),
            2 => format!("{letter} dobbeltkryss"),
            -2 => format!("{letter} dobbelt-b"),
            _ => letter.to_string(),
        }
    }

    fn pitch(&self, p: &Value, key: i64, style: &str) -> String {
        let step = gs(p, "step").unwrap_or("");
        let alter = gi(p, "alter", 0);
        let octave = p.get("octave").map(fmt_num).unwrap_or_default();
        if self.nb {
            let name = Lex::nb_name(step, alter);
            if style == "helmholtz" {
                let low = name.to_lowercase();
                let o = gi(p, "octave", 0);
                return match o {
                    2 => format!("store {name}"),
                    3 => format!("lille {low}"),
                    4 => format!("enstrøken {low}"),
                    5 => format!("tostrøken {low}"),
                    6 => format!("trestrøken {low}"),
                    _ if o <= 1 => format!("kontra {name}"),
                    _ => format!("{low} {o}"),
                };
            }
            return format!("{name} {octave}");
        }
        let mut acc = match alter {
            2 => "-double-sharp",
            1 => "-sharp",
            -1 => "-flat",
            -2 => "-double-flat",
            _ => "",
        };
        if alter == 0 && key_alters(step, key) {
            acc = "-natural";
        }
        format!("{step}{acc} {octave}")
    }

    fn dots(&self, dots: i64) -> &'static str {
        match (dots, self.nb) {
            (0, _) => "",
            (1, false) => "dotted ",
            (2, false) => "double-dotted ",
            (_, false) => "triple-dotted ",
            (1, true) => "punktert ",
            (2, true) => "dobbeltpunktert ",
            (_, true) => "trippelpunktert ",
        }
    }

    fn type_name(&self, t: &str, brief: bool) -> String {
        if self.nb {
            NB_TYPES.iter().find(|x| x.0 == t).map(|x| if brief { x.2 } else { x.1 }.to_string()).unwrap_or_else(|| t.to_string())
        } else {
            EN_TYPES.iter().find(|x| x.0 == t).map(|x| if brief { x.2 } else { x.1 }.to_string()).unwrap_or_else(|| t.to_string())
        }
    }

    fn duration(&self, t: &str, dots: i64, brief: bool) -> String {
        format!("{}{}", self.dots(dots), self.type_name(t, brief))
    }

    fn rest(&self, t: &str, dots: i64) -> String {
        if self.nb {
            let r = NB_TYPES.iter().find(|x| x.0 == t).map(|x| x.3.to_string()).unwrap_or_else(|| format!("{t} pause"));
            format!("{}{r}", self.dots(dots))
        } else {
            format!("{}{} rest", self.dots(dots), self.type_name(t, true))
        }
    }

    fn chord(&self, n: usize) -> String {
        if self.nb {
            format!("akkord, {n} toner")
        } else {
            format!("chord, {n} notes")
        }
    }

    fn tied_to(&self, d: &str, bar: Option<&Value>) -> String {
        match (bar, self.nb) {
            (None, false) => format!("tied to {d}"),
            (Some(b), false) => format!("tied to {d} in bar {}", fmt_num(b)),
            (None, true) => format!("bundet til {d}"),
            (Some(b), true) => format!("bundet til {d} i takt {}", fmt_num(b)),
        }
    }

    fn tied_chain(&self, beats: f64) -> String {
        let whole = beats.floor();
        let half = (beats - whole - 0.5).abs() < 1e-9;
        if self.nb {
            let b = if half { format!("{} og et halvt", whole as i64) } else { self.number(beats) };
            format!("bundet, {b} slag i alt")
        } else {
            let b = if half { format!("{} and a half", whole as i64) } else { self.number(beats) };
            format!("tied, {b} beats in all")
        }
    }

    fn tuplet(&self, t: &Value) -> String {
        let (a, n, i) = (t.get("actual").map(fmt_num).unwrap_or_default(), t.get("normal").map(fmt_num).unwrap_or_default(), t.get("index").map(fmt_num).unwrap_or_default());
        let triplet = gi(t, "actual", 0) == 3 && gi(t, "normal", 0) == 2;
        match (triplet, self.nb) {
            (true, false) => format!("triplet, {i} of 3"),
            (true, true) => format!("triol, {i} av 3"),
            (false, false) => format!("{a} in the time of {n}, {i} of {a}"),
            (false, true) => format!("{a} på {n}, {i} av {a}"),
        }
    }

    fn articulation(&self, a: &str) -> String {
        match (a, self.nb) {
            ("strong-accent", _) => "marcato",
            ("fermata", true) => "fermat",
            ("accent", true) => "aksent",
            ("trill", false) => "trill",
            ("trill", true) => "trille",
            ("trill-sharp", false) => "trill with sharp",
            ("trill-sharp", true) => "trille med kryss",
            ("trill-flat", false) => "trill with flat",
            ("trill-flat", true) => "trille med b",
            ("trill-natural", false) => "trill with natural",
            ("trill-natural", true) => "trille med oppløsningstegn",
            ("trill-double-sharp", false) => "trill with double sharp",
            ("trill-double-sharp", true) => "trille med dobbeltkryss",
            ("trill-flat-flat", false) => "trill with double flat",
            ("trill-flat-flat", true) => "trille med dobbelt-b",
            _ => a,
        }
        .to_string()
    }

    fn seconds_word(&self, one: bool) -> &'static str {
        match (one, self.nb) {
            (true, false) => "second",
            (false, false) => "seconds",
            (true, true) => "sekund",
            (false, true) => "sekunder",
        }
    }

    fn held_about(&self, s: f64) -> String {
        format!("{} {} {}", self.t("held about", "holdes omtrent"), self.number(s), self.seconds_word(s == 1.0))
    }

    fn at_time(&self, seconds: f64) -> String {
        let s = round_half_up(seconds);
        let at = self.t("at", "ved");
        if s < 60 {
            return format!("{at} {s} {}", self.seconds_word(s == 1));
        }
        let (m, r) = (floordiv(s, 60), s.rem_euclid(60));
        let mw = match (m == 1, self.nb) {
            (true, false) => "minute",
            (false, false) => "minutes",
            (true, true) => "minutt",
            (false, true) => "minutter",
        };
        format!("{at} {m} {mw} {r} {}", self.seconds_word(r == 1))
    }

    fn ad_lib(&self, a: &Value, b: &Value, s: i64) -> String {
        let pickup = |v: &Value| v.as_i64() == Some(PICKUP_BAR) || v.as_f64() == Some(PICKUP_BAR as f64);
        let bars = match (pickup(a), pickup(b), self.nb) {
            (true, true, _) => self.pickup().to_string(),
            (true, false, true) => format!("opptakt til takt {}", fmt_num(b)),
            (true, false, false) => format!("pickup to bar {}", fmt_num(b)),
            (false, _, true) => format!("takt {} til {}", fmt_num(a), fmt_num(b)),
            (false, _, false) => format!("bars {} to {}", fmt_num(a), fmt_num(b)),
        };
        if self.nb {
            format!("Ad lib, fritt tempo, {bars}, omtrent {s} sekunder")
        } else {
            format!("Ad lib, free time, {bars}, about {s} seconds")
        }
    }

    fn a_tempo(&self, bpm: i64) -> String {
        if self.nb {
            format!("A tempo, {bpm} slag per minutt")
        } else {
            format!("A tempo, {bpm} beats per minute")
        }
    }

    fn key(&self, f: i64) -> String {
        if self.nb {
            return if f == 0 {
                "ingen faste fortegn".into()
            } else if f > 0 {
                format!("{f} kryss")
            } else {
                format!("{} b", f.unsigned_abs())
            };
        }
        if f == 0 {
            return "no sharps or flats".into();
        }
        let n = f.unsigned_abs();
        format!("key {n} {}{}", if f > 0 { "sharp" } else { "flat" }, if n == 1 { "" } else { "s" })
    }

    fn time(&self, t: &Value) -> String {
        let beats = t.get("beats").map(fmt_num).unwrap_or_default();
        let bt = gi(t, "beat_type", 4);
        if self.nb {
            let unit = match bt {
                1 => "hel".to_string(),
                2 => "halvdels".into(),
                4 => "fjerdedels".into(),
                8 => "åttendedels".into(),
                16 => "sekstendedels".into(),
                _ => format!("{bt}-dels"),
            };
            format!("{beats} {unit} takt")
        } else {
            format!("{beats} {bt} time")
        }
    }

    fn rehearsal(&self, m: &str) -> String {
        format!("{} {m}", self.t("rehearsal", "øvingsbokstav"))
    }

    fn confidence_percent(&self, p: i64) -> String {
        if self.nb {
            format!("sikkerhet {p} prosent")
        } else {
            format!("confidence {p} percent")
        }
    }

    fn sources(&self, names: &[String]) -> String {
        let w = match (names.len() == 1, self.nb) {
            (true, false) => "source ",
            (false, false) => "sources ",
            (true, true) => "kilde ",
            (false, true) => "kilder ",
        };
        format!("{w}{}", self.join_and(names))
    }

    fn written_sounds(&self, w: &str, s: &str) -> String {
        if self.nb {
            format!("skrevet {w}, klinger {s}")
        } else {
            format!("written {w}, sounds {s}")
        }
    }

    fn instrument_name(&self, i: &str) -> String {
        if self.nb {
            i.to_string()
        } else {
            i.replace('♭', "-flat").replace('♯', "-sharp")
        }
    }

    fn bar_heading(&self, a: i64, b: Option<i64>) -> String {
        let w = self.t("Bar", "Takt");
        if a == PICKUP_BAR {
            let p = self.t("Pickup", "Opptakt");
            return match (b, self.nb) {
                (None, _) => p.to_string(),
                (Some(1), true) => format!("{p} og takt 1"),
                (Some(1), false) => format!("{p} and bar 1"),
                (Some(b), true) => format!("{p} og takt 1–{b}"),
                (Some(b), false) => format!("{p} and bars 1–{b}"),
            };
        }
        match b {
            None => format!("{w} {a}"),
            Some(b) => format!("{}{} {a}–{b}", w, if self.nb { "" } else { "s" }),
        }
    }
}

fn bar_changes(bar: &Bar, l: &Lex) -> Vec<String> {
    let mut out = Vec::new();
    if bar.key_changed {
        out.push(l.key(bar.key_fifths));
    }
    if let Some(t) = &bar.time_changed {
        if truthy(Some(t)) {
            out.push(l.time(t));
        }
    }
    if let Some(t) = bar.tempo_marked {
        if !bar.a_tempo {
            out.push(format!("tempo {}", round_half_up(t)));
        }
    }
    if let Some(r) = bar.rehearsal.as_deref().filter(|r| !r.is_empty()) {
        out.push(l.rehearsal(r));
    }
    out
}

/// One announcement (spec §4). `by_bar`: the user navigated by bar.
pub fn announce(part: &Part, bar: &Bar, ev: &Value, ctx: &Context, s: &Settings, by_bar: bool) -> String {
    let l = Lex::of(s);
    let kind = gs(ev, "kind").unwrap_or("note");
    if kind == "mode-change" {
        if s.pitch_mode == "concert" {
            return l.t("Concert pitch", "Klingende tone").into();
        }
        let written = l.t("Written pitch", "Skrevet tone");
        let inst = if s.nb() { part.instrument_nb.as_ref().or(part.instrument.as_ref()) } else { part.instrument.as_ref() };
        return match inst {
            None => written.into(),
            Some(i) => format!("{written}, {}", l.instrument_name(i)),
        };
    }

    let mut out = String::new();
    let region = bar.free_region.as_ref().filter(|r| truthy(Some(r)));
    if let (Some(r), true) = (region, bar.entering_region) {
        let len = round_half_up(gf(r, "end_s").unwrap_or(0.0) - gf(r, "start_s").unwrap_or(0.0));
        out.push_str(&l.ad_lib(&r["start_bar"], &r["end_bar"], len));
        out.push_str(". ");
    } else if bar.a_tempo && bar.tempo_marked.is_some() {
        out.push_str(&l.a_tempo(round_half_up(bar.tempo_marked.unwrap())));
        out.push_str(". ");
    }

    let part_changed = ctx.part.as_ref().is_some_and(|p| *p != part.name);
    let mut bar = bar.clone();
    if part_changed {
        let name = if s.nb() { part.name_nb.as_ref().filter(|n| !n.is_empty()).unwrap_or(&part.name) } else { &part.name };
        out.push_str(name);
        out.push_str(". ");
        bar.key_changed = true; // §4.9: the new part's key is always announced
    }

    let time_s = present(ev.get("time_s")).and_then(|x| x.as_f64());
    let in_free = region.is_some_and(|r| gs(r, "notation").unwrap_or("proportional") == "proportional") && time_s.is_some();
    let changes = bar_changes(&bar, &l);
    let show_bar = s.verbosity == "full" || by_bar || ctx.bar != Some(bar.number) || part_changed || !changes.is_empty() || kind == "bar-rest";

    if kind == "bar-rest" {
        let n = gi(ev, "bars", 1);
        if bar.number == PICKUP_BAR {
            out.push_str(&l.pickup_rest(n));
        } else if n > 1 {
            out.push_str(&format!("{}: {}", l.bars_range(bar.number, bar.number + n - 1), l.rest_bars(n)));
        } else {
            out.push_str(&format!("{}: {}", l.bar(bar.number), l.t("rest, whole bar", "pause hele takten")));
        }
        return out;
    }

    let brief = s.verbosity == "brief";
    if !brief && show_bar {
        out.push_str(&l.bar(bar.number));
        if s.verbosity == "full" && bar.total_bars > 0 && bar.number != PICKUP_BAR {
            out.push_str(l.of_word());
            out.push_str(&bar.total_bars.to_string());
        }
        for c in &changes {
            out.push_str(", ");
            out.push_str(c);
        }
        out.push_str(", ");
    }

    if in_free {
        out.push_str(&l.at_time(time_s.unwrap()));
    } else if let Some(p) = ev.get("pos").filter(|p| truthy(Some(p))) {
        out.push_str(&if brief { l.position_brief(p) } else { l.position(p) });
    }
    out.push_str(": ");

    let concert_mode = s.pitch_mode == "concert";
    let key = if concert_mode { concert_key(bar.key_fifths, part.transpose.as_ref()) } else { bar.key_fifths };
    let pick = |e: &Value| -> Option<Value> {
        let w = e.get("written").filter(|x| truthy(Some(x))).cloned();
        let c = e.get("concert").filter(|x| truthy(Some(x))).cloned();
        if concert_mode {
            c.or(w)
        } else {
            w.or(c)
        }
    };
    let pitch_of = |e: &Value| -> String { pick(e).map(|p| l.pitch(&p, key, &s.octave_style)).unwrap_or_default() };

    let typ = gs(ev, "type").filter(|t| !t.is_empty()).unwrap_or("quarter").to_string();
    let dots = gi(ev, "dots", 0);
    if kind == "held" {
        out.push_str(&format!("{} {}, {}", pitch_of(ev), l.t("held", "holdes"), l.t("from ", "fra ")));
        if let Some(f) = ev.get("held_from").filter(|f| truthy(Some(f))) {
            if gi(f, "bar", i64::MIN) != bar.number {
                out.push_str(&l.bar(gi(f, "bar", 0)));
                out.push(' ');
            }
            let mut from = f.clone();
            if let Some(m) = from.as_object_mut() {
                m.remove("bar");
            }
            out.push_str(&l.position(&from));
        }
        return out;
    }
    match kind {
        "rest" => out.push_str(&l.rest(&typ, dots)),
        "chord" => {
            let field = if concert_mode { "concert" } else { "written" };
            let mut ps: Vec<Value> = ev.get("pitches").and_then(|x| x.as_array()).map(|a| a.iter().map(|cp| cp[field].clone()).collect()).unwrap_or_default();
            ps.sort_by_key(midi);
            let names: Vec<String> = ps.iter().map(|p| l.pitch(p, key, &s.octave_style)).collect();
            out.push_str(&format!("{}: {}, {}", l.chord(names.len()), names.join(", "), l.duration(&typ, dots, brief)));
        }
        "unpitched" => {
            let en = ev.get("instruments");
            let names = if s.nb() { ev.get("instruments_nb").filter(|x| truthy(Some(x))).or(en) } else { en };
            let names: Vec<String> = names.and_then(|x| x.as_array()).map(|a| a.iter().map(|x| x.as_str().unwrap_or("").to_string()).collect()).unwrap_or_default();
            out.push_str(&format!("{}, {}", l.join_and(&names), l.duration(&typ, dots, brief)));
        }
        _ => {
            let w = ev.get("written").filter(|x| truthy(Some(x)));
            let c = ev.get("concert").filter(|x| truthy(Some(x)));
            match (s.verbosity == "full", w, c) {
                (true, Some(w), Some(c)) => {
                    let (wk, ck) = (bar.key_fifths, concert_key(bar.key_fifths, part.transpose.as_ref()));
                    out.push_str(&l.written_sounds(&l.pitch(w, wk, &s.octave_style), &l.pitch(c, ck, &s.octave_style)));
                }
                _ => out.push_str(&pitch_of(ev)),
            }
            out.push_str(if brief { " " } else { ", " });
            out.push_str(&l.duration(&typ, dots, brief));
        }
    }

    let mut mods: Vec<String> = Vec::new();
    if let Some(tie) = ev.get("tie").filter(|t| truthy(Some(t))) {
        if truthy(tie.get("start")) {
            if let Some(cb) = present(tie.get("chain_beats")).and_then(|x| x.as_f64()) {
                mods.push(l.tied_chain(cb));
            } else if let Some(nx) = tie.get("next").filter(|x| truthy(Some(x))) {
                let d = l.duration(gs(nx, "type").unwrap_or(""), gi(nx, "dots", 0), false);
                let nb = &nx["bar"];
                mods.push(l.tied_to(&d, if nb.as_i64() != Some(bar.number) { Some(nb) } else { None }));
            }
        }
    }
    if let Some(t) = ev.get("tuplet").filter(|t| truthy(Some(t))) {
        mods.push(l.tuplet(t));
    }
    if let Some(a) = ev.get("articulations").and_then(|a| a.as_array()) {
        mods.extend(a.iter().map(|x| l.articulation(x.as_str().unwrap_or(""))));
    }
    if let Some(d) = ev.get("dynamic").filter(|d| truthy(Some(d))) {
        mods.push(l.dynamic(d.as_str().unwrap_or("")));
    }
    if region.is_some() {
        let ps = present(ev.get("performed_s")).and_then(|x| x.as_f64()).unwrap_or(0.0);
        if ps >= 1.0 {
            mods.push(l.held_about(round_half(ps)));
        }
    }
    if let Some(conf) = present(ev.get("confidence")).and_then(|x| x.as_f64()) {
        if !truthy(ev.get("checked")) {
            let level = if conf < VERY_UNCERTAIN_BELOW {
                0
            } else if conf < UNCERTAIN_BELOW {
                1
            } else {
                2
            };
            match level {
                0 => mods.push(l.t("very uncertain", "svært usikker").into()),
                1 => mods.push(l.t("uncertain", "usikker").into()),
                _ => {
                    if s.verbosity == "full" && s.announce_confident {
                        mods.push(l.t("confident", "sikker").into());
                    }
                }
            }
            if s.verbosity == "full" && (level != 2 || s.announce_confident) {
                mods.push(l.confidence_percent(round_half_up(conf * 100.0)));
                if let Some(src) = ev.get("sources").and_then(|x| x.as_array()).filter(|a| !a.is_empty()) {
                    let names: Vec<String> = src.iter().map(|x| source_name(x.as_str().unwrap_or(""))).collect();
                    mods.push(l.sources(&names));
                }
            }
        }
    }
    for m in mods {
        out.push_str(", ");
        out.push_str(&m);
    }
    out
}

// ---------------------------------------------------------------------------
// build from MusicXML

pub fn nb_part_name(name: &str) -> &str {
    match name {
        "Soprano Cornet" => "Sopran-kornett",
        "Solo Cornet" => "Solokornett",
        "1st Cornet" => "1. kornett",
        "Tenor Horn" => "Althorn",
        "Repiano Cornet" => "Repiano-kornett",
        "2nd Cornet" => "2. kornett",
        "3rd Cornet" => "3. kornett",
        "Flugelhorn" => "Flygelhorn",
        "Solo Horn" => "Solo althorn",
        "1st Horn" => "1. althorn",
        "2nd Horn" => "2. althorn",
        "1st Baritone" => "1. baryton",
        "2nd Baritone" => "2. baryton",
        "1st Trombone" => "1. trombone",
        "2nd Trombone" => "2. trombone",
        "Bass Trombone" => "Basstrombone",
        "Euphonium" => "Eufonium",
        "E♭ Bass" => "Ess-bass",
        "B♭ Bass" => "B-bass",
        "Percussion" => "Slagverk",
        "Trumpet" => "Trompet",
        other => other,
    }
}

pub fn instrument_nb(en: &str) -> String {
    let mut s = en.to_string();
    for (a, b) in [
        ("Soprano Cornet", "sopran-kornett"),
        ("Cornet", "kornett"),
        ("Trumpet", "trompet"),
        ("Flugelhorn", "flygelhorn"),
        ("Tenor Horn", "althorn"),
        ("Horn", "althorn"),
        ("Baritone", "baryton"),
        ("Euphonium", "eufonium"),
        ("Bass Trombone", "basstrombone"),
        ("Drum Kit", "trommesett"),
        (" in B♭", " i B"),
        (" in E♭", " i Ess"),
        (" in C", " i C"),
    ] {
        s = s.replace(a, b);
    }
    let mut c = s.chars();
    match c.next() {
        None => String::new(),
        Some(f) => f.to_lowercase().collect::<String>() + c.as_str(),
    }
}

fn drum(step: &str, octave: i64, notehead: Option<&str>) -> (&'static str, &'static str) {
    let x = notehead == Some("x");
    match (step, octave) {
        ("F", 4) | ("E", 4) => return ("bass drum", "stortromme"),
        ("C", 5) => return ("snare drum", "skarptromme"),
        _ => {}
    }
    if x {
        match (step, octave) {
            ("G", 5) => return ("hi-hat", "hi-hat"),
            ("A", 5) => return ("crash cymbal", "crashcymbal"),
            ("F", 5) => return ("ride cymbal", "ridecymbal"),
            ("D", 4) => return ("pedal hi-hat", "pedal-hi-hat"),
            _ => {}
        }
    }
    match (step, octave) {
        ("E", 5) | ("D", 5) => ("tom", "tom"),
        ("A", 4) => ("floor tom", "gulvtom"),
        _ => ("drum", "tromme"),
    }
}

/// Concert pitch keeping the diatonic spelling: written + chromatic semitones and diatonic steps.
pub fn to_concert(written: &Value, t: &Value) -> Value {
    let diatonic = gi(t, "diatonic", 0) + 7 * gi(t, "octave", 0);
    let chromatic = gi(t, "chromatic", 0) + 12 * gi(t, "octave", 0);
    let step = gs(written, "step").unwrap_or("C");
    let abs_step = gi(written, "octave", 0) * 7 + STEPS.find(step).unwrap_or(0) as i64 + diatonic;
    let (octave, rem) = (floordiv(abs_step, 7), abs_step.rem_euclid(7));
    let tstep = &STEPS[rem as usize..rem as usize + 1];
    let mut target = json!({"step": tstep, "alter": 0, "octave": octave});
    let alter = midi(written) + chromatic - midi(&target);
    target["alter"] = json!(alter);
    target
}

fn position(offset: i64, divisions: i64, time: &Value) -> Value {
    let (beats, bt) = (gi(time, "beats", 4), gi(time, "beat_type", 4));
    let compound = bt == 8 && beats.rem_euclid(3) == 0 && beats > 3;
    let beat_div = if bt == 0 { 0 } else { floordiv(divisions * 4, bt) * if compound { 3 } else { 1 } };
    if beat_div <= 0 {
        return json!({"beat": 1, "num": 0, "den": 1});
    }
    let (beat, rem) = (floordiv(offset, beat_div), offset.rem_euclid(beat_div));
    let (n, d) = if rem == 0 { (0, 1) } else { reduce(rem, beat_div) };
    let mut pos = json!({"beat": beat + 1, "num": n, "den": d});
    if compound {
        pos["compound"] = json!(true);
    }
    pos
}

fn type_from_duration(dur: i64, divisions: i64) -> &'static str {
    let q = dur as f64 / divisions as f64;
    for (limit, t) in [(8.0, "breve"), (4.0, "whole"), (2.0, "half"), (1.0, "quarter"), (0.5, "eighth"), (0.25, "16th"), (0.125, "32nd")] {
        if q >= limit {
            return t;
        }
    }
    "64th"
}

// ElementTree-like helpers

fn children<'a, 'i>(n: Node<'a, 'i>, tag: &'a str) -> impl Iterator<Item = Node<'a, 'i>> + 'a {
    n.children().filter(move |c| c.is_element() && c.tag_name().name() == tag)
}

fn find<'a, 'i>(n: Node<'a, 'i>, path: &str) -> Option<Node<'a, 'i>> {
    let mut cur = n;
    for seg in path.split('/') {
        cur = cur.children().find(|c| c.is_element() && c.tag_name().name() == seg)?;
    }
    Some(cur)
}

/// `findtext`: the element's text ("" when it has none), None when missing.
fn findtext(n: Node, path: &str) -> Option<String> {
    find(n, path).map(|e| e.text().unwrap_or("").to_string())
}

fn el_int(e: Option<Node>, default: i64) -> i64 {
    match e.and_then(|e| e.text()) {
        Some(t) => t.trim().parse::<i64>().unwrap_or(default),
        None => default,
    }
}

fn iter_desc<'a, 'i>(n: Node<'a, 'i>, tag: &'a str) -> impl Iterator<Item = Node<'a, 'i>> + 'a {
    n.descendants().filter(move |c| c.is_element() && c.tag_name().name() == tag)
}

fn has_tie(note: Node, kind: &str) -> bool {
    children(note, "tie").any(|t| t.attribute("type") == Some(kind)) || find(note, "notations").is_some_and(|ns| children(ns, "tied").any(|t| t.attribute("type") == Some(kind)))
}

fn element_count(n: Node) -> usize {
    n.children().filter(|c| c.is_element()).count()
}

fn first_child_tag(n: Node) -> Option<String> {
    n.children().find(|c| c.is_element()).map(|c| c.tag_name().name().to_string())
}

/// The Composition note behind a printed note: same onset tick and concert pitch, else the same pitch class.
struct Matcher {
    tpb: i64,
    by_onset: HashMap<i64, Vec<Value>>,
}

impl Matcher {
    fn new(comp: &Value) -> Matcher {
        let mut by_onset: HashMap<i64, Vec<Value>> = HashMap::new();
        for v in comp.get("voices").and_then(|x| x.as_array()).map(|a| a.as_slice()).unwrap_or(&[]) {
            if gs(v, "layer") == Some("drums") || gs(v, "role") == Some("rhythm") {
                continue;
            }
            for n in v.get("notes").and_then(|x| x.as_array()).map(|a| a.as_slice()).unwrap_or(&[]) {
                by_onset.entry(gi(n, "start", 0)).or_default().push(n.clone());
            }
        }
        Matcher { tpb: gi(comp, "ticks_per_beat", 24), by_onset }
    }

    fn matched(&self, quarter: f64, pitch: i64) -> Option<&Value> {
        let tick = round_half_up(quarter * self.tpb as f64);
        for t in [tick, tick - 1, tick + 1] {
            if let Some(c) = self.by_onset.get(&t) {
                if let Some(h) = c.iter().find(|n| gi(n, "pitch", i64::MIN) == pitch).or_else(|| c.iter().find(|n| (gi(n, "pitch", 0) - pitch).rem_euclid(12) == 0)) {
                    return Some(h);
                }
            }
        }
        None
    }
}

pub fn seconds_at(comp: &Value, tick: f64) -> f64 {
    let tpb = gi(comp, "ticks_per_beat", 24);
    let bt: Vec<f64> = comp.get("beat_times").and_then(|x| x.as_array()).map(|a| a.iter().filter_map(|x| x.as_f64()).collect()).unwrap_or_default();
    let beat = gi(comp, "first_downbeat", 0) as f64 + tick / tpb as f64;
    if bt.is_empty() {
        return beat * 0.5;
    }
    if bt.len() == 1 {
        return bt[0] + beat * 0.5;
    }
    let i = (beat.floor() as i64).max(0).min(bt.len() as i64 - 2) as usize;
    bt[i] + (beat - i as f64) * (bt[i + 1] - bt[i])
}

struct Chain {
    head: usize,
    bar: i64,
    length: i64,
    count: i64,
}

/// What a pickup measure lacks of a full bar, in divisions: 0 when it is a full bar or empty.
fn lead_in(m: Node, mut divisions: i64, time: &Value) -> i64 {
    let mut time = time.clone();
    let (mut offset, mut length) = (0i64, 0i64);
    for el in m.children().filter(|c| c.is_element()) {
        match el.tag_name().name() {
            "attributes" => {
                divisions = el_int(find(el, "divisions"), divisions);
                if find(el, "time").is_some() {
                    time = json!({"beats": el_int(find(el, "time/beats"), 4), "beat_type": el_int(find(el, "time/beat-type"), 4)});
                }
            }
            "backup" => offset -= el_int(find(el, "duration"), 0),
            "forward" => {
                offset += el_int(find(el, "duration"), 0);
                length = length.max(offset);
            }
            "note" if find(el, "chord").is_none() && find(el, "grace").is_none() => {
                offset += el_int(find(el, "duration"), 0);
                length = length.max(offset);
            }
            _ => {}
        }
    }
    let bt = gi(&time, "beat_type", 4);
    let full = if bt > 0 { floordiv(divisions * 4 * gi(&time, "beats", 4), bt) } else { 0 };
    if 0 < length && length < full {
        full - length
    } else {
        0
    }
}

/// `lead`: the divisions a pickup lacks of a full bar; `pos` counts from where that bar would start.
#[allow(clippy::too_many_arguments)]
fn read_note(el: Node, start: i64, dur: i64, divisions: i64, time: &Value, percussion: bool, transpose: &Value, tuplet_count: &mut i64, lead: i64) -> Result<Option<Value>, String> {
    let typ = findtext(el, "type");
    let mut ev = Map::new();
    ev.insert("kind".into(), json!("note"));
    ev.insert("tick".into(), json!(floordiv(start * TICKS_PER_QUARTER, divisions)));
    ev.insert("dur_ticks".into(), json!(floordiv(dur * TICKS_PER_QUARTER, divisions)));
    ev.insert("pos".into(), position(start + lead, divisions, time));
    ev.insert("type".into(), typ.clone().map(Value::String).unwrap_or(Value::Null));
    ev.insert("dots".into(), json!(children(el, "dot").count()));
    for k in ["tuplet", "tie"] {
        ev.insert(k.into(), Value::Null);
    }
    ev.insert("articulations".into(), json!([]));
    ev.insert("dynamic".into(), Value::Null);
    ev.insert("confidence".into(), Value::Null);
    ev.insert("sources".into(), json!([]));
    ev.insert("checked".into(), json!(false));
    ev.insert("time_s".into(), Value::Null);
    ev.insert("performed_s".into(), Value::Null);
    let type_or = |ev: &mut Map<String, Value>| {
        if !truthy(ev.get("type")) {
            ev.insert("type".into(), json!(type_from_duration(dur, divisions)));
        }
    };
    if let Some(rest) = find(el, "rest") {
        if rest.attribute("measure") == Some("yes") || (typ.is_none() && start == 0) {
            ev.insert("kind".into(), json!("bar-rest"));
            ev.insert("pos".into(), position(0, divisions, time));
            ev.insert("bars".into(), json!(1));
        } else {
            ev.insert("kind".into(), json!("rest"));
        }
        type_or(&mut ev);
        return Ok(Some(Value::Object(ev)));
    }
    type_or(&mut ev);
    if let Some(tm) = find(el, "time-modification") {
        let (actual, normal) = (el_int(find(tm, "actual-notes"), 3), el_int(find(tm, "normal-notes"), 2));
        if actual == 0 {
            return Err("a tuplet of 0 notes (<actual-notes>0</actual-notes>)".into());
        }
        ev.insert("tuplet".into(), json!({"actual": actual, "normal": normal, "index": crate::py::pymod(*tuplet_count, actual) + 1}));
        *tuplet_count += 1;
    } else {
        *tuplet_count = 0;
    }
    if let Some(nots) = find(el, "notations") {
        let arts = ev.get_mut("articulations").unwrap().as_array_mut().unwrap();
        if let Some(a) = find(nots, "articulations") {
            arts.extend(a.children().filter(|c| c.is_element()).map(|c| json!(c.tag_name().name())));
        }
        if let Some(o) = find(nots, "ornaments").filter(|o| find(*o, "trill-mark").is_some()) {
            let mark = findtext(o, "accidental-mark").map(|t| t.trim().to_string()).unwrap_or_default();
            arts.push(json!(if mark.is_empty() { "trill".to_string() } else { format!("trill-{mark}") }));
        }
        if find(nots, "fermata").is_some() {
            arts.push(json!("fermata"));
        }
        if let Some(d) = find(nots, "dynamics") {
            if element_count(d) > 0 {
                ev.insert("dynamic".into(), json!(first_child_tag(d)));
            }
        }
    }
    if let Some(up) = find(el, "unpitched") {
        let step = findtext(up, "display-step").filter(|s| !s.is_empty()).unwrap_or_else(|| "C".into());
        let (en, nb) = drum(&step, el_int(find(up, "display-octave"), 5), findtext(el, "notehead").as_deref());
        ev.insert("kind".into(), json!("unpitched"));
        ev.insert("instruments".into(), json!([en]));
        ev.insert("instruments_nb".into(), json!([nb]));
        return Ok(Some(Value::Object(ev)));
    }
    let Some(p) = find(el, "pitch") else { return Ok(None) };
    let written = read_pitch(p);
    let concert = if percussion { written.clone() } else { to_concert(&written, transpose) };
    ev.insert("written".into(), written);
    ev.insert("concert".into(), concert);
    if let Some(nh) = find(el, "notehead") {
        if nh.attribute("parentheses") == Some("yes") && ev["confidence"].is_null() {
            ev.insert("confidence".into(), json!(0.3));
        }
    }
    Ok(Some(Value::Object(ev)))
}

fn read_pitch(p: Node) -> Value {
    json!({
        "step": findtext(p, "step").filter(|s| !s.is_empty()).unwrap_or_else(|| "C".into()),
        "alter": el_int(find(p, "alter"), 0),
        "octave": el_int(find(p, "octave"), 4),
    })
}

fn add_chord_tone(head: &mut Value, el: Node, percussion: bool, transpose: &Value) {
    if let Some(up) = find(el, "unpitched") {
        let step = findtext(up, "display-step").filter(|s| !s.is_empty()).unwrap_or_else(|| "C".into());
        let (en, nb) = drum(&step, el_int(find(up, "display-octave"), 5), findtext(el, "notehead").as_deref());
        for (k, name) in [("instruments", en), ("instruments_nb", nb)] {
            if let Some(a) = head.get_mut(k).and_then(|x| x.as_array_mut()) {
                if !a.iter().any(|x| x.as_str() == Some(name)) {
                    a.push(json!(name));
                }
            }
        }
        return;
    }
    let Some(p) = find(el, "pitch") else { return };
    if present(head.get("written")).is_none() {
        return;
    }
    let written = read_pitch(p);
    if gs(head, "kind") == Some("note") {
        head["kind"] = json!("chord");
        let w = head["written"].clone();
        let c = head.get("concert").filter(|x| truthy(Some(x))).cloned().unwrap_or_else(|| w.clone());
        head["pitches"] = json!([{"written": w, "concert": c}]);
    }
    let concert = if percussion { written.clone() } else { to_concert(&written, transpose) };
    if let Some(a) = head.get_mut("pitches").and_then(|x| x.as_array_mut()) {
        a.push(json!({"written": written, "concert": concert}));
    }
}

/// TalkingScore document (spec §6) from partwise MusicXML text, plus the Composition when known.
pub fn build(musicxml: &str, composition: Option<&Value>) -> Result<Value, String> {
    let opts = ParsingOptions { allow_dtd: true, ..Default::default() };
    let doc = Document::parse_with_options(musicxml, opts).map_err(|e| e.to_string())?;
    let root = doc.root_element();
    if root.tag_name().name() != "score-partwise" {
        return Err("only score-partwise MusicXML is supported".into());
    }
    let title = findtext(root, "work/work-title").filter(|t| !t.is_empty()).or_else(|| findtext(root, "movement-title")).unwrap_or_default().trim().to_string();
    let mut info: HashMap<String, (String, Option<String>)> = HashMap::new();
    if let Some(pl) = find(root, "part-list") {
        for sp in children(pl, "score-part") {
            let name = findtext(sp, "part-name").filter(|t| !t.is_empty()).unwrap_or_else(|| "Part".into());
            info.insert(sp.attribute("id").unwrap_or("").to_string(), (name, findtext(sp, "score-instrument/instrument-name")));
        }
    }
    let matcher = composition.map(Matcher::new);
    let comp_tpb = composition.map(|c| gi(c, "ticks_per_beat", 24)).unwrap_or(24) as f64;
    let mut measure_starts: Vec<f64> = Vec::new();
    let mut parts: Vec<Value> = Vec::new();
    for (pi, part_el) in children(root, "part").enumerate() {
        let pid = part_el.attribute("id").unwrap_or("").to_string();
        let (name, inst) = info.get(&pid).cloned().unwrap_or(("Part".into(), None));
        let mut transpose = json!({"chromatic": 0, "diatonic": 0, "octave": 0});
        let mut percussion = false;
        let (mut divisions, mut fifths, mut time) = (1i64, 0i64, json!({"beats": 4, "beat_type": 4}));
        let mut part_q = 0.0f64;
        let mut tuplet_count = 0i64;
        // events of this part in an arena; bars hold indices
        let mut arena: Vec<Value> = Vec::new();
        let mut bars: Vec<(Map<String, Value>, Vec<usize>)> = Vec::new();
        let mut pending: Vec<(usize, i64, i64)> = Vec::new(); // (tie-start event, concert MIDI, bar number)
        let mut chain_of: HashMap<usize, usize> = HashMap::new();
        let mut chains: Vec<Chain> = Vec::new();
        for (idx, m) in children(part_el, "measure").enumerate() {
            let mut number = m.attribute("number").and_then(|n| n.trim().parse::<i64>().ok()).unwrap_or(idx as i64 + 1);
            // A pickup: the first measure, numbered 0 or left out of the numbering. Its notes are placed on the
            // beats they fall on in the bar they lead into.
            let mut lead = 0i64;
            if idx == 0 && (number == PICKUP_BAR || m.attribute("implicit") == Some("yes")) {
                number = PICKUP_BAR;
                lead = lead_in(m, divisions, &time);
            }
            let (mut tempo, mut rehearsal, mut pending_dyn): (Option<f64>, Option<String>, Option<String>) = (None, None, None);
            let (mut offset, mut length) = (0i64, 0i64);
            let mut last: Option<usize> = None;
            if pi == 0 {
                measure_starts.push(part_q);
            }
            let mut events: Vec<usize> = Vec::new();
            for el in m.children().filter(|c| c.is_element()) {
                match el.tag_name().name() {
                    "attributes" => {
                        divisions = el_int(find(el, "divisions"), divisions);
                        if divisions == 0 {
                            return Err("MusicXML <divisions> of 0".into());
                        }
                        fifths = el_int(find(el, "key/fifths"), fifths);
                        if find(el, "time").is_some() {
                            time = json!({"beats": el_int(find(el, "time/beats"), 4), "beat_type": el_int(find(el, "time/beat-type"), 4)});
                        }
                        if let Some(tr) = find(el, "transpose") {
                            transpose = json!({"chromatic": el_int(find(tr, "chromatic"), 0), "diatonic": el_int(find(tr, "diatonic"), 0), "octave": el_int(find(tr, "octave-change"), 0)});
                        }
                        if findtext(el, "clef/sign").as_deref() == Some("percussion") {
                            percussion = true;
                        }
                    }
                    "direction" => {
                        if let Some(snd) = iter_desc(el, "sound").find(|s| s.attribute("tempo").is_some_and(|t| !t.is_empty())) {
                            tempo = Some(snd.attribute("tempo").unwrap().trim().parse::<f64>().map_err(|e| e.to_string())?);
                        }
                        if let Some(rh) = iter_desc(el, "rehearsal").next() {
                            if let Some(t) = rh.text().filter(|t| !t.is_empty()) {
                                rehearsal = Some(t.trim().to_string());
                            }
                        }
                        if let Some(dyn_) = iter_desc(el, "dynamics").next() {
                            if element_count(dyn_) > 0 {
                                pending_dyn = first_child_tag(dyn_);
                            }
                        }
                    }
                    "backup" => offset -= el_int(find(el, "duration"), 0),
                    "forward" => {
                        offset += el_int(find(el, "duration"), 0);
                        length = length.max(offset);
                    }
                    "note" => {
                        let dur = el_int(find(el, "duration"), 0);
                        let (is_chord, grace) = (find(el, "chord").is_some(), find(el, "grace").is_some());
                        let voice = findtext(el, "voice").filter(|v| !v.is_empty()).unwrap_or_else(|| "1".into());
                        if is_chord {
                            if let Some(li) = last {
                                add_chord_tone(&mut arena[li], el, percussion, &transpose);
                                continue;
                            }
                        }
                        let start = offset;
                        if !grace {
                            offset += dur;
                        }
                        length = length.max(offset);
                        if grace || voice != "1" {
                            if voice != "1" {
                                last = None;
                            }
                            continue;
                        }
                        let Some(mut ev) = read_note(el, start, dur, divisions, &time, percussion, &transpose, &mut tuplet_count, lead)? else { continue };
                        let kind = gs(&ev, "kind").unwrap_or("").to_string();
                        if pending_dyn.is_some() && kind != "rest" && kind != "bar-rest" {
                            ev["dynamic"] = json!(pending_dyn.take());
                        }
                        let abs_q = part_q + start as f64 / divisions as f64;
                        if kind == "rest" {
                            if let Some(c) = composition {
                                ev["time_s"] = json!(seconds_at(c, abs_q * comp_tpb));
                            }
                        }
                        let me = arena.len();
                        if truthy(ev.get("concert")) {
                            let mp = midi(&ev["concert"]);
                            let hit = matcher.as_ref().and_then(|mt| mt.matched(abs_q, mp));
                            if let Some(hit) = hit {
                                ev["confidence"] = hit.get("confidence").cloned().unwrap_or(Value::Null);
                                ev["sources"] = hit.get("sources").cloned().filter(|x| x.is_array()).unwrap_or(json!([]));
                                if let Some(on) = present(hit.get("onset_s")) {
                                    ev["time_s"] = on.clone();
                                    if let Some(off) = present(hit.get("offset_s")) {
                                        ev["performed_s"] = json!(off.as_f64().unwrap_or(0.0) - on.as_f64().unwrap_or(0.0));
                                    }
                                }
                                if let Some(arts) = hit.get("articulations").and_then(|a| a.as_array()) {
                                    let mine = ev["articulations"].as_array_mut().unwrap();
                                    for a in arts {
                                        if !mine.contains(a) {
                                            mine.push(a.clone());
                                        }
                                    }
                                }
                            } else if el.attribute("color").is_some_and(|c| !c.is_empty()) || find(el, "notehead").and_then(|n| n.attribute("color")).is_some_and(|c| !c.is_empty()) {
                                ev["confidence"] = json!(COLOUR_ONLY_CONFIDENCE);
                            }
                            if ev["time_s"].is_null() {
                                if let Some(c) = composition {
                                    ev["time_s"] = json!(seconds_at(c, abs_q * comp_tpb));
                                }
                            }
                            if has_tie(el, "stop") {
                                if let Some(i) = pending.iter().position(|(_, pm, _)| *pm == mp) {
                                    let (frm, _, frm_bar) = pending.remove(i);
                                    let mut tie = arena[frm].get("tie").filter(|t| truthy(Some(t))).cloned().unwrap_or(json!({"start": true}));
                                    tie["next"] = json!({"bar": number, "type": ev["type"].clone(), "dots": ev["dots"].clone()});
                                    arena[frm]["tie"] = tie;
                                    ev["tie"] = json!({"stop": true, "start": has_tie(el, "start")});
                                    let (head_ev, head_bar) = match chain_of.get(&frm) {
                                        Some(&c) => (chains[c].head, chains[c].bar),
                                        None => (frm, frm_bar),
                                    };
                                    let mut hf = Map::new();
                                    hf.insert("bar".into(), json!(head_bar));
                                    if let Some(pos) = arena[head_ev].get("pos").and_then(|p| p.as_object()) {
                                        for (k, v) in pos {
                                            hf.insert(k.clone(), v.clone());
                                        }
                                    }
                                    ev["held_from"] = Value::Object(hf);
                                    let c = match chain_of.get(&frm) {
                                        Some(&c) => c,
                                        None => {
                                            chains.push(Chain { head: frm, bar: frm_bar, length: gi(&arena[frm], "dur_ticks", 0), count: 1 });
                                            chain_of.insert(frm, chains.len() - 1);
                                            chains.len() - 1
                                        }
                                    };
                                    chains[c].length += gi(&ev, "dur_ticks", 0);
                                    chains[c].count += 1;
                                    chain_of.insert(me, c);
                                }
                            }
                            if has_tie(el, "start") {
                                let mut tie = ev.get("tie").filter(|t| truthy(Some(t))).cloned().unwrap_or(json!({}));
                                tie["start"] = json!(true);
                                ev["tie"] = tie;
                                pending.push((me, mp, number));
                                if let std::collections::hash_map::Entry::Vacant(v) = chain_of.entry(me) {
                                    chains.push(Chain { head: me, bar: number, length: gi(&ev, "dur_ticks", 0), count: 1 });
                                    v.insert(chains.len() - 1);
                                }
                            }
                        }
                        arena.push(ev);
                        events.push(me);
                        last = Some(me);
                    }
                    _ => {}
                }
            }
            let mut bar = Map::new();
            bar.insert("number".into(), json!(number));
            bar.insert("key_fifths".into(), json!(fifths));
            bar.insert("time".into(), time.clone());
            bar.insert("tempo_bpm".into(), tempo.map(|t| json!(t)).unwrap_or(Value::Null));
            bar.insert("rehearsal".into(), rehearsal.map(Value::String).unwrap_or(Value::Null));
            bars.push((bar, events));
            part_q += if length > 0 { length as f64 / divisions as f64 } else { 4.0 * gi(&time, "beats", 4) as f64 / gi(&time, "beat_type", 4) as f64 };
        }
        for c in &chains {
            if c.count > 2 && truthy(arena[c.head].get("tie")) {
                arena[c.head]["tie"]["chain_beats"] = json!(c.length as f64 / TICKS_PER_QUARTER as f64);
            }
        }
        let bars_v: Vec<Value> = bars
            .into_iter()
            .map(|(meta, evs)| {
                let mut b = Map::new();
                b.insert("number".into(), meta["number"].clone());
                b.insert("events".into(), Value::Array(evs.iter().map(|&i| arena[i].clone()).collect()));
                for k in ["key_fifths", "time", "tempo_bpm", "rehearsal"] {
                    b.insert(k.into(), meta[k].clone());
                }
                Value::Object(b)
            })
            .collect();
        let mut part = Map::new();
        part.insert("id".into(), part_el.attribute("id").map(|s| json!(s)).unwrap_or(Value::Null));
        part.insert("name".into(), json!(name));
        part.insert("name_nb".into(), json!(nb_part_name(&name)));
        part.insert("instrument".into(), inst.clone().map(Value::String).unwrap_or(Value::Null));
        part.insert("instrument_nb".into(), inst.as_deref().filter(|i| !i.is_empty()).map(|i| json!(instrument_nb(i))).unwrap_or(Value::Null));
        part.insert("transpose".into(), transpose);
        part.insert("percussion".into(), json!(percussion));
        part.insert("bars".into(), Value::Array(bars_v));
        parts.push(Value::Object(part));
    }

    // Tempo marks are global but usually written in one part only: share them with every part.
    let nbars0 = parts.first().map(|p| p["bars"].as_array().unwrap().len()).unwrap_or(0);
    for b in 0..nbars0 {
        let tempo = parts.iter().find_map(|p| p["bars"].as_array().unwrap().get(b).map(|x| x["tempo_bpm"].clone()).filter(|t| truthy(Some(t))));
        if let Some(t) = tempo {
            for p in parts.iter_mut() {
                if let Some(bar) = p["bars"].as_array_mut().unwrap().get_mut(b) {
                    if bar["tempo_bpm"].is_null() {
                        bar["tempo_bpm"] = t.clone();
                    }
                }
            }
        }
    }

    // The pickup is not one of the bars counted.
    let total = parts.iter().map(|p| p["bars"].as_array().unwrap().iter().filter(|b| gi(b, "number", 1) != PICKUP_BAR).count()).max().unwrap_or(0);
    let mut d = Map::new();
    d.insert("version".into(), json!(1));
    d.insert("title".into(), json!(title));
    d.insert("total_bars".into(), json!(total));
    d.insert("free_regions".into(), json!([]));
    if let (Some(c), Some(p0)) = (composition, parts.first()) {
        d.insert("free_regions".into(), free_regions(c, &measure_starts, p0));
    }
    d.insert("parts".into(), Value::Array(parts));
    Ok(Value::Object(d))
}

fn free_regions(comp: &Value, measure_starts: &[f64], part: &Value) -> Value {
    let tpb = gi(comp, "ticks_per_beat", 24) as f64;
    let bars = part["bars"].as_array().unwrap();
    let bar_at = |q: f64| -> Value {
        let i = measure_starts.iter().enumerate().filter(|(_, s)| **s <= q + 1e-9).map(|(k, _)| k).max().unwrap_or(0);
        let i = (i as i64).max(0).min(bars.len() as i64 - 1);
        if i < 0 {
            return Value::Null;
        }
        bars[i as usize]["number"].clone()
    };
    let mut out = Vec::new();
    for r in comp.get("free_regions").and_then(|x| x.as_array()).map(|a| a.as_slice()).unwrap_or(&[]) {
        let (sq, eq) = (gi(r, "start", 0) as f64 / tpb, gi(r, "end", 0) as f64 / tpb);
        let e = eq - 1e-6;
        let mut m = Map::new();
        m.insert("start_bar".into(), bar_at(sq));
        m.insert("end_bar".into(), bar_at(if sq > e { sq } else { e }));
        m.insert("start_s".into(), r.get("start_s").cloned().unwrap_or(json!(0.0)));
        m.insert("end_s".into(), r.get("end_s").cloned().unwrap_or(json!(0.0)));
        m.insert("tempo_bpm".into(), r.get("tempo_bpm").cloned().unwrap_or(Value::Null));
        m.insert("notation".into(), r.get("notation").cloned().unwrap_or(json!("proportional")));
        m.insert("label".into(), r.get("label").cloned().unwrap_or(json!("ad lib.")));
        out.push(Value::Object(m));
    }
    Value::Array(out)
}

// ---------------------------------------------------------------------------
// walk and export

fn region_at(doc: &Value, bar: i64) -> Option<usize> {
    doc["free_regions"].as_array()?.iter().position(|r| gi(r, "start_bar", i64::MAX) <= bar && bar <= gi(r, "end_bar", i64::MIN))
}

fn is_tie_continuation(ev: &Value) -> bool {
    ev.get("tie").is_some_and(|t| truthy(t.get("stop")))
}

fn is_rest_bar(bar: &Value) -> bool {
    let e = bar["events"].as_array().map(|a| a.as_slice()).unwrap_or(&[]);
    e.len() == 1 && gs(&e[0], "kind") == Some("bar-rest")
}

/// The announcer's view of a part.
pub fn part_of(doc: &Value, part_index: usize) -> Part {
    let p = &doc["parts"][part_index];
    let s = |k: &str| gs(p, k).map(|x| x.to_string());
    Part { name: s("name").unwrap_or_default(), name_nb: s("name_nb"), instrument: s("instrument"), instrument_nb: s("instrument_nb"), transpose: present(p.get("transpose")).cloned() }
}

/// The announcer's view of bar `b` (index) of a part, arriving from `ctx`.
pub fn bar_of(doc: &Value, part_index: usize, b: usize, ctx: &Context) -> Bar {
    let bars = bars_of(doc, part_index);
    // A bar the document does not have reads as an empty one.
    let bar = bars.get(b).unwrap_or(&Value::Null);
    let prev = if b > 0 { bars.get(b - 1) } else { None };
    let number = gi(bar, "number", b as i64 + 1);
    let region = region_at(doc, number);
    let prev_region = ctx.bar.and_then(|cb| region_at(doc, cb));
    let entering = region.is_some() && region != prev_region;
    let a_tempo = region.is_none() && prev_region.is_some();
    let region_v = region.map(|i| doc["free_regions"][i].clone());
    let tempo_of = |x: &Value| present(x.get("tempo_bpm")).and_then(|t| t.as_f64());
    let mut tempo = tempo_of(bar);
    if let Some(r) = &region_v {
        if gs(r, "notation").unwrap_or("proportional") == "proportional" {
            tempo = None;
        }
    }
    if a_tempo {
        if tempo.is_none_or(|t| t == 0.0) {
            tempo = bars[..b].iter().rev().find(|x| tempo_of(x).is_some_and(|t| t != 0.0) && region_at(doc, gi(x, "number", 0)).is_none()).and_then(tempo_of);
        }
    } else if tempo.is_some() && prev.is_some() {
        let eff = bars[..b].iter().rev().find_map(|x| tempo_of(x).filter(|t| *t != 0.0));
        if eff == tempo {
            tempo = None;
        }
    }
    let key = gi(bar, "key_fifths", 0);
    Bar {
        number,
        key_fifths: key,
        key_changed: prev.is_some_and(|p| p.get("key_fifths") != bar.get("key_fifths")),
        time_changed: if prev.is_some_and(|p| p.get("time") != bar.get("time")) { bar.get("time").cloned() } else { None },
        tempo_marked: tempo,
        rehearsal: gs(bar, "rehearsal").map(|s| s.to_string()),
        free_region: region_v,
        entering_region: entering,
        a_tempo: a_tempo && tempo.is_some(),
        total_bars: gi(doc, "total_bars", 0),
    }
}

fn plain_bar(b: &Bar) -> Bar {
    Bar { entering_region: false, a_tempo: false, key_changed: false, time_changed: None, tempo_marked: None, rehearsal: None, ..b.clone() }
}

/// (bar heading, announcements) for every bar of a part, walking note by note as a reader would.
pub fn part_lines(doc: &Value, part_index: usize, s: &Settings) -> Vec<(String, Vec<String>)> {
    let l = Lex::of(s);
    let ap = part_of(doc, part_index);
    let bars = bars_of(doc, part_index);
    let mut ctx = Context::default();
    let mut out = Vec::new();
    let here = |ctx: &mut Context, number: i64| {
        *ctx = Context { part: Some(ap.name.clone()), bar: Some(number), pitch_mode: Some(s.pitch_mode.clone()) };
    };
    let mut b = 0;
    while b < bars.len() {
        let bar = &bars[b];
        let abar = bar_of(doc, part_index, b, &ctx);
        let number = abar.number;
        let default_events = vec![json!({"kind": "bar-rest", "bars": 1})];
        let events = bar["events"].as_array().filter(|a| !a.is_empty()).unwrap_or(&default_events);
        if events.len() == 1 && gs(&events[0], "kind") == Some("bar-rest") {
            let mut run = 1;
            while b + run < bars.len() && is_rest_bar(&bars[b + run]) {
                run += 1;
            }
            let ev = json!({"kind": "bar-rest", "bars": run});
            let line = announce(&ap, &abar, &ev, &ctx, s, true);
            out.push((l.bar_heading(number, if run > 1 { Some(number + run as i64 - 1) } else { None }), vec![line]));
            here(&mut ctx, number);
            b += run;
            continue;
        }
        let mut lines = Vec::new();
        let mut first = true;
        for ev in events {
            if is_tie_continuation(ev) {
                continue;
            }
            let v = if first { abar.clone() } else { plain_bar(&abar) };
            lines.push(announce(&ap, &v, ev, &ctx, s, first));
            here(&mut ctx, number);
            first = false;
        }
        if lines.is_empty() {
            let held = held_event(&events[0]);
            lines.push(announce(&ap, &abar, &held, &ctx, s, true));
            here(&mut ctx, number);
        }
        out.push((l.bar_heading(number, None), lines));
        b += 1;
    }
    out
}

/// The `held` event for a tie continuation (the note from an earlier bar is still sounding).
pub fn held_event(cont: &Value) -> Value {
    let g = |k: &str| cont.get(k).cloned().unwrap_or(Value::Null);
    let mut m = Map::new();
    m.insert("kind".into(), json!("held"));
    for k in ["pos", "written", "concert", "held_from"] {
        m.insert(k.into(), g(k));
    }
    Value::Object(m)
}

fn part_title(doc: &Value, i: usize, s: &Settings) -> String {
    let p = &doc["parts"][i];
    let name = gs(p, "name").unwrap_or("").to_string();
    if s.nb() {
        gs(p, "name_nb").filter(|n| !n.is_empty()).map(|n| n.to_string()).unwrap_or(name)
    } else {
        name
    }
}

/// The parts to export: those asked for that the document has (in the order asked), or all.
fn part_indices(doc: &Value, parts: Option<&[usize]>) -> Vec<usize> {
    let n = doc["parts"].as_array().map(|a| a.len()).unwrap_or(0);
    match parts {
        Some(p) => p.iter().copied().filter(|&i| i < n).collect(),
        None => (0..n).collect(),
    }
}

/// Python `html.escape` (quotes included).
fn escape(s: &str) -> String {
    s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;").replace('\'', "&#x27;")
}

/// HTML export: `<h2>` per part, `<h3>` per bar, a list of announcements.
pub fn to_html(doc: &Value, s: &Settings, parts: Option<&[usize]>) -> String {
    let title = escape(gs(doc, "title").unwrap_or(""));
    let lang = if s.nb() { "nb" } else { "en" };
    let mut out = format!("<!DOCTYPE html>\n<html lang=\"{lang}\">\n<head><meta charset=\"utf-8\"><title>{title}</title></head>\n<body>\n<h1>{title}</h1>\n");
    for i in part_indices(doc, parts) {
        out.push_str(&format!("<h2>{}</h2>\n", escape(&part_title(doc, i, s))));
        for (heading, lines) in part_lines(doc, i, s) {
            out.push_str(&format!("<h3>{}</h3>\n<ul>\n", escape(&heading)));
            for x in lines {
                out.push_str(&format!("<li>{}</li>\n", escape(&x)));
            }
            out.push_str("</ul>\n");
        }
    }
    out.push_str("</body>\n</html>\n");
    out
}

/// Plain-text export.
pub fn to_text(doc: &Value, s: &Settings, parts: Option<&[usize]>) -> String {
    let mut out = format!("{}\n\n", gs(doc, "title").unwrap_or(""));
    for i in part_indices(doc, parts) {
        let t = part_title(doc, i, s);
        out.push_str(&format!("{t}\n{}\n\n", "=".repeat(t.chars().count())));
        for (heading, lines) in part_lines(doc, i, s) {
            out.push_str(&heading);
            out.push('\n');
            for x in lines {
                out.push_str(&format!("  {x}\n"));
            }
            out.push('\n');
        }
    }
    out
}

// ---------------------------------------------------------------------------
// navigation (spec §5)

/// A position in a TalkingScore document: indices of part, bar and event.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Cursor {
    pub part: usize,
    pub bar: usize,
    pub event: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Unit {
    /// Next event in the part, skipping tie continuations.
    Note,
    /// First event of the next bar.
    Bar,
    /// Same time position in the next part.
    Part,
    /// Next event with confidence below 0.7 that has not been checked.
    Uncertain,
}

fn bars_of(doc: &Value, part: usize) -> &[Value] {
    doc["parts"].get(part).and_then(|p| p["bars"].as_array()).map(|a| a.as_slice()).unwrap_or(&[])
}

fn events_of(bar: &Value) -> &[Value] {
    bar["events"].as_array().map(|a| a.as_slice()).unwrap_or(&[])
}

fn is_uncertain(ev: &Value) -> bool {
    present(ev.get("confidence")).and_then(|c| c.as_f64()).is_some_and(|c| c < UNCERTAIN_BELOW) && !truthy(ev.get("checked"))
}

/// Every stop of a part in reading order: (bar, event), with tie continuations
/// left out except where a bar holds nothing else.
fn stops(doc: &Value, part: usize) -> Vec<(usize, usize)> {
    let mut out = Vec::new();
    for (b, bar) in bars_of(doc, part).iter().enumerate() {
        let before = out.len();
        for (e, ev) in events_of(bar).iter().enumerate() {
            if !is_tie_continuation(ev) {
                out.push((b, e));
            }
        }
        if out.len() == before {
            out.push((b, 0));
        }
    }
    out
}

/// The cursor one step away, or None at either end of the score.
pub fn navigate(doc: &Value, c: Cursor, unit: Unit, forward: bool) -> Option<Cursor> {
    let nparts = doc["parts"].as_array().map(|a| a.len()).unwrap_or(0);
    match unit {
        Unit::Part => {
            let p = if forward { c.part.checked_add(1)? } else { c.part.checked_sub(1)? };
            if p >= nparts {
                return None;
            }
            let bars = bars_of(doc, p);
            let b = c.bar.min(bars.len().checked_sub(1)?);
            let tick = bars_of(doc, c.part).get(c.bar).and_then(|bar| events_of(bar).get(c.event)).map(|e| gi(e, "tick", 0)).unwrap_or(0);
            let e = events_of(&bars[b]).iter().rposition(|e| gi(e, "tick", 0) <= tick).unwrap_or(0);
            Some(Cursor { part: p, bar: b, event: e })
        }
        Unit::Bar => {
            let bars = bars_of(doc, c.part);
            let b = if forward { c.bar.checked_add(1)? } else { c.bar.checked_sub(1)? };
            (b < bars.len()).then_some(Cursor { part: c.part, bar: b, event: 0 })
        }
        Unit::Note | Unit::Uncertain => {
            let st = stops(doc, c.part);
            let bars = bars_of(doc, c.part);
            let ok = |&(b, e): &(usize, usize)| unit == Unit::Note || events_of(&bars[b]).get(e).is_some_and(is_uncertain);
            let found = if forward {
                st.iter().filter(|&&x| x > (c.bar, c.event)).find(|x| ok(x)).copied()
            } else {
                st.iter().rev().filter(|&&x| x < (c.bar, c.event)).find(|x| ok(x)).copied()
            };
            found.map(|(b, e)| Cursor { part: c.part, bar: b, event: e })
        }
    }
}

/// The announcement at a cursor, arriving from `ctx`. A tie continuation is
/// spoken as `held`; the bar's changes go with its first stop (or `by_bar`).
pub fn announce_at(doc: &Value, c: Cursor, ctx: &Context, s: &Settings, by_bar: bool) -> Result<String, String> {
    let bars = bars_of(doc, c.part);
    let bar = bars.get(c.bar).ok_or("bar out of range")?;
    let part = part_of(doc, c.part);
    let abar = bar_of(doc, c.part, c.bar, ctx);
    let evs = events_of(bar);
    if evs.is_empty() || (evs.len() == 1 && gs(&evs[0], "kind") == Some("bar-rest")) {
        let mut run = 1;
        while c.bar + run < bars.len() && is_rest_bar(&bars[c.bar + run]) {
            run += 1;
        }
        return Ok(announce(&part, &abar, &json!({"kind": "bar-rest", "bars": run}), ctx, s, true));
    }
    let ev = evs.get(c.event).ok_or("event out of range")?;
    let first = evs.iter().position(|e| !is_tie_continuation(e));
    if is_tie_continuation(ev) {
        return Ok(announce(&part, &abar, &held_event(ev), ctx, s, by_bar || first.is_none()));
    }
    let lead = by_bar || first == Some(c.event);
    let view = if lead { abar } else { plain_bar(&abar) };
    Ok(announce(&part, &view, ev, ctx, s, lead))
}

/// Number of parts, bars of a part and events of a bar.
pub fn shape(doc: &Value) -> Vec<Vec<usize>> {
    doc["parts"].as_array().map(|ps| ps.iter().enumerate().map(|(i, _)| bars_of(doc, i).iter().map(|b| events_of(b).len()).collect()).collect()).unwrap_or_default()
}

// ---------------------------------------------------------------------------
// JSON forms of the announcer inputs (for bindings that pass JSON)

pub fn settings_from_json(v: &Value) -> Settings {
    let d = Settings::default();
    let s = |k: &str, d: String| gs(v, k).map(String::from).unwrap_or(d);
    Settings {
        lang: s("lang", d.lang),
        pitch_mode: s("pitch_mode", d.pitch_mode),
        verbosity: s("verbosity", d.verbosity),
        octave_style: s("octave_style", d.octave_style),
        announce_confident: v.get("announce_confident").and_then(|x| x.as_bool()).unwrap_or(false),
    }
}

pub fn context_from_json(v: &Value) -> Context {
    Context { part: gs(v, "part").map(String::from), bar: v.get("bar").and_then(|x| x.as_i64()), pitch_mode: gs(v, "pitch_mode").map(String::from) }
}

pub fn part_from_json(v: &Value) -> Part {
    let s = |k: &str| gs(v, k).map(String::from);
    Part { name: s("name").unwrap_or_default(), name_nb: s("name_nb"), instrument: s("instrument"), instrument_nb: s("instrument_nb"), transpose: present(v.get("transpose")).cloned() }
}

/// `{"number", "key_fifths", "key_changed", "time_changed", "tempo_bpm", "rehearsal",
///   "free_region", "entering_region", "a_tempo", "total_bars"}`.
pub fn bar_from_json(v: &Value) -> Bar {
    let b = |k: &str| v.get(k).and_then(|x| x.as_bool()).unwrap_or(false);
    Bar {
        number: gi(v, "number", 1),
        key_fifths: gi(v, "key_fifths", 0),
        key_changed: b("key_changed"),
        time_changed: present(v.get("time_changed")).cloned(),
        tempo_marked: present(v.get("tempo_bpm")).and_then(|x| x.as_f64()),
        rehearsal: gs(v, "rehearsal").map(String::from),
        free_region: present(v.get("free_region")).cloned(),
        entering_region: b("entering_region"),
        a_tempo: b("a_tempo"),
        total_bars: gi(v, "total_bars", 0),
    }
}
