"""Days until an item is past its best: a temperature-aware ripening clock.

Vision reads the item's state (CIELAB colour plus the quality model's two
heads). A ridge regression turns that state into shelf life left in
20 C-equivalent days, and temperature turns those into real days: ripening runs
``q10`` times faster for every 10 C warmer, so

    real days left = days left at 20 C / q10 ** ((T - 20) / 10)

The assumption is physical: the same look means the same remaining ripening
*progress*; heat only changes how fast the clock ticks. ``q10`` is fitted from
data, not assumed. Predictions are made in log1p(days), because shelf-life
errors scale with the horizon, and come with an interval taken from residuals
on held-out fruit.
"""

import math
from dataclasses import dataclass, field

import numpy as np

REF_TEMP_C = 20.0
FEATURES = ("L", "a", "b", "hue_sin", "hue_cos", "chroma", "dark_frac", "p_ripeness", "p_defect")
Q10_GRID = tuple(np.round(np.arange(1.0, 4.01, 0.1), 2))


def rate(temp_c: float, q10: float) -> float:
    """How much faster than at 20 C the item ripens at ``temp_c``."""
    return q10 ** ((temp_c - REF_TEMP_C) / 10.0)


def feature_vector(stats: dict) -> np.ndarray:
    """Model inputs from colour stats and model readings (hue enters as sin/cos: it is an angle)."""
    h = math.radians(stats["hue_deg"])
    row = {**stats, "hue_sin": math.sin(h), "hue_cos": math.cos(h)}
    return np.array([float(row[k]) for k in FEATURES])


@dataclass
class Forecast:
    days: float   # expected days left at the given temperature
    low: float    # lower end of the interval
    high: float   # upper end of the interval


@dataclass
class ForecastModel:
    weights: np.ndarray
    bias: float
    mean: np.ndarray
    std: np.ndarray
    q10: float
    resid_lo: float = 0.0  # residual quantiles in log1p space, from held-out fruit
    resid_hi: float = 0.0
    meta: dict = field(default_factory=dict)

    def days_at_20(self, X: np.ndarray) -> np.ndarray:
        z = (np.atleast_2d(X) - self.mean) / self.std
        return np.expm1(np.clip(z @ self.weights + self.bias, 0.0, None))

    def predict_days(self, X: np.ndarray, temps_c: np.ndarray) -> np.ndarray:
        r = np.array([rate(t, self.q10) for t in np.atleast_1d(temps_c)])
        return self.days_at_20(X) / r

    def predict(self, x: np.ndarray, temp_c: float) -> Forecast:
        d20 = float(self.days_at_20(x)[0])
        r = rate(temp_c, self.q10)
        centre = math.log1p(d20)
        low = math.expm1(max(0.0, centre + self.resid_lo)) / r
        high = math.expm1(max(0.0, centre + self.resid_hi)) / r
        return Forecast(d20 / r, low, high)


def _ridge(Z: np.ndarray, y: np.ndarray, alpha: float) -> tuple[np.ndarray, float]:
    A = np.hstack([Z, np.ones((len(Z), 1))])
    reg = alpha * np.eye(A.shape[1])
    reg[-1, -1] = 0.0  # no penalty on the bias
    coef = np.linalg.solve(A.T @ A + reg, A.T @ y)
    return coef[:-1], float(coef[-1])


def fit(X: np.ndarray, days_left: np.ndarray, temps_c: np.ndarray, alpha: float = 1.0,
        q10_grid: tuple[float, ...] = Q10_GRID) -> ForecastModel:
    """Fit weights and pick q10 by mean absolute error in real days on the training rows."""
    X, days_left, temps_c = np.asarray(X, float), np.asarray(days_left, float), np.asarray(temps_c, float)
    mean, std = X.mean(0), X.std(0) + 1e-9
    Z = (X - mean) / std
    best = None
    for q10 in q10_grid:
        r = np.array([rate(t, q10) for t in temps_c])
        w, b = _ridge(Z, np.log1p(days_left * r), alpha)
        pred = np.expm1(np.clip(Z @ w + b, 0.0, None)) / r
        mae = float(np.mean(np.abs(pred - days_left)))
        if best is None or mae < best[0]:
            best = (mae, q10, w, b)
    _, q10, w, b = best
    return ForecastModel(w, b, mean, std, float(q10), meta={"train_mae": best[0]})


def calibrate_interval(model: ForecastModel, X: np.ndarray, days_left: np.ndarray, temps_c: np.ndarray,
                       coverage: float = 0.8) -> None:
    """Set the interval from residuals (log1p space) on data the model was NOT fitted on."""
    r = np.array([rate(t, model.q10) for t in np.atleast_1d(temps_c)])
    resid = np.log1p(np.asarray(days_left, float) * r) - np.log1p(model.days_at_20(X))
    tail = (1.0 - coverage) / 2.0
    model.resid_lo, model.resid_hi = (float(q) for q in np.quantile(resid, [tail, 1.0 - tail]))
