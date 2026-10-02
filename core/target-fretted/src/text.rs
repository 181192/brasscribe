//! Tablature as plain text: one line per string with the fret numbers on it, for a monospace
//! font, a printed page or a message.
//!
//! [`write_tab_text`] lays out the same notes, chords, bars and marks as [`write_tab_musicxml`]
//! (both read one plan of the score), so the two never disagree. The same input always gives the
//! same text. Apart from the title and the instrument's and tuning's names, the text is ASCII:
//! sharps and flats are written `#` and `b`, so columns line up in any monospace font.
//!
//! [`write_tab_musicxml`]: crate::tab::write_tab_musicxml

use serde::{Deserialize, Serialize};

use crate::tab::{clean, doubtful, number, open_name, uses_flats, Event, Link, Plan, TabOptions, TabScore};

/// Characters per line unless [`TextOptions::width`] says otherwise: a line fits an A4 page in a
/// 10 or 11 point monospace font, and a phone held sideways.
pub const TEXT_WIDTH: usize = 72;
/// The narrowest and the widest page.
pub const MIN_TEXT_WIDTH: usize = 24;
pub const MAX_TEXT_WIDTH: usize = 400;
/// A bar is drawn on one even grid when that takes at most this many columns; a busier bar is
/// drawn beat by beat, each beat as wide as its own notes need.
const EVEN_GRID_COLUMNS: i64 = 16;

/// How the text exports are written.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct TextOptions {
    /// The text tab's longest line, in characters: [`MIN_TEXT_WIDTH`] to [`MAX_TEXT_WIDTH`].
    pub width: usize,
    /// The language of the playing instructions: "en" or "nb".
    pub lang: String,
}

impl Default for TextOptions {
    fn default() -> Self {
        TextOptions { width: TEXT_WIDTH, lang: "en".into() }
    }
}

/// Text without what could make one line look like two, or hide or reorder what it says: control
/// characters as [`clean`] leaves them out, and also the line and paragraph separators, the
/// bidirectional controls, the zero-width characters and the byte order mark. A title or a name is
/// one line of the text exports, and cannot pass for a header line of its own.
pub(crate) fn clean_text(text: &str) -> String {
    let hidden = |c: char| matches!(c, '\u{2028}' | '\u{2029}' | '\u{202A}'..='\u{202E}' | '\u{2066}'..='\u{2069}' | '\u{200B}'..='\u{200F}' | '\u{FEFF}');
    let kept: String = clean(text).chars().map(|c| if matches!(c, '\u{2028}' | '\u{2029}') { ' ' } else { c }).filter(|c| !hidden(*c)).collect();
    // One space where there were several, or a break: a line of words.
    kept.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// Per note of an event: the string it shares with an earlier note of the event, if it does. A
/// string sounds one note at a time, so the later note cannot be played with the earlier one: it is
/// not written on the string, and both text exports say so.
pub(crate) fn crowded(ev: &Event) -> Vec<Option<u8>> {
    let mut taken: Vec<u8> = Vec::new();
    ev.notes
        .iter()
        .map(|w| {
            let (string, _) = w.place?;
            if taken.contains(&string) {
                return Some(string);
            }
            taken.push(string);
            None
        })
        .collect()
}

/// How a note is reached from the note before it on its string.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Arrival {
    HammerOn,
    PullOff,
    /// Slid into, from this fret when the note before it is on the same string.
    Slide(Option<u8>),
    /// Bent up to, from this fret when the note before it is on the same string.
    Bend(Option<u8>),
}

/// Per event and written note: how the note is reached, for the notes a technique leads to. A note
/// that is not written on its string ([`crowded`]) is reached by none.
pub(crate) fn arrivals(events: &[Event]) -> Vec<Vec<Option<Arrival>>> {
    // The string and fret each open link started from. Numbers are reused from chord to chord, so
    // the latest start is the one a stop belongs to.
    let mut open: Vec<((Link, u8), (u8, u8))> = Vec::new();
    let mut out = Vec::with_capacity(events.len());
    for ev in events {
        let apart = crowded(ev);
        let reached = ev
            .notes
            .iter()
            .zip(&apart)
            .map(|(w, apart)| {
                let (string, _) = w.place.filter(|_| apart.is_none())?;
                // The fret a slide or bend comes from is only said when it is on this note's string:
                // a fret of another string is not where the finger starts.
                let from = |link: &(Link, u8)| open.iter().rev().find(|(l, _)| l == link).filter(|(_, place)| place.0 == string).map(|&(_, place)| place.1);
                let by = |want: fn(Link) -> bool| w.stops.iter().find(|(l, _)| want(*l));
                if let Some(link) = by(|l| matches!(l, Link::Bend(_))) {
                    Some(Arrival::Bend(from(link)))
                } else if let Some(link) = by(|l| l == Link::Slide) {
                    Some(Arrival::Slide(from(link)))
                } else if by(|l| l == Link::HammerOn).is_some() {
                    Some(Arrival::HammerOn)
                } else if by(|l| l == Link::PullOff).is_some() {
                    Some(Arrival::PullOff)
                } else {
                    None
                }
            })
            .collect();
        for (w, apart) in ev.notes.iter().zip(&apart) {
            if let Some(place) = w.place.filter(|_| apart.is_none()) {
                open.extend(w.starts.iter().map(|&link| (link, place)));
            }
        }
        // Only the previous event's links can be stopped: older ones are dropped.
        let keep = ev.notes.iter().map(|w| w.starts.len()).sum::<usize>();
        let drop = open.len() - keep;
        open.drain(..drop);
        out.push(reached);
    }
    out
}

/// Whether an event starts a run of ringing notes: the words "let ring" go there, once per run.
pub(crate) fn ring_starts(events: &[Event], e: usize) -> bool {
    let rings = |ev: &Event| ev.notes.iter().any(|n| n.let_ring);
    let before = e.checked_sub(1).is_some_and(|p| rings(&events[p]) && events[p].end == events[e].start);
    rings(&events[e]) && !before
}

/// A sharp or flat sign as the ASCII letter text tabs use.
fn ascii_signs(text: &str) -> String {
    text.replace('\u{266d}', "b").replace('\u{266f}', "#")
}

fn accidental(alter: i32) -> &'static str {
    match alter {
        2 => "##",
        1 => "#",
        -1 => "b",
        -2 => "bb",
        _ => "",
    }
}

fn gcd(a: i64, b: i64) -> i64 {
    if b == 0 {
        a.abs()
    } else {
        gcd(b, a % b)
    }
}

/// One bar as columns: the tick each column stands for.
struct Bar {
    /// None for a pickup, which has no number.
    number: Option<usize>,
    columns: Vec<i64>,
}

/// A run of a bar's columns on one line: the whole bar, or a piece of a bar wider than the page.
#[derive(Clone, Copy)]
struct Piece {
    bar: usize,
    from: usize,
    to: usize,
}

/// What stands in one string's cell of a column.
#[derive(Clone)]
struct Cell {
    /// What leads to the note: `-`, or the mark of a technique.
    lead: char,
    text: String,
}

/// Everything above and on the lines at one tick.
#[derive(Default, Clone)]
struct Column {
    /// One cell per string; None is an empty line.
    cells: Vec<Option<Cell>>,
    marks: String,
    ring: bool,
}

/// Stands for a space the legend is not broken at, until its lines are made.
const GLUE: &str = "\u{a0}";
/// The most bars the legend names notes of; the rest are counted.
const LEGEND_BARS: usize = 12;

/// Notes that are not on the lines, bar by bar: ("bar 3", ["D1", "C#1"]).
type Missing = Vec<(String, Vec<String>)>;

struct Legend {
    doubt: bool,
    /// The notes no string can play.
    lost: Missing,
    /// The notes whose string holds another note of their chord: "G2 (string 2)".
    crowded: Missing,
    hammer: bool,
    pull: bool,
    slide_up: bool,
    slide_down: bool,
    bend: bool,
    vibrato: bool,
    dead: bool,
    /// The forms of "let ring" that were written.
    ring: Vec<&'static str>,
}

struct Layout<'a> {
    plan: &'a Plan<'a>,
    bars: Vec<Bar>,
    /// By tick.
    columns: std::collections::BTreeMap<i64, Column>,
    /// Characters of a cell's text; a cell is one wider, for what leads to the note.
    cell: usize,
    labels: Vec<String>,
    legend: Legend,
}

/// The columns of one measure: an even grid fine enough for every start in it when that stays
/// narrow, else each beat on a grid of its own.
fn columns_of(plan: &Plan, a: i64, b: i64, starts: &[i64]) -> Vec<i64> {
    let beat = plan.beam_group;
    // The starts are in time order: those of a span are one run of them.
    let within = |from: i64, to: i64| starts[starts.partition_point(|&t| t < from)..starts.partition_point(|&t| t < to)].iter().map(move |&t| t - from);
    let even = within(a, b).fold(gcd(b - a, beat), gcd);
    if (b - a) / even <= EVEN_GRID_COLUMNS {
        return (0..(b - a) / even).map(|k| a + k * even).collect();
    }
    // Beats are counted from the bar line, also in a pickup that starts inside one.
    let bar_start = a.div_euclid(plan.bar) * plan.bar;
    let mut out = Vec::new();
    let mut from = a;
    while from < b {
        let to = (bar_start + ((from - bar_start) / beat + 1) * beat).min(b);
        let step = within(from, to).fold(to - from, gcd);
        out.extend((0..(to - from) / step).map(|k| from + k * step));
        from = to;
    }
    out
}

impl<'a> Layout<'a> {
    fn new(plan: &'a Plan<'a>) -> Layout<'a> {
        let inst = &plan.score.instrument;
        let strings = inst.string_count();
        let open: Vec<i32> = inst.tuning.strings.iter().map(|s| s.open_pitch).collect();
        let flats = uses_flats(&inst.tuning.name, &open);
        let mut labels: Vec<String> = open
            .iter()
            .map(|&p| {
                let (step, alter, _) = open_name(p, flats);
                format!("{step}{}", accidental(alter))
            })
            .collect();
        let widest = labels.iter().map(|l| l.chars().count()).max().unwrap_or(1);
        for l in &mut labels {
            *l = format!("{l:<widest$}");
        }

        let reached = arrivals(&plan.events);
        let mut legend = Legend { doubt: false, lost: Vec::new(), crowded: Vec::new(), hammer: false, pull: false, slide_up: false, slide_down: false, bend: false, vibrato: false, dead: false, ring: Vec::new() };
        let mut columns = std::collections::BTreeMap::new();
        let mut cell = 1;
        for (e, ev) in plan.events.iter().enumerate() {
            let mut col = Column { cells: vec![None; strings], marks: String::new(), ring: ring_starts(&plan.events, e) };
            let (mut lost, mut apart, mut doubt) = (Vec::new(), Vec::new(), false);
            let shared = crowded(ev);
            for (k, w) in ev.notes.iter().enumerate() {
                doubt |= doubtful(w, plan.opts);
                let name = format!("{}{}{}", w.spelled.step, accidental(w.spelled.alter), w.spelled.octave);
                // A string holds one number per column: a second note on it is named, not written.
                if let Some(string) = shared[k] {
                    apart.push(format!("{name} (string {string})"));
                    continue;
                }
                let Some((string, fret)) = w.place else {
                    lost.push(name);
                    continue;
                };
                let lead = match reached[e][k] {
                    Some(Arrival::HammerOn) => {
                        legend.hammer = true;
                        'h'
                    }
                    Some(Arrival::PullOff) => {
                        legend.pull = true;
                        'p'
                    }
                    Some(Arrival::Slide(Some(from))) if from > fret => {
                        legend.slide_down = true;
                        '\\'
                    }
                    Some(Arrival::Slide(_)) => {
                        legend.slide_up = true;
                        '/'
                    }
                    Some(Arrival::Bend(_)) => {
                        legend.bend = true;
                        'b'
                    }
                    None => '-',
                };
                let text = if w.dead {
                    legend.dead = true;
                    "x".to_string()
                } else if w.vibrato {
                    legend.vibrato = true;
                    format!("{fret}~")
                } else {
                    fret.to_string()
                };
                cell = cell.max(text.len());
                col.cells[usize::from(string) - 1] = Some(Cell { lead, text });
            }
            if !lost.is_empty() || !apart.is_empty() {
                col.marks.push('!');
                // The measures follow each other: the one an event starts in is the last that starts at or before it.
                let measure = plan.measures.partition_point(|m| m.0 <= ev.start).checked_sub(1).map(|i| plan.measures[i]);
                let bar = measure.filter(|m| !m.3).map_or("pickup".to_string(), |m| format!("bar {}", m.2));
                for (names, missing) in [(lost, &mut legend.lost), (apart, &mut legend.crowded)] {
                    match missing.last_mut().filter(|(b, _)| *b == bar) {
                        _ if names.is_empty() => {}
                        Some((_, of_bar)) => of_bar.extend(names),
                        None => missing.push((bar.clone(), names)),
                    }
                }
            }
            if doubt {
                col.marks.push('?');
                legend.doubt = true;
            }
            columns.insert(ev.start, col);
        }

        let starts: Vec<i64> = plan.events.iter().map(|e| e.start).collect();
        let bars = plan.measures.iter().map(|&(a, b, number, implicit)| Bar { number: (!implicit).then_some(number), columns: columns_of(plan, a, b, &starts) }).collect();
        Layout { plan, bars, columns, cell, labels, legend }
    }

    /// Characters a piece takes after the line's opening bar line.
    fn width(&self, p: Piece) -> usize {
        let closing = if p.to < self.bars[p.bar].columns.len() {
            0
        } else if p.bar + 1 == self.bars.len() {
            2
        } else {
            1
        };
        (p.to - p.from) * (self.cell + 1) + closing
    }

    /// The bars shared out on lines of at most `width` characters. A bar is never divided, unless
    /// it alone is wider than the page: then it takes lines of its own.
    fn systems(&self, width: usize) -> Vec<Vec<Piece>> {
        let room = width - self.labels[0].chars().count() - 1;
        let mut out: Vec<Vec<Piece>> = Vec::new();
        let (mut line, mut used) = (Vec::new(), 0);
        for (bar, b) in self.bars.iter().enumerate() {
            let whole = Piece { bar, from: 0, to: b.columns.len() };
            let w = self.width(whole);
            if w <= room {
                if used + w > room {
                    out.push(std::mem::take(&mut line));
                    used = 0;
                }
                line.push(whole);
                used += w;
                continue;
            }
            if !line.is_empty() {
                out.push(std::mem::take(&mut line));
                used = 0;
            }
            // Room for the two closing bar lines of the last bar on every line keeps the pieces even.
            let per_line = ((room - 2) / (self.cell + 1)).max(1);
            let mut from = 0;
            while from < b.columns.len() {
                let to = (from + per_line).min(b.columns.len());
                out.push(vec![Piece { bar, from, to }]);
                from = to;
            }
        }
        if !line.is_empty() {
            out.push(line);
        }
        out
    }

    fn system(&mut self, pieces: &[Piece], out: &mut String) {
        fn put(row: &mut Vec<char>, at: usize, text: &str) {
            if row.len() < at {
                row.resize(at, ' ');
            }
            for (i, c) in text.chars().enumerate() {
                match row.get_mut(at + i) {
                    Some(slot) => *slot = c,
                    None => row.push(c),
                }
            }
        }
        let mut lines: Vec<Vec<char>> = self.labels.iter().map(|l| format!("{l}|").chars().collect()).collect();
        let (mut numbers, mut marks) = (Vec::new(), Vec::new());
        let mut rings: Vec<usize> = Vec::new();
        for p in pieces {
            let bar = &self.bars[p.bar];
            let at = lines[0].len();
            let end = at + self.width(*p);
            if let (0, Some(n)) = (p.from, bar.number) {
                let text = n.to_string();
                // Where it has room: after the number before it, and inside its bar.
                if numbers.len() < at && at + text.len() <= end {
                    put(&mut numbers, at, &text);
                }
            }
            for tick in &bar.columns[p.from..p.to] {
                let at = lines[0].len();
                let col = self.columns.get(tick);
                for (s, line) in lines.iter_mut().enumerate() {
                    match col.and_then(|c| c.cells[s].as_ref()) {
                        Some(c) => {
                            line.push(c.lead);
                            line.extend(format!("{:-<w$}", c.text, w = self.cell).chars());
                        }
                        None => line.extend(std::iter::repeat_n('-', self.cell + 1)),
                    }
                }
                if let Some(c) = col {
                    if !c.marks.is_empty() {
                        put(&mut marks, at + 1, &c.marks);
                    }
                    if c.ring {
                        rings.push(at + 1);
                    }
                }
            }
            let closing = end - lines[0].len();
            for line in &mut lines {
                line.extend(std::iter::repeat_n('|', closing));
            }
        }
        // "let ring" in full where the next one and the end of the line leave room for it.
        let mut ring = Vec::new();
        for (i, &at) in rings.iter().enumerate() {
            let room = rings.get(i + 1).map_or(lines[0].len() + 1, |&next| next.min(lines[0].len() + 1)) - at;
            let form = if room > "let ring".len() {
                "let ring"
            } else if room > "l.r.".len() {
                "l.r."
            } else {
                "r"
            };
            if !self.legend.ring.contains(&form) {
                self.legend.ring.push(form);
            }
            put(&mut ring, at, form);
        }
        for row in [numbers, ring, marks].into_iter().chain(lines) {
            if !row.is_empty() {
                out.extend(row);
                out.push('\n');
            }
        }
    }

    fn header(&self) -> String {
        let score = self.plan.score;
        let inst = &score.instrument;
        let mut out = String::new();
        let title = clean_text(&score.title);
        if !title.is_empty() {
            out.push_str(&title);
            out.push('\n');
        }
        out.push_str(&format!("{}\n", clean_text(&inst.name)));
        // The bottom line first, as the strings are named from low to high.
        let open: Vec<&str> = self.labels.iter().rev().map(|l| l.trim_end()).collect();
        out.push_str(&format!("Tuning: {} ({}), bottom line to top\n", ascii_signs(&clean_text(&inst.tuning.name)), open.join(" ")));
        if inst.capo > 0 {
            out.push_str(&format!("Capo: fret {} (frets are counted from the capo)\n", inst.capo));
        } else {
            out.push_str("Capo: none\n");
        }
        out.push_str(&format!("Tempo: {} quarter notes per minute\n", number(score.tempo_bpm)));
        out.push_str(&format!("Time: {}/{}\n", score.beats, score.beat_unit));
        out
    }

    /// The marks that occur, each with what it means, in lines of at most `width` characters.
    fn legend(&self, width: usize) -> String {
        let l = &self.legend;
        let mut rows: Vec<(String, String)> = Vec::new();
        if l.doubt {
            rows.push(("?".into(), "a note to check: it was not heard clearly".into()));
        }
        // Bar by bar, the first LEGEND_BARS of them; the notes of the others are counted.
        let named = |missing: &Missing| {
            // A bar and its notes stay on one line: the spaces inside an entry are not places to break.
            let mut bars: Vec<String> = missing.iter().take(LEGEND_BARS).map(|(bar, names)| format!("{bar}: {}", names.join(" ")).replace(' ', GLUE)).collect();
            let more: usize = missing.iter().skip(LEGEND_BARS).map(|(_, names)| names.len()).sum();
            if more > 0 {
                bars.push(format!("and{GLUE}{more}{GLUE}more"));
            }
            bars.join("; ")
        };
        if !l.lost.is_empty() {
            rows.push(("!".into(), format!("a note with no string to play it on, not in the lines: {}", named(&l.lost))));
        }
        if !l.crowded.is_empty() {
            rows.push(("!".into(), format!("a note that cannot be played together with another note on its string, not in the lines: {}", named(&l.crowded))));
        }
        for (on, mark, means) in [
            (l.hammer, "h", "hammer-on"),
            (l.pull, "p", "pull-off"),
            (l.slide_up, "/", "slide up"),
            (l.slide_down, "\\", "slide down"),
            (l.bend, "b", "bend: the string is bent up to the pitch of the fret after the b"),
            (l.vibrato, "~", "vibrato"),
            (l.dead, "x", "dead note: the string is muted"),
        ] {
            if on {
                rows.push((mark.into(), means.into()));
            }
        }
        if !l.ring.is_empty() {
            let mut forms: Vec<&str> = ["let ring", "l.r.", "r"].into_iter().filter(|f| l.ring.contains(f)).collect();
            if forms == ["let ring"] {
                forms.clear();
            }
            if !forms.is_empty() {
                rows.push((forms.join(", "), "let ring: the notes ring on".into()));
            }
        }
        let wide = rows.iter().map(|r| r.0.len()).max().unwrap_or(0);
        // What a mark means is broken between words, and goes on under its first word.
        let mut out = String::new();
        for (mark, means) in &rows {
            let mut line = format!("{mark:<wide$} ");
            let mut empty = true;
            for word in means.split(' ') {
                if !empty && line.chars().count() + 1 + word.chars().count() > width {
                    out.push_str(&line);
                    out.push('\n');
                    line = " ".repeat(wide + 1);
                }
                line.push(' ');
                line.push_str(word);
                empty = false;
            }
            out.push_str(&line);
            out.push('\n');
        }
        out.replace(GLUE, " ")
    }
}

/// The score as a text tab, each line at most [`TextOptions::width`] characters (the header is not
/// wrapped). Err when the score or the options cannot be written: see
/// [`TabScore::validate`].
///
/// - One line per string, string 1 on top, with the open string's name at its left.
/// - Time runs evenly inside a bar where the bar's notes allow it; a note that is held into the
///   next bar is written once, where it starts.
/// - Notes that start together stand in one column, and every column is as wide as the widest
///   number.
/// - `h`, `p`, `/`, `\` and `b` stand before the note they lead to; `~` after a note with vibrato;
///   `x` is a dead note; "let ring" stands above the first note that rings.
/// - A "?" above a column marks a doubtful note ([`TabOptions::doubt_below`]), a "!" a note that
///   is not on the lines: no string can play it, or its string holds another note of its chord.
///   The legend names such notes bar by bar, the first twelve bars of them.
pub fn write_tab_text(score: &TabScore, tab: &TabOptions, text: &TextOptions) -> Result<String, String> {
    if !(MIN_TEXT_WIDTH..=MAX_TEXT_WIDTH).contains(&text.width) {
        return Err(format!("a line of the text tab is {MIN_TEXT_WIDTH} to {MAX_TEXT_WIDTH} characters, not {}", text.width));
    }
    let plan = Plan::new(score, tab)?;
    let mut layout = Layout::new(&plan);
    let mut out = layout.header();
    for pieces in layout.systems(text.width) {
        out.push('\n');
        layout.system(&pieces, &mut out);
    }
    let legend = layout.legend(text.width);
    if !legend.is_empty() {
        out.push('\n');
        out.push_str(&legend);
    }
    Ok(out)
}
