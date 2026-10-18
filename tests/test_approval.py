import json
import threading
import time

import pytest

from chhaant.agent.approval import ApprovalQueue, PersonReviewer, SimulatedReviewer
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


def test_simulated_reviewer_discards_only_spoiled_items():
    q = ApprovalQueue()
    req = q.ask("A1", "reject", "Not ripe for tonight; discard it?", {})
    assert SimulatedReviewer().review(req, truth_ok_to_pack=False, truth_defective=False)[0] is False  # sound: keep
    assert SimulatedReviewer().review(req, truth_ok_to_pack=False, truth_defective=True)[0] is True
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


def test_person_reviewer_waits_for_the_web_answer():
    q, person = ApprovalQueue(), PersonReviewer(timeout_s=5)
    req = q.ask("T1", "pack", "Pack?", {})
    got = {}
    t = threading.Thread(target=lambda: got.update(v=person.review(req, True)))
    t.start()
    for _ in range(100):
        if person.waiting:
            break
        time.sleep(0.01)
    assert person.waiting == ["Q1"]
    assert person.answer("Q1", True, "yes, pack it")
    t.join(2)
    assert got["v"] == (True, "yes, pack it") and not person.waiting


def test_person_reviewer_times_out_and_leaves_it_pending():
    req = ApprovalQueue().ask("T1", "pack", "Pack?", {})
    assert PersonReviewer(timeout_s=0.05).review(req, True) is None
    assert not PersonReviewer().answer("Q9", True, "nobody asked")


def test_a_person_sees_a_whole_batch_at_once_and_answers_in_any_order():
    q, person = ApprovalQueue(), PersonReviewer(timeout_s=5)
    b = q.new_batch()
    reqs = [q.ask(i, "pack", "Pack these for line 3?", {}, order_line=3, batch=b) for i in ("T1", "T2", "T3")]
    got = {}
    t = threading.Thread(target=lambda: got.update(v=person.review_many(reqs, [(True, False)] * 3)))
    t.start()
    for _ in range(100):  # every request of the batch is on screen before any answer
        if len(person.waiting) == 3:
            break
        time.sleep(0.01)
    assert sorted(person.waiting) == ["Q1", "Q2", "Q3"]
    for rid, ok in (("Q3", True), ("Q1", False), ("Q2", True)):
        assert person.answer(rid, ok, "")
    t.join(2)
    assert [v[0] for v in got["v"]] == [False, True, True] and person.waiting == []
    assert q.reviews == 1


def test_an_unanswered_item_in_a_batch_stays_pending():
    q, person = ApprovalQueue(), PersonReviewer(timeout_s=0.2)
    reqs = [q.ask(i, "pack", "?", {}, order_line=1, batch=q.new_batch()) for i in ("T1", "T2")]
    threading.Timer(0.05, lambda: person.answer("Q1", True, "")).start()
    out = person.review_many(reqs)
    assert out[0] == (True, "") and out[1] is None
