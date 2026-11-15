"""scribe engine: job DAG, artifact cache, profiles, benchmark suites and the HTTP service."""

import os

__version__ = "0.1.0"

# ONNX Runtime (in the adapters, and swift-f0 in the evaluation) sends events about its use to Microsoft unless this
# is set when it starts: set for this process and every adapter it runs. On Windows the runtime does not read it; there
# the adapters that load it themselves switch its events off (ml/adapters/swift-f0).
os.environ["ORT_DISABLE_TELEMETRY"] = "1"
