from chhaant.decide.forecast import Forecast
from chhaant.decide.route import route


def test_defective_is_rejected_whatever_the_forecast():
    assert route("defective", Forecast(5, 4, 6), 1).action == "reject"


def test_undecided_inspection_goes_to_a_person():
    assert route("escalate", Forecast(5, 4, 6), 1).action == "ask"


def test_clean_but_over_ripe_is_sold_today_not_packed():
    # the TR-6 mango case: no visible defect, ripeness 0.9
    r = route("clean", Forecast(0.4, 0.1, 0.8), 3)
    assert r.action == "sell_today"


def test_firm_item_is_packed_for_thursday():
    assert route("clean", Forecast(5.0, 3.5, 6.5), 3).action == "pack"


def test_item_that_will_not_last_is_kept_for_a_sooner_order():
    r = route("clean", Forecast(1.8, 1.2, 2.4), 3)
    assert r.action == "skip"
    assert route("clean", Forecast(1.8, 1.2, 2.4), 0.5).action == "pack"  # fine for tonight


def test_borderline_shelf_life_goes_to_a_person():
    r = route("clean", Forecast(3.0, 2.0, 4.0), 3)
    assert r.action == "ask" and "may not last" in r.reason


def test_no_forecast_means_no_automatic_packing():
    assert route("clean", None, 1).action == "ask"
