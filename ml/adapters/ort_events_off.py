"""Runs a package's command with ONNX Runtime's telemetry events switched off first:
`python ort_events_off.py <command> <args>...`, in the adapter's environment.

On Windows the runtime writes its events to ETW for Windows' diagnostic data and does not read ORT_DISABLE_TELEMETRY;
its events are switched off only by a call in the process that runs it, before its sessions. The separator, homr and
basic-pitch adapters run their packages' own programs, so run_adapter.py starts those through this file there: it
switches the events off, then runs the command's entry point in the same process. (The runtime still writes one event
as it loads, before the call can run; THIRD_PARTY_NOTICES.md.)
"""

from __future__ import annotations

import sys
from importlib.metadata import entry_points


def main(argv: list[str]) -> object:
    """Runs the command; returns what its entry point returns, for sys.exit, as a console script's wrapper does
    (None or 0 is success, another number its exit status, anything else printed and status 1)."""
    name, args = argv[0], argv[1:]
    try:
        import onnxruntime
    except ImportError:  # an environment without the runtime: nothing to switch off
        pass
    else:
        onnxruntime.disable_telemetry_events()
    found = entry_points(group="console_scripts", name=name)
    if not found:
        raise SystemExit(f"ort_events_off.py: no command {name!r} in this environment")
    sys.argv = [name, *args]
    return next(iter(found)).load()()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
