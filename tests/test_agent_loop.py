import json

from chhaant.agent.cell import Cell
from chhaant.agent.crate import CrateItem
from chhaant.agent.llm import BedrockBackend, OpenAICompatBackend, Reply, ScriptedBackend, ToolCall
from chhaant.agent.loop import run
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


def test_openai_compatible_translation_for_nemotron():
    sent = {}

    def post(payload):
        sent.update(payload)
        return {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "inspect", "arguments": json.dumps({"item_id": "T1"})}}]},
            "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}

    backend = OpenAICompatBackend("https://example.invalid/v1", "key", "nvidia/nemotron", post=post)
    msgs = [{"role": "user", "content": [{"text": "hi"}]},
            {"role": "assistant", "content": [{"text": "checking"}, {"tool_use": {"id": "t0", "name": "list_crate", "input": {}}}]},
            {"role": "user", "content": [{"tool_result": {"id": "t0", "content": {"ok": True}, "error": False}}]}]
    reply = backend.chat("sys", msgs, TOOLS)
    assert reply.tool_calls[0].input == {"item_id": "T1"}
    roles = [m["role"] for m in sent["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]
    assert sent["messages"][2]["tool_calls"][0]["function"]["name"] == "list_crate"
    assert sent["tools"][0]["function"]["parameters"]["required"] == ["lines"]
