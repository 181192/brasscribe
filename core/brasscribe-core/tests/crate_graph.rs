//! The shape of the workspace: the shared core knows no target, and targets do not know each other.
//!
//! A target (`target-*`) turns the core's notes into one kind of output. The compiler keeps the core
//! free of them only as long as the manifests say so, and cargo accepts a dev-dependency from the
//! core on a target without complaint, so this test reads the manifests through `cargo metadata` and
//! follows every kind of dependency (normal, dev and build) between the workspace's crates.

use std::collections::{BTreeMap, BTreeSet};
use std::process::Command;

use serde_json::Value;

const CORE: &str = "brasscribe-core";

fn is_target(name: &str) -> bool {
    name.starts_with("target-")
}

/// Workspace crate -> the workspace crates it depends on directly, whatever the kind of dependency.
fn workspace_graph() -> BTreeMap<String, BTreeSet<String>> {
    let out = Command::new(env!("CARGO"))
        .args(["metadata", "--format-version", "1", "--no-deps", "--offline"])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()
        .expect("cargo metadata runs");
    assert!(out.status.success(), "cargo metadata failed: {}", String::from_utf8_lossy(&out.stderr));
    let meta: Value = serde_json::from_slice(&out.stdout).expect("cargo metadata writes JSON");
    let packages = meta["packages"].as_array().expect("packages");
    let names: BTreeSet<String> = packages.iter().map(|p| p["name"].as_str().unwrap().to_owned()).collect();
    packages
        .iter()
        .map(|p| {
            let deps = p["dependencies"]
                .as_array()
                .unwrap()
                .iter()
                .map(|d| d["name"].as_str().unwrap().to_owned())
                // A workspace crate is named by path; a registry crate of the same name would not be one.
                .filter(|d| names.contains(d))
                .collect();
            (p["name"].as_str().unwrap().to_owned(), deps)
        })
        .collect()
}

/// Every workspace crate `from` reaches, through any number of steps.
fn reachable(graph: &BTreeMap<String, BTreeSet<String>>, from: &str) -> BTreeSet<String> {
    let mut seen = BTreeSet::new();
    let mut todo: Vec<&str> = graph[from].iter().map(String::as_str).collect();
    while let Some(name) = todo.pop() {
        if seen.insert(name.to_owned()) {
            todo.extend(graph[name].iter().map(String::as_str));
        }
    }
    seen
}

#[test]
fn the_core_depends_on_no_other_crate_of_the_workspace() {
    let graph = workspace_graph();
    let deps = reachable(&graph, CORE);
    assert!(deps.is_empty(), "{CORE} must stand alone in the workspace, but depends on {deps:?}");
}

#[test]
fn targets_do_not_depend_on_each_other() {
    let graph = workspace_graph();
    let targets: Vec<&String> = graph.keys().filter(|n| is_target(n)).collect();
    assert!(targets.len() >= 2, "expected the target crates in the workspace, found {targets:?}");
    for target in targets {
        let deps = reachable(&graph, target);
        let others: Vec<&String> = deps.iter().filter(|d| is_target(d)).collect();
        assert!(others.is_empty(), "{target} must not depend on another target, but depends on {others:?}");
        assert!(deps.contains(CORE), "{target} is expected to build on {CORE}");
    }
}

#[test]
fn the_walk_follows_dependencies_through_other_crates() {
    let graph: BTreeMap<String, BTreeSet<String>> = [("a", vec!["b"]), ("b", vec!["c"]), ("c", vec![]), ("d", vec!["a"])]
        .into_iter()
        .map(|(n, d)| (n.to_owned(), d.into_iter().map(str::to_owned).collect()))
        .collect();
    assert_eq!(reachable(&graph, "d").into_iter().collect::<Vec<_>>(), ["a", "b", "c"]);
    assert!(reachable(&graph, "c").is_empty());
}
