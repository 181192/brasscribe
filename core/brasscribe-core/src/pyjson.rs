//! `json.dumps(obj, indent=1)` as written by the Python reference: ASCII
//! output with `\uXXXX` escapes, Python float repr, one-space indentation.

use serde_json::Value;

use crate::py::float_repr;

pub fn dumps(v: &Value) -> String {
    let mut out = String::new();
    write(v, 0, &mut out);
    out
}

/// `json.dumps(obj)` without indentation (", " and ": " separators).
pub fn dumps_compact(v: &Value) -> String {
    let mut out = String::new();
    compact(v, &mut out);
    out
}

fn compact(v: &Value, out: &mut String) {
    match v {
        Value::Array(a) => {
            out.push('[');
            for (i, x) in a.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                compact(x, out);
            }
            out.push(']');
        }
        Value::Object(m) => {
            out.push('{');
            for (i, (k, x)) in m.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                write_str(k, out);
                out.push_str(": ");
                compact(x, out);
            }
            out.push('}');
        }
        other => write(other, 0, out),
    }
}

fn write(v: &Value, level: usize, out: &mut String) {
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                out.push_str(&i.to_string());
            } else if let Some(u) = n.as_u64() {
                out.push_str(&u.to_string());
            } else {
                out.push_str(&float_repr(n.as_f64().unwrap()));
            }
        }
        Value::String(s) => write_str(s, out),
        Value::Array(a) => {
            if a.is_empty() {
                out.push_str("[]");
                return;
            }
            out.push('[');
            for (i, x) in a.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                newline(level + 1, out);
                write(x, level + 1, out);
            }
            newline(level, out);
            out.push(']');
        }
        Value::Object(m) => {
            if m.is_empty() {
                out.push_str("{}");
                return;
            }
            out.push('{');
            for (i, (k, x)) in m.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                newline(level + 1, out);
                write_str(k, out);
                out.push_str(": ");
                write(x, level + 1, out);
            }
            newline(level, out);
            out.push('}');
        }
    }
}

fn newline(level: usize, out: &mut String) {
    out.push('\n');
    for _ in 0..level {
        out.push(' ');
    }
}

fn write_str(s: &str, out: &mut String) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            c if (c as u32) < 0x20 || (c as u32) > 0x7e => {
                let mut buf = [0u16; 2];
                for u in c.encode_utf16(&mut buf) {
                    out.push_str(&format!("\\u{:04x}", u));
                }
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn layout() {
        let v = json!({"a": [1, 2.0, "é"], "b": [], "c": null});
        assert_eq!(dumps(&v), "{\n \"a\": [\n  1,\n  2.0,\n  \"\\u00e9\"\n ],\n \"b\": [],\n \"c\": null\n}");
    }
}
