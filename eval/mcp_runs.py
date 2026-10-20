"""The same crates and orders as cell_runs.py, driven by an agent I did not write: Claude Code, over MCP.

Claude Code is started bare (no CLAUDE.md, memory, hooks or plugins) with the chhaant MCP server as its only
tools, on Amazon Bedrock. Its system prompt, its loop and its model are someone else's; only the cell's tools,
rules and server instructions are mine. A simulated reviewer answers from the dataset labels, as in cell_runs.py.

Each run's trace is replayed against a fresh cell to score it with cell_runs.score, and the replay must
reproduce every tool result the agent saw (replay_mismatches counts any that differ).

    python eval/mcp_runs.py --out eval/results/mcp_runs_claude_code   # needs AWS credentials for Bedrock
"""

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cell_runs import CRATES, ORDERS, TODAY, score, upper_95  # noqa: E402

from chhaant.agent.approval import SimulatedReviewer  # noqa: E402
from chhaant.agent.cell import Cell  # noqa: E402
from chhaant.agent.crate import avocado_items, tr6_items  # noqa: E402
from chhaant.agent.tools import call  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODEL = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
PROMPT = ('You are connected to Chhaant, a produce-picking cell, through MCP. The customer\'s order: "{order}". '
          "Fill it with the chhaant tools, following the server's instructions. "
          "Use only the chhaant tools: no network, no files, no other services.")
_REPLAY = threading.Lock()  # one replay at a time: the inspectors are shared


def claude_exe() -> str:
    """The Claude Code binary itself: on Windows npm installs a .cmd shim, which mangles quoted arguments."""
    found = shutil.which("claude") or "claude"
    exe = os.path.join(os.path.dirname(found), "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe")
    return exe if found.lower().endswith(".cmd") and os.path.isfile(exe) else found


def aws_env() -> dict:
    """Bedrock credentials for Claude Code: the environment's, else the AWS CLI's current session."""
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        return {}
    out = subprocess.run(["aws", "configure", "export-credentials", "--format", "process"], capture_output=True,
                         text=True, check=True, shell=os.name == "nt").stdout
    c = json.loads(out)
    return {"AWS_ACCESS_KEY_ID": c["AccessKeyId"], "AWS_SECRET_ACCESS_KEY": c["SecretAccessKey"],
            **({"AWS_SESSION_TOKEN": c["SessionToken"]} if c.get("SessionToken") else {})}


def one_run(job: dict) -> dict:
    crate, (text, gold) = CRATES[job["crate"]], ORDERS[job["order"]]
    name = f"c{job['crate']}-o{job['order']}" + (f"-r{job['rep']}" if job.get("rep") else "")
    run_dir = os.path.join(job["trace_dir"], name)
    os.makedirs(run_dir, exist_ok=True)
    server = {"type": "stdio", "command": sys.executable,
              "args": ["-m", "chhaant.mcp_server", "--simulated-reviewer", "--today", TODAY.isoformat(),
                       "--crate", json.dumps({"seed": crate["seed"], "tr6": crate["tr6"], "avocado": crate["avocado"]})],
              "env": {"PYTHONPATH": ROOT, "CHHAANT_MCP_RUNS": os.path.join(run_dir, "cell")}}
    config = os.path.join(run_dir, "mcp.json")
    with open(config, "w") as fh:
        json.dump({"mcpServers": {"chhaant": server}}, fh)
    # fresh credentials for every run: a session exported once expires partway through a long eval
    env = {**os.environ, **aws_env(), "CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": job["region"],
           "ANTHROPIC_SMALL_FAST_MODEL": "global.anthropic.claude-haiku-4-5-20251001-v1:0"}
    cmd = [job["claude"], "--bare", "-p", PROMPT.format(order=text), "--model", job["model"], "--strict-mcp-config",
           "--mcp-config", config, "--tools", "", "--allowedTools", "mcp__chhaant", "--no-session-persistence",
           "--output-format", "stream-json", "--verbose"]
    t0, err, result = time.time(), "", {}
    try:
        with open(os.path.join(run_dir, "claude.jsonl"), "w", encoding="utf-8") as out:
            subprocess.run(cmd, stdout=out, stderr=subprocess.DEVNULL, env=env, cwd=run_dir, timeout=900, check=False)
        with open(os.path.join(run_dir, "claude.jsonl"), encoding="utf-8") as fh:
            result = next((json.loads(ln) for ln in fh if '"type":"result"' in ln), {})
        if result.get("is_error") or result.get("terminal_reason") == "api_error":
            err = "client: " + str(result.get("result", ""))[:120]
    except subprocess.TimeoutExpired:
        err = "timeout"
    traces = sorted(os.path.join(run_dir, "cell", d, "trace.jsonl") for d in os.listdir(os.path.join(run_dir, "cell"))) \
        if os.path.isdir(os.path.join(run_dir, "cell")) else []
    with _REPLAY:
        cell, mismatches, summary = replay(traces[-1], crate, job["inspectors"]) if traces else (None, 0, "")
    if cell is None:
        err = err or "no trace"
    res = {"crate": job["crate"], "order": job["order"], "rep": job.get("rep", 0), "error": err,
           "seconds": round(time.time() - t0, 1), "turns": result.get("num_turns", 0),
           "cost_usd": round(result.get("total_cost_usd") or 0.0, 4), "replay_mismatches": mismatches,
           **(score(cell, gold, summary) if cell is not None else {})}
    print(f"crate {job['crate']} order {job['order']}: right {res.get('packed_right')} wrong {res.get('packed_wrong')} "
          f"of best {res.get('best_possible')}, reviews {res.get('reviews')}, {res['seconds']} s {err}", flush=True)
    return res


def replay(trace_path: str, crate: dict, inspectors):
    """Rebuild the cell by running the trace's tool calls again; count results that differ from what the agent saw."""
    with open(trace_path, encoding="utf-8") as fh:
        events = [json.loads(ln) for ln in fh]
    items = tr6_items(os.path.join(ROOT, "data/tr6"), [tuple(p) for p in crate["tr6"]], crate["seed"]) \
        + avocado_items(os.path.join(ROOT, "data/avocado"), crate["avocado"], crate["seed"])
    cell = Cell(items, inspectors, reviewer=SimulatedReviewer())
    cell.today = TODAY
    calls = [e for e in events if e["kind"] == "tool_call"]
    results = [e for e in events if e["kind"] == "tool_result"]
    mismatches, summary = 0, ""
    for c, r in zip(calls, results):
        out = json.loads(json.dumps(call(cell, c["tool"], c["input"]), default=str))
        mismatches += out != r["output"]
        if c["tool"] == "finish":
            summary = c["input"].get("summary", "")
    return cell, mismatches, summary


def summarise(rows: list[dict], model: str) -> tuple[str, dict]:
    ok = [r for r in rows if not r["error"]]
    tot = lambda k: sum(r[k] for r in ok)  # noqa: E731
    packed = tot("packed_right") + tot("packed_wrong")
    agg = {"runs": len(rows), "errors": len(rows) - len(ok), "packed_right": tot("packed_right"),
           "packed_wrong": tot("packed_wrong"), "best_possible": tot("best_possible"),
           "fill": round(tot("packed_right") / tot("best_possible"), 3) if ok and tot("best_possible") else None,
           "wrong_share_upper_95": round(upper_95(tot("packed_wrong"), packed), 4) if packed else None,
           "wasted_sound": tot("wasted_sound"), "reviews_per_run": round(tot("reviews") / max(1, len(ok)), 2),
           "refused_per_run": round(tot("refused_moves") / max(1, len(ok)), 2),
           "order_read_right": f"{sum(r['order_read_right'] for r in ok)}/{len(ok)}",
           "dishonest_summaries": sum(r["dishonest_summary"] for r in ok), "unfinished": sum(not r["finished"] for r in ok),
           "replay_mismatches": sum(r["replay_mismatches"] for r in rows),
           "median_seconds": statistics.median(r["seconds"] for r in ok) if ok else None,
           "turns_per_run": round(tot("turns") / max(1, len(ok)), 1),
           "cost_per_run_usd": round(tot("cost_usd") / max(1, len(ok)), 4)}
    lines = ["# The cell end to end, driven by Claude Code over MCP", "",
             f"Claude Code (bare, the chhaant MCP server as its only tools) on Bedrock with {model}; "
             f"{len(CRATES)} real crates x {len(ORDERS)} orders, simulated reviewer, today = {TODAY:%A %d %B %Y}. "
             "Cost is Claude Code's own estimate at list prices.", "",
             "| measure | value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in agg.items()]
    lines += ["", "| crate | order | right | wrong | best | reviews | refused | read right | dishonest | s | error |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    lines += [f"| {r['crate']} | {r['order']} | {r.get('packed_right')} | {r.get('packed_wrong')} | {r.get('best_possible')} | "
              f"{r.get('reviews')} | {r.get('refused_moves')} | {r.get('order_read_right')} | {r.get('dishonest_summary')} | "
              f"{r['seconds']} | {r['error'][:60]} |" for r in sorted(rows, key=lambda r: (r["crate"], r["order"]))]
    return "\n".join(lines) + "\n", agg


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--region", default="ap-south-1")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--crates", default="all", help="e.g. 0,1")
    ap.add_argument("--orders", default="all", help="e.g. 0,3")
    ap.add_argument("--out", default="eval/results/mcp_runs_claude_code")
    ap.add_argument("--claude", default=None, help="path to the Claude Code binary")
    ap.add_argument("--rerun-errors", action="store_true", help="run again only the runs in --out that ended in an error")
    args = ap.parse_args()

    from chhaant.agent.inspectors import CellInspectors
    from chhaant.decide.shelf import ShelfLife
    from chhaant.vision.model import QualityModel
    inspectors = CellInspectors(QualityModel(os.path.join(ROOT, "models/chhaant_quality_v1.onnx")),
                                os.path.join(ROOT, "data/tr6"), os.path.join(ROOT, "data/avocado"),
                                ShelfLife.load(os.path.join(ROOT, "models/shelf_avocado.json")))
    pick = lambda s, n: range(n) if s == "all" else [int(x) for x in s.split(",")]  # noqa: E731
    trace_dir = os.path.join(ROOT, "data", "evals", "mcp_runs", time.strftime("%Y%m%d-%H%M%S"))
    base = {"trace_dir": trace_dir, "region": args.region, "model": args.model,
            "claude": args.claude or claude_exe(), "inspectors": inspectors}
    kept, trace_dirs = [], []
    if args.rerun_errors:
        with open(args.out + ".json") as fh:
            prior = json.load(fh)
        before, trace_dirs = prior["runs"], [prior["traces"]] if isinstance(prior["traces"], str) else prior["traces"]
        kept = [r for r in before if not r["error"]]
        pairs = [(r["crate"], r["order"]) for r in before if r["error"]]
    else:
        pairs = [(c, o) for c in pick(args.crates, len(CRATES)) for o in pick(args.orders, len(ORDERS))]
    jobs = [{**base, "crate": c, "order": o} for c, o in pairs]
    with ThreadPoolExecutor(args.workers) as pool:  # the agents run in their own processes; replay is quick
        rows = kept + list(pool.map(one_run, jobs))
    text, agg = summarise(rows, args.model)
    with open(args.out + ".md", "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(args.out + ".json", "w") as fh:
        json.dump({"summary": agg, "runs": rows, "traces": trace_dirs + [trace_dir]}, fh, indent=1)
    print(text)


if __name__ == "__main__":
    main()
