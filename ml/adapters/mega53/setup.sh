#!/bin/sh
# One-time setup: pinned MSST inference code + Mega-53 v1 weights (licence unstated; personal use).
# The same setup run_adapter.py does before every run: it fetches only what is missing, into
# BRASSCRIBE_MODELS (default <repo>/models), and checks the weights' SHA-256.
here=$(cd "$(dirname "$0")" && pwd)
exec "${BRASSCRIBE_PYTHON:-python3}" "$here/../run_adapter.py" --setup mega53
