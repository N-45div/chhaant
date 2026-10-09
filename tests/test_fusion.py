import pytest

from chhaant.decide.fusion import agreement, angular_gap, fuse, neighbours


def test_angular_gap_wraps_around():
    assert angular_gap(350, 10) == 20
    assert angular_gap(0, 180) == 180


def test_neighbours_include_the_view_itself():
    views = {0.0: 0.1, 22.5: 0.2, 90.0: 0.3, 337.5: 0.4}
    assert sorted(neighbours(views, 0.0)) == [0.0, 22.5, 337.5]


def test_a_single_hot_view_is_not_confirmed():
    assert agreement({0.0: 0.95}) == (0.0, 0)


def test_lone_false_alarm_is_outvoted_by_its_neighbours():
    score, support = agreement({0.0: 0.95, 22.5: 0.05, 337.5: 0.05, 180.0: 0.05})
    assert score == 0.05 and support == 3


def test_two_views_are_not_enough_to_confirm():
    assert agreement({0.0: 0.95, 22.5: 0.9}) == (0.0, 0)


def test_a_defect_seen_from_adjacent_angles_scores_high():
    score, support = agreement({67.5: 0.85, 90.0: 0.95, 112.5: 0.8, 270.0: 0.05})
    assert score > 0.8 and support >= 2


@pytest.mark.parametrize("method,expected", [("max", 0.9), ("mean", 0.4), ("median", 0.3), ("top2", 0.7)])
def test_baseline_fusions(method, expected):
    assert fuse([0.1, 0.3, 0.5, 0.9, 0.2], method) == pytest.approx(expected)
