import json

import pytest

from chhaant.agent.approval import ApprovalQueue, SimulatedReviewer
from chhaant.agent.trace import Trace


def test_request_is_pending_until_answered():
    q = ApprovalQueue()
    r = q.ask("T1", "pack", "Pack this tomato?", {"defect": 0.4})
    assert r.id == "Q1" and q.pending == [r] and not q.approved("T1", "pack")
    q.answer("Q1", True, "fine", by="Divij")
    assert q.approved("T1", "pack") and not q.pending
    assert r.by == "Divij" and r.answered_at


def test_a_request_cannot_be_answered_twice():
    q = ApprovalQueue()
    q.ask("T1", "reject", "Discard?", {})
    q.answer("Q1", False, "keep it", by="Divij")
    with pytest.raises(RuntimeError):
        q.answer("Q1", True, "changed my mind", by="Divij")


def test_unknown_kind_is_refused():
    with pytest.raises(ValueError):
        ApprovalQueue().ask("T1", "eat", "?", {})


def test_simulated_reviewer_follows_the_truth():
    q = ApprovalQueue()
    req = q.ask("T1", "pack", "Pack?", {})
    assert SimulatedReviewer().review(req, truth_ok_to_pack=False) == (False, "do not pack this one")
    assert SimulatedReviewer.name == "simulated reviewer"


def test_trace_writes_one_json_line_per_event(tmp_path):
    path = tmp_path / "run" / "trace.jsonl"
    tr = Trace(str(path))
    tr.log("tool_call", tool="inspect", input={"item_id": "T1"})
    tr.log("tool_result", tool="inspect", output={"verdict": "clean"})
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [e["kind"] for e in lines] == ["tool_call", "tool_result"]
    assert lines[1]["output"]["verdict"] == "clean" and lines[0]["t"] <= lines[1]["t"]
    assert len(tr.of_kind("tool_call")) == 1
