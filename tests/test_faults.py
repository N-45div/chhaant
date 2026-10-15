import numpy as np
import pytest

from chhaant.decide.camera import TurntableCamera
from chhaant.decide.policy import InspectionPolicy
from chhaant.robot.faults import FAULTS, FaultyTurntable, split_ref, with_fault
from chhaant.robot.turntable import VirtualTurntable
from test_camera import BrightnessModel, make_session


def table(tmp_path, faults):
    session = make_session(tmp_path, [(60, 90, 200)] * 17)
    return FaultyTurntable(VirtualTurntable(session, str(tmp_path)), faults)


def test_only_the_chosen_angle_is_spoiled(tmp_path):
    t = table(tmp_path, {22.5: "motion 17"})
    t.rotate_to(0.0)
    clean = t.capture()
    t.rotate_to(22.5)
    spoiled = t.capture()
    assert "#" not in clean.source and spoiled.source.endswith("#motion 17")
    assert not np.array_equal(spoiled.image, VirtualTurntable(t.inner.session, str(tmp_path))._read(spoiled.source[4:].split("#")[0]))


def test_glare_at_every_angle_stops_the_inspection_and_says_why(tmp_path):
    v = InspectionPolicy().inspect(TurntableCamera(table(tmp_path, {"every": "glare 20%"}), BrightnessModel()))
    assert v.decision == "escalate" and "3 captures in a row unusable" in v.reason and "glare" in v.reason


def test_fault_references_accept_only_known_faults():
    assert split_ref(with_fault("tr6:a.jpg", "motion 17")) == ("tr6:a.jpg", "motion 17")
    assert split_ref("tr6:a.jpg") == ("tr6:a.jpg", None)
    assert all(split_ref(with_fault("x:y.jpg", f))[1] == f for f in FAULTS)
    with pytest.raises(ValueError):
        split_ref("tr6:a.jpg#../../etc/passwd")


def test_the_agent_sees_how_many_photos_were_unusable(tmp_path):
    from chhaant.agent.cell import Cell
    from chhaant.agent.crate import CrateItem
    from test_camera import make_session as session_of

    class Inspectors:  # the real inspection path, glare at every angle
        def inspect(self, item):
            table = FaultyTurntable(VirtualTurntable(session_of(tmp_path, [(60, 90, 200)] * 17), str(tmp_path)),
                                    {"every": "glare 20%"})
            v = InspectionPolicy().inspect(TurntableCamera(table, BrightnessModel()))
            return {"capability": "test", "verdict": v.decision, "reason": v.reason, "forecast": None,
                    "unusable_photos": sum(1 for s in v.steps if s.problem), "looks": []}

    cell = Cell([CrateItem("T1", "Tomato", "tr6", 30.0, truth={"defective": False})], Inspectors())
    out = cell.inspect("T1")
    assert out["verdict"] == "escalate" and out["unusable_photos"] == 3
    assert cell.score()["unusable_photos"] == 3

