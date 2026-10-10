import numpy as np
import pytest

from chhaant.decide.forecast import calibrate_interval, feature_vector, fit, rate


def synthetic(n=600, q10=2.5, seed=0):
    """Items whose colour encodes ripening progress; shelf life left depends on progress and temperature."""
    rng = np.random.default_rng(seed)
    progress = rng.uniform(0, 1, n)                 # 0 just picked .. 1 past its best
    temps = rng.choice([10.0, 20.0, 28.0], n)
    days20 = 8.0 * (1 - progress)                   # 8 days at 20 C from fresh
    days = days20 / np.array([rate(t, q10) for t in temps])
    X = np.column_stack([60 - 30 * progress, 20 * progress - 5, 40 - 10 * progress,
                         np.sin(progress), np.cos(progress), 30 + 5 * progress,
                         0.2 * progress, progress, 0.1 * progress]) + rng.normal(0, 0.3, (n, 9))
    return X, days, temps


def test_rate_is_one_at_20c_and_q10_per_ten_degrees():
    assert rate(20, 2.4) == 1.0
    assert rate(30, 2.4) == pytest.approx(2.4)
    assert rate(10, 2.4) == pytest.approx(1 / 2.4)


def test_fit_recovers_the_temperature_effect():
    X, days, temps = synthetic(q10=2.5)
    model = fit(X, days, temps)
    assert model.q10 == pytest.approx(2.5, abs=0.4)


def test_same_look_lasts_longer_in_the_cold():
    X, days, temps = synthetic()
    model = fit(X, days, temps)
    x = X[:1]
    assert model.predict(x, 10.0).days > model.predict(x, 20.0).days > model.predict(x, 30.0).days


def test_ignoring_temperature_is_worse_on_mixed_storage():
    X, days, temps = synthetic(q10=2.5)
    aware = fit(X[:400], days[:400], temps[:400])
    blind = fit(X[:400], days[:400], temps[:400], q10_grid=(1.0,))
    err = lambda m: np.mean(np.abs(m.predict_days(X[400:], temps[400:]) - days[400:]))
    assert err(aware) < 0.6 * err(blind)


def test_interval_covers_most_held_out_items():
    X, days, temps = synthetic(n=900, seed=3)
    model = fit(X[:300], days[:300], temps[:300])
    calibrate_interval(model, X[300:600], days[300:600], temps[300:600])
    hits = [model.predict(X[i:i + 1], temps[i]).low - 1e-6 <= days[i] <= model.predict(X[i:i + 1], temps[i]).high + 1e-6
            for i in range(600, 900)]
    assert np.mean(hits) > 0.7


def test_feature_vector_encodes_hue_as_an_angle():
    stats = dict(L=50, a=10, b=20, hue_deg=90, chroma=22, dark_frac=0.0, p_ripeness=0.5, p_defect=0.1)
    v = feature_vector(stats)
    assert v[3] == pytest.approx(1.0) and abs(v[4]) < 1e-9
