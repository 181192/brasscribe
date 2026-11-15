import os

# ONNX Runtime (swift-f0, run here in-process) sends events about its use to Microsoft unless this is set when it
# starts, as in scribe_engine.
os.environ["ORT_DISABLE_TELEMETRY"] = "1"
