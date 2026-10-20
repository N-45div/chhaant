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
from chhaant.mcp_server import ClientReviewer, Desk, build_server


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


def run(desk, steps, answer=None, mode="auto"):
    """Drive the server with an in-process MCP client; ``answer`` fills in each form (None: no form support)."""
    forms = []

    async def on_form(context, params):
        forms.append(params)
        return answer(params)

    async def go():
        out = []
        async with Client(build_server(desk), elicitation_callback=on_form if answer else None, mode=mode) as c:
            for name, args in steps:
                r = await c.call_tool(name, args)
                out.append(json.loads(r.content[0].text))
        return out

    return anyio.run(go), forms


def accept(**ticks):
    return lambda params: types.ElicitResult(action="accept", content={"note": "", **ticks})


def test_the_client_sees_the_cell_tools_and_no_hidden_review_argument(tmp_path):
    async def go():
        async with Client(build_server(desk_for(tmp_path))) as c:
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
