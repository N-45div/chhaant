import json
import os
from datetime import date

import anyio
import mcp_types as types
import pytest
from mcp import Client

from chhaant.agent.approval import SimulatedReviewer
from chhaant.agent.crate import CrateItem
from chhaant.decide.forecast import Forecast
from chhaant.mcp_server import ClientReviewer, Desk, Jobs, build_server, hosted


class FakeInspectors:
    def __init__(self, results):
        self.results = results

    def inspect(self, item):
        return self.results[item.item_id]

    def look(self, item, azimuth):
        return {"azimuth": azimuth, "defect": 0.1, "ripeness": 0.5, "photo": "tr6:x.jpg"}

    def with_faults(self, faults):
        return self


def inspection(verdict, forecast=None, reason="test"):
    return {"capability": "test", "verdict": verdict, "reason": reason, "defect_score": 0.1, "ripeness": 0.5,
            "coverage": 0.6, "unseen_share": 0.4, "side_views": 4, "forecast": forecast,
            "looks": [{"photo": "tr6:Tomato/a.jpg"}]}


def crate(seed):
    return [CrateItem("T1", "Tomato", "tr6", 30.0, truth={"defective": False, "days_left": None}),
            CrateItem("T2", "Tomato", "tr6", 30.0, truth={"defective": True, "days_left": None}),
            CrateItem("T3", "Tomato", "tr6", 30.0, truth={"defective": False, "days_left": None}),
            CrateItem("A1", "Avocado", "avocado", 20.0, truth={"defective": False, "days_left": 4.0})]


RESULTS = {"T1": inspection("escalate", reason="A person confirms: for tomato this inspection missed 10 of 10"),
           "T2": inspection("defective"), "T3": inspection("escalate"),
           "A1": inspection("clean", Forecast(3.5, 2.6, 4.6))}
TOMATOES = [{"produce": "tomato", "quantity": 2, "eat_in_days": None}]


def desk_for(tmp_path, reviewer=None):
    reviewer = reviewer or ClientReviewer({"tr6": "data/tr6", "avocado": "data/avocado"})
    return Desk(FakeInspectors(RESULTS), crate, str(tmp_path), lambda: date(2026, 10, 22), reviewer)  # a Thursday


def server_for(desk):
    return build_server(Jobs(lambda job, answers: desk), desk.today)


def run(desk, steps, answer=None, mode="auto"):
    """Drive the server with an in-process MCP client; ``answer`` fills in each form (None: no form support)."""
    forms = []

    async def on_form(context, params):
        forms.append(params)
        return answer(params)

    async def go():
        out = []
        async with Client(server_for(desk), elicitation_callback=on_form if answer else None, mode=mode) as c:
            for name, args in steps:
                r = await c.call_tool(name, args)
                out.append(json.loads(r.content[0].text))
        return out

    return anyio.run(go), forms


def accept(**ticks):
    return lambda params: types.ElicitResult(action="accept", content={"note": "", **ticks})


def test_the_client_sees_the_cell_tools_and_no_hidden_review_argument(tmp_path):
    async def go():
        async with Client(server_for(desk_for(tmp_path))) as c:
            return {t.name: t for t in (await c.list_tools()).tools}, c.instructions

    tools, instructions = anyio.run(go)
    assert set(tools) == {"new_crate", "read_order", "list_crate", "inspect", "look_closer", "ask_person", "place", "finish"}
    assert "review" not in tools["ask_person"].input_schema["properties"]
    assert "never assume one" in instructions and "Thursday 22 October 2026" in instructions


@pytest.mark.parametrize("mode", ["legacy", "auto"])  # a mid-call form (2025-11-25) and input-required rounds (2026-07-28)
def test_one_form_for_a_batch_and_only_a_ticked_item_is_packed(tmp_path, mode):
    desk = desk_for(tmp_path)
    out, forms = run(desk, [("read_order", {"lines": TOMATOES}), ("inspect", {"item_id": "T1"}), ("inspect", {"item_id": "T3"}),
                            ("ask_person", {"kind": "pack", "question": "Pack these?", "item_ids": ["T1", "T3"], "order_line": 1}),
                            ("place", {"item_id": "T1", "destination": "order", "order_line": 1, "reason": "approved"}),
                            ("place", {"item_id": "T3", "destination": "order", "order_line": 1, "reason": "try"})],
                     answer=accept(T1=True), mode=mode)
    assert len(forms) == 1
    assert set(forms[0].requested_schema["properties"]) == {"T1", "T3", "note"}
    assert "missed 10 of 10" in forms[0].message and os.path.join("data", "tr6", "Tomato", "a.jpg") in forms[0].message
    answers = {a["item_id"]: a for a in out[3]["answers"]}
    assert answers["T1"]["status"] == "approved" and answers["T1"]["by"] == "person via MCP client"
    assert answers["T3"]["status"] == "declined"  # an empty box is a no
    assert out[4]["ok"] and not out[5]["ok"]


def test_a_declined_form_leaves_the_question_pending_and_nothing_packs(tmp_path):
    desk = desk_for(tmp_path)
    out, _ = run(desk, [("read_order", {"lines": TOMATOES}), ("inspect", {"item_id": "T1"}),
                        ("ask_person", {"kind": "pack", "question": "Pack it?", "item_id": "T1", "order_line": 1}),
                        ("place", {"item_id": "T1", "destination": "order", "order_line": 1, "reason": "?"})],
                 answer=lambda params: types.ElicitResult(action="decline"))
    assert out[2]["status"] == "pending" and "declined the form" in out[2]["note"]
    assert not out[3]["ok"]
    assert desk.cell.trace.of_kind("no_answer")


def test_a_client_without_forms_gets_pending_questions_and_says_so(tmp_path):
    desk = desk_for(tmp_path)
    out, _ = run(desk, [("read_order", {"lines": TOMATOES}), ("inspect", {"item_id": "T1"}),
                        ("ask_person", {"kind": "pack", "question": "Pack it?", "item_id": "T1", "order_line": 1})])
    assert out[2]["status"] == "pending" and "cannot show a form" in out[2]["note"]


def test_a_question_the_cell_refuses_never_reaches_the_person(tmp_path):
    desk = desk_for(tmp_path)
    out, forms = run(desk, [("read_order", {"lines": TOMATOES}),
                            ("ask_person", {"kind": "pack", "question": "Pack the avocado?", "item_id": "A1", "order_line": 1})],
                     answer=accept(A1=True))
    assert not out[1]["ok"] and not forms


def test_finish_writes_the_score_to_disk_but_never_returns_it(tmp_path):
    desk = desk_for(tmp_path)
    out, _ = run(desk, [("new_crate", {"seed": 3}), ("read_order", {"lines": [{"produce": "Avocado", "quantity": 1, "eat_on": "Saturday"}]}),
                        ("inspect", {"item_id": "A1"}),
                        ("place", {"item_id": "A1", "destination": "order", "order_line": 1, "reason": "clean, ripe in time"}),
                        ("finish", {"summary": "Packed A1."}), ("place", {"item_id": "T1", "destination": "crate", "reason": "x"})],
                 answer=accept())
    assert out[0]["today"] == "Thursday 22 October 2026"
    assert out[1]["order"][0]["eat_in_days"] == 2.0  # the cell counted the days to Saturday
    assert out[4]["ok"] and "packed_ok" not in json.dumps(out[4])
    with open(os.path.join(desk.run_dir, "score.json")) as fh:
        assert json.load(fh)["packed_ok"] == 1
    assert "finished" in out[5]["error"]


def test_the_simulated_reviewer_answers_unattended_and_is_named_as_such(tmp_path):
    desk = desk_for(tmp_path, SimulatedReviewer())
    out, forms = run(desk, [("read_order", {"lines": TOMATOES}), ("inspect", {"item_id": "T1"}),
                            ("ask_person", {"kind": "pack", "question": "Pack it?", "item_id": "T1", "order_line": 1})],
                     answer=accept(T1=False))
    assert out[2]["status"] == "approved" and out[2]["by"] == "simulated reviewer" and not forms


def test_new_crate_never_drops_an_order_under_way(tmp_path):
    # Found over MCP: an agent read the order, then called new_crate "to start the job", and lost the order.
    desk = desk_for(tmp_path)
    out, _ = run(desk, [("read_order", {"lines": TOMATOES}), ("new_crate", {"seed": 1}), ("list_crate", {}),
                        ("new_crate", {"seed": 1, "restart": True}), ("list_crate", {})])
    assert not out[1]["ok"] and "under way" in out[1]["error"]
    assert out[2]["order"] and not out[4]["order"]


def hosted_for(tmp_path, **kw):
    return hosted(FakeInspectors(RESULTS), crate, str(tmp_path), lambda: date(2026, 10, 22),
                  {"tr6": "data/tr6", "avocado": "data/avocado"}, photo_url="https://cell.example/", **kw)


def call_all(server, steps, answer=None):
    async def on_form(context, params):
        return answer(params)

    async def go():
        out = []
        async with Client(server, elicitation_callback=on_form if answer else None) as c:
            for step in steps:
                name, args = step(out) if callable(step) else step
                out.append(json.loads((await c.call_tool(name, args)).content[0].text))
        return out
    return anyio.run(go)


def test_hosted_jobs_are_separate_and_the_job_id_is_needed(tmp_path):
    job = lambda i: lambda out: out[i]["job"]  # noqa: E731
    out = call_all(hosted_for(tmp_path), [
        ("new_crate", {}), ("new_crate", {}),
        lambda out: ("read_order", {"lines": TOMATOES, "job": out[0]["job"]}),
        lambda out: ("list_crate", {"job": job(1)(out)}),
        ("list_crate", {}), ("list_crate", {"job": "nope"})])
    assert out[0]["job"] != out[1]["job"]
    assert out[2]["ok"] and not out[3]["order"]  # the second job does not see the first job's order
    assert "job id" in out[4]["error"] and "no open job" in out[5]["error"]


def test_hosted_limits_close_idle_jobs_and_cap_new_ones(tmp_path):
    out = call_all(hosted_for(tmp_path, per_ip_per_hour=2), [("new_crate", {}), ("new_crate", {}), ("new_crate", {})])
    assert out[0]["ok"] and out[1]["ok"] and "an hour" in out[2]["error"]
    out = call_all(hosted_for(tmp_path, max_jobs=1, idle_s=3600), [("new_crate", {}), ("new_crate", {})])
    assert "limit of 1 open jobs" in out[1]["error"]
    now = [0.0]

    def later(out):
        now[0] += 61  # a minute passes
        return "new_crate", {}

    out = call_all(hosted_for(tmp_path, max_jobs=1, idle_s=60, clock=lambda: now[0]), [
        ("new_crate", {}), later, lambda out: ("list_crate", {"job": out[0]["job"]})])
    assert out[1]["ok"] and "no open job" in out[2]["error"]  # the idle one was closed to make room


def test_hosted_form_links_the_photos_and_simulated_answers_need_nobody(tmp_path):
    forms = []

    def tick(params):
        forms.append(params)
        return types.ElicitResult(action="accept", content={"T1": True, "note": ""})

    out = call_all(hosted_for(tmp_path), [
        ("new_crate", {}),
        lambda out: ("read_order", {"lines": TOMATOES, "job": out[0]["job"]}),
        lambda out: ("inspect", {"item_id": "T1", "job": out[0]["job"]}),
        lambda out: ("ask_person", {"kind": "pack", "question": "Pack?", "item_id": "T1", "order_line": 1, "job": out[0]["job"]}),
        ("new_crate", {"answers": "simulated"}),
        lambda out: ("read_order", {"lines": TOMATOES, "job": out[4]["job"]}),
        lambda out: ("inspect", {"item_id": "T1", "job": out[4]["job"]}),
        lambda out: ("ask_person", {"kind": "pack", "question": "Pack?", "item_id": "T1", "order_line": 1, "job": out[4]["job"]})],
        answer=tick)
    assert out[3]["status"] == "approved" and out[3]["by"] == "person via MCP client"
    assert "https://cell.example/api/photo?ref=tr6%3ATomato/a.jpg&w=512" in forms[0].message
    assert out[4]["answers"] == "simulated reviewer" and out[7]["by"] == "simulated reviewer" and len(forms) == 1


def test_hosted_job_caps_its_calls_but_can_always_finish_and_is_archived(tmp_path):
    archived = []
    out = call_all(hosted_for(tmp_path, max_calls=2, on_finish=archived.append), [
        ("new_crate", {}),
        lambda out: ("list_crate", {"job": out[0]["job"]}), lambda out: ("list_crate", {"job": out[0]["job"]}),
        lambda out: ("list_crate", {"job": out[0]["job"]}),
        lambda out: ("finish", {"summary": "Nothing ordered.", "job": out[0]["job"]})])
    assert out[2]["ok"] and "2 tool calls" in out[3]["error"]
    assert out[4]["ok"] and len(archived) == 1 and os.path.exists(os.path.join(archived[0], "score.json"))


def test_the_web_app_serves_mcp_over_http_on_both_protocols(tmp_path):
    import socket
    import threading
    import time

    import uvicorn

    from chhaant.web.app import create_app
    from chhaant.web.runs import RunManager

    app = create_app(RunManager(None, None, str(tmp_path / "runs")), {}, lambda seed: [], "test", None, hosted_for(tmp_path))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)

    async def on_form(context, params):
        return types.ElicitResult(action="accept", content={"T1": True, "note": "looks fine"})

    async def go(mode):
        async with Client(f"http://127.0.0.1:{port}/mcp", elicitation_callback=on_form, mode=mode) as c:
            async def tool(name, **args):
                return json.loads((await c.call_tool(name, args)).content[0].text)
            job = (await tool("new_crate"))["job"]
            await tool("read_order", lines=TOMATOES, job=job)
            await tool("inspect", item_id="T1", job=job)
            asked = await tool("ask_person", kind="pack", question="Pack?", item_id="T1", order_line=1, job=job)
            placed = await tool("place", item_id="T1", destination="order", order_line=1, reason="approved", job=job)
            return c.protocol_version, asked, placed

    try:
        for mode in ("legacy", "auto"):
            version, asked, placed = anyio.run(go, mode)
            assert asked["status"] == "approved" and asked["answer"] == "looks fine" and placed["ok"], (mode, version)
    finally:
        server.should_exit = True
        thread.join(5)
