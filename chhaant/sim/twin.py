"""A MuJoCo twin of the cell that turns the agent's actions into arm motion.

The agent's tools do not change. ``TwinInspectors`` and ``TwinActuator`` wrap
the real inspectors and the cell's actuator, so that:

* inspecting an item carries it to the turntable and turns it to exactly the
  angles the inspection photographed (avocados show both sides);
* placing an item carries it to the order bin (green), the sell-today tray
  (amber), the reject bin (red) or back to its crate slot.

Every recorded frame holds the world pose of each moving body, for the web
viewer; captions mark what the arm is doing. The pixels the decisions use are
still the real photographs; only the motion is simulated.
"""

import threading

import numpy as np

from chhaant.sim.cell import PHYSICS_PER_FRAME, SimCell

PRODUCE_RGBA = {
    "Tomato": (0.80, 0.16, 0.10, 1), "Mango": (0.93, 0.62, 0.15, 1), "Avocado": (0.22, 0.29, 0.12, 1),
    "Banana": (0.95, 0.85, 0.25, 1), "Guava": (0.55, 0.70, 0.30, 1), "Carrot": (0.95, 0.50, 0.10, 1),
    "Indian_Gooseberry": (0.70, 0.80, 0.40, 1),
}
DEST = {"order": "pack", "reject": "reject", "sell_today": "sell_today", "crate": "crate"}
RECORD_EVERY = 2  # every other physics frame: 12.5 poses per second of motion


class SimTwin:
    def __init__(self, items: list[tuple[str, str]]):
        self.index = {item_id: i for i, (item_id, _) in enumerate(items)}
        self.names = [item_id for item_id, _ in items]
        self.rgba = [PRODUCE_RGBA.get(produce, (0.6, 0.6, 0.6, 1)) for _, produce in items]
        self.cell = SimCell(self.rgba)
        m = self.cell.model
        self.moving = [b for b in range(1, m.nbody) if m.body_jntnum[b] or m.body_mocapid[b] >= 0 or m.body_parentid[b] != 0]
        self.fps = 1.0 / (m.opt.timestep * PHYSICS_PER_FRAME * RECORD_EVERY)
        self.frames: list[list[float]] = []
        self.captions: list[list] = []
        self._lock = threading.Lock()
        self._tick = 0
        self.cell.pose_sink = self._record
        self._record(self.cell.data, force=True)

    def _record(self, data, force: bool = False) -> None:
        self._tick += 1
        if not force and self._tick % RECORD_EVERY:
            return
        pose = np.concatenate([np.concatenate([data.xpos[b], data.xquat[b]]) for b in self.moving])
        with self._lock:
            self.frames.append([round(float(x), 4) for x in pose])

    def caption(self, text: str) -> None:
        with self._lock:
            self.captions.append([len(self.frames), text])

    def since(self, after: int) -> dict:
        with self._lock:
            return {"frames": self.frames[after:], "captions": [c for c in self.captions if c[0] >= after],
                    "next": len(self.frames), "fps": self.fps, "bodies": self.moving}

    # ---- motions, driven by the agent's tools -------------------------------
    def _onto_turntable(self, item_id: str) -> None:
        i, cell = self.index[item_id], self.cell
        other = cell.on_table
        if other is not None and other != i:
            self.caption(f"{self.names[other]} back to the crate")
            cell.pick(other)
            cell.place("crate")
        if cell.on_table != i:
            if cell.where[i] != "crate":
                return  # already placed elsewhere: it is not brought back for a look
            self.caption(f"{item_id} onto the turntable")
            cell.pick(i)
            cell.place("turntable")

    def inspect_motion(self, item_id: str, azimuths: list[float]) -> None:
        self._onto_turntable(item_id)
        for az in azimuths:
            self.caption(f"{item_id}: turning to {az:.1f} degrees")
            self.cell.rotate_turntable_to(az)

    def place_motion(self, item_id: str, destination: str) -> None:
        i, cell = self.index[item_id], self.cell
        if destination == "crate" and cell.where[i] == "crate" and cell.on_table != i:
            return
        label = {"order": "the order", "reject": "the reject bin", "sell_today": "the sell-today tray", "crate": "the crate"}
        self.caption(f"{item_id} to {label.get(destination, destination)}")
        cell.pick(i)
        cell.place(DEST[destination])


class TwinInspectors:
    """Real inspection results, with the matching motion played on the twin."""

    def __init__(self, inner, twin: SimTwin):
        self.inner, self.twin = inner, twin

    def inspect(self, item):
        result = self.inner.inspect(item)
        angles = [l["azimuth"] for l in result.get("looks", []) if l.get("azimuth") is not None]
        self.twin.inspect_motion(item.item_id, angles or [0.0, 180.0])  # avocados: the two photographed sides
        return result

    def look(self, item, azimuth: float):
        out = self.inner.look(item, azimuth)
        self.twin.inspect_motion(item.item_id, [out["azimuth"]])
        return out


class TwinActuator:
    def __init__(self, twin: SimTwin):
        self.twin = twin
        self.moves: list[tuple[str, str]] = []

    def move(self, item_id: str, destination: str) -> None:
        self.moves.append((item_id, destination))
        self.twin.place_motion(item_id, destination)
