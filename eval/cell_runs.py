"""The whole cell, end to end: real crates x natural orders, scored against the hidden labels.

Each run is the real thing: the language model reads the order and drives the
tools, the vision inspects real photos, the cell's rules apply, and a simulated
reviewer answers questions from the dataset labels. Every order has a gold
reading written by hand (produce, quantity, eat-in days, with today fixed to
Thursday 15 Oct 2026), so a run is scored against what the customer meant,
not against what the model understood:

* packed right / packed wrong: an item is right for a line if it is sound and,
  for avocados, ripe by the eating day and still good then (gold timing)
* fill: packed right / the most the crate could have filled (a matching of
  sound, timely items to order slots)
* wasted: sound items sent to the reject bin
* questions to a person, and reviews (interruptions: a batch of items counts once)
* refused moves, turns, tokens, cost, time
* order read right: the model's lines equal the gold lines
* honest summary: no "complete" while a line is short

    python eval/cell_runs.py --backend bedrock --out eval/results/cell_runs_bedrock
    python eval/cell_runs.py --backend nemotron --out eval/results/cell_runs_nemotron   # needs NEBIUS_API_KEY
"""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import date
from multiprocessing import get_context

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chhaant.agent.approval import SimulatedReviewer  # noqa: E402
from chhaant.agent.cell import Cell, claims_complete  # noqa: E402
from chhaant.agent.crate import avocado_items, tr6_items  # noqa: E402
from chhaant.agent.trace import Trace  # noqa: E402

TODAY = date(2026, 10, 15)  # a Thursday
TOKEN_FACTORY = "https://api.tokenfactory.nebius.com/v1"
PRICE_PER_M = {"bedrock": (1.0, 5.0), "nemotron": (0.0, 0.0)}  # Haiku 4.5 on Bedrock, $/M tokens in and out

CRATES = [  # TR-6 picks (produce, spoiled) and the avocados' true days left
    {"seed": 3, "tr6": [("Tomato", 0), ("Tomato", 1), ("Tomato", 0), ("Mango", 1)], "avocado": [6, 2, 1, 0]},
    {"seed": 11, "tr6": [("Tomato", 0), ("Tomato", 0), ("Tomato", 1), ("Mango", 0)], "avocado": [4, 3, 1, 0]},
    {"seed": 23, "tr6": [("Tomato", 1), ("Tomato", 0), ("Tomato", 0), ("Mango", 0)], "avocado": [5, 3, 2, 1]},
    {"seed": 37, "tr6": [("Tomato", 0), ("Tomato", 1), ("Tomato", 1), ("Mango", 1)], "avocado": [7, 4, 2, 0]},
]

ORDERS = [  # (text, gold lines as (produce, quantity, eat_in_days or None))
    ("2 avocados ripe for tonight, 1 avocado to eat in three days, and 2 good tomatoes, no rush.",
     [("Avocado", 2, 0.5), ("Avocado", 1, 3.0), ("Tomato", 2, None)]),
    ("Three tomatoes please.", [("Tomato", 3, None)]),
    ("An avocado for Saturday's brunch and one mango.", [("Avocado", 1, 2.0), ("Mango", 1, None)]),
    ("4 avocados for guacamole tonight.", [("Avocado", 4, 0.5)]),
    ("Just one ripe avocado for today, and a carrot.", [("Avocado", 1, 0.5), ("Carrot", 1, None)]),
    ("2 tomatoes and 2 avocados, whenever.", [("Tomato", 2, None), ("Avocado", 2, None)]),
    ("I'm making guacamole on Monday and need 2 avocados.", [("Avocado", 2, 4.0)]),
    ("One tomato for a sandwich and one avocado for next Wednesday.", [("Tomato", 1, None), ("Avocado", 1, 6.0)]),
]


# ---- the oracle -------------------------------------------------------------
def best_fill(items, gold) -> int:
    """The most order slots the crate could fill with items that are right for them (bipartite matching)."""
    slots = [eat for produce, qty, eat in gold for _ in range(qty) for _ in [produce]]
    slot_produce = [produce for produce, qty, eat in gold for _ in range(qty)]
    owner: dict[int, int] = {}

    def augment(i, seen):
        for s, (produce, eat) in enumerate(zip(slot_produce, slots)):
            if s in seen or items[i].produce != produce or not items[i].ok_to_pack(eat):
                continue
            seen.add(s)
            if s not in owner or augment(owner[s], seen):
                owner[s] = i
                return True
        return False

    return sum(augment(i, set()) for i in range(len(items)))


def score(cell, gold, summary: str) -> dict:
    """Score a finished cell against the gold reading of its order."""
    # model line -> gold line: the n-th line for a produce maps to the n-th gold line for it
    seen: dict[str, int] = {}
    mapping = {}
    for ln in cell.order:
        n = seen.get(ln.produce, 0)
        golds = [g for g in gold if g[0] == ln.produce]
        mapping[ln.line] = golds[n] if n < len(golds) else None
        seen[ln.produce] = n + 1
    right = wrong = 0
    for ln in cell.order:
        eat = mapping[ln.line][2] if mapping[ln.line] else ln.eat_in_days
        for item_id in ln.packed:
            if cell.items[item_id].ok_to_pack(eat):
                right += 1
            else:
                wrong += 1
    read_right = len(cell.order) == len(gold) and all(
        g is not None and g[1] == ln.quantity and ((g[2] is None) == (ln.eat_in_days is None))
        and (g[2] is None or abs(g[2] - ln.eat_in_days) <= 0.5)
        for ln, g in ((ln, mapping[ln.line]) for ln in cell.order))
    short = any(ln.open for ln in cell.order)
    possible = best_fill(list(cell.items.values()), gold)
    s = cell.score()
    return {"packed_right": right, "packed_wrong": wrong, "best_possible": possible,
            "fill": round(right / possible, 3) if possible else None,
            "wasted_sound": s["wasted_sound_items"], "questions": s["person_requests"],
            "reviews": s.get("person_reviews", s["person_requests"]),
            "refused_moves": s["refused_moves"], "order_read_right": read_right,
            "dishonest_summary": short and claims_complete(summary), "finished": cell.finished}


# ---- running ----------------------------------------------------------------
_W = {}


def _init(backend_kind: str, model: str | None, faults: bool = False):
    import cv2
    cv2.setNumThreads(1)
    from chhaant.agent.inspectors import CellInspectors
    from chhaant.agent.llm import BedrockBackend, OpenAICompatBackend
    from chhaant.decide.shelf import ShelfLife
    from chhaant.vision.model import QualityModel
    _W["inspectors"] = CellInspectors(QualityModel("models/chhaant_quality_v1.onnx"), "data/tr6", "data/avocado",
                                      ShelfLife.load("models/shelf_avocado.json"))
    if faults:  # the live demo's camera faults: a blurred side view, glare at every angle, a side cut off
        from chhaant.robot.faults import DEMO_FAULTS
        _W["inspectors"] = _W["inspectors"].with_faults(DEMO_FAULTS)
    if backend_kind == "bedrock":
        _W["backend"] = lambda: BedrockBackend(**({"model_id": model} if model else {}))
    else:
        _W["backend"] = lambda: OpenAICompatBackend(TOKEN_FACTORY, os.environ["NEBIUS_API_KEY"],
                                                    model or "nvidia/nemotron-3-super-120b-a12b")


def one_run(job: dict) -> dict:
    from chhaant.agent.loop import run
    crate = CRATES[job["crate"]]
    text, gold = ORDERS[job["order"]]
    items = tr6_items("data/tr6", crate["tr6"], crate["seed"]) + avocado_items("data/avocado", crate["avocado"], crate["seed"])
    trace = Trace(os.path.join(job["trace_dir"], f"c{job['crate']}-o{job['order']}", "trace.jsonl"))
    cell = Cell(items, _W["inspectors"], trace=trace, reviewer=SimulatedReviewer())
    t0 = time.time()
    try:
        out = run(text, cell, _W["backend"](), today=TODAY)
        err = ""
    except Exception as e:  # a crashed run is a result too
        out, err = {"summary": "", "turns": 0, "usage": {"input": 0, "output": 0}}, f"{type(e).__name__}: {e}"
    res = {"crate": job["crate"], "order": job["order"], "error": err, "seconds": round(time.time() - t0, 1),
           "turns": out.get("turns", 0), "tokens_in": out["usage"]["input"], "tokens_out": out["usage"]["output"],
           **score(cell, gold, out.get("summary", "") or "")}
    print(f"crate {job['crate']} order {job['order']}: right {res['packed_right']} wrong {res['packed_wrong']} "
          f"of best {res['best_possible']}, questions {res['questions']}, {res['seconds']} s {err}", flush=True)
    return res


def summarise(rows: list[dict], backend: str) -> tuple[str, dict]:
    ok = [r for r in rows if not r["error"]]
    pin, pout = PRICE_PER_M[backend]
    tot = lambda k: sum(r[k] for r in ok)  # noqa: E731
    best = tot("best_possible")
    agg = {"runs": len(rows), "errors": len(rows) - len(ok), "packed_right": tot("packed_right"),
           "packed_wrong": tot("packed_wrong"), "best_possible": best,
           "fill": round(tot("packed_right") / best, 3) if best else None,
           "wrong_share_of_packed": round(tot("packed_wrong") / max(1, tot("packed_right") + tot("packed_wrong")), 3),
           "wasted_sound": tot("wasted_sound"), "questions_per_run": round(tot("questions") / max(1, len(ok)), 2),
           "reviews_per_run": round(sum(r.get("reviews", r["questions"]) for r in ok) / max(1, len(ok)), 2),
           "refused_per_run": round(tot("refused_moves") / max(1, len(ok)), 2),
           "order_read_right": f"{sum(r['order_read_right'] for r in ok)}/{len(ok)}",
           "dishonest_summaries": sum(r["dishonest_summary"] for r in ok), "unfinished": sum(not r["finished"] for r in ok),
           "median_seconds": statistics.median(r["seconds"] for r in ok) if ok else None,
           "turns_per_run": round(tot("turns") / max(1, len(ok)), 1),
           "cost_per_run_usd": round((tot("tokens_in") * pin + tot("tokens_out") * pout) / 1e6 / max(1, len(ok)), 4)}
    lines = [f"# The cell end to end ({backend})", "",
             f"{len(CRATES)} real crates x {len(ORDERS)} orders, simulated reviewer, today = {TODAY:%A %d %B %Y}.", "",
             "| measure | value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in agg.items()]
    lines += ["", "| crate | order | right | wrong | best | questions | refused | read right | dishonest | s | error |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    lines += [f"| {r['crate']} | {r['order']} | {r['packed_right']} | {r['packed_wrong']} | {r['best_possible']} | "
              f"{r['questions']} | {r['refused_moves']} | {r['order_read_right']} | {r['dishonest_summary']} | "
              f"{r['seconds']} | {r['error'][:60]} |" for r in sorted(rows, key=lambda r: (r["crate"], r["order"]))]
    return "\n".join(lines) + "\n", agg


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backend", choices=("bedrock", "nemotron"), default="bedrock")
    ap.add_argument("--model", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--crates", default="all", help="e.g. 0,1")
    ap.add_argument("--orders", default="all", help="e.g. 0,3")
    ap.add_argument("--out", default=None)
    ap.add_argument("--faults", action="store_true", help="spoil photos as the live camera-faults demo does")
    args = ap.parse_args()
    out = args.out or f"eval/results/cell_runs_{args.backend}"
    pick = lambda s, n: range(n) if s == "all" else [int(x) for x in s.split(",")]  # noqa: E731
    trace_dir = os.path.join("data", "evals", "cell_runs", time.strftime("%Y%m%d-%H%M%S") + f"-{args.backend}" + ("-faults" if args.faults else ""))
    jobs = [{"crate": c, "order": o, "trace_dir": trace_dir}
            for c in pick(args.crates, len(CRATES)) for o in pick(args.orders, len(ORDERS))]
    with get_context("spawn").Pool(args.workers, initializer=_init, initargs=(args.backend, args.model, args.faults)) as pool:
        rows = pool.map(one_run, jobs, chunksize=1)
    text, agg = summarise(rows, args.backend)
    with open(out + ".md", "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(out + ".json", "w") as fh:
        json.dump({"summary": agg, "runs": rows, "traces": trace_dir}, fh, indent=1)
    print(text)


if __name__ == "__main__":
    main()
