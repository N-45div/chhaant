# Architecture

A map of the code for someone about to read or change it. The measurements behind each design choice are in
[docs/REPORT.md](docs/REPORT.md); this file says where things live and how they fit together.

![Architecture](docs/architecture.svg)

## The loop of one order

```
customer's order (plain words)
        │
        ▼
  agent (language model)  ──tool calls──▶  cell (chhaant/agent/cell.py: tools + rules, in code)
        ▲                                     │            │                 │
        │                                     ▼            ▼                 ▼
        └────── tool results ────────   inspectors     a person          the arm
                                     (vision + decisions) (approvals)   (simulated, MuJoCo)
                                                  │
                                                  ▼
                                   trace.jsonl ─▶ S3 · metrics ─▶ CloudWatch
```

1. **Read the order.** The agent turns the order into lines (`read_order`): produce, quantity, and when it will be
   eaten. A named day ("Saturday") is passed through as `eat_on`, and the cell counts the days from its own date.
2. **Inspect.** For each candidate item the agent calls `inspect`. The cell moves the item to the turntable,
   photographs it and runs the vision and decision layers (below). The result says what was measured, what was not,
   and a routing for every open order line: pack, skip, sell today, reject, or ask.
3. **Act.** The agent calls `place` or `ask_person`. The cell refuses any move its rules do not allow, and says why.
4. **Finish.** `finish` is refused while a short line still has an unexplored candidate, or while the summary calls a
   short order complete.

Every step is one line of the run's trace.

## Packages

| Package | What it owns | Main entry points |
|---|---|---|
| `chhaant/vision/` | OpenCV 5 on one photo: where the item is, its colour, whether the photo is usable, what the model reads | `segment_fruit`, `colour_stats`, `check_capture`, `item_crop`, `QualityModel`, `CoverageMap` |
| `chhaant/decide/` | Decisions on top of vision: fusing views, the inspection loop, shelf life, routing, crate acceptance | `InspectionPolicy`, `fuse`, `ShelfLife`, `route`, `LotInspection` |
| `chhaant/agent/` | The cell as the agent sees it: tools, rules, approvals, the agent loop, model backends, the trace | `Cell`, `TOOLS` + `call`, `run`, `CellInspectors`, `ApprovalQueue`, `BedrockBackend`, `Trace` |
| `chhaant/robot/` | The turntable and camera (replaying real recorded photos) and simulated camera faults | `VirtualTurntable`, `FaultyTurntable`, `spoil` |
| `chhaant/sim/` | The SO-101 arm in MuJoCo, driven by the cell's moves, and its scene for the browser | `SimCell`, `SimTwin`, `scene_meshes` |
| `chhaant/data/` | Dataset loaders: TR-6 sessions and the avocado photos | `load_sessions`, `load_photos` |
| `chhaant/web/` | The web app: runs, the page, a person's answers, evidence, the S3/CloudWatch reporter | `create_app`, `RunManager`, `AwsReporter` |
| `chhaant/mcp_server.py` | The same cell as an MCP server (stdio locally, HTTP at `/mcp` on the site) | `build_server`, `hosted`, `Jobs`, `Desk`, `ClientReviewer` |

### Vision (`chhaant/vision/`)

One photo at a time, at a 512-pixel working size so a recorded photo and a 12 MP frame give the same numbers:

* `segment.py` finds the item on the plain backdrop: CIELAB distance from the backdrop's colour, estimated from the
  image border, with soft shadows ignored. It falls back to GrabCut when that mask's size is implausible, and says
  whether to trust the result.
* `capture.py` decides whether the photo is usable evidence: blur (outline sharpness), glare, overexposure, darkness,
  framing (item cut off) and presence (an empty turntable). A failed photo is recorded with its problem and never
  scored. A check may never turn a dark or smooth rotten item into "bad photo".
* `color.py` white-balances on the backdrop and reads the item's colour in CIELAB.
* `crop.py` makes the model's view: a square crop with the backdrop greyed out, shared by training and inference.
* `model.py` runs the quality model (ONNX, defect probability and ripeness) through OpenCV 5's DNN module on the new
  engine.
* `views.py` keeps a coverage map: which parts of the item's surface have been seen from the angles used so far.
* `defects.py` and `chart.py` are the classical defect map and ColorChecker correction (`cv2.mcc`, `cv2.ccm`).

### Decisions (`chhaant/decide/`)

* `policy.py`: **rotate until sure.** After each look, call the item defective when neighbouring views agree, call it
  clean only once enough surface is covered and every suspicious view is cross-checked, otherwise look again where
  it helps most, and escalate to a person when the view budget runs out. `fusion.py` holds the agreement rule.
* `forecast.py` and `shelf.py`: the avocado shelf-life forecast from two photos and the storage temperature, with an
  80% interval. It is the only shelf-life number the cell acts on, because it is the only one validated.
* `route.py`: what an inspected item is fit for, given when the order line will be eaten. An avocado is packed only
  if its whole interval lasts until that day and it is ripe in time; otherwise the routing is "ask".
* `lot.py`: sequential acceptance of a supplier's crate (inspect until the risk is decided, not a fixed sample).

### The cell and its rules (`chhaant/agent/`)

* `cell.py` is the single place the rules live. The agent cannot talk its way past them:
  * nothing is placed before it is inspected;
  * an item the vision calls defective never goes into an order, even with a person's approval;
  * packing needs a "pack" routing for that line, or a person's approval for that item and that line;
  * discarding a sound item needs a person's approval;
  * selling today needs a forecast under a day, or a person's yes to that exact question;
  * a yes to a general question permits no move;
  * `finish` is refused while a short line has an unexplored or person-approved candidate left, and when the summary
    calls a short order complete.
* `inspectors.py` picks each produce's measured capability: rotate until sure on TR-6 produce, the forecaster on
  avocados. Its validation gate reads `eval/results/rotate_until_sure.csv`. A verdict is acted on alone only where
  held-out validation says it can be (no more than 10% missed or wrongly rejected); otherwise it escalates with the
  measured reason. Tomatoes always go to a person.
* `approval.py`: questions and answers. One review can hold several items (a batch). `PersonReviewer` waits for a real
  person on the page. `SimulatedReviewer` answers from the dataset labels, for evaluation, and is always labelled
  simulated.
* `loop.py` and `llm.py`: the agent loop and its model backend, Claude Haiku 4.5 on Amazon Bedrock through the
  Converse API (any Bedrock model with tool use fits). `tools.py` holds the tool schemas and a dispatcher that turns bad arguments into errors the
  model can read.
* `crate.py`: crates of real produce, each item carrying hidden labels that only the scorer reads.

## Two front doors

**The web app** (`python -m chhaant.web`, `chhaant/web/`). `RunManager` runs one agent run at a time in a background
thread, with per-visitor and daily limits, because each run calls a paid model. The page polls the run's trace,
shows the 3D arm (MuJoCo poses streamed to three.js), and lets a person answer the cell's questions. After a run,
`AwsReporter` archives the trace to S3 and publishes metrics.

**The MCP server** (`chhaant/mcp_server.py`). The same tools for an agent the client brings. Locally it serves one
desk over stdio. Hosted, `Jobs` gives every `new_crate` a desk and job id of its own (the 2026-07-28 protocol keeps no
session), with idle expiry and caps. `ask_person` becomes an MCP elicitation form (one per review, a box per item)
through the SDK's resolvers, which work on both protocol versions. A client that cannot show forms leaves questions
pending. The score against the hidden labels is written to disk, never returned to the client.

Both doors call the same `Cell`, so an outside agent is refused exactly what the built-in one is.

## Evidence and observability

* **Trace** (`agent/trace.py`): one JSON line per event, written as it happens. The kinds are `start`, `model`,
  `tool_call`, `tool_result`, `guardrail` (a refused move and why), `ask_person`, `answer`, `no_answer`, `action`,
  `score`, `end`, `error` and `hook_error` (an archive or metrics call that failed after a run).
* **S3**: every web run's trace and result under `runs/<id>/`, every hosted MCP job's under `runs/mcp/<job>/`.
* **CloudWatch**: per-run metrics (seconds, failures, refused moves, questions, unusable photos, wrong packs for
  simulated runs), a dashboard, and alarms on failed runs, bursts of unusable photos and failed status checks.

## Deployment (`deploy/`)

* `chhaant.yaml`: one CloudFormation stack in ap-south-1. An EC2 c8g.large (Graviton4) on the COOL AMI, an Elastic
  IP, CloudFront in front (the security group admits only CloudFront), an instance role scoped to the bucket prefixes
  and the one Bedrock model, the dashboard, alarms, SNS and EC2 auto-recovery.
* `bootstrap.sh`: sets up the instance with COOL's own OpenCV (never the PyPI wheel), the data and the model, then
  starts `chhaant.service` (uvicorn).
* `deploy.sh update`: ships the committed tree through S3 and Systems Manager (no SSH) and reruns bootstrap.
* `eval_job.sh` and `bench.sh`: heavy evaluations and the COOL benchmark, run on throwaway Graviton instances that
  terminate themselves.

## Evaluation (`eval/`)

Each script writes its results to `eval/results/`, and the report quotes those files. The main ones:

| Script | Measures | Report |
|---|---|---|
| `cell_runs.py` | the whole cell, end to end: 4 real crates x 8 orders, scored against hidden labels (also `--faults`, `--repeat`, `--reviewer-error`) | §7.1 |
| `mcp_runs.py` | the same orders driven by Claude Code over MCP, scored by replaying each trace | §7.1 |
| `explain_wrong.py` | why each wrong pack happened, from its trace | §7.1 |
| `rotate_until_sure.py` | rotate until sure against looking at every angle, leave one fruit out | §5.1 |
| `forecast_avocado.py` | the shelf-life forecast on held-out avocados | §5.2 |
| `lot_acceptance.py` | sequential crate acceptance against the fixed sampling plan | §5.4 |
| `capture_failures.py` | the capture checks on spoiled photos | §4.5 |
| `bench_cool.py` | COOL against the PyPI wheel, Graviton4 against x86 | §8.2 |

## Why it is built this way

* **Rules in code, not in the prompt.** The model plans; the cell decides what is allowed. With the rules and the
  validation gate in code, the built-in agent (Claude Haiku 4.5) and one I did not write (Claude Code with Claude
  Sonnet 4.5, over MCP) packed no wrong item across the evaluation.
* **Act only on what was measured.** Each produce gets only the capability validated for it, and every result states
  what was not inspected (the underside, a missing shelf-life number).
* **A person where the camera cannot judge.** Questions carry the evidence and the measured reason, and are batched
  so one review covers several items.
* **Real pixels, simulated motion.** The arm and turntable are simulated, but every decision is made on real
  photographs from public datasets.
