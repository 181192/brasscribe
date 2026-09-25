//! Numeric semantics of the Python reference (CPython and NumPy), reproduced
//! bit for bit where the outputs depend on them.
//!
//! * `round` in Python and NumPy rounds halves to even.
//! * `round(x, n)` in Python rounds the exact binary value to `n` decimals.
//! * `np.round(x, n)` multiplies by 10^n, rounds to even and divides back.
//! * `np.sum` uses pairwise summation with an 8-way unrolled inner loop.
//! * `np.interp` and `np.median` follow NumPy's formulas.

/// Python `round(x)` / `np.rint(x)`: nearest integer, halves to even.
#[inline]
pub fn rint(x: f64) -> f64 {
    x.round_ties_even()
}

/// Python `round(x)` returning an integer.
#[inline]
pub fn round_int(x: f64) -> i64 {
    x.round_ties_even() as i64
}

/// NumPy `np.round(x, decimals)` for `decimals >= 0`.
pub fn np_round(x: f64, decimals: u32) -> f64 {
    let f = 10f64.powi(decimals as i32);
    (x * f).round_ties_even() / f
}

/// Python `round(x, ndigits)` for `ndigits >= 0`: the exact binary value of
/// `x` rounded half-to-even at the given decimal, read back as the nearest
/// double.
pub fn py_round(x: f64, ndigits: u32) -> f64 {
    if !x.is_finite() || x == 0.0 {
        return x;
    }
    let bits = x.to_bits();
    let neg = bits >> 63 == 1;
    let exp = ((bits >> 52) & 0x7ff) as i64;
    let frac = bits & ((1u64 << 52) - 1);
    let (m, e) = if exp == 0 { (frac, -1074i64) } else { (frac | (1u64 << 52), exp - 1075) };
    // |x| = m * 2^e
    if e >= 0 {
        return x; // an integer already
    }
    let k = (-e) as u32;
    let p10 = 10u128.pow(ndigits);
    let num = m as u128 * p10; // < 2^53 * 10^ndigits
    let q = if k >= 127 {
        0u128
    } else {
        let q = num >> k;
        let rem = num - (q << k);
        let half = 1u128 << (k - 1);
        if rem > half || (rem == half && q & 1 == 1) {
            q + 1
        } else {
            q
        }
    };
    let s = format!("{}{}e-{}", if neg { "-" } else { "" }, q, ndigits);
    s.parse::<f64>().unwrap_or(0.0)
}

/// Python floor division for integers.
#[inline]
pub fn floordiv(a: i64, b: i64) -> i64 {
    a.div_euclid(b) - if b < 0 && a.rem_euclid(b) != 0 { 1 } else { 0 }
}

/// Python `%` for integers (result has the sign of the divisor).
#[inline]
pub fn pymod(a: i64, b: i64) -> i64 {
    a - b * floordiv(a, b)
}

const PW_BLOCKSIZE: usize = 128;

/// `np.sum` over a contiguous float64 array (pairwise summation).
pub fn pairwise_sum_f64(a: &[f64]) -> f64 {
    let n = a.len();
    if n < 8 {
        let mut res = 0.0;
        for &v in a {
            res += v;
        }
        res
    } else if n <= PW_BLOCKSIZE {
        let mut r = [a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]];
        let mut i = 8;
        while i < n - (n % 8) {
            for j in 0..8 {
                r[j] += a[i + j];
            }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            res += a[i];
            i += 1;
        }
        res
    } else {
        let mut n2 = n / 2;
        n2 -= n2 % 8;
        pairwise_sum_f64(&a[..n2]) + pairwise_sum_f64(&a[n2..])
    }
}

/// `np.sum` over a contiguous float32 array (pairwise summation in float32).
pub fn pairwise_sum_f32(a: &[f32]) -> f32 {
    let n = a.len();
    if n < 8 {
        let mut res = 0.0f32;
        for &v in a {
            res += v;
        }
        res
    } else if n <= PW_BLOCKSIZE {
        let mut r = [a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]];
        let mut i = 8;
        while i < n - (n % 8) {
            for j in 0..8 {
                r[j] += a[i + j];
            }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            res += a[i];
            i += 1;
        }
        res
    } else {
        let mut n2 = n / 2;
        n2 -= n2 % 8;
        pairwise_sum_f32(&a[..n2]) + pairwise_sum_f32(&a[n2..])
    }
}

/// `np.interp(x, xp, fp)` for one point (xp increasing).
pub fn interp(x: f64, xp: &[f64], fp: &[f64]) -> f64 {
    let n = xp.len();
    if x.is_nan() {
        return x;
    }
    if x < xp[0] {
        return fp[0];
    }
    if x > xp[n - 1] {
        return fp[n - 1];
    }
    // largest j with xp[j] <= x
    let j = match xp.partition_point(|&v| v <= x) {
        0 => 0,
        p => p - 1,
    };
    if j == n - 1 {
        return fp[j];
    }
    if xp[j] == x {
        return fp[j];
    }
    let slope = (fp[j + 1] - fp[j]) / (xp[j + 1] - xp[j]);
    let mut r = slope.mul_add(x - xp[j], fp[j]); // NumPy is compiled with FMA contraction here
    if r.is_nan() {
        r = slope.mul_add(x - xp[j + 1], fp[j + 1]);
        if r.is_nan() && fp[j] == fp[j + 1] {
            r = fp[j];
        }
    }
    r
}

/// `np.median` of a slice (mean of the two middle values for even lengths).
pub fn median(v: &[f64]) -> f64 {
    let mut s = v.to_vec();
    s.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let n = s.len();
    if n % 2 == 1 {
        s[n / 2]
    } else {
        (s[n / 2 - 1] + s[n / 2]) / 2.0
    }
}

/// Python `repr(float)`.
pub fn float_repr(x: f64) -> String {
    if x.is_nan() {
        return "NaN".into();
    }
    if x.is_infinite() {
        return if x > 0.0 { "Infinity".into() } else { "-Infinity".into() };
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0.0".into() } else { "0.0".into() };
    }
    let sci = format!("{:e}", x); // shortest round-trip digits, e.g. "-1.2345e-5"
    let (mant, exp) = sci.split_once('e').unwrap();
    let exp: i32 = exp.parse().unwrap();
    let (neg, mant) = match mant.strip_prefix('-') {
        Some(m) => (true, m),
        None => (false, mant),
    };
    let digits: String = mant.chars().filter(|c| *c != '.').collect();
    let decpt = exp + 1; // value = 0.DIGITS * 10^decpt
    let mut out = String::new();
    if neg {
        out.push('-');
    }
    if decpt <= -4 || decpt > 16 {
        out.push_str(&digits[..1]);
        if digits.len() > 1 {
            out.push('.');
            out.push_str(&digits[1..]);
        }
        let e = decpt - 1;
        out.push('e');
        out.push(if e < 0 { '-' } else { '+' });
        out.push_str(&format!("{:02}", e.abs()));
    } else if decpt <= 0 {
        out.push_str("0.");
        for _ in 0..(-decpt) {
            out.push('0');
        }
        out.push_str(&digits);
    } else {
        let d = decpt as usize;
        if digits.len() <= d {
            out.push_str(&digits);
            for _ in digits.len()..d {
                out.push('0');
            }
            out.push_str(".0");
        } else {
            out.push_str(&digits[..d]);
            out.push('.');
            out.push_str(&digits[d..]);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repr_matches_python() {
        assert_eq!(float_repr(1.0), "1.0");
        assert_eq!(float_repr(0.1), "0.1");
        assert_eq!(float_repr(1e-05), "1e-05");
        assert_eq!(float_repr(0.0001), "0.0001");
        assert_eq!(float_repr(1e16), "1e+16");
        assert_eq!(float_repr(1234567890123456.0), "1234567890123456.0");
        assert_eq!(float_repr(0.033191287878787876), "0.033191287878787876");
        assert_eq!(float_repr(-2.5), "-2.5");
        assert_eq!(float_repr(123.456), "123.456");
    }

    #[test]
    fn python_round() {
        assert_eq!(py_round(0.125, 2), 0.12);
        assert_eq!(py_round(0.375, 2), 0.38);
        assert_eq!(py_round(2.675, 2), 2.67);
        assert_eq!(py_round(1.25, 1), 1.2);
        assert_eq!(py_round(1.35, 1), 1.4);
        assert_eq!(py_round(0.7599999999999999, 3), 0.76);
        assert_eq!(np_round(0.125, 2), 0.12);
    }

    #[test]
    fn floor_ops() {
        assert_eq!(floordiv(-7, 2), -4);
        assert_eq!(pymod(-7, 24), 17);
        assert_eq!(floordiv(7, -2), -4);
    }
}
