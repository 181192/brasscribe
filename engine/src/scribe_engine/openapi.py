"""Write the engine's OpenAPI spec: `python -m brasscribe_engine.openapi engine/openapi.json`.

The committed spec is the contract the native apps generate clients from; a
test fails when the app and the committed file disagree.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from .api import create_app
from .config import Settings


def spec() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        return create_app(Settings(data_dir=Path(tmp))).openapi()


def render() -> str:
    return json.dumps(spec(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("engine/openapi.json")
    out.write_text(render())
    print(out)


if __name__ == "__main__":
    main()
