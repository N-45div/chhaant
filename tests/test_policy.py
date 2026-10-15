from chhaant.decide.policy import InspectionPolicy, Look, PolicyConfig


class FakeCamera:
    """Scores per azimuth (16 steps of 22.5 degrees), plus the overhead view."""

    def __init__(self, side: dict[float, float], top: float = 0.05, default: float = 0.05):
        self.side, self.top, self.default = side, top, default
        self.looked: list[float] = []

    def look_down(self) -> Look:
        return Look(0.0, 90.0, self.top, 0.6)

    def look_at(self, azimuth: float) -> Look:
        self.looked.append(azimuth)
        return Look(azimuth, 40.0, self.side.get(azimuth, self.default), 0.6)


def test_clean_item_is_cleared_with_few_spread_views():
    cam = FakeCamera({})
    v = InspectionPolicy().inspect(cam)
    assert v.decision == "clean"
    assert v.side_views <= 5
    assert v.coverage >= 0.55
    gaps = [min(abs(a - b) % 360, 360 - abs(a - b) % 360) for i, a in enumerate(cam.looked) for b in cam.looked[i + 1:]]
    assert min(gaps) >= 67.5  # spread around the item, not bunched on one side


def test_lone_false_alarm_is_cross_checked_and_dismissed():
    cam = FakeCamera({0.0: 0.95})  # glare on the very first view
    v = InspectionPolicy().inspect(cam)
    assert v.decision == "clean"
    assert sorted(cam.looked[1:3]) == [22.5, 337.5]  # checked both sides of the alarm next
    assert "cross-check" in v.steps[2].why and "cross-check" in v.steps[3].why


def test_defect_seen_from_neighbouring_angles_is_called():
    cam = FakeCamera({157.5: 0.85, 180.0: 0.95, 202.5: 0.9})
    v = InspectionPolicy().inspect(cam)
    assert v.decision == "defective"
    assert v.side_views <= 5


def test_borderline_item_goes_to_a_person_within_budget():
    cam = FakeCamera({}, default=0.5)
    cfg = PolicyConfig(max_views=6)
    v = InspectionPolicy(cfg).inspect(cam)
    assert v.decision == "escalate"
    assert v.side_views == 6 and len(cam.looked) == 6


def test_suspicious_overhead_view_blocks_an_early_clean_call():
    cam = FakeCamera({}, top=0.9)
    v = InspectionPolicy().inspect(cam)
    assert v.side_views >= 3
    assert v.steps[0].azimuth is None and v.steps[0].p_defect == 0.9


def test_every_step_explains_itself():
    v = InspectionPolicy().inspect(FakeCamera({0.0: 0.95}))
    assert all(s.why for s in v.steps)
    assert v.reason


class FlakyCamera(FakeCamera):
    """Like FakeCamera, but the photos at some angles fail the capture checks."""

    def __init__(self, bad: dict[float, str], top_bad: str = "", **kw):
        super().__init__({}, **kw)
        self.bad, self.top_bad = bad, top_bad

    def look_down(self) -> Look:
        return Look(0.0, 90.0, float("nan"), float("nan"), problem=self.top_bad) if self.top_bad else super().look_down()

    def look_at(self, azimuth: float) -> Look:
        if azimuth in self.bad:
            self.looked.append(azimuth)
            return Look(azimuth, 40.0, float("nan"), float("nan"), problem=self.bad[azimuth])
        return super().look_at(azimuth)


def test_unusable_photo_is_skipped_not_scored():
    cam = FlakyCamera({0.0: "blurred (outline sharpness 0.1)"})
    v = InspectionPolicy().inspect(cam)
    assert v.decision == "clean"
    assert cam.looked[0] == 0.0 and 0.0 not in cam.looked[1:]  # never retried at the failed angle
    bad = [s for s in v.steps if s.problem]
    assert len(bad) == 1 and "unusable" in v.steps[2].why
    assert "1 photo unusable (blurred x1)" in v.reason


def test_three_failed_captures_in_a_row_stop_the_inspection():
    cam = FlakyCamera({a: "no usable item: no item stands out from the background" for a in [22.5 * i for i in range(16)]})
    v = InspectionPolicy().inspect(cam)
    assert v.decision == "escalate" and len(cam.looked) == 3
    assert "3 captures in a row unusable" in v.reason and v.side_views == 0
    assert v.ripeness == 0.6  # the overhead view still counted


def test_failed_overhead_view_gives_no_ripeness_and_no_coverage():
    cam = FlakyCamera({a: "too dark (item grey 12)" for a in [22.5 * i for i in range(16)]}, top_bad="too dark (item grey 12)")
    v = InspectionPolicy().inspect(cam)
    assert v.decision == "escalate" and v.ripeness is None and v.coverage == 0.0


def test_failed_looks_use_up_the_view_budget():
    cam = FlakyCamera({a: "glare on 30% of the item" for a in (0.0, 135.0, 270.0)}, default=0.5)  # undecided everywhere else
    v = InspectionPolicy(PolicyConfig(max_views=6)).inspect(cam)
    assert v.decision == "escalate" and len(cam.looked) == 6 and v.side_views + sum(1 for s in v.steps if s.problem) == 6
