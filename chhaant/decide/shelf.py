"""Shelf-life estimates the robot is allowed to act on.

Only one forecaster has measured accuracy: the avocado ripening clock
(eval/forecast_avocado.py, 1.05-day error on 426 held-out fruit, q10 2.66).
A forecaster learned on some produce types did not transfer to others
(eval/forecast_tr6.py), so for any produce not listed here the robot gives no
number and a person decides timing.

``measure`` is the single photo-measurement step shared by the evaluation and
the robot: segment, backdrop white balance, CIELAB colour, quality model.
"""

import json

import numpy as np

from chhaant.decide.forecast import Forecast, ForecastModel, feature_vector
from chhaant.vision.color import ColourStats, apply_gains, background_gains, colour_stats, item_window
from chhaant.vision.segment import segment_fruit

COLOUR_ERODE_PX = 3  # colour_stats' default edge trim


def colour_reading(bgr: np.ndarray, mask: np.ndarray) -> ColourStats:
    """``colour_stats(white_balance_from_background(bgr, mask), mask)``, computed on the
    item's window only: the backdrop sets the gains, but only item pixels are measured."""
    gains = background_gains(bgr, mask)
    rows, cols = item_window(mask, COLOUR_ERODE_PX + 1)  # room for the erosion to see the edge
    return colour_stats(apply_gains(bgr[rows, cols], gains), mask[rows, cols], COLOUR_ERODE_PX)


def measure(bgr: np.ndarray, quality_model) -> dict | None:
    """Colour and model readings for one photo, or None when the item cannot be segmented."""
    seg = segment_fruit(bgr)
    if not seg.ok:
        return None
    st = colour_reading(bgr, seg.mask)
    reading = quality_model.predict(bgr, seg.mask)
    return dict(L=st.L, a=st.a, b=st.b, hue_deg=st.hue_deg, chroma=st.chroma, dark_frac=st.dark_frac,
                p_ripeness=reading.ripeness, p_defect=reading.defect)


class ShelfLife:
    """A validated forecaster for the produce types listed in ``produce``."""

    def __init__(self, model: ForecastModel, produce: set[str]):
        self.model = model
        self.produce = produce

    @classmethod
    def load(cls, path: str) -> "ShelfLife":
        with open(path) as fh:
            d = json.load(fh)
        return cls(ForecastModel.from_dict(d["model"]), set(d["produce"]))

    def save(self, path: str) -> None:
        with open(path, "w") as fh:
            json.dump({"model": self.model.to_dict(), "produce": sorted(self.produce)}, fh, indent=1)

    def covers(self, produce: str) -> bool:
        return produce in self.produce

    def estimate(self, produce: str, photos: list[dict], temp_c: float) -> Forecast | None:
        """Days left at ``temp_c`` from one or more photos' measurements; None if not validated."""
        photos = [p for p in photos if p is not None]
        if not self.covers(produce) or not photos:
            return None
        x = np.mean([feature_vector(p) for p in photos], axis=0, keepdims=True)
        return self.model.predict(x, temp_c)
