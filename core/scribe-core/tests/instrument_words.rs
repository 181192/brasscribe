//! The shared core knows no instruments: its code names none.
//!
//! The crate graph keeps the core from using a target's code (`crate_graph.rs`). This test keeps
//! instrument knowledge from being written into the core itself: a table of part names, a range, a
//! translation. It reads the crate's sources for the names of the instruments and parts the targets
//! know, in the languages they are named in. A new target adds its words here.
//!
//! Two things are left alone on purpose. The unit tests at the end of a file are not read: their
//! fixtures are scores a target wrote and vectors shared with the reference (sounds/README.md).
//! And an unpitched staff is notation, so the drum sounds the writer and the talking score map staff
//! positions to are not instrument words here.

use std::fs;
use std::path::{Path, PathBuf};

/// Lower case; matched anywhere in a line, whatever the case.
const WORDS: &[&str] = &[
    // target-brass, English and Norwegian
    "cornet", "kornett", "trumpet", "trompet", "flugel", "flygel", "horn", "bariton", "baryton", "euphonium", "eufonium", "trombone",
    "tuba", "ess-bass", "slagverk",
    // target-fretted
    "guitar", "gitar", "ukulele", "mandolin", "banjo",
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

/// The lines of a source file before its unit tests, numbered from 1.
fn code_lines(text: &str) -> impl Iterator<Item = (usize, &str)> {
    text.lines().enumerate().take_while(|(_, l)| l.trim() != "#[cfg(test)]").map(|(i, l)| (i + 1, l))
}

/// (line number, word) for every instrument word in the code of a file.
fn instrument_words(text: &str) -> Vec<(usize, &'static str)> {
    code_lines(text)
        .flat_map(|(n, line)| {
            let line = line.to_lowercase();
            WORDS.iter().filter(move |w| line.contains(**w)).map(move |w| (n, *w))
        })
        .collect()
}

#[test]
fn the_core_names_no_instrument() {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
    let mut files = Vec::new();
    rust_files(&src, &mut files);
    files.sort();
    assert!(files.len() > 20, "expected the core's sources under {}", src.display());
    let mut found = Vec::new();
    for file in &files {
        let text = fs::read_to_string(file).unwrap();
        let rel = file.strip_prefix(&src).unwrap().display().to_string();
        found.extend(instrument_words(&text).into_iter().map(|(n, w)| format!("{rel}:{n}: {w}")));
    }
    assert!(
        found.is_empty(),
        "the shared core must not know instruments; move what names them into a target crate, or have \
         the target pass it in as data:\n  {}",
        found.join("\n  ")
    );
}

#[test]
fn the_reader_finds_words_in_code_and_comments_but_not_in_unit_tests() {
    let text = "/// Solo Cornet\nlet a = \"althorn\";\nfn f() {}\n#[cfg(test)]\nmod tests { const P: &str = \"Tuba\"; }\n";
    assert_eq!(instrument_words(text), [(1, "cornet"), (2, "horn")]);
    assert!(instrument_words("// the percussion staff, a bass drum, the bass line").is_empty());
}

#[test]
fn what_is_not_read_is_the_tests_module() {
    // What follows `#[cfg(test)]` is not read, so in every file it has to be the one tests module.
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
    let mut files = Vec::new();
    rust_files(&src, &mut files);
    for file in &files {
        let text = fs::read_to_string(file).unwrap();
        let marks: Vec<usize> = text.lines().enumerate().filter(|(_, l)| l.trim() == "#[cfg(test)]").map(|(i, _)| i).collect();
        assert!(marks.len() <= 1, "{}: more than one `#[cfg(test)]`", file.display());
        if let Some(&at) = marks.first() {
            let next = text.lines().nth(at + 1).unwrap_or("");
            assert!(next.starts_with("mod "), "{}: `#[cfg(test)]` is not on a tests module", file.display());
        }
    }
}
