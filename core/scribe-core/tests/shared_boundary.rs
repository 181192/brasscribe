//! Keeps the last instrument knowledge in this crate out of its other modules.
//!
//! The core serves any instrument family: the brass-band instruments, lineups, arrangers and band
//! score live in `target-brass`, and the crate graph keeps them out (`crate_graph.rs`). What is left
//! here are the modules below. This test fails when another module of the core starts using one of
//! them, so they can leave for their target without anything else following.

use std::fs;
use std::path::{Path, PathBuf};

/// Modules that know about instruments, as `::` paths from the crate root. They may use each other.
const INSTRUMENT_AWARE: &[&str] = &[
    "talking_score", // Norwegian names of the brass-band parts and instruments
];

fn rust_files(dir: &Path, out: &mut Vec<PathBuf>) {
    for entry in fs::read_dir(dir).unwrap() {
        let path = entry.unwrap().path();
        if path.is_dir() {
            rust_files(&path, out);
        } else if path.extension().is_some_and(|e| e == "rs") {
            out.push(path);
        }
    }
}

/// The module a file defines, as path segments from the crate root (`lib.rs` is the root, `[]`).
fn module_path(src: &Path, file: &Path) -> Vec<String> {
    let rel = file.strip_prefix(src).unwrap().with_extension("");
    let mut segments: Vec<String> = rel.iter().map(|s| s.to_string_lossy().into_owned()).collect();
    if matches!(segments.last().map(String::as_str), Some("mod" | "lib")) {
        segments.pop();
    }
    segments
}

fn is_instrument_aware(path: &[String]) -> bool {
    INSTRUMENT_AWARE.iter().any(|aware| {
        let aware: Vec<&str> = aware.split("::").collect();
        path.len() >= aware.len() && path.iter().zip(&aware).all(|(a, b)| a == b)
    })
}

/// The source without `//` and `/* */` comments, so a comment naming a module is not a use.
fn strip_comments(text: &str) -> String {
    let (mut out, mut chars) = (String::new(), text.chars().peekable());
    while let Some(c) = chars.next() {
        match (c, chars.peek()) {
            ('/', Some('/')) => {
                for c in chars.by_ref() {
                    if c == '\n' {
                        out.push('\n');
                        break;
                    }
                }
            }
            ('/', Some('*')) => {
                chars.next();
                let mut prev = ' ';
                for c in chars.by_ref() {
                    if prev == '*' && c == '/' {
                        break;
                    }
                    prev = c;
                }
            }
            ('\'', Some('"')) => {
                // The character literal '"', not the start of a string.
                chars.next();
                chars.next();
            }
            ('"', _) => {
                // Skip string literals too, escapes included.
                let mut escaped = false;
                for c in chars.by_ref() {
                    if !escaped && c == '"' {
                        break;
                    }
                    escaped = !escaped && c == '\\';
                }
            }
            _ => out.push(c),
        }
    }
    out
}

fn ident(text: &str) -> &str {
    let end = text.find(|c: char| !(c.is_ascii_alphanumeric() || c == '_')).unwrap_or(text.len());
    &text[..end]
}

/// The module paths an item names, e.g. `notation::score::Thing` or `notation::{score, xml::El}`
/// (one path per leaf; a glob or the end stops a path).
fn item_paths(text: &str, prefix: &[String]) -> Vec<Vec<String>> {
    let mut path = prefix.to_vec();
    let mut rest = text.trim_start();
    loop {
        let name = ident(rest);
        if name.is_empty() {
            return vec![path];
        }
        path.push(name.to_owned());
        match rest[name.len()..].trim_start().strip_prefix("::") {
            Some(next) => {
                let next = next.trim_start();
                if let Some(group) = next.strip_prefix('{') {
                    return group_items(group).into_iter().flat_map(|item| item_paths(item, &path)).collect();
                }
                rest = next;
            }
            None => return vec![path],
        }
    }
}

/// The items of a `{…}` group, split on top-level commas: `b::{C, D}` is one item.
fn group_items(group: &str) -> Vec<&str> {
    let (mut depth, mut start, mut items) = (0usize, 0usize, Vec::new());
    for (i, c) in group.char_indices() {
        match c {
            '{' => depth += 1,
            '}' if depth == 0 => {
                items.push(&group[start..i]);
                return items;
            }
            '}' => depth -= 1,
            ',' if depth == 0 => {
                items.push(&group[start..i]);
                start = i + 1;
            }
            _ => {}
        }
    }
    items.push(&group[start..]);
    items
}

/// Every module path a file reaches through `crate::` or `super::`, resolved from the crate root.
fn referenced_paths(text: &str, this: &[String]) -> Vec<Vec<String>> {
    let text = strip_comments(text);
    let mut found = Vec::new();
    let mut i = 0;
    while i < text.len() {
        let rest = &text[i..];
        let at_word_start = i == 0 || !text[..i].ends_with(|c: char| c.is_ascii_alphanumeric() || c == '_');
        let base: Option<(Vec<String>, usize)> = if !at_word_start {
            None
        } else if rest.starts_with("crate::") {
            Some((Vec::new(), "crate::".len()))
        } else if rest.starts_with("super::") {
            let mut base = this.to_vec();
            let mut used = 0;
            while rest[used..].starts_with("super::") {
                base.pop();
                used += "super::".len();
            }
            Some((base, used))
        } else {
            None
        };
        let Some((base, used)) = base else {
            i += rest.chars().next().map_or(1, char::len_utf8);
            continue;
        };
        let after = &rest[used..];
        let paths = match after.trim_start().strip_prefix('{') {
            Some(group) => group_items(group).into_iter().flat_map(|item| item_paths(item, &base)).collect(),
            None => item_paths(after, &base),
        };
        found.extend(paths.into_iter().filter(|p| !p.is_empty()));
        i += used;
    }
    found
}

#[test]
fn shared_modules_do_not_use_instrument_knowledge() {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
    let mut files = Vec::new();
    rust_files(&src, &mut files);
    files.sort();
    let mut violations = Vec::new();
    for file in &files {
        let this = module_path(&src, file);
        if this.is_empty() || is_instrument_aware(&this) {
            continue;
        }
        let text = fs::read_to_string(file).unwrap();
        for used in referenced_paths(&text, &this) {
            if is_instrument_aware(&used) {
                violations.push(format!("{} uses crate::{}", this.join("::"), used.join("::")));
            }
        }
    }
    violations.dedup();
    assert!(
        violations.is_empty(),
        "shared modules must not depend on instrument knowledge; move the code into a target \
         crate or pass what it needs in as data:\n  {}",
        violations.join("\n  ")
    );
}

#[test]
fn the_scanner_resolves_crate_super_and_groups() {
    let quantize = vec!["quantize".to_owned()];
    let beams = vec!["notation".to_owned(), "beams".to_owned()];
    let paths = |text: &str, this: &[String]| -> Vec<String> {
        referenced_paths(text, this).into_iter().map(|p| p.join("::")).collect()
    };
    assert_eq!(
        paths("use crate::{model::Note, instruments::{Instrument, Role}};\nlet x = crate::arranger::arrange();", &quantize),
        ["model::Note", "instruments::Instrument", "instruments::Role", "arranger::arrange"]
    );
    assert_eq!(paths("use crate::instruments as i;", &quantize), ["instruments"]);
    assert_eq!(paths("use super::score::Score;", &beams), ["notation::score::Score"]);
    assert_eq!(paths("use super::super::instruments;", &beams), ["instruments"]);
    assert_eq!(paths("use crate::notation::{score, xml::El};", &quantize), ["notation::score", "notation::xml::El"]);
    // Comments and strings are not uses; a quote character literal does not open a string.
    assert!(paths("// see crate::instruments\n/* crate::arranger */ let s = \"crate::pipeline\";", &quantize).is_empty());
    assert_eq!(paths("let q = '\"'; use crate::instruments;", &quantize), ["instruments"]);
    // An identifier that merely ends in `crate` or `super` is not a path start.
    assert!(paths("let supercrate::x = 1; my_super::instruments();", &quantize).is_empty());
}

#[test]
fn the_instrument_aware_check_matches_whole_segments() {
    let p = |s: &str| s.split("::").map(str::to_owned).collect::<Vec<_>>();
    assert!(is_instrument_aware(&p("talking_score::build")));
    assert!(is_instrument_aware(&p("talking_score")));
    assert!(!is_instrument_aware(&p("talking_score_vectors")));
    assert!(!is_instrument_aware(&p("notation::score")));
}

#[test]
fn every_instrument_aware_module_exists() {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
    for module in INSTRUMENT_AWARE {
        let rel = module.replace("::", "/");
        assert!(
            src.join(format!("{rel}.rs")).exists() || src.join(&rel).join("mod.rs").exists(),
            "{module} is listed as instrument-aware but not found"
        );
    }
}
