//! Beaming inside one measure, following the time signature's beam groups
//! (the reference's `TimeSignature.getBeams`, including its partial-beam
//! sanitising and merging), and stem direction per beam group.

use super::duration::{DType, Rat, EIGHTH};

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum BT {
    Start,
    Continue,
    Stop,
    Partial,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum BDir {
    Left,
    Right,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Beam {
    pub number: u8,
    pub typ: Option<BT>,
    pub dir: Option<BDir>,
}

pub type Beams = Vec<Beam>;

fn numbers(b: &Beams) -> Vec<u8> {
    b.iter().map(|x| x.number).collect()
}

fn get(b: &Beams, n: u8) -> Option<&Beam> {
    b.iter().find(|x| x.number == n)
}

fn get_mut(b: &mut Beams, n: u8) -> Option<&mut Beam> {
    b.iter_mut().find(|x| x.number == n)
}

/// "start", "stop", "partial-left", ...: the type with its direction.
fn type_by_number(b: &Beams, n: u8) -> Option<(BT, Option<BDir>)> {
    get(b, n).and_then(|x| x.typ.map(|t| (t, x.dir)))
}

/// Beam groups of a time signature n/4: top level and each subdivision level.
#[derive(Clone, Debug)]
pub struct BeamSequence {
    levels: Vec<Vec<(Rat, Rat)>>,
    pub bar: Rat,
}

impl BeamSequence {
    pub fn for_quarters(numerator: i64) -> BeamSequence {
        let q = Rat::int(1);
        let bar = Rat::int(numerator);
        let spans = |lens: &[Rat]| -> Vec<(Rat, Rat)> {
            let mut out = Vec::new();
            let mut pos = Rat::ZERO;
            for &l in lens {
                out.push((pos, pos + l));
                pos = pos + l;
            }
            out
        };
        let levels = match numerator {
            2..=4 => {
                let top = vec![q; numerator as usize];
                let sub = vec![Rat::new(1, 2); 2 * numerator as usize];
                vec![spans(&top), spans(&sub)]
            }
            5 => {
                let top = vec![Rat::int(2), Rat::int(3)];
                let sub = vec![q; 5];
                vec![spans(&top), spans(&sub)]
            }
            7 => vec![spans(&[Rat::new(7, 3); 3])],
            6 | 9 | 12 | 15 | 18 | 21 => vec![spans(&vec![Rat::int(3); (numerator / 3) as usize])],
            _ => vec![spans(&[bar])],
        };
        BeamSequence { levels, bar }
    }

    fn level(&self, depth: usize) -> &[(Rat, Rat)] {
        &self.levels[depth.min(self.levels.len() - 1)]
    }

    fn span_at(&self, depth: usize, pos: Rat) -> (Rat, Rat) {
        let lv = self.level(depth);
        lv.iter().copied().find(|&(s, e)| s <= pos && pos < e).unwrap_or((Rat::ZERO, Rat::ZERO))
    }
}

/// One entry per note or rest of the measure: offset, length, written type and whether it is a note.
#[derive(Clone, Copy, Debug)]
pub struct BeamInput {
    pub offset: Rat,
    pub ql: Rat,
    pub typ: Option<DType>,
    pub notrest: bool,
}

fn beam_count(typ: Option<DType>) -> Option<u8> {
    match typ {
        Some(DType::T(i)) if i >= EIGHTH => Some(i - EIGHTH + 1),
        _ => None,
    }
}

/// Beams for each element (empty when not beamed).
pub fn get_beams(src: &[BeamInput], seq: &BeamSequence) -> Vec<Beams> {
    let n = src.len();
    if n <= 1 {
        return vec![Vec::new(); n];
    }
    let mut list: Vec<Option<Beams>> = src
        .iter()
        .map(|e| {
            if !e.notrest {
                return None;
            }
            beam_count(e.typ).map(|c| (1..=c).map(|k| Beam { number: k, typ: None, dir: None }).collect())
        })
        .collect();
    // remove sandwiched unbeamables
    let mut last_none = true;
    for i in 0..n {
        let next_none = if i + 1 < n { list[i + 1].is_none() } else { true };
        if last_none && next_none {
            list[i] = None;
        }
        last_none = list[i].is_none();
    }
    for depth in 0..9usize {
        for i in 0..n {
            fix(&mut list, src, seq, i, depth);
        }
    }
    sanitize(&mut list);
    merge_partials(&mut list);
    list.into_iter().map(|b| b.unwrap_or_default()).collect()
}

fn fix(list: &mut [Option<Beams>], src: &[BeamInput], seq: &BeamSequence, i: usize, depth: usize) {
    let Some(beams) = list[i].as_ref() else { return };
    let number = (depth + 1) as u8;
    if !numbers(beams).contains(&number) {
        return;
    }
    let start = src[i].offset;
    let end = start + src[i].ql;
    let start_next = end;
    let is_last = i == src.len() - 1;
    let is_first = i == 0;
    let next = if is_last { None } else { list[i + 1].clone() };
    let prev = if is_first { None } else { list[i - 1].clone() };
    let (span_start, span_end) = seq.span_at(depth, start);
    let span_next_start = if next.is_none() { Rat::ZERO } else { seq.span_at(depth, start_next).0 };
    if end == span_end && (start == span_start || (prev.is_none() && number == 1)) {
        list[i] = None;
        return;
    }
    let has = |b: &Option<Beams>| b.as_ref().is_some_and(|b| numbers(b).contains(&number));
    let (typ, dir): (BT, Option<BDir>) = if is_first {
        if next.is_none() || !has(&next) {
            (BT::Partial, Some(BDir::Right))
        } else {
            (BT::Start, None)
        }
    } else if is_last {
        if prev.is_none() || !has(&prev) {
            (BT::Partial, Some(BDir::Left))
        } else {
            (BT::Stop, None)
        }
    } else if prev.is_none() || !has(&prev) {
        if number == 1 && next.is_none() {
            list[i] = None;
            return;
        } else if next.is_none() && number > 1 {
            (BT::Partial, Some(BDir::Left))
        } else if start_next >= span_end {
            (BT::Partial, Some(BDir::Left))
        } else if next.is_none() || !has(&next) {
            (BT::Partial, Some(BDir::Right))
        } else {
            (BT::Start, None)
        }
    } else if matches!(type_by_number(prev.as_ref().unwrap(), number), Some((BT::Stop, _)) | Some((BT::Partial, Some(BDir::Left)))) {
        if next.is_some() {
            if has(&next) {
                (BT::Start, None)
            } else {
                (BT::Partial, Some(BDir::Right))
            }
        } else {
            (BT::Partial, Some(BDir::Left))
        }
    } else if next.is_none() || !has(&next) {
        (BT::Stop, None)
    } else if start_next < span_end {
        (BT::Continue, None)
    } else if start_next >= span_next_start {
        (BT::Stop, None)
    } else {
        (BT::Stop, None)
    };
    let b = get_mut(list[i].as_mut().unwrap(), number).unwrap();
    b.typ = Some(typ);
    b.dir = dir;
}

fn sanitize(list: &mut [Option<Beams>]) {
    for slot in list.iter_mut() {
        let Some(b) = slot.as_mut() else { continue };
        let types: Vec<Option<BT>> = b.iter().map(|x| x.typ).collect();
        if !types.iter().any(|t| matches!(t, Some(BT::Start) | Some(BT::Stop) | Some(BT::Continue))) {
            *slot = None;
            continue;
        }
        let mut has_start = false;
        let mut has_stop = false;
        for x in b.iter_mut() {
            match x.typ {
                Some(BT::Start) => {
                    has_start = true;
                    continue;
                }
                Some(BT::Stop) => {
                    has_stop = true;
                    continue;
                }
                _ => {}
            }
            if has_start && x.typ == Some(BT::Partial) && x.dir == Some(BDir::Left) {
                x.dir = Some(BDir::Right);
            } else if has_stop && x.typ == Some(BT::Partial) && x.dir == Some(BDir::Right) {
                x.dir = Some(BDir::Left);
            }
        }
    }
}

fn merge_partials(list: &mut [Option<Beams>]) {
    let n = list.len();
    for i in 0..n.saturating_sub(1) {
        if list[i].as_ref().map_or(true, |b| b.is_empty()) || list[i + 1].as_ref().map_or(true, |b| b.is_empty()) {
            continue;
        }
        let nums = numbers(list[i].as_ref().unwrap());
        for num in nums {
            let this = *get(list[i].as_ref().unwrap(), num).unwrap();
            if this.typ != Some(BT::Partial) || this.dir != Some(BDir::Right) {
                continue;
            }
            let Some(next) = get(list[i + 1].as_ref().unwrap(), num).copied() else { continue };
            if next.typ == Some(BT::Partial) && next.dir == Some(BDir::Right) {
                continue;
            }
            if matches!(next.typ, Some(BT::Continue) | Some(BT::Stop)) {
                continue;
            }
            let t = get_mut(list[i].as_mut().unwrap(), num).unwrap();
            t.typ = Some(BT::Start);
            t.dir = None;
            let nb = get_mut(list[i + 1].as_mut().unwrap(), num).unwrap();
            if nb.typ == Some(BT::Partial) {
                nb.typ = Some(BT::Stop);
            } else if nb.typ == Some(BT::Start) {
                nb.typ = Some(BT::Continue);
            }
            nb.dir = None;
        }
    }
    for i in 1..n {
        if list[i].as_ref().map_or(true, |b| b.is_empty()) || list[i - 1].as_ref().map_or(true, |b| b.is_empty()) {
            continue;
        }
        let nums = numbers(list[i].as_ref().unwrap());
        for num in nums {
            let this = *get(list[i].as_ref().unwrap(), num).unwrap();
            if this.typ != Some(BT::Partial) || this.dir != Some(BDir::Left) {
                continue;
            }
            let Some(prev) = get(list[i - 1].as_ref().unwrap(), num).copied() else { continue };
            if prev.typ != Some(BT::Stop) {
                continue;
            }
            let t = get_mut(list[i].as_mut().unwrap(), num).unwrap();
            t.typ = Some(BT::Stop);
            t.dir = None;
            get_mut(list[i - 1].as_mut().unwrap(), num).unwrap().typ = Some(BT::Continue);
        }
    }
}
