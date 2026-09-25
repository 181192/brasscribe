import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import contrast as c  # noqa: E402


def test_contrast_extremes():
    assert round(c.contrast("#000000", "#FFFFFF"), 2) == 21.0
    assert round(c.contrast("#777777", "#FFFFFF"), 2) == 4.48


def test_ciede2000_reference_pair():
    # Sharma et al. (2005) test data, pair 1: 2.0425
    assert abs(c.ciede2000((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485)) - 2.0425) < 1e-3


def test_simulation_keeps_greys():
    grey = c.simulate((0.5, 0.5, 0.5), "deutan")
    assert all(abs(x - 0.5) < 0.01 for x in grey)
