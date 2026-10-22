"""One table across the end-to-end iterations (eval/cell_runs.py results), per language model.

    python eval/cell_runs_compare.py baseline iter1 iter2 iter3   # writes eval/results/cell_runs_iterations.md
"""

import json
import os
import sys

ROWS = [("packed wrong", "packed_wrong"), ("packed right", "packed_right"), ("fill (of the best possible)", "fill"),
        ("sound items thrown away", "wasted_sound"), ("questions to a person per run", "questions_per_run"),
        ("times a person is interrupted per run", "reviews_per_run"),
        ("refused moves per run", "refused_per_run"), ("orders read right", "order_read_right"),
        ("'complete' claimed while short", "dishonest_summaries"), ("median seconds per run", "median_seconds"),
        ("cost per run (USD)", "cost_per_run_usd")]
CHANGES = {
    "baseline": "the cell as of Oct 16",
    "iter1": "questions and approvals bound to one line; avocado packed only if the whole forecast range is ripe in "
             "time; verdicts acted on alone only where validated for that produce; the cell counts days to a named "
             "day; no 'complete' while short",
    "iter2": "a discard needs a spoiled item; ask before placing an 'ask' item; a declined item goes back to the crate",
    "iter3": "no finishing short with an approved item still in the crate; each 'ask' line is asked about",
    "iter4": "a person reviews several items in one glance (ask_person item_ids); the agent batches per line",
}


def main() -> None:
    names = sys.argv[1:]
    out = ["# The cell end to end, iteration by iteration", "",
           "4 real crates x 8 natural orders per column, scored against the hidden labels (eval/cell_runs.py). "
           "The simulated reviewer answers from the labels, so \"packed wrong\" assumes a person answers correctly.", ""]
    for name in names:
        out.append(f"* **{name}**: {CHANGES.get(name, '')}")
    for backend, label in (("bedrock", "Claude Haiku 4.5 on Amazon Bedrock"),):
        runs = {}
        for name in names:
            path = f"eval/results/cell_runs_{backend}_{name}.json"
            if os.path.exists(path):
                with open(path) as fh:
                    runs[name] = json.load(fh)["summary"]
        if not runs:
            continue
        out += ["", f"## {label}", "", "| | " + " | ".join(runs) + " |", "|---|" + "---|" * len(runs)]
        for r in runs.values():  # before batching, every question was its own interruption
            r.setdefault("reviews_per_run", r["questions_per_run"])
        for title, key in ROWS:
            out.append(f"| {title} | " + " | ".join(
                "-" if key not in r else str(round(r[key], 3)) if isinstance(r[key], float) else str(r[key])
                for r in runs.values()) + " |")
    text = "\n".join(out) + "\n"
    with open("eval/results/cell_runs_iterations.md", "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
