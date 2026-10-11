//! Shared by the integration tests that read data/ (not in git; scripts/worktree-setup.sh links it).

use std::io::Write;
use std::path::{Path, PathBuf};

/// `data/mikkel/repro` in this checkout or in the one BRASSCRIBE_REPO names, when it holds all of
/// `need`. Otherwise the calling test is skipped: a SKIPPED line goes straight to stderr (past the
/// test harness's capture, so it shows even when the test passes), and with BRASSCRIBE_REQUIRE_DATA
/// set the test fails instead.
pub fn repro(test: &str, need: &[&str]) -> Option<PathBuf> {
    let root = std::env::var_os("BRASSCRIBE_REPO").map(PathBuf::from).unwrap_or_else(|| Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."));
    let d = root.join("data/mikkel/repro");
    if need.iter().all(|f| d.join(f).exists()) {
        return Some(d);
    }
    let why = format!("{} is missing {need:?} (set BRASSCRIBE_REPO or run scripts/worktree-setup.sh)", d.display());
    if std::env::var_os("BRASSCRIBE_REQUIRE_DATA").is_some_and(|v| !v.is_empty() && v != "0") {
        panic!("{test}: {why}; BRASSCRIBE_REQUIRE_DATA is set");
    }
    let _ = writeln!(std::io::stderr(), "SKIPPED {test}: {why}");
    None
}
