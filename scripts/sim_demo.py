"""Render a short clip of the simulated cell doing one inspect-and-sort cycle.

Usage (MuJoCo needs an OpenGL context; under WSL use MUJOCO_GL=glfw):
    python scripts/sim_demo.py --out data/sim/sim_demo.mp4
"""

import argparse
import os
import sys

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chhaant.sim.cell import SimCell  # noqa: E402

TOMATO_RED = (0.78, 0.16, 0.10, 1.0)
OVERRIPE = (0.85, 0.42, 0.12, 1.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/sim/sim_demo.mp4")
    args = ap.parse_args()

    cell = SimCell([TOMATO_RED, OVERRIPE, TOMATO_RED, TOMATO_RED, OVERRIPE, TOMATO_RED])
    cell.record = True
    cell.run(0.5)
    for item, verdict in ((0, "pack"), (1, "reject")):
        cell.pick(item)
        cell.place("turntable")
        for _ in range(3):
            cell.rotate_turntable(90)
        cell.pick(item)
        cell.place(verdict)
    cell.run(0.5)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    h, w = cell.frames[0].shape[:2]
    fps = round(1 / (cell.model.opt.timestep * 8))
    vw = cv2.VideoWriter(args.out, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for f in cell.frames:
        vw.write(cv2.cvtColor(f, cv2.COLOR_RGB2BGR))
    vw.release()
    print(f"{len(cell.frames)} frames at {fps} fps -> {args.out}; items now in: {cell.where}")


if __name__ == "__main__":
    main()
