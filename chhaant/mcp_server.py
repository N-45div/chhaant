"""The cell as an MCP server, so any MCP client's agent can drive it under the cell's own rules.

    python -m chhaant.mcp_server                        # stdio: Claude Code, Claude Desktop, any MCP client
    python -m chhaant.mcp_server --simulated-reviewer   # questions answered from the dataset labels, unattended

The web app also serves it over HTTP at /mcp (see ``hosted``), where every new_crate opens a job of its own and the
job id travels with every call: the 2026-07-28 protocol keeps no session, and visitors must never share a crate.

The client brings the agent; the cell keeps the rules. Every tool is the cell's own tool, so a client's agent is
refused exactly what the built-in agent is refused (packing an item a person declined, calling a short order
complete). ask_person goes to the client's person as one MCP elicitation form per review, with a yes or no per
item. A client that cannot show forms, or a person who closes the form, leaves the questions pending, and pending
is never approval. The cell cannot see who filled the form in, so those answers are marked "person via MCP client".

Each crate's trace goes to data/mcp_runs/<time>-seed<seed>/trace.jsonl. When the job finishes, the score against
the hidden labels is written next to it as score.json; it is never returned to the agent.

Settings: CHHAANT_TR6, CHHAANT_AVOCADO, CHHAANT_MODEL, CHHAANT_SHELF (as for the web app), CHHAANT_MCP_RUNS,
and CHHAANT_UTC_OFFSET_H (the cell's time zone, default 5.5).
"""

import argparse
import json
import os
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

import anyio
import anyio.to_thread
from mcp.server.mcpserver import AcceptedElicitation, Context, Elicit, ElicitationResult, MCPServer
from mcp.server.mcpserver.resolve import Resolve
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field, create_model

from chhaant.agent.approval import SimulatedReviewer
from chhaant.agent.cell import Cell
from chhaant.agent.loop import system_prompt
from chhaant.agent.tools import TOOLS, call
from chhaant.agent.trace import Trace

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTIONS = {t["name"]: t["description"] for t in TOOLS}
FIXED = ToolAnnotations(openWorldHint=False)
Job = Annotated[str | None, Field(description="the job id new_crate returned (needed on the hosted server)")]


class OrderLineIn(BaseModel):
    produce: str
    quantity: int = Field(ge=1)
    eat_in_days: float | None = Field(None, description="0.5 = tonight, 1 = tomorrow; null when no timing was given")
    eat_on: str | None = Field(None, description="a named day ('Saturday', 'next Wednesday'); the cell counts the days")


class ClientReviewer:
    """Answers a review from the form the MCP client's person filled in, a yes or no per item.

    The form is put to the client before the cell records the question (see ``form``); the cell then calls
    ``review_many`` and gets the answers. Anything not answered stays pending. ``photo_url`` (the hosted
    server's public address) turns the evidence photos into links instead of local file paths.
    """

    name = "person via MCP client"

    def __init__(self, photo_roots: dict[str, str], photo_url: str = ""):
        self.photo_roots, self.photo_url = photo_roots, photo_url.rstrip("/")
        self.outcome = None  # the elicitation outcome for the review in progress, or None
        self.note = ""       # why the last review went unanswered, for the agent

    def review_many(self, reqs, truths=None) -> list[tuple[bool, str] | None]:
        outcome, self.outcome = self.outcome, None
        if not isinstance(outcome, AcceptedElicitation) or outcome.data is None:
            if not self.note:
                how = {"decline": "declined", "cancel": "closed"}.get(getattr(outcome, "action", ""), "did not answer")
                self.note = f"the person {how} the form; the question stays pending"
            return [None] * len(reqs)
        note = outcome.data.note.strip()
        return [(ok, note or ("yes" if ok else "no") + ", in the MCP client's form")
                for ok in (bool(getattr(outcome.data, r.item_id, False)) for r in reqs)]

    def form(self, cell, kind: str, question: str, ids: list[str], order_line: int | None):
        """The form for one review, or None when the cell would refuse the question anyway."""
        rows = []
        for i in ids:
            if i not in cell.items or not i.isidentifier():
                return None
            line = None
            if kind == "pack":
                line = cell._pack_line(i, order_line)
                if line is None or line.produce != cell.items[i].produce or not line.open:
                    return None
            rows.append((i, line))
        fields = {i: (bool, Field(False, title=_title(kind, i, line))) for i, line in rows}
        model = create_model("Review", **fields,
                             note=(str, Field("", title="Anything to tell the agent (optional)", max_length=300)))
        parts = [f"The picking agent asks: {question}"] + [self._evidence(cell, i, line) for i, line in rows]
        parts.append("Tick each item you approve. An empty box is a no: nothing is packed or discarded without a yes.")
        return Elicit("\n\n".join(parts), model)

    def _evidence(self, cell, item_id: str, line) -> str:
        insp = cell.state[item_id].inspection or {}
        reason = insp.get("reason", "").rstrip(".")
        bits = [f"{item_id} ({cell.items[item_id].produce}): verdict {insp.get('verdict', 'not inspected')}."
                + (f" {reason}." if reason else "")]
        if line is not None:
            when = "no timing given" if line.eat_in_days is None else f"to be eaten in {line.eat_in_days:g} days"
            bits.append(f"For order line {line.line} ({when}).")
        f = insp.get("forecast")
        if f is not None:
            bits.append(f"Shelf-life forecast {f.days:.1f} days left (80% interval {f.low:.1f}-{f.high:.1f}).")
        photos = [self._photo(lk["photo"]) for lk in insp.get("looks", []) if lk.get("photo")][:3]
        if photos:
            bits.append("Photos: " + ", ".join(photos))
        return " ".join(bits)

    def _photo(self, ref: str) -> str:
        if self.photo_url:
            return f"{self.photo_url}/api/photo?ref={quote(ref)}&w=512"
        prefix, _, rel = ref.partition(":")
        return str(Path(self.photo_roots[prefix], rel)) if prefix in self.photo_roots else ref


def _can_ask(ctx: Context) -> bool:
    caps = ctx.client_capabilities
    el = caps.elicitation if caps is not None else None
    return el is not None and (el.form is not None or el.url is None)  # an empty capability means forms


def _title(kind: str, item_id: str, line) -> str:
    if kind == "pack":
        return f"Pack {item_id} into order line {line.line}"
    if kind == "reject":
        return f"Discard {item_id}"
    if kind == "sell_today":
        return f"Sell {item_id} today, marked down"
    return f"{item_id}: yes"


class Desk:
    """One crate at a time, and one tool at a time: the arm does one thing at once."""

    def __init__(self, inspectors, crate, runs_dir: str, today, reviewer, faults: dict | None = None,
                 label: str = "", max_calls: int | None = None, on_finish=None):
        self.inspectors, self.crate, self.runs_dir, self.today = inspectors, crate, runs_dir, today
        self.reviewer, self.faults, self.label, self.max_calls = reviewer, faults, label, max_calls
        self.on_finish = on_finish  # called with the run folder once a job finishes (the hosted server archives it)
        self.cell: Cell | None = None
        self.run_dir = ""
        self.lock = anyio.Lock()

    def new(self, seed: int = 0, camera_faults: bool = False) -> Cell:
        name = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-seed{seed}" + (f"-{self.label}" if self.label else "")
        self.run_dir = os.path.join(self.runs_dir, name)
        trace = Trace(os.path.join(self.run_dir, "trace.jsonl"))
        inspectors = self.inspectors.with_faults(self.faults) if camera_faults and self.faults else self.inspectors
        self.cell = Cell(self.crate(seed), inspectors, trace=trace, reviewer=self.reviewer)
        self.cell.today = self.today()
        trace.log("start", backend="mcp client", seed=seed, faults=camera_faults, reviewer=self.reviewer.name,
                  today=self.cell.today.isoformat())
        return self.cell

    def under_way(self) -> bool:
        return self.cell is not None and not self.cell.finished and bool(self.cell.trace.of_kind("tool_call"))

    async def run(self, name: str, args: dict, review=None, note: str = "") -> dict:
        async with self.lock:
            cell = self.cell or self.new()
            if cell.finished and name != "list_crate":
                return {"ok": False, "error": "this job is finished: call new_crate to start another"}
            if name != "finish" and self.max_calls is not None and len(cell.trace.of_kind("tool_call")) >= self.max_calls:
                return {"ok": False, "error": f"this job has used its {self.max_calls} tool calls: call finish"}
            return await self._call(cell, name, args, review, note)

    async def _call(self, cell, name, args, review, note) -> dict:
        if isinstance(self.reviewer, ClientReviewer):
            self.reviewer.outcome, self.reviewer.note = review, note
        cell.trace.log("tool_call", tool=name, input=args)
        out = await anyio.to_thread.run_sync(call, cell, name, args)
        if name == "ask_person" and getattr(self.reviewer, "note", ""):
            out["note"] = self.reviewer.note
        cell.trace.log("tool_result", tool=name, output=out)
        if name == "finish" and out.get("ok"):
            path = os.path.join(self.run_dir, "score.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(cell.score(), fh, indent=2)
            cell.trace.log("score", path=path)
            if self.on_finish is not None:
                await anyio.to_thread.run_sync(self.on_finish, self.run_dir)
        return out


class JobError(Exception):
    pass


class Jobs:
    """Which desk a tool call is for.

    Locally there is one desk, and the job argument is ignored. Hosted, each new_crate opens a job with a desk of
    its own; idle jobs close, and the number of open jobs, new jobs per address and calls per job are capped.
    """

    def __init__(self, make_desk, hosted: bool = False, max_jobs: int = 20, idle_s: float = 1800.0,
                 per_ip_per_hour: int = 30, reviewer=None, clock=time.monotonic):
        self.make_desk, self.hosted, self.clock = make_desk, hosted, clock  # make_desk(job, answers) -> Desk
        self.reviewer = reviewer                          # answers -> a fresh reviewer, for new_crate's answers
        self.max_jobs, self.idle_s, self.per_ip_per_hour = max_jobs, idle_s, per_ip_per_hour
        self.desks: dict[str, Desk] = {}
        self.used: dict[str, float] = {}
        self.starts: dict[str, list[float]] = {}
        self.local = None if hosted else make_desk("", None)

    def get(self, job: str | None) -> Desk:
        if not self.hosted:
            return self.local
        self._close_idle()
        if not job:
            raise JobError("pass the job id new_crate returned as job; call new_crate to open a job")
        if job not in self.desks:
            raise JobError(f"no open job {job!r} (jobs close after {self.idle_s / 60:.0f} idle minutes): "
                           "call new_crate to open another")
        self.used[job] = self.clock()
        return self.desks[job]

    def open(self, ip: str, answers: str | None) -> tuple[str, Desk]:
        self._close_idle()
        now = self.clock()
        recent = [t for t in self.starts.get(ip, []) if now - t < 3600]
        if len(recent) >= self.per_ip_per_hour:
            raise JobError(f"at most {self.per_ip_per_hour} new jobs an hour from one address; carry on with an open job")
        if len(self.desks) >= self.max_jobs:
            raise JobError(f"the cell is serving its limit of {self.max_jobs} open jobs; try again in a few minutes")
        job = secrets.token_urlsafe(9)
        self.desks[job], self.used[job] = self.make_desk(job, answers), now
        self.starts[ip] = recent + [now]
        return job, self.desks[job]

    def _close_idle(self):
        now = self.clock()
        for job in [j for j, t in self.used.items() if now - t > self.idle_s]:
            self.desks.pop(job, None), self.used.pop(job, None)


def _client_ip(ctx: Context) -> str:
    headers = ctx.headers or {}
    fwd = headers.get("x-forwarded-for", "")  # CloudFront puts the visitor first
    return fwd.split(",")[0].strip() or "?"


def build_server(jobs: Jobs, today) -> MCPServer:
    if jobs.hosted:
        start = ("Start with new_crate: it opens a job of your own on a crate and returns its job id; pass that id as "
                 "job to every other tool. Jobs close after 30 idle minutes. answers 'you' puts each question to your "
                 "person as a form; 'simulated' answers from the datasets' labels, for a run with nobody there.")
    else:
        start = ("A crate is ready: start with read_order. Call new_crate only to work a different crate, or after "
                 "finish.")
    instructions = ("Chhaant is a produce-picking cell. The customer's order comes from the person you work with. "
                    + start + " Work the order with these rules, which the cell enforces in code.\n\n"
                    + system_prompt(today()))
    server = MCPServer("chhaant", title="Chhaant picking cell", instructions=instructions)

    async def run(job, name, args, review=None, note=""):
        try:
            desk = jobs.get(job)
        except JobError as err:
            return {"ok": False, "error": str(err)}
        return await desk.run(name, args, review, note)

    @server.tool(description=("Start a new job on a fresh crate of real produce photos: three tomatoes, a mango and "
                              "four avocados (the web app's crate). On the local server a crate (seed 0) is ready "
                              "without it, and it is refused while a job is under way unless restart is true; on the "
                              "hosted server it opens a job of your own and returns its job id. Returns the crate "
                              "and today's date."),
                 annotations=FIXED)
    async def new_crate(ctx: Context,
                        seed: Annotated[int, Field(ge=0, le=9999, description="which crate; the same seed is the same crate")] = 0,
                        camera_faults: Annotated[bool, Field(description="spoil some photos with blur, glare and "
                                                                         "cropping, to see the capture checks work")] = False,
                        restart: Annotated[bool, Field(description="drop the job under way and start over")] = False,
                        answers: Annotated[Literal["you", "simulated"] | None,
                                           Field(description="who answers questions: 'you' as forms in your client, "
                                                             "'simulated' from the datasets' labels")] = None) -> dict:
        if jobs.hosted:
            try:
                job, desk = jobs.open(_client_ip(ctx), answers)
            except JobError as err:
                return {"ok": False, "error": str(err)}
        else:
            job, desk = None, jobs.local
            if desk.under_way() and not restart:
                return {"ok": False, "error": "a job is already under way on this crate (the order is read or items "
                        "were handled): carry on with it, or call new_crate with restart true to drop it"}
            if answers is not None and jobs.reviewer is not None:
                desk.reviewer = jobs.reviewer(answers)
        async with desk.lock:
            cell = desk.new(seed, camera_faults)
            return {**cell.list_crate(), **({"job": job} if job else {}), "today": f"{cell.today:%A %d %B %Y}",
                    "answers": desk.reviewer.name}

    @server.tool(description=DESCRIPTIONS["read_order"], annotations=FIXED)
    async def read_order(lines: list[OrderLineIn], job: Job = None) -> dict:
        return await run(job, "read_order", {"lines": [ln.model_dump() for ln in lines]})

    @server.tool(description=DESCRIPTIONS["list_crate"], annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    async def list_crate(job: Job = None) -> dict:
        return await run(job, "list_crate", {})

    @server.tool(description=DESCRIPTIONS["inspect"], annotations=FIXED)
    async def inspect(item_id: str, job: Job = None) -> dict:
        return await run(job, "inspect", {"item_id": item_id})

    @server.tool(description=DESCRIPTIONS["look_closer"], annotations=FIXED)
    async def look_closer(item_id: str, azimuth: Annotated[float, Field(ge=0, le=360)], job: Job = None) -> dict:
        return await run(job, "look_closer", {"item_id": item_id, "azimuth": azimuth})

    async def review_form(ctx: Context, kind: str, question: str, item_id: str | None, item_ids: list[str] | None,
                          order_line: int | None, job: str | None) -> Elicit[BaseModel] | None:
        """Put the review to the client's person before the cell records it; re-run on each protocol round."""
        try:
            desk = jobs.get(job)
        except JobError:
            return None  # the tool body reports it
        if not isinstance(desk.reviewer, ClientReviewer) or not _can_ask(ctx):
            return None
        async with desk.lock:
            cell = desk.cell or desk.new()
            ids = list(dict.fromkeys(item_ids or ([item_id] if item_id else [])))
            return None if cell.finished or not ids else desk.reviewer.form(cell, kind, question, ids, order_line)

    @server.tool(description=DESCRIPTIONS["ask_person"], annotations=FIXED)
    async def ask_person(kind: Literal["pack", "reject", "sell_today", "question"], question: str,
                         review: Annotated[ElicitationResult[BaseModel], Resolve(review_form)], ctx: Context,
                         item_id: str | None = None, item_ids: list[str] | None = None,
                         order_line: int | None = None, job: Job = None) -> dict:
        note = "" if _can_ask(ctx) else ("this MCP client cannot show a form to its person, so the question stays "
                                         "pending; nothing that needs a person can be packed or discarded")
        return await run(job, "ask_person", {"kind": kind, "question": question, "item_id": item_id,
                                             "item_ids": item_ids, "order_line": order_line}, review, note)

    @server.tool(description=DESCRIPTIONS["place"], annotations=ToolAnnotations(destructiveHint=True, openWorldHint=False))
    async def place(item_id: str, destination: Literal["order", "reject", "sell_today", "crate"], reason: str,
                    order_line: int | None = None, job: Job = None) -> dict:
        return await run(job, "place", {"item_id": item_id, "destination": destination,
                                        "order_line": order_line, "reason": reason})

    @server.tool(description=DESCRIPTIONS["finish"], annotations=FIXED)
    async def finish(summary: str, job: Job = None) -> dict:
        return await run(job, "finish", {"summary": summary})

    return server


def reviewers(photo_roots: dict[str, str], default: str = "you", photo_url: str = ""):
    """answers ('you', 'simulated' or None for the default) -> a fresh reviewer: a ClientReviewer holds one review."""
    def make(answers: str | None):
        return SimulatedReviewer() if (answers or default) == "simulated" else ClientReviewer(photo_roots, photo_url)
    return make


def hosted(inspectors, crate, runs_dir: str, today, photo_roots: dict[str, str], photo_url: str = "",
           faults: dict | None = None, on_finish=None, max_calls: int = 300, **limits) -> MCPServer:
    """The server the web app mounts at /mcp: a job per new_crate, forms by default."""
    reviewer = reviewers(photo_roots, "you", photo_url)
    jobs = Jobs(lambda job, answers: Desk(inspectors, crate, runs_dir, today, reviewer(answers), faults,
                                          label=job, max_calls=max_calls, on_finish=on_finish), hosted=True, **limits)
    return build_server(jobs, today)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--simulated-reviewer", action="store_true",
                   help="answer questions from the dataset labels (marked 'simulated reviewer'), for unattended runs")
    p.add_argument("--today", type=date.fromisoformat, default=None,
                   help="the date the cell works on (YYYY-MM-DD), for reproducible runs; default: today in the cell's zone")
    p.add_argument("--crate", type=json.loads, default=None,
                   help='serve this one crate whatever seed new_crate gets, e.g. {"seed": 3, "tr6": [["Tomato", 0]], '
                        '"avocado": [6, 2]} (TR-6 picks as produce and spoiled 0/1, avocados as true days left)')
    args = p.parse_args(argv)

    from chhaant.agent.crate import avocado_items, demo_crate, tr6_items
    from chhaant.agent.inspectors import CellInspectors
    from chhaant.decide.shelf import ShelfLife
    from chhaant.robot.faults import DEMO_FAULTS
    from chhaant.vision.model import QualityModel

    env = os.environ.get
    tr6, avocado = env("CHHAANT_TR6", str(ROOT / "data/tr6")), env("CHHAANT_AVOCADO", str(ROOT / "data/avocado"))
    inspectors = CellInspectors(QualityModel(env("CHHAANT_MODEL", str(ROOT / "models/chhaant_quality_v1.onnx"))), tr6, avocado,
                                ShelfLife.load(env("CHHAANT_SHELF", str(ROOT / "models/shelf_avocado.json"))))
    reviewer = reviewers({"tr6": tr6, "avocado": avocado}, "simulated" if args.simulated_reviewer else "you")
    cell_tz = timezone(timedelta(hours=float(env("CHHAANT_UTC_OFFSET_H", "5.5"))))
    today = (lambda: args.today) if args.today else (lambda: datetime.now(cell_tz).date())
    spec = args.crate

    def crate(seed: int):
        if spec is None:
            return demo_crate(tr6, avocado, seed)
        return (tr6_items(tr6, [tuple(pick) for pick in spec.get("tr6", [])], spec["seed"])
                + avocado_items(avocado, spec.get("avocado", []), spec["seed"]))

    runs = env("CHHAANT_MCP_RUNS", str(ROOT / "data/mcp_runs"))
    jobs = Jobs(lambda job, answers: Desk(inspectors, crate, runs, today, reviewer(answers), DEMO_FAULTS), reviewer=reviewer)
    build_server(jobs, today).run()


if __name__ == "__main__":
    main()
