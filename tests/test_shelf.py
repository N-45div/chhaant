import os

import numpy as np
import pytest

from chhaant.decide.forecast import fit
from chhaant.decide.shelf import ShelfLife

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def photo(progress):
    return dict(L=60 - 30 * progress, a=20 * progress - 5, b=40 - 10 * progress, hue_deg=100 - 60 * progress,
                chroma=30 + 5 * progress, dark_frac=0.2 * progress, p_ripeness=progress, p_defect=0.1 * progress)


@pytest.fixture
def shelf():
    from chhaant.decide.forecast import feature_vector

    rng = np.random.default_rng(0)
    progress = rng.uniform(0, 1, 300)
    X = np.array([feature_vector(photo(p)) for p in progress])
    return ShelfLife(fit(X, 8 * (1 - progress), np.full(300, 20.0)), {"Avocado"})


def test_no_number_for_produce_it_was_not_validated_on(shelf):
    assert shelf.estimate("Tomato", [photo(0.3)], 20.0) is None
    assert not shelf.covers("Tomato")


def test_riper_item_has_fewer_days_left(shelf):
    firm = shelf.estimate("Avocado", [photo(0.1), photo(0.15)], 20.0)
    ripe = shelf.estimate("Avocado", [photo(0.8)], 20.0)
    assert firm.days > ripe.days


def test_unsegmentable_photos_are_ignored(shelf):
    assert shelf.estimate("Avocado", [None], 20.0) is None
    assert shelf.estimate("Avocado", [None, photo(0.5)], 20.0) is not None


def test_saved_forecaster_round_trips(shelf, tmp_path):
    path = tmp_path / "shelf.json"
    shelf.save(str(path))
    again = ShelfLife.load(str(path))
    assert again.estimate("Avocado", [photo(0.4)], 15.0).days == pytest.approx(shelf.estimate("Avocado", [photo(0.4)], 15.0).days)


@pytest.mark.skipif(not os.path.exists(os.path.join(ROOT, "models", "shelf_avocado.json")), reason="run eval/forecast_avocado.py")
def test_shipped_avocado_forecaster_loads():
    shipped = ShelfLife.load(os.path.join(ROOT, "models", "shelf_avocado.json"))
    assert shipped.covers("Avocado") and 2.0 < shipped.model.q10 < 3.5
