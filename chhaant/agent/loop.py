"""The agent loop: the model plans and calls tools; the cell acts and enforces its rules."""

from chhaant.agent.tools import TOOLS, call

SYSTEM = """You run Chhaant, a produce-picking cell: a robot arm, a turntable and a camera over a crate of real produce.
Your job is to fill the customer's order from the crate, and to leave every decision traceable to evidence.

How to work:
1. Call read_order first with your reading of the order. Use eat_in_days 0.5 for "tonight", 1 for "tomorrow",
   and so on; use null when the customer gave no timing.
2. Call list_crate, then inspect items of the produce you need, one at a time. Each inspection moves the arm and
   takes photos, so do not inspect more items than the order needs, but do put any defective item you find into
   the reject bin so it cannot spoil the rest of the crate.
3. Follow each item's routing_for_open_lines. "pack" means place it into that order line. "skip" means it does not
   suit that line; leave it in the crate. "sell_today" means move it to sell_today. "reject" means the reject bin.
4. When the verdict is "escalate" or a routing says "ask", do not guess: either look_closer at the angles that worry
   you, or ask_person. Only pack or discard such an item after a person approves. Never leave an order line short
   while an item whose routing for that line is "ask" has not been put to a person.
5. The cell enforces its rules. If a move is refused, read the reason and choose another action.
6. Each tool's capability field says what was measured and what was not. Never claim more than it says.
7. Call finish with a short, concrete summary: what went where and why (cite verdicts, scores, forecasts), which
   lines are short, and anything waiting for a person. Never call the order complete while any line is short."""


def _tool_result(call_id: str, output: dict) -> dict:
    return {"tool_result": {"id": call_id, "content": output, "error": not output.get("ok", False)}}


def run(order_text: str, cell, backend, max_turns: int = 40, nudges: int = 2) -> dict:
    trace = cell.trace
    trace.log("start", order=order_text, backend=getattr(backend, "name", "?"), model=getattr(backend, "model_id", getattr(backend, "model", "")))
    messages = [{"role": "user", "content": [{"text": order_text}]}]
    usage = {"input": 0, "output": 0}
    turns = 0
    for turns in range(1, max_turns + 1):
        reply = backend.chat(SYSTEM, messages, TOOLS)
        for k in usage:
            usage[k] += reply.usage.get(k, 0)
        trace.log("model", turn=turns, text=reply.text, tool_calls=[{"name": c.name, "input": c.input} for c in reply.tool_calls],
                  stop=reply.stop, usage=reply.usage, latency_s=round(reply.latency_s, 3))
        content = ([{"text": reply.text}] if reply.text else []) + \
                  [{"tool_use": {"id": c.id, "name": c.name, "input": c.input}} for c in reply.tool_calls]
        messages.append({"role": "assistant", "content": content or [{"text": "(no reply)"}]})
        if not reply.tool_calls:
            if cell.finished or nudges <= 0:
                break
            nudges -= 1
            messages.append({"role": "user", "content": [{"text": "Continue with the tools; call finish when the order is done."}]})
            continue
        results = []
        for c in reply.tool_calls:
            trace.log("tool_call", turn=turns, tool=c.name, input=c.input)
            out = call(cell, c.name, c.input)
            trace.log("tool_result", turn=turns, tool=c.name, output=out)
            results.append(_tool_result(c.id, out))
        messages.append({"role": "user", "content": results})
        if cell.finished:
            break
    result = {"finished": cell.finished, "turns": turns, "summary": cell.summary, "score": cell.score(), "usage": usage}
    trace.log("end", **result)
    return result
