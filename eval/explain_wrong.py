"""Why did the cell pack the wrong items? Replays eval/cell_runs.py traces against the hidden labels.

For every item packed into a line it was not right for, it reports what the
cell knew when it packed: the inspection verdict, the shelf-life forecast, the
routing for that line, and whether a person approved it. Causes:

* vision missed a defect: the item is spoiled but the inspection said clean
* forecast off: the avocado was not ripe (or already gone) on the eating day,
  though the forecast said it would be
* person approved: the routing said ask, and the (simulated) person said yes
* timing misread: the model's eating day differs from the customer's

    python eval/explain_wrong.py data/evals/cell_runs/<run dir>
"""

import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import cell_runs as cr  # noqa: E402
from chhaant.agent.crate import avocado_items, tr6_items  # noqa: E402


def explain(run_dir: str) -> tuple[list[dict], collections.Counter]:
    rows, causes = [], collections.Counter()
    for name in sorted(os.listdir(run_dir)):
        m = re.match(r"c(\d+)-o(\d+)$", name)
        if not m:
            continue
        c, o = int(m.group(1)), int(m.group(2))
        crate = cr.CRATES[c]
        items = {it.item_id: it for it in tr6_items("data/tr6", crate["tr6"], crate["seed"])
                 + avocado_items("data/avocado", crate["avocado"], crate["seed"])}
        gold = cr.ORDERS[o][1]
        events = [json.loads(line) for line in open(os.path.join(run_dir, name, "trace.jsonl"), encoding="utf-8")]
        order = next((e["output"]["order"] for e in events if e.get("kind") == "tool_result" and e.get("tool") == "read_order"
                      and e["output"].get("ok")), [])
        model_eat = {ln["line"]: ln["eat_in_days"] for ln in order}
        seen, gold_eat = collections.Counter(), {}
        for ln in order:  # model line -> gold line, as eval/cell_runs.py maps them
            g = [x for x in gold if x[0] == ln["produce"]]
            gold_eat[ln["line"]] = g[seen[ln["produce"]]][2] if seen[ln["produce"]] < len(g) else ln["eat_in_days"]
            seen[ln["produce"]] += 1
        inspections = {e["output"]["item_id"]: e["output"] for e in events
                       if e.get("kind") == "tool_result" and e.get("tool") == "inspect" and e["output"].get("ok")}
        approved = {(e2.get("item_id")): True for e2 in events if e2.get("kind") == "answer" and e2.get("approved")}
        asked = {e["request"]: e["item_id"] for e in events if e.get("kind") == "ask_person"}
        approved = {asked.get(e["request"]) for e in events if e.get("kind") == "answer" and e.get("approved")}
        for e in events:
            if e.get("kind") != "action" or e.get("destination") != "order":
                continue
            item, line = items[e["item_id"]], e["order_line"]
            eat = gold_eat.get(line)
            if item.ok_to_pack(eat):
                continue
            insp = inspections.get(item.item_id, {})
            route = next((r for r in insp.get("routing_for_open_lines", []) if r["line"] == line), {})
            if item.truth.get("defective"):
                cause = "vision missed a defect" if insp.get("verdict") == "clean" else "person approved a defective item"
            elif model_eat.get(line) != eat and not (model_eat.get(line) is not None and eat is not None
                                                     and abs(model_eat[line] - eat) <= 0.5):
                cause = "timing misread"
            elif item.item_id in approved and route.get("action") != "pack":
                cause = "person approved"
            else:
                cause = "forecast off"
            causes[cause] += 1
            rows.append({"crate": c, "order": o, "item": item.item_id, "produce": item.produce, "line": line,
                         "eat": eat, "truth": item.truth, "verdict": insp.get("verdict"),
                         "forecast": insp.get("forecast_days_left"), "routing": route.get("action"),
                         "approved": item.item_id in approved, "cause": cause})
    return rows, causes


if __name__ == "__main__":
    rows, causes = explain(sys.argv[1])
    for r in rows:
        print(f"c{r['crate']} o{r['order']} {r['item']} line {r['line']} eat {r['eat']}: {r['cause']} | truth {r['truth']} "
              f"| verdict {r['verdict']} forecast {r['forecast']} routing {r['routing']} approved {r['approved']}")
    print(dict(causes))
