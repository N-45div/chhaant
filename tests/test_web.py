import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from chhaant.agent.cell import Cell
from chhaant.agent.crate import CrateItem
from chhaant.agent.llm import Reply, ScriptedBackend, ToolCall
from chhaant.web.app import create_app
from chhaant.web.runs import RunManager


class FakeSession:
    files = ["tr6_512/Tomato/a.jpg"]


class FakeInspectors:
    def inspect(self, item):
        return {"capability": "test", "verdict": "escalate" if item.item_id == "T2" else "clean", "reason": "test",
                "defect_score": 0.1, "ripeness": 0.5, "coverage": 0.6, "unseen_share": 0.4, "side_views": 3,
                "forecast": None, "looks": [{"azimuth": 0.0, "defect": 0.1, "ripeness": 0.5, "why": "first", "photo": "tr6:tr6_512/Tomato/a.jpg"}]}

    def look(self, item, azimuth):
        return {"azimuth": azimuth, "defect": 0.1, "ripeness": 0.5, "photo": "tr6:tr6_512/Tomato/a.jpg"}


def crate(seed=3):
    return [CrateItem("T1", "Tomato", "tr6", 30.0, session=FakeSession(), truth={"defective": False}),
            CrateItem("T2", "Tomato", "tr6", 30.0, session=FakeSession(), truth={"defective": False})]


def script(asks=True):
    tc = lambda i, n, **a: ToolCall(f"c{i}", n, a)
    steps = [Reply("", [tc(1, "read_order", lines=[{"produce": "Tomato", "quantity": 2, "eat_in_days": None}])], "tool_use"),
             Reply("", [tc(2, "inspect", item_id="T1"), tc(3, "inspect", item_id="T2")], "tool_use"),
             Reply("", [tc(4, "place", item_id="T1", destination="order", order_line=1, reason="clean")], "tool_use")]
    if asks:
        steps += [Reply("", [tc(5, "ask_person", item_id="T2", kind="pack", question="Undecided; pack T2?")], "tool_use"),
                  Reply("", [tc(6, "place", item_id="T2", destination="order", order_line=1, reason="approved")], "tool_use")]
    return steps + [Reply("", [tc(7, "finish", summary="done")], "tool_use")]


@pytest.fixture
def client(tmp_path):
    img = np.full((40, 40, 3), 200, np.uint8)
    (tmp_path / "tr6" / "tr6_512" / "Tomato").mkdir(parents=True)
    cv2.imwrite(str(tmp_path / "tr6" / "tr6_512" / "Tomato" / "a.jpg"), img)
    (tmp_path / "secret.txt").write_text("not for you")
    manager = RunManager(lambda trace, reviewer, seed: Cell(crate(seed), FakeInspectors(), trace=trace, reviewer=reviewer),
                         lambda: ScriptedBackend(script()), str(tmp_path / "runs"), per_ip_per_hour=3, person_timeout_s=5)
    app = create_app(manager, {"tr6": str(tmp_path / "tr6"), "avocado": str(tmp_path / "avo")}, crate, "scripted")
    return TestClient(app), manager


def wait_for(client, run_id, pred, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        snap = client.get(f"/api/runs/{run_id}").json()
        if pred(snap):
            return snap
        time.sleep(0.05)
    raise AssertionError("condition not reached")


def test_page_and_health(client):
    c, _ = client
    assert c.get("/").status_code == 200 and "Chhaant" in c.get("/").text
    assert c.get("/api/health").json()["backend"] == "scripted"
    assert [i["item_id"] for i in c.get("/api/crate").json()["items"]] == ["T1", "T2"]


def test_person_answers_through_the_api_and_the_agent_carries_on(client):
    c, _ = client
    run_id = c.post("/api/runs", json={"order": "two tomatoes", "reviewer": "person"}).json()["id"]
    snap = wait_for(c, run_id, lambda s: s["waiting"])
    assert snap["waiting"][0]["item_id"] == "T2"
    assert c.post(f"/api/runs/{run_id}/answer", json={"request_id": snap["waiting"][0]["request_id"], "approved": True}).json()["ok"]
    done = wait_for(c, run_id, lambda s: s["status"] != "running")
    assert done["status"] == "done" and done["order"][0]["packed"] == ["T1", "T2"]
    assert done["result"]["score"]["person_requests"] == 1
    ev = c.get(f"/api/runs/{run_id}/items/T2").json()
    assert ev["requests"][0]["by"] == "person" and ev["requests"][0]["status"] == "approved"


def test_events_come_back_from_a_cursor(client):
    c, _ = client
    run_id = c.post("/api/runs", json={"order": "two tomatoes", "reviewer": "simulated"}).json()["id"]
    snap = wait_for(c, run_id, lambda s: s["status"] != "running")
    later = c.get(f"/api/runs/{run_id}?after={snap['next']}").json()
    assert later["events"] == [] and later["next"] == snap["next"]


def test_second_run_while_one_is_active_is_told_to_watch(client):
    c, manager = client
    first = c.post("/api/runs", json={"order": "two tomatoes", "reviewer": "person"}).json()["id"]
    second = c.post("/api/runs", json={"order": "two tomatoes", "reviewer": "person"})
    assert second.status_code == 409 and second.json()["active"] == first
    waiting = wait_for(c, first, lambda s: s["waiting"])["waiting"][0]["request_id"]
    c.post(f"/api/runs/{first}/answer", json={"request_id": waiting, "approved": False})
    wait_for(c, first, lambda s: s["status"] != "running")


def test_rate_limit(client):
    c, manager = client
    for _ in range(3):
        rid = c.post("/api/runs", json={"order": "two tomatoes", "reviewer": "simulated"}).json()["id"]
        wait_for(c, rid, lambda s: s["status"] != "running")
    assert c.post("/api/runs", json={"order": "two tomatoes", "reviewer": "simulated"}).status_code == 429


def test_photos_only_from_the_data_folders(client):
    c, _ = client
    ok = c.get("/api/photo", params={"ref": "tr6:tr6_512/Tomato/a.jpg", "w": 20})
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/jpeg"
    for ref in ("tr6:../secret.txt", "tr6:../../secret.txt", "etc:passwd", "tr6:", "avocado:a.jpg"):
        assert c.get("/api/photo", params={"ref": ref}).status_code == 404


def test_bad_requests_are_refused(client):
    c, _ = client
    assert c.post("/api/runs", json={"order": "x", "reviewer": "person"}).status_code == 422
    assert c.post("/api/runs", json={"order": "two tomatoes", "reviewer": "robot"}).status_code == 400
    assert c.get("/api/runs/nope").status_code == 404
    assert c.post("/api/runs/nope/answer", json={"request_id": "Q1", "approved": True}).status_code == 409
