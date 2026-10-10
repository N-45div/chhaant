from chhaant.data.avocado import by_fruit, rows_to_photos


def rows(group, sample, stages):
    out = []
    for day, stage in enumerate(stages, 1):
        for side in "ab":
            out.append((f"{group}_d{day:02d}_{sample:03d}_{side}_{stage}", "2022-04-04 18:56:55", group, sample, day, stage, None))
    return out


def test_days_left_counts_down_to_the_first_stage_four():
    photos = rows_to_photos(rows("T20", 1, [1, 2, 3, 3, 4, 5]))
    a_side = [p for p in photos if p.side == "a"]
    assert [p.days_left for p in a_side] == [4, 3, 2, 1, 0, 0]
    assert {p.side for p in photos} == {"a", "b"}


def test_fruit_that_never_reached_stage_four_is_censored():
    photos = rows_to_photos(rows("T10", 7, [1, 1, 2, 2, 3]))
    assert all(p.days_left is None for p in photos)


def test_same_sample_number_in_two_groups_is_two_fruits():
    photos = rows_to_photos(rows("T10", 5, [1, 4]) + rows("Tamb", 5, [3, 4]))
    fruits = by_fruit(photos)
    assert set(fruits) == {"T10-005", "Tamb-005"}
    assert all(len(v) == 4 for v in fruits.values())
