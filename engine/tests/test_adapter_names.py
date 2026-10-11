"""The adapter scripts run in environments of their own, which the tests here do not have, so none of them is
imported by a test. This reads them instead: a name a script uses must be one it binds, imports or Python has,
and a name it imports from the script beside it must be defined there. A function removed from one script and
still called from another is found here, not by a job that fails."""
import ast
import builtins
from pathlib import Path

import pytest

from brasscribe_engine import config

SCRIPTS = sorted(
    p for folder in ("ml/adapters", "convert", "eval/brasscribe_eval", "apps/android/pitch/src/test/python")
    for p in (config.REPO_ROOT / folder).rglob("*.py")
    if not {".venv", "__pycache__", "node_modules", "site-packages"} & set(p.parts)
)


def bound(tree: ast.AST) -> set[str]:
    """Every name the script binds anywhere: scopes are not told apart, so a name is only missed when it is bound nowhere."""
    names = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.MatchAs) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.MatchStar) and node.name:
            names.add(node.name)
    return names


def top_level(tree: ast.Module) -> set[str]:
    return bound(ast.Module(body=[n for n in tree.body], type_ignores=[]))


def test_there_are_adapter_scripts():
    assert any(p.parent.name == "swift-f0" for p in SCRIPTS), SCRIPTS


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: str(p.relative_to(config.REPO_ROOT)))
def test_a_script_uses_only_names_that_exist(script: Path):
    tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    star = any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in ast.walk(tree))
    if not star:
        known = bound(tree)
        missing = sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)} - known)
        assert not missing, f"{script} uses names it never binds: {missing}"
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
            continue
        beside = script.parent / f"{node.module}.py"
        if not beside.is_file():
            continue
        there = top_level(ast.parse(beside.read_text(encoding="utf-8")))
        missing = sorted(a.name for a in node.names if a.name != "*" and a.name not in there)
        assert not missing, f"{script} imports {missing} from {beside.name}, which does not define them"
