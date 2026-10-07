from chhaant.data.tr6 import group_sessions


def rows_for(fruit, date, day, start_hms, n, spoiled, step_s=5):
    h, m, s = start_hms
    out = []
    for i in range(n):
        t = h * 3600 + m * 60 + s + i * step_s
        out.append({
            "fruit": fruit, "date": date, "day": str(day),
            "file": f"tr6_512/{fruit}/{date}_{t // 3600:02d}{t % 3600 // 60:02d}{t % 60:02d}.jpg",
            "spoiled": str(spoiled), "temp_min_c": "28.0", "temp_max_c": "31.0",
        })
    return out


def test_sessions_split_on_long_gaps_and_keep_short_pauses():
    rows = rows_for("Tomato", "20250723", 1, (9, 20, 0), 8, 0)
    rows += rows_for("Tomato", "20250723", 1, (9, 24, 0), 9, 0)   # 3-minute pause, same fruit
    rows += rows_for("Tomato", "20250723", 1, (12, 0, 0), 17, 0)  # hours later: next fruit
    sessions = group_sessions(rows)
    assert [len(s.files) for s in sessions] == [17, 17]
    assert [s.slot for s in sessions] == [1, 2]
    assert sessions[0].top_view.endswith("092000.jpg")
    assert len(sessions[0].side_views) == 16
    assert sessions[0].temp_c == 29.5


def test_back_to_back_fruits_are_cut_apart():
    rows = rows_for("Indian_Gooseberry", "20250801", 1, (10, 0, 0), 17, 0)
    rows += rows_for("Indian_Gooseberry", "20250801", 1, (10, 2, 0), 17, 0)  # 40 s later, under the gap
    sessions = group_sessions(rows)
    assert [len(s.files) for s in sessions] == [17, 17]


def test_one_fruit_tracked_through_the_day_and_hours_to_spoiled():
    rows = []
    labels = [(0, 0), (0, 1), (1, 1)]  # (morning, evening) labels on days 1-3: spoils on day 2 evening
    for day, (am, pm) in enumerate(labels, 1):
        rows += rows_for("Banana", f"202509{10 + day:02d}", day, (9, 0, 0), 17, am)
        rows += rows_for("Banana", f"202509{10 + day:02d}", day, (17, 0, 0), 17, pm)
    sessions = sorted(group_sessions(rows), key=lambda s: s.taken_at)
    assert {s.fruit_id for s in sessions} == {"Banana-1"}
    assert [s.slot for s in sessions] == [1, 2] * 3
    assert [s.hours_in_life for s in sessions] == [0, 8, 24, 32, 48, 56]
    assert [s.hours_to_spoiled for s in sessions] == [32, 24, 8, 0, 0, 0]


def test_a_fresh_fruit_after_a_spoiled_one_is_a_new_fruit():
    rows = []
    for day, lab in enumerate([0, 1, 0], 1):
        rows += rows_for("Mango", f"202509{20 + day:02d}", day, (9, 0, 0), 17, lab)
    sessions = sorted(group_sessions(rows), key=lambda s: s.taken_at)
    assert [s.fruit_id for s in sessions] == ["Mango-1", "Mango-1", "Mango-2"]
    assert sessions[2].hours_to_spoiled is None
