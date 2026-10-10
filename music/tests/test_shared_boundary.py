"""Keeps instrument knowledge out of the shared modules of the Python reference.

In the Rust port the same line is a crate boundary: the modules below are the crate `target-brass`
(core/targets/brass/src), the rest is the shared core (core/scribe-core), and
core/scribe-core/tests/crate_graph.rs keeps the core from depending on a target. This package is not
split yet, so here a test holds the line: only the modules below know about brass-band instruments,
lineups, arranging or the score written from them. The rest serves any instrument family, and this test
fails when one of them starts importing an instrument-aware module.
"""

import ast
from pathlib import Path

import brasscribe_music

# target-brass's modules, by the same names. `musicxml` is brass only in part: its band score
# (band_score, band_sounds) is target-brass's `musicxml`, its writer is the shared core's
# `notation::score`, which this package has not separated. target-brass's `pipeline` is the entry
# points in eval/brasscribe_eval, outside this package.
INSTRUMENT_AWARE = {"instruments", "arranger", "difficulty", "musicxml"}


def imported_modules(tree: ast.AST) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 1 and node.module:
                found.add(node.module.split(".")[0])
            elif node.level == 1:
                found.update(alias.name for alias in node.names)
            elif node.module == "brasscribe_music":
                found.update(alias.name for alias in node.names)
            elif node.module and node.module.startswith("brasscribe_music."):
                found.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            found.update(a.name.split(".")[1] for a in node.names if a.name.startswith("brasscribe_music."))
    return found


def test_shared_modules_do_not_import_instrument_knowledge():
    package = Path(brasscribe_music.__file__).parent
    violations = []
    for path in sorted(package.glob("*.py")):
        if path.stem in INSTRUMENT_AWARE or path.stem == "__init__":
            continue
        used = imported_modules(ast.parse(path.read_text(), filename=str(path))) & INSTRUMENT_AWARE
        violations += [f"{path.stem} imports {m}" for m in sorted(used)]
    assert not violations, "shared modules must not depend on instrument knowledge:\n  " + "\n  ".join(violations)


def test_the_import_scanner_sees_inline_and_grouped_imports():
    tree = ast.parse("def f():\n    from .instruments import BRASS_BAND\nfrom . import arranger, quantize\n"
                     "from brasscribe_music import difficulty\nimport brasscribe_music.musicxml as mx\n")
    assert imported_modules(tree) == {"instruments", "arranger", "quantize", "difficulty", "musicxml"}


def test_every_instrument_aware_module_exists():
    package = Path(brasscribe_music.__file__).parent
    assert all((package / f"{m}.py").exists() for m in INSTRUMENT_AWARE)
