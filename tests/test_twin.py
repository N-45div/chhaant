"""The web scene export and the MuJoCo twin. Runs where MuJoCo loads (Linux/WSL)."""

import base64
import os

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from chhaant.sim.cell import BINS, SO101_XML, TURNTABLE  # noqa: E402
from chhaant.sim.twin import SimTwin, TwinActuator, TwinInspectors  # noqa: E402
from chhaant.sim.web_scene import COLLISION_GROUP, scene_geoms, scene_meshes, simplify, visible_geoms  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(SO101_XML), reason="run scripts/fetch_so101.py first")
ITEMS = [("T1", "Tomato"), ("T2", "Tomato"), ("A1", "Avocado")]


def test_vertex_clustering_merges_close_vertices_and_drops_collapsed_triangles():
    v = np.array([[0, 0, 0], [0.0005, 0, 0], [1, 0, 0], [0, 1, 0]], float)
    f = np.array([[0, 1, 2], [0, 2, 3], [1, 2, 3]])
    nv, nf = simplify(v, f, cell=0.002)
    assert len(nv) == 3 and len(nf) == 1  # the first triangle collapses, the other two become one


def test_scene_has_no_collision_geoms_and_much_lighter_meshes():
    twin = SimTwin(ITEMS)
    m = twin.cell.model
    geoms = scene_geoms(m)
    shown = visible_geoms(m)
    assert len(geoms) == len(shown) > 0
    assert all(m.geom_group[g] != COLLISION_GROUP for g in shown)
    assert any(m.geom_group[g] == COLLISION_GROUP for g in range(m.ngeom))  # there were some to leave out
    meshes = scene_meshes(m)
    faces = sum(x["nf"] for x in meshes.values())
    assert 0 < faces < 0.25 * m.nmeshface
    one = next(iter(meshes.values()))
    assert len(base64.b64decode(one["v"])) == one["nv"] * 12 and len(base64.b64decode(one["f"])) == one["nf"] * 12


def test_inspecting_carries_the_item_to_the_turntable_and_turns_it():
    twin = SimTwin(ITEMS)
    twin.inspect_motion("T1", [0.0, 90.0])
    out = twin.since(0)
    assert np.linalg.norm(twin.cell.item_pos(0)[:2] - TURNTABLE[:2]) < 0.01
    assert out["next"] > 50 and len(out["frames"][0]) == 7 * len(out["bodies"])
    assert any("turning to 90.0" in c[1] for c in out["captions"])


def test_next_inspection_returns_the_previous_item_to_the_crate():
    twin = SimTwin(ITEMS)
    twin.inspect_motion("T1", [0.0])
    twin.inspect_motion("T2", [0.0])
    assert twin.cell.where[0] == "crate" and twin.cell.on_table == 1


def test_wrappers_play_the_motion_for_real_tool_calls():
    twin = SimTwin(ITEMS)

    class Inner:
        def inspect(self, item):
            return {"verdict": "clean", "looks": [{"azimuth": None}, {"azimuth": 0.0}, {"azimuth": 157.5}]}

    class Item:
        item_id = "T1"

    TwinInspectors(Inner(), twin).inspect(Item())
    TwinActuator(twin).move("T1", "order")
    assert np.linalg.norm(twin.cell.item_pos(0)[:2] - BINS["pack"][:2]) < 0.01
    assert any("to the order" in c[1] for c in twin.since(0)["captions"])
