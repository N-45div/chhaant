"""Run the agent on a crate of real produce and print what it did, step by step.

The crate mixes TR-6 items (16 real photo angles, inspected by rotate-until-sure)
and avocados (two real side photos, validated shelf-life forecast). By default
a simulated reviewer answers the agent's questions from the dataset labels and
is reported as such; --no-reviewer leaves questions pending for a person.

Usage:
    python scripts/run_agent.py                                  # Bedrock, Claude Haiku 4.5
    python scripts/run_agent.py --backend nemotron --model nvidia/nemotron-3-super-120b-a12b
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chhaant.agent.approval import SimulatedReviewer  # noqa: E402
from chhaant.agent.cell import Cell  # noqa: E402
from chhaant.agent.crate import avocado_items, tr6_items  # noqa: E402
from chhaant.agent.inspectors import CellInspectors  # noqa: E402
from chhaant.agent.llm import BedrockBackend, OpenAICompatBackend  # noqa: E402
from chhaant.agent.loop import run  # noqa: E402
from chhaant.agent.trace import Trace  # noqa: E402
from chhaant.decide.shelf import ShelfLife  # noqa: E402
from chhaant.vision.model import QualityModel  # noqa: E402

DEFAULT_ORDER = ("Hi! For tonight's guacamole I need 2 avocados that are ripe today, plus 1 avocado for "
                 "Saturday, three days from now. Also 2 good tomatoes for a salad, no rush on those.")
TOKEN_FACTORY = "https://api.tokenfactory.nebius.com/v1"


def short(out: dict) -> str:
    if not out.get("ok"):
        return f"REFUSED: {out.get('error')}"
    if "verdict" in out:
        r = "; ".join(f"line {x['line']}: {x['action']}" for x in out.get("routing_for_open_lines", []))
        return f"{out['verdict']} (views {out['views_used']}, forecast {out['forecast_days_left']}) -> {r or 'no open line'}"
    for key in ("now", "status", "order", "items"):
        if key in out:
            return f"{key}: {json.dumps(out[key])[:140]}"
    return json.dumps(out)[:140]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=("bedrock", "nemotron"), default="bedrock")
    ap.add_argument("--model", default=None)
    ap.add_argument("--order", default=DEFAULT_ORDER)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--no-reviewer", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    items = tr6_items("data/tr6", [("Tomato", 0), ("Tomato", 1), ("Tomato", 0), ("Mango", 1)], seed=args.seed) \
        + avocado_items("data/avocado", [6, 2, 1, 0], seed=args.seed)
    inspectors = CellInspectors(QualityModel("models/chhaant_quality_v1.onnx"), "data/tr6", "data/avocado",
                                ShelfLife.load("models/shelf_avocado.json"))
    run_dir = args.out or os.path.join("data", "runs", datetime.now().strftime("%Y%m%d-%H%M%S"))
    trace = Trace(os.path.join(run_dir, "trace.jsonl"))
    cell = Cell(items, inspectors, trace=trace, reviewer=None if args.no_reviewer else SimulatedReviewer())

    if args.backend == "bedrock":
        backend = BedrockBackend(**({"model_id": args.model} if args.model else {}))
    else:
        key = os.environ.get("NEBIUS_API_KEY")
        if not key:
            sys.exit("set NEBIUS_API_KEY for the Nemotron backend")
        backend = OpenAICompatBackend(TOKEN_FACTORY, key, args.model or "nvidia/nemotron-3-super-120b-a12b")

    print(f"order: {args.order}\ncrate: {[f'{i.item_id}={i.produce}' for i in items]}\n")
    result = run(args.order, cell, backend)
    events = trace.events
    for n, e in enumerate(events):
        if e["kind"] == "model" and e["text"]:
            print(f"[model] {e['text'][:300]}")
        elif e["kind"] == "tool_call":
            # a call's own result is the first tool_result after it (questions and moves log in between)
            res = next(x for x in events[n + 1:] if x["kind"] == "tool_result")
            print(f"  -> {e['tool']}({json.dumps(e['input'])[:110]}) => {short(res['output'])}")
    print(f"\nSUMMARY: {result['summary']}\nSCORE: {result['score']}\nturns {result['turns']}, tokens {result['usage']}\ntrace: {trace.path}")
    with open(os.path.join(run_dir, "result.json"), "w") as fh:
        json.dump(result, fh, indent=1, default=str)


if __name__ == "__main__":
    main()
