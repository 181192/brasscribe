//! Playing instructions: the tab as sentences, for a screen reader or a braille display.
//!
//! [`write_playing_instructions`] says, bar by bar and beat by beat, which string and fret to play
//! and for how long, in English or Norwegian Bokmål. It reads the same plan of the score as the
//! MusicXML and the text tab, so all three hold the same notes. The same input always gives the
//! same text.
//!
//! The words follow the talking score of the brass parts (`docs/accessibility/talking-score-spec.md`):
//! bar headings, beat positions ("2 and", "2-og"), note values, and the Norwegian note names (H,
//! B, Ess, Ass). One [`Lex`] holds both languages, chosen by `lang`: "en", or "nb" or "no", with or
//! without a region. Strings are named by number, never by note, and accidentals are written as words.

use std::collections::HashMap;

use crate::tab::{doubtful, number, open_name, uses_flats, value, Plan, Symbol, TabOptions, TabScore, Written};
use crate::instrument::{preset, Instrument};
use crate::text::{arrivals, clean_text, crowded, ring_starts, Arrival, TextOptions};

/// The words of one language.
struct Lex {
    nb: bool,
}

/// Written type, full name, name of the rest.
const EN_VALUES: [(&str, &str, &str); 6] = [
    ("whole", "whole note", "whole rest"),
    ("half", "half note", "half rest"),
    ("quarter", "quarter note", "quarter rest"),
    ("eighth", "eighth note", "eighth rest"),
    ("16th", "sixteenth note", "sixteenth rest"),
    ("32nd", "thirty-second note", "thirty-second rest"),
];
const NB_VALUES: [(&str, &str, &str); 6] = [
    ("whole", "helnote", "helpause"),
    ("half", "halvnote", "halvpause"),
    ("quarter", "fjerdedelsnote", "fjerdedelspause"),
    ("eighth", "åttendedelsnote", "åttendedelspause"),
    ("16th", "sekstendedelsnote", "sekstendedelspause"),
    ("32nd", "trettitodelsnote", "trettitodelspause"),
];

/// Names of the preset instruments in Norwegian; any other name is kept.
const NB_INSTRUMENTS: [(&str, &str); 9] = [
    ("Guitar", "Gitar"),
    ("7-string guitar", "7-strengs gitar"),
    ("8-string guitar", "8-strengs gitar"),
    ("5-string bass", "5-strengs bass"),
    ("6-string bass", "6-strengs bass"),
    ("Ukulele (high G)", "Ukulele (høy G)"),
    ("Ukulele (low G)", "Ukulele (lav G)"),
    ("Baritone ukulele", "Barytonukulele"),
    ("Mandolin", "Mandolin"),
];

/// "en" or "nb" for a language tag that is one of them, in any case, alone or followed by a region
/// or other subtags ("en-GB", "nb_NO"). "no" is Norwegian Bokmål too, as the talking score takes
/// it. None for any other tag.
pub fn instructions_language(lang: &str) -> Option<&'static str> {
    let l = lang.to_lowercase();
    match l.split(['-', '_']).next() {
        Some("en") => Some("en"),
        Some("nb") | Some("no") => Some("nb"),
        _ => None,
    }
}

/// Whether the instrument's strings are pairs played as one, as the mandolin preset's are: it has
/// that preset's strings and scale, whatever it is called and wherever its capo is.
fn paired_strings(inst: &Instrument) -> bool {
    preset("mandolin").is_some_and(|m| m.tuning.strings == inst.tuning.strings && m.scale_length_mm == inst.scale_length_mm)
}

fn capitalised(text: &str) -> String {
    let mut chars = text.chars();
    chars.next().map_or(String::new(), |c| c.to_uppercase().chain(chars).collect())
}

impl Lex {
    fn t<'a>(&self, en: &'a str, nb: &'a str) -> &'a str {
        if self.nb {
            nb
        } else {
            en
        }
    }

    fn decimal(&self, text: String) -> String {
        if self.nb {
            text.replace('.', ",")
        } else {
            text
        }
    }

    fn bar(&self, n: usize) -> String {
        format!("{} {n}", self.t("bar", "takt"))
    }

    fn bar_heading(&self, a: usize, b: Option<usize>) -> String {
        let w = self.t("Bar", "Takt");
        match b {
            None => format!("{w} {a}"),
            Some(b) => format!("{w}{} {a}\u{2013}{b}", if self.nb { "" } else { "s" }),
        }
    }

    fn pickup(&self) -> &str {
        self.t("Pickup", "Opptakt")
    }

    /// Where a measure is, in a sentence: "bar 3", "the pickup".
    fn in_measure(&self, number: Option<usize>) -> String {
        number.map_or(self.t("the pickup", "opptakten").to_string(), |n| self.bar(n))
    }

    /// A place in the bar: a beat and the part of it that has passed, in lowest terms. `in_three`
    /// says the beat is a dotted quarter: its parts are its eighths and sixteenths, not a triplet.
    fn position(&self, beat: i64, num: i64, den: i64, in_three: bool) -> String {
        let b = beat;
        // In sixths of the beat: the even ones are its three eighths, all six its sixteenths.
        let sixths = (in_three && num > 0 && 6 % den == 0).then(|| num * 6 / den);
        let named = match ((num, den), self.nb) {
            ((0, _), _) => Some(b.to_string()),
            (_, false) if sixths.is_some_and(|k| k % 2 == 0) => sixths.map(|k| format!("{b}, eighth {}", k / 2 + 1)),
            (_, false) if sixths.is_some() => sixths.map(|k| format!("{b}, sixteenth {}", k + 1)),
            (_, true) if sixths.is_some_and(|k| k % 2 == 0) => sixths.map(|k| format!("{b}, {}. åttendedel", k / 2 + 1)),
            (_, true) if sixths.is_some() => sixths.map(|k| format!("{b}, {}. sekstendedel", k + 1)),
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
        format!("{} {}", self.t("Beat", "Slag"), named.unwrap_or_else(|| format!("{b} {} {num}/{den}", self.t("plus", "pluss"))))
    }

    fn dots(&self, dots: u8) -> &str {
        match dots {
            0 => "",
            _ => self.t("dotted ", "punktert "),
        }
    }

    /// A length in ticks as a note value, or as a rest: "dotted quarter note", "eighth note in a
    /// triplet". A length no single value has is counted in quarter notes.
    fn length(&self, ticks: i64, rest: bool) -> String {
        let Some((typ, dots, triplet)) = value(ticks) else {
            let quarters = self.decimal(format!("{:.2}", ticks as f64 / 24.0));
            return match (rest, self.nb) {
                (false, false) => format!("note of {quarters} quarter notes"),
                (true, false) => format!("rest of {quarters} quarter notes"),
                (false, true) => format!("tone på {quarters} fjerdedeler"),
                (true, true) => format!("pause på {quarters} fjerdedeler"),
            };
        };
        let table = if self.nb { &NB_VALUES } else { &EN_VALUES };
        let name = table.iter().find(|v| v.0 == typ).map_or(typ, |v| if rest { v.2 } else { v.1 });
        format!("{}{name}{}", self.dots(dots), if triplet { self.t(" in a triplet", " i triol") } else { "" })
    }

    fn tied(&self, lengths: &[String]) -> String {
        lengths.join(self.t(" tied to ", " bundet til "))
    }

    fn string(&self, n: u8) -> String {
        format!("{} {n}", self.t("string", "streng"))
    }

    fn fret(&self, n: u8) -> String {
        format!("{} {n}", self.t("fret", "bånd"))
    }

    fn nb_name(step: char, alter: i32) -> String {
        let letter = if step == 'B' { 'H' } else { step };
        match (step, alter) {
            ('B', -1) => "B".into(),
            ('E', -1) => "Ess".into(),
            ('A', -1) => "Ass".into(),
            (_, -1) => format!("{letter}ess"),
            (_, 1) => format!("{letter}iss"),
            (_, 2) => format!("{letter} dobbeltkryss"),
            (_, -2) => format!("{letter} dobbelt-b"),
            _ => letter.to_string(),
        }
    }

    /// A note name without its octave: "E-flat", "Ess".
    fn note_name(&self, step: char, alter: i32) -> String {
        if self.nb {
            return Lex::nb_name(step, alter);
        }
        let accidental = match alter {
            2 => "-double-sharp",
            1 => "-sharp",
            -1 => "-flat",
            -2 => "-double-flat",
            _ => "",
        };
        format!("{step}{accidental}")
    }

    /// A tuning's name as it is said: sharp and flat signs as words, and in Norwegian the note
    /// names of the language, so the name agrees with the open strings said after it ("H standard",
    /// "Drop H", "DGHE", "Ess standard"). A word is a note name, or a row of them, when it holds
    /// only the letters A to G in capitals, each with or without a sign; any other word is kept.
    fn tuning_name(&self, name: &str) -> String {
        let words: Vec<String> = name
            .split(' ')
            .map(|word| {
                let chars: Vec<char> = word.chars().collect();
                let sign = |c: char| matches!(c, '\u{266d}' | '\u{266f}');
                let notes = !chars.is_empty() && ('A'..='G').contains(&chars[0]) && chars.iter().enumerate().all(|(i, &c)| ('A'..='G').contains(&c) || (sign(c) && !sign(chars[i - 1])));
                if !notes {
                    let said = match (word, self.nb) {
                        ("high", true) => "høy",
                        ("low", true) => "lav",
                        _ => word,
                    };
                    return said.replace('\u{266d}', self.t("-flat", "-b")).replace('\u{266f}', self.t("-sharp", "-kryss"));
                }
                let mut out = String::new();
                for (i, &c) in chars.iter().enumerate() {
                    if sign(c) {
                        continue;
                    }
                    let alter = match chars.get(i + 1) {
                        Some('\u{266d}') => -1,
                        Some('\u{266f}') => 1,
                        _ => 0,
                    };
                    out.push_str(&self.note_name(c, alter));
                }
                out
            })
            .collect();
        words.join(" ")
    }

    fn instrument(&self, name: &str) -> String {
        if self.nb {
            if let Some((_, nb)) = NB_INSTRUMENTS.iter().find(|(en, _)| *en == name) {
                return nb.to_string();
            }
        }
        name.to_string()
    }

    /// The time signature: its two numbers in English, and in Norwegian what a bar holds ("4
    /// fjerdedeler", "2 halve", "1 hel").
    fn time(&self, beats: i64, unit: i64) -> String {
        if !self.nb {
            return format!("Time signature: {beats} {unit}.");
        }
        let one = beats == 1;
        let name = match unit {
            1 if one => "hel".to_string(),
            1 => "hele".into(),
            2 if one => "halv".into(),
            2 => "halve".into(),
            4 if one => "fjerdedel".into(),
            4 => "fjerdedeler".into(),
            8 if one => "åttendedel".into(),
            8 => "åttendedeler".into(),
            16 if one => "sekstendedel".into(),
            16 => "sekstendedeler".into(),
            _ => format!("{unit}-deler"),
        };
        format!("Taktart: {beats} {name}.")
    }
}

/// What is said about one written note. `shared` is the string a note cannot have because another
/// note of its chord is on it ([`crowded`]).
fn note_words(l: &Lex, w: &Written, reached: Option<Arrival>, shared: Option<u8>, doubt: bool) -> String {
    let mut parts = Vec::new();
    let name = || format!("{} {}", l.note_name(w.spelled.step, w.spelled.alter), w.spelled.octave);
    match w.place.filter(|_| shared.is_none()) {
        Some((string, fret)) => {
            parts.push(l.string(string));
            parts.push(if w.dead {
                l.t("dead note", "dempet tone").to_string()
            } else if fret == 0 {
                l.t("open", "løs").to_string()
            } else {
                l.fret(fret)
            });
            match reached {
                Some(Arrival::HammerOn) => parts.push("hammer-on".into()),
                Some(Arrival::PullOff) => parts.push("pull-off".into()),
                Some(Arrival::Slide(Some(from))) => parts.push(format!("{} {}", l.t("slide from", "slide fra"), l.fret(from))),
                Some(Arrival::Slide(None)) => parts.push("slide".into()),
                Some(Arrival::Bend(Some(from))) => parts.push(format!("{} {}", l.t("bend up from", "bend opp fra"), l.fret(from))),
                Some(Arrival::Bend(None)) => parts.push(l.t("bend up", "bend opp").into()),
                None => {}
            }
            if w.vibrato && !w.dead {
                parts.push("vibrato".into());
            }
            if w.let_ring {
                parts.push(l.t("let ring", "la klinge").into());
            }
        }
        None => {
            parts.push(name());
            parts.push(match shared {
                Some(string) => format!("{} {string}", l.t("cannot be played together with the note on string", "kan ikke spilles sammen med tonen på streng")),
                None => l.t("no string to play it on", "ingen streng å spille den på").into(),
            });
        }
    }
    if doubt {
        parts.push(l.t("to check", "bør sjekkes").into());
    }
    parts.join(", ")
}

/// The lines before the first bar: what the instrument is and how it is set up, said once.
fn opening(l: &Lex, score: &TabScore, any_doubt: bool) -> Vec<String> {
    let inst = &score.instrument;
    let strings = inst.string_count();
    let open: Vec<i32> = inst.tuning.strings.iter().map(|s| s.open_pitch).collect();
    let flats = uses_flats(&inst.tuning.name, &open);
    let names: Vec<String> = open
        .iter()
        .rev()
        .map(|&p| {
            let (step, alter, _) = open_name(p, flats);
            l.note_name(step, alter)
        })
        .collect();
    let name = l.instrument(&clean_text(&inst.name));
    let tuning = l.tuning_name(&clean_text(&inst.tuning.name));
    let tempo = l.decimal(number(score.tempo_bpm));
    // A mandolin's strings are pairs: a reader who cannot see the instrument is told that a number is a pair.
    let courses = paired_strings(inst);
    let mut out = if l.nb {
        vec![
            if courses { format!("{name}, {strings} strengepar. Hvert par spilles som én streng og har ett nummer.") } else { format!("{name}, {strings} strenger.") },
            format!("Streng 1 er strengen nærmest gulvet når du spiller. Streng {strings} er nærmest taket."),
            format!("Stemming: {tuning}. Løse strenger fra streng {strings} til streng 1: {}.", names.join(", ")),
            if inst.capo > 0 { format!("Capo på bånd {}. Båndene telles fra capoen.", inst.capo) } else { "Ingen capo.".into() },
            format!("Tempo: {tempo} fjerdedelsnoter per minutt."),
        ]
    } else {
        vec![
            if courses { format!("{name}, {strings} pairs of strings. Each pair is played as one string and has one number.") } else { format!("{name}, {strings} strings.") },
            format!("String 1 is the string nearest the floor as you play. String {strings} is nearest the ceiling."),
            format!("Tuning: {tuning}. Open strings from string {strings} to string 1: {}.", names.join(", ")),
            if inst.capo > 0 { format!("Capo on fret {}. Frets are counted from the capo.", inst.capo) } else { "No capo.".into() },
            format!("Tempo: {tempo} quarter notes per minute."),
        ]
    };
    out.push(l.time(score.beats, score.beat_unit));
    if any_doubt {
        out.push(l.t("A note marked \"to check\" was not heard clearly.", "En tone merket «bør sjekkes» ble ikke hørt tydelig.").into());
    }
    out
}

/// Whether the beat is a dotted quarter, as the talking score counts 6/8, 9/8 and 12/8; any other
/// time is counted in its lower number.
fn in_three(score: &TabScore) -> bool {
    score.beat_unit == 8 && score.beats % 3 == 0 && score.beats > 3
}

/// The beat a tick is on, counted in the bar that starts at `bar_start`, and the part of the beat
/// that has passed, in lowest terms.
fn beat_of(score: &TabScore, tick: i64, bar_start: i64) -> (i64, i64, i64) {
    fn gcd(a: i64, b: i64) -> i64 {
        if b == 0 {
            a
        } else {
            gcd(b, a % b)
        }
    }
    let beat = (96 / score.beat_unit * if in_three(score) { 3 } else { 1 }).max(1);
    let offset = tick - bar_start;
    let (whole, rest) = (offset.div_euclid(beat), offset.rem_euclid(beat));
    let d = gcd(rest, beat).max(1);
    (whole + 1, rest / d, beat / d)
}

/// The score as playing instructions in the language of `text.lang`. Err when the score or the
/// options cannot be written (see [`TabScore::validate`]), or for a language other than "en" and
/// "nb".
///
/// - The title, then the instrument, how its strings are numbered, the tuning, the capo, the tempo
///   and the time signature, each said once.
/// - A heading per bar, and under it one line per note, chord or rest in the order they are
///   played: the beat, the string and fret of each note, and the note value. A chord's notes are
///   said from its highest-numbered string to its lowest.
/// - "Let ring" is said where the ringing starts, and once for a chord.
/// - A note held over a bar line is said once, where it starts, with every tied value; the bars
///   it is held into say which bar it came from.
/// - Bars of rest that follow each other share a heading, and a bar that is the same as an earlier
///   one says which.
/// - A slide or a bend says the fret it comes from when that is on the same string.
/// - A doubtful note ([`TabOptions::doubt_below`]) is "to check"; a note with no place is named by
///   its pitch.
pub fn write_playing_instructions(score: &TabScore, tab: &TabOptions, text: &TextOptions) -> Result<String, String> {
    let lang = instructions_language(&text.lang).ok_or_else(|| format!("playing instructions are written in en or nb, not {:?}", text.lang))?;
    let l = Lex { nb: lang == "nb" };
    let plan = Plan::new(score, tab)?;
    let reached = arrivals(&plan.events);
    let any_doubt = plan.events.iter().flat_map(|e| &e.notes).any(|w| doubtful(w, tab));

    let mut out = String::new();
    let title = clean_text(&score.title);
    if !title.is_empty() {
        out.push_str(&format!("{title}\n\n"));
    }
    for line in opening(&l, score, any_doubt) {
        out.push_str(&line);
        out.push('\n');
    }

    // Per measure: its number (None for the pickup) and its lines; no lines for a bar of rest.
    let mut bars: Vec<(Option<usize>, Vec<String>)> = Vec::new();
    // The measure each event starts in, for a bar that only holds a note on.
    let mut started_in: Vec<Option<usize>> = vec![None; plan.events.len()];
    // The tied values of each event, in order.
    let mut values: Vec<Vec<i64>> = vec![Vec::new(); plan.events.len()];
    for s in &plan.symbols {
        if let Some(e) = s.event {
            values[e].push(s.end - s.start);
        }
    }
    // The symbols are in time order, and so are the measures: each measure takes the next ones.
    let mut next = 0;
    for &(_, b, number, implicit) in &plan.measures {
        let number = (!implicit).then_some(number);
        let bar_start = b - plan.bar;
        let from = next;
        while next < plan.symbols.len() && plan.symbols[next].start < b {
            next += 1;
        }
        let symbols: &[Symbol] = &plan.symbols[from..next];
        let mut lines = Vec::new();
        // A bar that starts inside a note says where the note came from.
        if let Some(e) = symbols.first().filter(|s| !s.first).and_then(|s| s.event) {
            let from = l.in_measure(started_in[e]);
            lines.push(if l.nb { format!("Holdes fra {from}.") } else { format!("Held from {from}.") });
        }
        for sym in symbols {
            let (beat, num, den) = beat_of(score, sym.start, bar_start);
            let position = l.position(beat, num, den, in_three(score));
            let Some(e) = sym.event else {
                if !sym.whole_measure {
                    lines.push(format!("{position}. {}.", capitalised(&l.length(sym.end - sym.start, true))));
                }
                continue;
            };
            if !sym.first {
                continue;
            }
            started_in[e] = number;
            let ev = &plan.events[e];
            // From the highest-numbered string, the way a chord is strummed; notes without a string last.
            let shared = crowded(ev);
            let placed = |k: usize| ev.notes[k].place.filter(|_| shared[k].is_none());
            let mut order: Vec<usize> = (0..ev.notes.len()).collect();
            order.sort_by_key(|&k| (placed(k).is_none(), std::cmp::Reverse(placed(k).map(|p| p.0)), k));
            // "let ring" is said where the ringing starts, as the page writes it once, and once for a chord.
            let ring = ring_starts(&plan.events, e);
            let chord = ev.notes.len() > 1;
            let words: Vec<String> = order
                .iter()
                .map(|&k| {
                    let mut w = ev.notes[k].clone();
                    w.let_ring = ring && !chord;
                    note_words(&l, &w, reached[e][k], shared[k], doubtful(&w, tab))
                })
                .collect();
            let what = if chord {
                let ring = if ring { l.t(", let ring", ", la klinge") } else { "" };
                let n = words.len();
                format!("{}{ring}: {}", if l.nb { format!("Akkord, {n} toner") } else { format!("Chord, {n} notes") }, words.join("; "))
            } else {
                capitalised(&words[0])
            };
            let lengths: Vec<String> = values[e].iter().map(|&ticks| l.length(ticks, false)).collect();
            lines.push(format!("{position}. {what}. {}.", capitalised(&l.tied(&lengths))));
        }
        bars.push((number, lines));
    }

    // The first bar that says each set of lines.
    let mut first_said: HashMap<&[String], usize> = HashMap::new();
    let mut i = 0;
    while i < bars.len() {
        let (number, lines) = &bars[i];
        out.push('\n');
        let Some(n) = *number else {
            out.push_str(&format!("{}\n", l.pickup()));
            for line in lines {
                out.push_str(&format!("  {line}\n"));
            }
            i += 1;
            continue;
        };
        if lines.is_empty() {
            let run = bars[i..].iter().take_while(|b| b.1.is_empty()).count();
            if run > 1 {
                out.push_str(&format!("{}\n", l.bar_heading(n, Some(n + run - 1))));
                out.push_str(&if l.nb { format!("  Pause, {run} takter.\n") } else { format!("  Rest, {run} bars.\n") });
            } else {
                out.push_str(&format!("{}\n  {}\n", l.bar_heading(n, None), l.t("Whole-bar rest.", "Pause hele takten.")));
            }
            i += run;
            continue;
        }
        out.push_str(&format!("{}\n", l.bar_heading(n, None)));
        // The first earlier bar with the same notes. A bar that starts inside a held note is said in
        // full: what it holds depends on the bar before it.
        let held = !lines[0].starts_with(l.t("Beat", "Slag"));
        let first = if held { n } else { *first_said.entry(lines.as_slice()).or_insert(n) };
        if first < n {
            out.push_str(&if l.nb { format!("  Samme som takt {first}.\n") } else { format!("  Same as bar {first}.\n") });
        } else {
            for line in lines {
                out.push_str(&format!("  {line}\n"));
            }
        }
        i += 1;
    }
    Ok(out)
}
