"""The simulated cell's arm must reach every station and carry items where it is told.

Runs where MuJoCo can load (Linux/WSL); skipped elsewhere. No rendering, so no
OpenGL context is needed.
"""

import os

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from chhaant.sim.cell import BINS, CRATE, SO101_XML, TURNTABLE, SimCell  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(SO101_XML), reason="run scripts/fetch_so101.py first")

RED = (0.8, 0.15, 0.1, 1.0)


@pytest.fixture
def cell():
    return SimCell([RED] * 6)


@pytest.mark.parametrize("target", [CRATE + [0, 0, 0.12], TURNTABLE + [0, 0, 0.12], BINS["pack"] + [0, 0, 0.1], BINS["reject"] + [0, 0, 0.1]])
def test_ik_reaches_each_station_pointing_down(cell, target):
    q = cell.ik(np.array(target))
    d = cell._ik_data
    d.qpos[cell.arm_qpos] = q
    mujoco.mj_kinematics(cell.model, d)
    assert np.linalg.norm(d.site_xpos[cell.site] - target) < 0.012
    assert d.site_xmat[cell.site].reshape(3, 3)[2, 0] < -0.95  # gripper axis points down


def test_item_travels_crate_to_turntable_to_pack_bin(cell):
    cell.pick(0)
    cell.place("turntable")
    assert cell.on_table == 0
    assert np.linalg.norm(cell.item_pos(0)[:2] - TURNTABLE[:2]) < 0.01
    cell.pick(0)
    cell.place("pack")
    assert cell.where[0] == "pack" and cell.on_table is None
    assert np.linalg.norm(cell.item_pos(0)[:2] - BINS["pack"][:2]) < 0.01
    assert cell.where[1:] == ["crate"] * 5


def test_turntable_turns_the_item_with_it(cell):
    cell.pick(2)
    cell.place("turntable")
    before = cell.data.mocap_quat[cell.mocap[2]].copy()
    cell.rotate_turntable(90)
    angle = cell.data.qpos[cell.model.joint("turntable").qposadr[0]]
    assert angle == pytest.approx(np.pi / 2, abs=0.05)
    assert not np.allclose(before, cell.data.mocap_quat[cell.mocap[2]])


def test_wrong_order_of_actions_is_refused(cell):
    with pytest.raises(RuntimeError):
        cell.place("pack")
    cell.pick(0)
    with pytest.raises(RuntimeError):
        cell.pick(1)
    with pytest.raises(ValueError):
        cell.place("floor")
