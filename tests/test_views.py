import math

import numpy as np
import pytest

from chhaant.vision.views import Circle, CoverageMap, sample_on_sphere, sphere_cells


def test_one_view_sees_the_expected_cap():
    for limit, expected in [(90, 0.5), (60, 0.25)]:
        cov = CoverageMap(n_cells=4000, max_obliquity=limit)
        cov.add_view(0, 0)
        assert cov.covered_frac == pytest.approx(expected, abs=0.01)


def test_two_opposite_views_cover_everything_without_a_limit():
    cov = CoverageMap(n_cells=4000, max_obliquity=90)
    cov.add_view(0, 0)
    cov.add_view(180, 0)
    assert cov.covered_frac == pytest.approx(1.0, abs=0.01)


def test_tr6_style_capture_never_inspects_the_underside():
    cov = CoverageMap(n_cells=4000, max_obliquity=60)
    cov.add_view(0, 90)  # top view
    for i in range(16):
        cov.add_view(22.5 * i, 40)
    # Lowest inspected latitude is 40 - 60 = -20 degrees; the cap below it is never seen.
    assert cov.covered_frac == pytest.approx(1 - (1 - math.sin(math.radians(20))) / 2, abs=0.02)
    # Turning the item over (a view from below) is the only move that still adds much.
    best = cov.best_next_view([(0, 40), (90, 0), (0, -90)])
    assert best[:2] == (0, -90) and best[2] > 0.15


def test_best_next_view_after_one_side_is_the_opposite_side():
    cov = CoverageMap(max_obliquity=60)
    cov.add_view(0, 0)
    az, el, gain = cov.best_next_view([(45, 0), (90, 0), (180, 0), (270, 0)])
    assert (az, el) == (180, 0) and gain == pytest.approx(0.25, abs=0.02)


def test_defect_painted_at_image_centre_lands_on_the_facing_cell():
    cells = sphere_cells(2000)
    defect_map = np.zeros((200, 200), np.float32)
    defect_map[95:106, 95:106] = 1.0  # small spot at the centre of the item's disc
    values, seen = sample_on_sphere(defect_map, Circle(100, 100, 80), cells, azimuth_deg=0, elevation_deg=90)
    hot = cells[seen & (values > 0.5)]
    assert len(hot) > 0
    assert np.all(hot[:, 2] > 0.95)  # straight up: what a top-down camera faces


def test_coverage_keeps_the_worst_evidence_per_cell():
    cov = CoverageMap(n_cells=500, max_obliquity=90)
    first = np.full(500, 0.2, np.float32)
    second = np.full(500, 0.7, np.float32)
    cov.add_view(0, 0, values=first)
    cov.add_view(0, 0, values=second)
    assert cov.worst_evidence() == pytest.approx(0.7)
