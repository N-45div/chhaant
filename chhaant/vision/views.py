"""Which parts of the item have actually been inspected?

The item is modelled as a unit sphere, z pointing up, split into equal-area
cells. A camera at (azimuth, elevation) looks at the sphere's centre. A cell
counts as inspected only when a camera saw it within ``max_obliquity`` of
head-on: near the silhouette a bruise is foreshortened to a few pixels, so a
grazing glimpse is not an inspection.

Geometry gives the limits before any model runs. TR-6's 16 side views at about
40 degrees elevation plus one top view inspect at most ~67% of the surface
(60 degree limit): everything below -20 degrees latitude is never seen unless
the item is turned over. That is the robot's "flip it" action.

Defect evidence is put on the sphere by projecting each cell into the photo
(orthographic, with the item's circle fitted from its mask) and sampling the
per-pixel defect map there.
"""

from dataclasses import dataclass

import cv2
import numpy as np

DEFAULT_CELLS = 2000
DEFAULT_MAX_OBLIQUITY = 60.0


def sphere_cells(n: int = DEFAULT_CELLS) -> np.ndarray:
    """``n`` near-uniform unit vectors (Fibonacci lattice), shape (n, 3)."""
    i = np.arange(n) + 0.5
    z = 1.0 - 2.0 * i / n
    r = np.sqrt(1.0 - z * z)
    phi = np.pi * (1.0 + 5 ** 0.5) * i
    return np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)


def view_vector(azimuth_deg: float, elevation_deg: float) -> np.ndarray:
    """Unit vector from the item's centre towards the camera."""
    az, el = np.radians(azimuth_deg), np.radians(elevation_deg)
    return np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])


def camera_basis(azimuth_deg: float, elevation_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(toward camera, image right, image up) for a camera looking at the centre."""
    v = view_vector(azimuth_deg, elevation_deg)
    right = np.cross(np.array([0.0, 0.0, 1.0]), v)
    if np.linalg.norm(right) < 1e-6:  # straight down: keep image right tied to the azimuth
        az = np.radians(azimuth_deg)
        right = np.array([-np.sin(az), np.cos(az), 0.0])
    right /= np.linalg.norm(right)
    return v, right, np.cross(v, right)


def seen_cells(cells: np.ndarray, azimuth_deg: float, elevation_deg: float,
               max_obliquity: float = DEFAULT_MAX_OBLIQUITY) -> np.ndarray:
    return cells @ view_vector(azimuth_deg, elevation_deg) >= np.cos(np.radians(max_obliquity))


@dataclass
class Circle:
    cx: float
    cy: float
    r: float


def circle_from_mask(mask: np.ndarray) -> Circle:
    """Centroid and equal-area radius of the item's mask."""
    m = cv2.moments(mask, binaryImage=True)
    if m["m00"] == 0:
        raise ValueError("empty mask")
    return Circle(m["m10"] / m["m00"], m["m01"] / m["m00"], float(np.sqrt(m["m00"] / np.pi)))


def sample_on_sphere(value_map: np.ndarray, circle: Circle, cells: np.ndarray,
                     azimuth_deg: float, elevation_deg: float,
                     max_obliquity: float = DEFAULT_MAX_OBLIQUITY) -> tuple[np.ndarray, np.ndarray]:
    """Per-cell values read from a per-pixel map. Returns (values, seen); unseen cells are NaN."""
    v, right, up = camera_basis(azimuth_deg, elevation_deg)
    seen = cells @ v >= np.cos(np.radians(max_obliquity))
    x = np.round(circle.cx + circle.r * (cells @ right)).astype(int)
    y = np.round(circle.cy - circle.r * (cells @ up)).astype(int)
    h, w = value_map.shape[:2]
    seen &= (x >= 0) & (x < w) & (y >= 0) & (y < h)
    values = np.full(len(cells), np.nan, np.float32)
    values[seen] = value_map[y[seen], x[seen]]
    return values, seen


class CoverageMap:
    """Accumulates what has been inspected, and the worst defect evidence per cell."""

    def __init__(self, n_cells: int = DEFAULT_CELLS, max_obliquity: float = DEFAULT_MAX_OBLIQUITY):
        self.cells = sphere_cells(n_cells)
        self.max_obliquity = max_obliquity
        self.seen_count = np.zeros(n_cells, np.int32)
        self.evidence = np.full(n_cells, np.nan, np.float32)
        self.views: list[tuple[float, float]] = []

    def add_view(self, azimuth_deg: float, elevation_deg: float, values: np.ndarray | None = None,
                 seen: np.ndarray | None = None) -> None:
        if seen is None:
            seen = seen_cells(self.cells, azimuth_deg, elevation_deg, self.max_obliquity)
        self.seen_count += seen
        if values is not None:
            both = seen & ~np.isnan(values)
            self.evidence[both] = np.fmax(self.evidence[both], values[both])
        self.views.append((azimuth_deg, elevation_deg))

    @property
    def covered_frac(self) -> float:
        return float(np.mean(self.seen_count > 0))

    def gain(self, azimuth_deg: float, elevation_deg: float) -> float:
        """Share of the surface a view at this pose would inspect for the first time."""
        new = seen_cells(self.cells, azimuth_deg, elevation_deg, self.max_obliquity) & (self.seen_count == 0)
        return float(np.mean(new))

    def best_next_view(self, candidates: list[tuple[float, float]]) -> tuple[float, float, float]:
        """The candidate pose that inspects the most new surface: (azimuth, elevation, gain)."""
        scored = [(az, el, self.gain(az, el)) for az, el in candidates]
        return max(scored, key=lambda t: t[2])

    def worst_evidence(self) -> float:
        return float(np.nanmax(self.evidence)) if np.any(~np.isnan(self.evidence)) else 0.0
