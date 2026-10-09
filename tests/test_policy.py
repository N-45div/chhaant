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
