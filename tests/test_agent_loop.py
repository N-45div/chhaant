from chhaant.agent.cell import Cell
from chhaant.agent.crate import CrateItem
from chhaant.agent.llm import BedrockBackend, Reply, ScriptedBackend, ToolCall
from datetime import date

from chhaant.agent.loop import run, system_prompt
from chhaant.agent.tools import TOOLS, call


class FakeInspectors:
    def inspect(self, item):
        verdict = "defective" if item.truth.get("defective") else "clean"
        return {"capability": "test", "verdict": verdict, "reason": "test", "defect_score": 0.1, "ripeness": 0.5,
                "coverage": 0.6, "unseen_share": 0.4, "side_views": 4, "forecast": None, "looks": []}

    def look(self, item, azimuth):
        return {"azimuth": azimuth, "defect": 0.1, "ripeness": 0.5, "photo": "tr6:x.jpg"}


def crate():
    return [CrateItem("T1", "Tomato", "tr6", 30.0, truth={"defective": False}),
            CrateItem("T2", "Tomato", "tr6", 30.0, truth={"defective": True})]


def tc(i, name, **args):
    return ToolCall(f"c{i}", name, args)


ORDER = [{"produce": "Tomato", "quantity": 1, "eat_in_days": None}]


def test_loop_runs_tools_until_finish_and_scores_the_result():
    script = [
        Reply("Reading the order.", [tc(1, "read_order", lines=ORDER), tc(2, "list_crate")], "tool_use"),
        Reply("", [tc(3, "inspect", item_id="T2")], "tool_use"),
        Reply("T2 is defective.", [tc(4, "place", item_id="T2", destination="reject", reason="defective")], "tool_use"),
        Reply("", [tc(5, "inspect", item_id="T1")], "tool_use"),
        Reply("", [tc(6, "place", item_id="T1", destination="order", order_line=1, reason="clean")], "tool_use"),
        Reply("", [tc(7, "finish", summary="T1 packed, T2 rejected")], "tool_use"),
    ]
    cell = Cell(crate(), FakeInspectors())
    out = run("One good tomato please.", cell, ScriptedBackend(script))
    assert out["finished"] and out["turns"] == 6
    assert out["score"]["packed_ok"] == 1 and out["score"]["packed_bad"] == 0
    kinds = [e["kind"] for e in cell.trace.events]
    assert kinds[0] == "start" and kinds[-1] == "end" and kinds.count("tool_call") == 7


def test_refused_move_reaches_the_model_as_an_error():
    script = [Reply("", [tc(1, "read_order", lines=ORDER)], "tool_use"),
              Reply("", [tc(2, "place", item_id="T1", destination="order", order_line=1, reason="looks fine")], "tool_use"),
              Reply("", [tc(3, "finish", summary="stopped")], "tool_use")]
    backend = ScriptedBackend(script)
    cell = Cell(crate(), FakeInspectors())
    run("One tomato.", cell, backend)
    result_block = backend.seen[2][-1]["content"][0]["tool_result"]
    assert result_block["error"] and "inspect" in result_block["content"]["error"]


def test_model_that_stops_talking_is_nudged_then_stopped():
    backend = ScriptedBackend([Reply("I think we are done.", [], "end_turn")] * 5)
    out = run("One tomato.", Cell(crate(), FakeInspectors()), backend, nudges=2)
    assert not out["finished"] and out["turns"] == 3


def test_unknown_tool_and_bad_arguments_do_not_crash():
    cell = Cell(crate(), FakeInspectors())
    assert call(cell, "launch_rocket", {})["error"].startswith("unknown tool")
    assert "bad arguments" in call(cell, "look_closer", {"item_id": "T1", "azimuth": "north"})["error"]


def test_null_sent_as_a_string_reads_as_null():
    # One model sent "order_line": "None" for crate and sell-today moves, ten times in one run.
    cell = Cell(crate(), FakeInspectors())
    out = call(cell, "read_order", {"lines": [{"produce": "tomato", "quantity": "1", "eat_in_days": "null"}]})
    assert out["ok"] and out["order"][0]["quantity"] == 1 and out["order"][0]["eat_in_days"] is None
    call(cell, "inspect", {"item_id": "T2"})
    assert call(cell, "place", {"item_id": "T2", "destination": "reject", "order_line": "None", "reason": "spoiled"})["ok"]
    call(cell, "inspect", {"item_id": "T1"})
    assert call(cell, "place", {"item_id": "T1", "destination": "order", "order_line": "1", "reason": "clean"})["ok"]
    assert "bad arguments" in call(cell, "place", {"item_id": "T1", "destination": "crate", "order_line": "first"})["error"]


def test_bedrock_messages_and_reply_translation():
    sent = {}

    class StubClient:
        def converse(self, **kw):
            sent.update(kw)
            return {"output": {"message": {"content": [{"text": "ok"}, {"toolUse": {"toolUseId": "u1", "name": "list_crate", "input": {}}}]}},
                    "stopReason": "tool_use", "usage": {"inputTokens": 10, "outputTokens": 5}}

    backend = BedrockBackend(client=StubClient())
    msgs = [{"role": "user", "content": [{"text": "hi"}]},
            {"role": "assistant", "content": [{"tool_use": {"id": "u0", "name": "inspect", "input": {"item_id": "T1"}}}]},
            {"role": "user", "content": [{"tool_result": {"id": "u0", "content": {"ok": False, "error": "x"}, "error": True}}]}]
    reply = backend.chat("sys", msgs, TOOLS)
    assert reply.tool_calls[0].name == "list_crate" and reply.usage == {"input": 10, "output": 5}
    assert sent["messages"][2]["content"][0]["toolResult"]["status"] == "error"
    assert sent["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"]["required"] == ["lines"]


def test_the_model_is_told_the_date_so_named_days_resolve():
    prompt = system_prompt(date(2026, 10, 15))  # a Thursday
    assert "Today is Thursday 15 October 2026" in prompt
    assert "Friday 1, Saturday 2, Sunday 3" in prompt and "Thursday 7" in prompt


def test_the_run_uses_and_records_the_date():
    class Recording(ScriptedBackend):
        def chat(self, system, messages, tools):
            self.system = system
            return super().chat(system, messages, tools)

    cell = Cell(crate(), FakeInspectors())
    backend = Recording([Reply("done", [], "end_turn")])
    run("One tomato.", cell, backend, nudges=0, today=date(2026, 10, 17))
    assert "Today is Saturday 17 October 2026" in backend.system
    assert cell.trace.events[0]["today"] == "2026-10-17"


def test_item_ids_may_arrive_as_a_comma_list():
    cell = Cell(crate(), FakeInspectors())
    call(cell, "read_order", {"lines": [{"produce": "tomato", "quantity": 2, "eat_in_days": None}]})
    out = call(cell, "ask_person", {"item_ids": "T1, T2", "kind": "question", "question": "Look at these?"})
    assert out["ok"] and [a["item_id"] for a in out["answers"]] == ["T1", "T2"]
