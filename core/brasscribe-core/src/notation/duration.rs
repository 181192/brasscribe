//! Exact durations: rational quarter lengths, note types, dots and tuplets.
//!
//! The conversion from a quarter length to a written value follows the rules
//! of the reference's notation layer (music21 `duration.quarterConversion`):
//! a single type, then a dotted type (up to four dots), then a tuplet of 3, 5,
//! 7, 11 or 13 over the smallest type, then a chain of tied components, and
//! as a last resort one non-power-of-two tuplet.

use std::cmp::Ordering;
use std::fmt;

fn gcd(a: i128, b: i128) -> i128 {
    let (mut a, mut b) = (a.abs(), b.abs());
    while b != 0 {
        let t = a % b;
        a = b;
        b = t;
    }
    a
}

/// A rational number with a positive denominator, always in lowest terms.
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub struct Rat {
    pub n: i64,
    pub d: i64,
}

impl fmt::Debug for Rat {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}/{}", self.n, self.d)
    }
}

impl Rat {
    pub const ZERO: Rat = Rat { n: 0, d: 1 };

    pub fn new(n: i64, d: i64) -> Rat {
        Rat::from_i128(n as i128, d as i128)
    }

    fn from_i128(n: i128, d: i128) -> Rat {
        assert!(d != 0, "zero denominator");
        let g = gcd(n, d).max(1);
        let (mut n, mut d) = (n / g, d / g);
        if d < 0 {
            n = -n;
            d = -d;
        }
        Rat { n: n as i64, d: d as i64 }
    }

    pub fn int(n: i64) -> Rat {
        Rat { n, d: 1 }
    }

    pub fn is_zero(self) -> bool {
        self.n == 0
    }

    pub fn recip(self) -> Rat {
        Rat::new(self.d, self.n)
    }

    /// Round half to even (Python `round` of a Fraction).
    pub fn round_even(self) -> i64 {
        let fl = self.n.div_euclid(self.d);
        let rem2 = 2 * self.n.rem_euclid(self.d);
        match rem2.cmp(&self.d) {
            Ordering::Less => fl,
            Ordering::Greater => fl + 1,
            Ordering::Equal => {
                if fl % 2 == 0 {
                    fl
                } else {
                    fl + 1
                }
            }
        }
    }

    pub fn to_f64(self) -> f64 {
        self.n as f64 / self.d as f64
    }
}

impl std::ops::Add for Rat {
    type Output = Rat;
    fn add(self, o: Rat) -> Rat {
        Rat::from_i128(self.n as i128 * o.d as i128 + o.n as i128 * self.d as i128, self.d as i128 * o.d as i128)
    }
}
impl std::ops::Sub for Rat {
    type Output = Rat;
    fn sub(self, o: Rat) -> Rat {
        Rat::from_i128(self.n as i128 * o.d as i128 - o.n as i128 * self.d as i128, self.d as i128 * o.d as i128)
    }
}
impl std::ops::Mul for Rat {
    type Output = Rat;
    fn mul(self, o: Rat) -> Rat {
        Rat::from_i128(self.n as i128 * o.n as i128, self.d as i128 * o.d as i128)
    }
}
impl std::ops::Div for Rat {
    type Output = Rat;
    fn div(self, o: Rat) -> Rat {
        Rat::from_i128(self.n as i128 * o.d as i128, self.d as i128 * o.n as i128)
    }
}
impl PartialOrd for Rat {
    fn partial_cmp(&self, o: &Rat) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}
impl Ord for Rat {
    fn cmp(&self, o: &Rat) -> Ordering {
        (self.n as i128 * o.d as i128).cmp(&(o.n as i128 * self.d as i128))
    }
}

/// Note types from longest to shortest; the index is the ordinal.
pub const TYPE_NAMES: [&str; 16] = [
    "duplex-maxima", "maxima", "longa", "breve", "whole", "half", "quarter", "eighth", "16th", "32nd", "64th", "128th",
    "256th", "512th", "1024th", "2048th",
];
pub const QUARTER: u8 = 6;
pub const EIGHTH: u8 = 7;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum DType {
    /// Ordinal into TYPE_NAMES.
    T(u8),
    Zero,
    Inexpressible,
}

impl DType {
    pub fn name(self) -> &'static str {
        match self {
            DType::T(i) => TYPE_NAMES[i as usize],
            DType::Zero => "zero",
            DType::Inexpressible => "inexpressible",
        }
    }

    pub fn musicxml(self) -> &'static str {
        match self {
            DType::T(2) => "long",
            t => t.name(),
        }
    }
}

/// Quarter length of a type (64 for duplex-maxima down to 1/512).
pub fn type_value(i: u8) -> Rat {
    if i <= 6 {
        Rat::int(64 >> i)
    } else {
        Rat::new(1, 1 << (i - 6))
    }
}

pub fn dot_multiplier(dots: u8) -> Rat {
    Rat::new((1 << (dots + 1)) - 1, 1 << dots)
}

/// Atomic un-tupleted value: type, dots and the quarter length they give.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct DT {
    pub typ: DType,
    pub dots: u8,
    pub ql: Rat,
}

impl DT {
    pub fn of(i: u8, dots: u8) -> DT {
        DT { typ: DType::T(i), dots, ql: type_value(i) * dot_multiplier(dots) }
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum TupletType {
    Start,
    Stop,
    StartStop,
}

#[derive(Clone, Copy, Debug)]
pub struct Tuplet {
    pub actual: i64,
    pub normal: i64,
    pub dur_actual: Option<DT>,
    pub dur_normal: Option<DT>,
    pub typ: Option<TupletType>,
    pub bracket: bool,
}

impl PartialEq for Tuplet {
    /// Equal when numbers and durations are equal (display does not matter).
    fn eq(&self, o: &Tuplet) -> bool {
        self.actual == o.actual && self.normal == o.normal && self.dur_actual == o.dur_actual && self.dur_normal == o.dur_normal
    }
}

impl Tuplet {
    fn new(actual: i64, normal: i64, dt: DT) -> Tuplet {
        Tuplet { actual, normal, dur_actual: Some(dt), dur_normal: Some(dt), typ: None, bracket: true }
    }

    pub fn total_length(&self) -> Rat {
        let dn = self.dur_normal.map(|d| d.ql).unwrap_or(Rat::new(1, 2));
        Rat::int(self.normal) * dn
    }

    pub fn multiplier(&self) -> Rat {
        let la = self.dur_actual.map(|d| d.ql).unwrap_or(Rat::new(1, 2));
        let ln = self.dur_normal.map(|d| d.ql).unwrap_or(Rat::new(1, 2));
        (ln * Rat::int(self.normal)) / (la * Rat::int(self.actual))
    }
}

/// A note's duration: its quarter length and how it is written.
#[derive(Clone, Debug)]
pub struct Dur {
    pub ql: Rat,
    pub comps: Vec<DT>,
    pub tuplets: Vec<Tuplet>,
    /// The written form was inferred from the quarter length (music21 `expressionIsInferred`).
    pub inferred: bool,
}

impl Dur {
    pub fn from_ql(ql: Rat) -> Dur {
        let (comps, tup) = quarter_conversion(ql);
        Dur { ql, comps, tuplets: tup.into_iter().collect(), inferred: true }
    }

    pub fn typ(&self) -> Option<DType> {
        match self.comps.len() {
            0 => Some(DType::Zero),
            1 => Some(self.comps[0].typ),
            _ => None, // complex
        }
    }

    pub fn is_complex(&self) -> bool {
        self.comps.len() > 1
    }

    pub fn dots(&self) -> u8 {
        if self.comps.len() == 1 {
            self.comps[0].dots
        } else {
            0
        }
    }

    pub fn aggregate_multiplier(&self) -> Rat {
        self.tuplets.iter().fold(Rat::int(1), |m, t| m * t.multiplier())
    }

    /// What a deep copy keeps: a single-component, tuplet-free duration is
    /// rebuilt from its component and no longer counts as inferred.
    pub fn deep_copied(&self) -> Dur {
        let mut d = self.clone();
        if d.comps.len() == 1 && d.tuplets.is_empty() {
            d.inferred = false;
        }
        d
    }
}

/// Numbers 4/ql of the named types (4 / quarter length), keyed by ordinal.
fn exact_type(ql: Rat) -> Option<u8> {
    (0..16u8).find(|&i| type_value(i) == ql)
}

/// (type ordinal, exact) of the largest type not longer than `ql`.
pub fn closest_type(ql: Rat) -> Result<(u8, bool), ()> {
    if ql.is_zero() {
        return Err(());
    }
    if let Some(i) = exact_type(ql) {
        return Ok((i, true));
    }
    // lower < 4/typeValue < upper  <=>  ql/2 < typeValue < ql ; smallest number first = longest type first
    for i in 0..16u8 {
        let v = type_value(i);
        if ql / Rat::int(2) < v && v < ql {
            return Ok((i, false));
        }
    }
    if ql > Rat::int(128) {
        return Ok((0, false));
    }
    Err(())
}

pub fn dotted_match(ql: Rat) -> Option<(u8, u8)> {
    for dots in 0..=4u8 {
        let pre = ql / dot_multiplier(dots);
        if let Ok((i, true)) = closest_type(pre) {
            return Some((dots, i));
        }
    }
    None
}

fn tuplet_candidates(ql: Rat) -> Option<Tuplet> {
    // types in increasing length, after 'zero'
    for i in (0..16u8).rev() {
        let tv = type_value(i);
        let mut post: Vec<Tuplet> = Vec::new();
        for &n in &[3i64, 5, 7, 11, 13] {
            let base = tv / Rat::int(n);
            for m in 1..n {
                for dots in 0..=1u8 {
                    if base * Rat::int(m) * dot_multiplier(dots) == ql {
                        post.push(Tuplet::new(n, m, DT::of(i, dots)));
                        break;
                    }
                }
            }
            if !post.is_empty() {
                break;
            }
        }
        if !post.is_empty() {
            return Some(post[0]);
        }
    }
    None
}

fn non_power_of_2_tuplet(ql: Rat) -> Result<(Tuplet, DT), ()> {
    let org = ql.recip();
    let mut q = org;
    if q.n < q.d {
        while q.n < q.d {
            q = q * Rat::int(2);
        }
    } else if q.n > q.d * 2 {
        while q.n > q.d * 2 {
            q = q / Rat::int(2);
        }
    }
    let (closest, _) = closest_type(ql / Rat::int(q.d))?;
    let rep_ql = q / org;
    let rep = match dotted_match(rep_ql) {
        Some((dots, i)) => DT::of(i, dots),
        None => DT { typ: DType::Inexpressible, dots: 0, ql: rep_ql },
    };
    Ok((Tuplet::new(q.n, q.d, DT::of(closest, 0)), rep))
}

/// Components and (optional) tuplet expressing a quarter length.
pub fn quarter_conversion(ql: Rat) -> (Vec<DT>, Option<Tuplet>) {
    if ql > Rat::ZERO {
        if let Some(i) = exact_type(ql) {
            return (vec![DT::of(i, 0)], None);
        }
    }
    if let Some((dots, i)) = dotted_match(ql) {
        return (vec![DT::of(i, dots)], None);
    }
    if ql.is_zero() {
        return (vec![DT { typ: DType::Zero, dots: 0, ql: Rat::ZERO }], None);
    }
    let inexpressible = || (vec![DT { typ: DType::Inexpressible, dots: 0, ql }], None);
    let Ok((closest, _)) = closest_type(ql) else { return inexpressible() };
    if closest == 0 {
        return inexpressible();
    }
    if let Some(t) = tuplet_candidates(ql) {
        return (vec![t.dur_actual.unwrap()], Some(t));
    }
    let mut comps = vec![DT::of(closest, 0)];
    let mut rem = ql - type_value(closest);
    for _ in 0..8 {
        if let Some((dots, i)) = dotted_match(rem) {
            comps.push(DT::of(i, dots));
            return (comps, None);
        }
        let Ok((c, _)) = closest_type(rem) else { break };
        rem = rem - type_value(c);
        comps.push(DT::of(c, 0));
    }
    match non_power_of_2_tuplet(ql) {
        Ok((t, rep)) => (vec![rep], Some(t)),
        Err(()) => inexpressible(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn names(ql: Rat) -> (Vec<(String, u8)>, Option<(i64, i64, String)>) {
        let (c, t) = quarter_conversion(ql);
        (
            c.iter().map(|d| (d.typ.name().to_string(), d.dots)).collect(),
            t.map(|t| (t.actual, t.normal, t.dur_normal.unwrap().typ.name().to_string())),
        )
    }

    #[test]
    fn conversions_match_reference_examples() {
        assert_eq!(names(Rat::int(3)), (vec![("half".into(), 1)], None));
        assert_eq!(names(Rat::new(7, 2)), (vec![("half".into(), 2)], None));
        assert_eq!(names(Rat::new(15, 4)), (vec![("half".into(), 3)], None));
        assert_eq!(names(Rat::new(2, 3)), (vec![("quarter".into(), 0)], Some((3, 2, "quarter".into()))));
        assert_eq!(names(Rat::new(1, 3)), (vec![("eighth".into(), 0)], Some((3, 2, "eighth".into()))));
        assert_eq!(names(Rat::new(1, 6)), (vec![("16th".into(), 0)], Some((3, 2, "16th".into()))));
        assert_eq!(names(Rat::new(1, 5)), (vec![("16th".into(), 0)], Some((5, 4, "16th".into()))));
        assert_eq!(names(Rat::new(4, 7)), (vec![("quarter".into(), 0)], Some((7, 4, "quarter".into()))));
        assert_eq!(names(Rat::new(5, 2)), (vec![("half".into(), 0), ("eighth".into(), 0)], None));
        assert_eq!(names(Rat::new(7, 3)), (vec![("whole".into(), 0)], Some((12, 7, "16th".into()))));
    }

    #[test]
    fn rounding() {
        assert_eq!(Rat::new(5, 2).round_even(), 2);
        assert_eq!(Rat::new(7, 2).round_even(), 4);
        assert_eq!(Rat::new(-5, 2).round_even(), -2);
    }
}
