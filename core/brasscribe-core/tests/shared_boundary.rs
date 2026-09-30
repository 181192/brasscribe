//! Keeps instrument knowledge out of the shared modules.
//!
//! The transcription side of the core (model, beats, quantization, spelling, keys, confidence and the
//! rest) is meant to serve any instrument family. Only the modules below know about brass-band
//! instruments, lineups, arranging or the score layout built on them. This test fails when a shared
//! module starts using one of them, so the boundary stays where it is while both sides keep changing.

use std::fs;
use std::path::{Path, PathBuf};

/// Modules that may use instrument knowledge, as paths under `src/` without the `.rs`.
const INSTRUMENT_AWARE: &[&str] = &["instruments", "arranger", "difficulty", "musicxml", "notation/score", "pipeline", "lib"];

/// What a shared module must not reference.
const FORBIDDEN: &[&str] = &["instruments", "arranger", "difficulty", "musicxml", "pipeline"];

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

fn module_name(src: &Path, file: &Path) -> String {
    let rel = file.strip_prefix(src).unwrap().with_extension("");
    let name = rel.to_string_lossy().replace('\\', "/");
    name.strip_suffix("/mod").map(str::to_owned).unwrap_or(name)
}

/// Every `crate::<module>` a file names, including `use crate::{a, b::{C, D}}` groups.
fn referenced_modules(text: &str) -> Vec<String> {
    let head = |item: &str| item.trim().split("::").next().unwrap_or("").trim().to_owned();
    let mut found = Vec::new();
    for (i, _) in text.match_indices("crate::") {
        let rest = &text[i + "crate::".len()..];
        if let Some(group) = rest.strip_prefix('{') {
            // Split on top-level commas only: `b::{C, D}` is one item.
            let (mut depth, mut item) = (0usize, String::new());
            for c in group.chars() {
                match c {
                    '}' if depth == 0 => break,
                    ',' if depth == 0 => {
                        found.push(head(&item));
                        item.clear();
                        continue;
                    }
                    '{' => depth += 1,
                    '}' => depth -= 1,
                    _ => {}
                }
                item.push(c);
            }
            found.push(head(&item));
        } else {
            found.push(rest.chars().take_while(|c| c.is_ascii_alphanumeric() || *c == '_').collect());
        }
    }
    found.retain(|m| !m.is_empty());
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
        let module = module_name(&src, file);
        if INSTRUMENT_AWARE.contains(&module.as_str()) {
            continue;
        }
        let text = fs::read_to_string(file).unwrap();
        for used in referenced_modules(&text) {
            if FORBIDDEN.contains(&used.as_str()) {
                violations.push(format!("{module} uses crate::{used}"));
            }
        }
    }
    violations.dedup();
    assert!(
        violations.is_empty(),
        "shared modules must not depend on instrument knowledge; move the code into an instrument-aware \
         module or pass what it needs in as data:\n  {}",
        violations.join("\n  ")
    );
}

#[test]
fn the_reference_scanner_sees_grouped_and_inline_uses() {
    let text = "use crate::{model::Note, instruments::{Instrument, Role}};\nlet x = crate::arranger::arrange();";
    assert_eq!(referenced_modules(text), ["model", "instruments", "arranger"]);
}

#[test]
fn every_instrument_aware_module_exists() {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
    for module in INSTRUMENT_AWARE {
        let file = src.join(format!("{module}.rs"));
        let dir = src.join(module).join("mod.rs");
        assert!(file.exists() || dir.exists(), "{module} is listed as instrument-aware but not found");
    }
}
