//! Spelled pitches, accidental display and diatonic transposition.
//!
//! Accidental display follows the reference's rules (music21
//! `Pitch.updateAccidentalDisplay` with cautionary pitch-class checks and
//! cautionary accidentals for non-immediate repeats), run per measure against
//! the key signature.

pub const STEPS: [char; 7] = ['C', 'D', 'E', 'F', 'G', 'A', 'B'];
const NATURAL: [i32; 7] = [0, 2, 4, 5, 7, 9, 11];

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Acc {
    pub alter: i32,
    /// None = not decided; Some(true) shown; Some(false) hidden.
    pub display: Option<bool>,
}

impl Acc {
    pub fn new(alter: i32) -> Acc {
        Acc { alter, display: None }
    }

    pub fn musicxml_name(&self) -> &'static str {
        match self.alter {
            0 => "natural",
            1 => "sharp",
            -1 => "flat",
            2 => "double-sharp",
            -2 => "flat-flat",
            3 => "triple-sharp",
            -3 => "triple-flat",
            _ => "other",
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct P {
    /// 0..7 = C..B
    pub step: u8,
    pub octave: i32,
    pub acc: Option<Acc>,
}

impl P {
    pub fn new(step: u8, alter: i32, octave: i32) -> P {
        P { step, octave, acc: if alter != 0 { Some(Acc::new(alter)) } else { None } }
    }

    pub fn alter(&self) -> i32 {
        self.acc.map(|a| a.alter).unwrap_or(0)
    }

    pub fn ps(&self) -> i32 {
        (self.octave + 1) * 12 + NATURAL[self.step as usize] + self.alter()
    }

    /// Octave * 7 + step + 1 (C4 = 29).
    pub fn diatonic_note_num(&self) -> i32 {
        self.octave * 7 + self.step as i32 + 1
    }

    /// Name without octave: step and alter.
    pub fn name(&self) -> (u8, i32) {
        (self.step, self.alter())
    }

    pub fn pitch_class(&self) -> i32 {
        self.ps().rem_euclid(12)
    }

    pub fn step_char(&self) -> char {
        STEPS[self.step as usize]
    }
}

/// Pitch names altered by a key signature, in signature order.
pub fn altered_names(fifths: i32) -> Vec<(u8, i32)> {
    // sharps: F C G D A E B, then double sharps; flats: B E A D G C F, then double flats
    let sharp_order = [3u8, 0, 4, 1, 5, 2, 6];
    let flat_order = [6u8, 2, 5, 1, 4, 0, 3];
    let mut out = Vec::new();
    if fifths > 0 {
        for i in 0..fifths as usize {
            out.push((sharp_order[i % 7], 1 + (i / 7) as i32));
        }
    } else {
        for i in 0..(-fifths) as usize {
            out.push((flat_order[i % 7], -1 - (i / 7) as i32));
        }
    }
    out
}

fn name_in_key(p: &P, altered: &[(u8, i32)]) -> bool {
    altered.contains(&p.name())
}

fn step_in_key(p: &P, altered: &[(u8, i32)]) -> bool {
    altered.iter().any(|(s, _)| *s == p.step)
}

/// Decide whether this pitch's accidental is shown, given the pitches before it
/// in the measure (`past`), in the previous measure (`past_measure`) and the
/// other pitches of its chord.
pub fn update_accidental_display(me: &mut P, past: &[P], past_measure: &[P], simultaneous: &[P], altered: &[(u8, i32)], last_tied: bool) {
    // overrideStatus False: a decided accidental stays as it is
    if let Some(a) = me.acc {
        if a.display.is_some() {
            return;
        }
    }
    let set_display = |me: &mut P, v: bool| {
        let a = me.acc.get_or_insert(Acc::new(0));
        a.display = Some(v);
    };
    if last_tied {
        if let Some(a) = me.acc.as_mut() {
            a.display = Some(false);
        }
        return;
    }
    if !simultaneous.is_empty() && simultaneous.iter().any(|o| o.step == me.step && o.pitch_class() != me.pitch_class()) {
        set_display(me, true);
        return;
    }
    let all: Vec<P> = past_measure.iter().chain(past.iter()).copied().collect();
    if all.is_empty() {
        if let Some(a) = me.acc {
            if a.display.is_none() || a.display == Some(false) {
                let v = if a.alter == 0 { step_in_key(me, altered) } else { !name_in_key(me, altered) };
                me.acc.as_mut().unwrap().display = Some(v);
                return;
            }
            if a.display == Some(true) && name_in_key(me, altered) {
                me.acc.as_mut().unwrap().display = Some(false);
                return;
            }
        }
        if me.acc.map_or(true, |a| a.alter == 0) && step_in_key(me, altered) {
            set_display(me, true);
        }
        return;
    }
    for pp in past.iter().rev() {
        if pp.step == me.step && pp.octave == me.octave {
            if pp.name() != me.name() {
                set_display(me, true);
                return;
            }
            break;
        }
    }
    // cautionaryAll False; displayType 'normal'
    let mut display_if_no_previous = false;
    let mut set_from_past = false;
    let out_len = past_measure.len();
    let self_name = me.name();
    let self_nwo = (me.step, me.alter(), me.octave);
    let mut i = all.len();
    while i > 0 {
        i -= 1;
        let in_measure: bool;
        let continuous: bool;
        if i < out_len {
            in_measure = false;
            continuous = false;
        } else {
            in_measure = true;
            continuous = all[i..].iter().all(|q| (q.step, q.alter(), q.octave) == self_nwo);
        }
        let acc = me.acc;
        if !in_measure && acc.is_some() && !name_in_key(me, altered) {
            me.acc.as_mut().unwrap().display = Some(true);
            return;
        }
        let pp = all[i];
        if pp.step != me.step {
            continue;
        }
        let octave_match = me.octave == pp.octave;
        let pacc = pp.acc;
        let sacc = me.acc;
        if continuous && pacc.is_some_and(|a| a.display == Some(true)) {
            if let Some(a) = me.acc.as_mut() {
                a.display = Some(false);
            }
            return;
        } else if continuous && pacc.is_some() && sacc.is_some() && pacc.unwrap().alter == sacc.unwrap().alter {
            if !name_in_key(me, altered) && (!octave_match || pacc.unwrap().display == Some(false)) {
                display_if_no_previous = true;
                continue;
            } else {
                me.acc.as_mut().unwrap().display = Some(false);
                set_from_past = true;
                break;
            }
        } else if pacc.is_some_and(|a| a.alter == 0) && sacc.map_or(true, |a| a.alter == 0) {
            if continuous {
                if step_in_key(me, altered) && !octave_match {
                    set_display(me, true);
                } else if let Some(a) = me.acc.as_mut() {
                    a.display = Some(false);
                }
            } else if step_in_key(me, altered) {
                // cautionaryNotImmediateRepeat is True
                set_display(me, true);
            } else if let Some(a) = me.acc.as_mut() {
                a.display = Some(false);
            }
            set_from_past = true;
            break;
        } else if pacc.is_some() && pp.name() != self_name && pacc.unwrap().alter != 0 && sacc.map_or(true, |a| a.display == Some(false)) {
            // cautionaryPitchClass is True: octave does not matter here
            set_display(me, true);
            set_from_past = true;
            break;
        } else if pacc.map_or(true, |a| a.alter == 0) && sacc.is_some_and(|a| a.alter != 0) {
            me.acc.as_mut().unwrap().display = Some(true);
            set_from_past = true;
            break;
        } else if pacc.is_some() && sacc.is_some() && pacc.unwrap().alter != sacc.unwrap().alter {
            me.acc.as_mut().unwrap().display = Some(true);
            set_from_past = true;
            break;
        } else if pacc.is_none() && sacc.is_some() {
            let v = if sacc.unwrap().alter == 0 { step_in_key(me, altered) } else { true };
            me.acc.as_mut().unwrap().display = Some(v);
            set_from_past = true;
            break;
        } else if !continuous && pacc.is_some() && sacc.is_some() && pacc.unwrap().alter == sacc.unwrap().alter && octave_match {
            if pacc.unwrap().display == Some(false) {
                display_if_no_previous = true;
            } else {
                let v = !name_in_key(me, altered);
                me.acc.as_mut().unwrap().display = Some(v);
                return;
            }
        }
    }
    if display_if_no_previous {
        if !name_in_key(me, altered) {
            set_display(me, true);
        } else if let Some(a) = me.acc.as_mut() {
            a.display = Some(false);
        }
    } else if !set_from_past && me.acc.is_some() {
        let a = me.acc.unwrap();
        let v = if a.alter == 0 { step_in_key(me, altered) } else { !name_in_key(me, altered) };
        me.acc.as_mut().unwrap().display = Some(v);
    } else if !set_from_past && me.acc.is_none() && step_in_key(me, altered) {
        set_display(me, true);
    }
}

/// Diatonic transposition by `steps` staff steps and `semitones` (music21
/// `Interval.transposePitch`): the new accidental is undecided (shown if any).
pub fn transpose(p: &P, steps: i32, semitones: i32) -> P {
    let dnn = p.diatonic_note_num() + steps;
    // diatonic number -> step, octave
    let z = dnn - 1;
    let mut octave = z.div_euclid(7);
    let step = z.rem_euclid(7) as u8;
    let natural = P { step, octave, acc: None };
    let mut fix = semitones - (natural.ps() - p.ps());
    while fix >= 12 {
        fix -= 12;
        octave -= 1;
    }
    P { step, octave, acc: if fix != 0 { Some(Acc::new(fix)) } else { None } }
}

/// Fifths of a major key whose tonic is this spelled pitch.
fn pitch_to_sharps(step: u8, alter: i32) -> i32 {
    let base = [0, 2, 4, -1, 1, 3, 5][step as usize];
    base + 7 * alter
}

/// Key signature transposed like its major tonic.
pub fn transpose_key(fifths: i32, steps: i32, semitones: i32) -> i32 {
    // tonic of the major key with `fifths`
    let order = [3u8, 0, 4, 1, 5, 2, 6]; // F C G D A E B
    let idx = (fifths + 1).rem_euclid(7) as usize;
    let alter = (fifths + 1).div_euclid(7);
    let tonic = P::new(order[idx], alter, 4);
    let t = transpose(&tonic, steps, semitones);
    pitch_to_sharps(t.step, t.alter())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn transposition() {
        // concert F#4 on a B-flat instrument (written a major second up) is G#4
        let w = transpose(&P::new(3, 1, 4), 1, 2);
        assert_eq!((w.step, w.alter(), w.octave), (4, 1, 4));
        // A#4 up a major sixth (E-flat horn) is F##5
        let w = transpose(&P::new(5, 1, 4), 5, 9);
        assert_eq!((w.step, w.alter(), w.octave), (3, 2, 5));
        assert_eq!(transpose_key(0, 1, 2), 2);
        assert_eq!(transpose_key(0, -2, -3), 3);
        assert_eq!(transpose_key(6, 5, 9), 9);
    }
}
