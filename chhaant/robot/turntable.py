"""The inspection cell's turntable and camera.

``VirtualTurntable`` replays a recorded TR-6 session: TR-6 photographed each
fruit from 16 evenly spaced angles plus once from above, so asking the
turntable to rotate returns the real photo taken nearest that angle. The
pixels the agent reasons over are real; only the motion is simulated.

Turning the item over is refused, because TR-6 never photographed the
underside. The decision logic has to live with unseen surface (or ask a
person) rather than pretend it looked.
"""

import os
from dataclasses import dataclass

import cv2
import numpy as np

from chhaant.data.tr6 import Session

SIDE_ELEVATION = 40.0  # TR-6's circling shots look down at roughly 40 degrees
TOP_ELEVATION = 90.0


class FlipUnavailable(RuntimeError):
    """The cell cannot show the item's underside."""


@dataclass
class Capture:
    image: np.ndarray   # BGR photo
    azimuth: float      # degrees around the item
    elevation: float    # degrees above the horizon (90 = straight down)
    source: str         # where the pixels came from


class VirtualTurntable:
    def __init__(self, session: Session, data_root: str):
        if len(session.side_views) < 2:
            raise ValueError("session has no circling views to replay")
        self.session = session
        self.data_root = data_root
        self.step = 360.0 / len(session.side_views)
        self.azimuth = 0.0
        self.moves = 0

    def rotate_to(self, azimuth_deg: float) -> float:
        """Turn to the recorded angle nearest ``azimuth_deg``; returns the angle reached."""
        index = round((azimuth_deg % 360.0) / self.step) % len(self.session.side_views)
        reached = index * self.step
        if reached != self.azimuth:
            self.moves += 1
        self.azimuth = reached
        return reached

    def rotate_by(self, delta_deg: float) -> float:
        return self.rotate_to(self.azimuth + delta_deg)

    def flip(self) -> None:
        raise FlipUnavailable("TR-6 never photographed the underside; it stays uninspected")

    def _read(self, rel_path: str) -> np.ndarray:
        img = cv2.imread(os.path.join(self.data_root, rel_path))
        if img is None:
            raise FileNotFoundError(rel_path)
        return img

    def capture(self) -> Capture:
        """Photo from the camera at the current angle."""
        rel = self.session.side_views[round(self.azimuth / self.step) % len(self.session.side_views)]
        return Capture(self._read(rel), self.azimuth, SIDE_ELEVATION, f"tr6:{rel}")

    def capture_top(self) -> Capture:
        """Photo from the overhead camera."""
        rel = self.session.top_view
        return Capture(self._read(rel), 0.0, TOP_ELEVATION, f"tr6:{rel}")
