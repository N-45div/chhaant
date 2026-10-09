import os

import cv2
import numpy as np
import pytest

from chhaant.data.tr6 import Session
from chhaant.robot.turntable import FlipUnavailable, VirtualTurntable


@pytest.fixture
def table(tmp_path):
    files = []
    for i in range(17):  # one top view, then 16 circling views
        rel = f"tr6_512/Tomato/20250723_0920{i:02d}.jpg"
        os.makedirs(os.path.dirname(tmp_path / rel), exist_ok=True)
        img = np.full((40, 30, 3), i * 10, np.uint8)  # brightness encodes the view index
        cv2.imwrite(str(tmp_path / rel), img)
        files.append(rel)
    session = Session(fruit="Tomato", date="20250723", day=1, slot=1, files=files, spoiled=0, temp_c=29.0)
    return VirtualTurntable(session, str(tmp_path))


def view_index(capture):
    return round(float(capture.image.mean()) / 10)


def test_rotation_snaps_to_the_nearest_recorded_angle(table):
    assert table.rotate_to(95) == 90.0
    cap = table.capture()
    assert cap.azimuth == 90.0 and cap.elevation == 40.0
    assert view_index(cap) == 1 + 4  # side view #4 sits at 90 degrees; file 0 is the top view


def test_rotation_wraps_around(table):
    assert table.rotate_to(-22.5) == 337.5
    assert table.rotate_by(45) == 22.5
    assert view_index(table.capture()) == 1 + 1


def test_moves_are_counted_only_when_the_table_turns(table):
    table.rotate_to(0)
    table.rotate_to(90)
    table.rotate_to(91)  # snaps to the same recorded angle
    assert table.moves == 1


def test_top_view_comes_from_above(table):
    cap = table.capture_top()
    assert cap.elevation == 90.0 and view_index(cap) == 0


def test_flip_is_refused_because_the_underside_was_never_photographed(table):
    with pytest.raises(FlipUnavailable):
        table.flip()
