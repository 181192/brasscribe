//! Split notes and rests into readable, tied values that show the beat.
//!
//! Brass-band parts show every beat and the middle of a 4/4 bar. A value is
//! written as one symbol only when:
//!   - it is shorter than a beat and stays inside one beat, or is an 8th or
//!     dotted 8th pushed over one beat (an anticipation, also over mid-bar), or
//!   - it is a beat or longer, starts on a beat, and does not cross the middle
//!     of the bar unless it starts on the downbeat, or
//!   - it is a quarter on the "and" of a beat inside a half bar,
//! and it is a plain or single-dotted value. Anything else is split at the
//! first boundary it crosses and tied. Tick sums are exact.

use crate::model::TICKS_PER_BEAT;
use crate::py::floordiv;

const BEAT: i64 = TICKS_PER_BEAT;
/// Plain and single-dotted values in ticks.
pub const SINGLE: [i64; 10] = [3, 6, 9, 12, 18, 24, 36, 48, 72, 96];
/// Triplet 16th, 8th and quarter.
pub const TRIPLET: [i64; 3] = [4, 8, 16];

pub fn is_single(n: i64) -> bool {
    SINGLE.contains(&n)
}

pub fn is_value(n: i64) -> bool {
    SINGLE.contains(&n) || TRIPLET.contains(&n)
}

/// The strong boundary inside a bar: beat 3 in 4/4 (none in 2/4 or 3/4).
fn middle(bar: i64) -> Option<i64> {
    let beats = floordiv(bar, BEAT);
    if beats >= 4 && beats % 2 == 0 {
        Some(floordiv(bar, 2))
    } else {
        None
    }
}

fn ok(a: i64, b: i64, bar: i64) -> bool {
    let n = b - a;
    if !is_value(n) {
        return false;
    }
    if n < BEAT {
        if floordiv(a, BEAT) == floordiv(b - 1, BEAT) {
            return true;
        }
        return n == 12 || n == 18;
    }
    let mid = middle(bar);
    if a.rem_euclid(BEAT) != 0 {
        return n == BEAT && a.rem_euclid(BEAT / 2) == 0 && mid.map_or(true, |m| !(a < m && m < b));
    }
    mid.map_or(true, |m| a == 0 || !(a < m && m < b))
}

fn in_bar(a: i64, b: i64, bar: i64) -> Vec<(i64, i64)> {
    if ok(a, b, bar) {
        return vec![(a, b)];
    }
    if let Some(m) = middle(bar) {
        if a < m && m < b && a != 0 {
            let mut v = in_bar(a, m, bar);
            v.extend(in_bar(m, b, bar));
            return v;
        }
    }
    if a.rem_euclid(BEAT) != 0 {
        let nxt = (floordiv(a, BEAT) + 1) * BEAT;
        if nxt < b {
            let mut v = in_bar(a, nxt, bar);
            v.extend(in_bar(nxt, b, bar));
            return v;
        }
        // Inside one beat but not a single value: largest value that fits.
        let mut all: Vec<i64> = SINGLE.iter().chain(TRIPLET.iter()).copied().collect();
        all.sort_unstable_by(|x, y| y.cmp(x));
        all.dedup();
        for n in all {
            if n < b - a {
                let mut v = in_bar(a, a + n, bar);
                v.extend(in_bar(a + n, b, bar));
                return v;
            }
        }
        return vec![(a, b)];
    }
    // On a beat: the longest allowed value from here, then the rest.
    for &n in SINGLE.iter().rev() {
        if n < b - a && ok(a, a + n, bar) {
            let mut v = vec![(a, a + n)];
            v.extend(in_bar(a + n, b, bar));
            return v;
        }
    }
    vec![(a, b)]
}

/// Readable (start, end) pieces of [start, end) in ticks from the first bar line.
pub fn pieces(start: i64, end: i64, bar: i64) -> Vec<(i64, i64)> {
    let mut out = Vec::new();
    let mut s = start;
    while s < end {
        let b0 = floordiv(s, bar) * bar;
        let e = end.min(b0 + bar);
        out.extend(in_bar(s - b0, e - b0, bar).into_iter().map(|(x, y)| (b0 + x, b0 + y)));
        s = e;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splits_at_the_middle_and_beats() {
        assert_eq!(pieces(0, 96, 96), vec![(0, 96)]);
        assert_eq!(pieces(24, 72, 96), vec![(24, 48), (48, 72)]);
        assert_eq!(pieces(12, 36, 96), vec![(12, 36)]);
        assert_eq!(pieces(6, 30, 96), vec![(6, 24), (24, 30)]);
    }
}
