"""The cell as an MCP server, so any MCP client's agent can drive it under the cell's own rules.

    python -m chhaant.mcp_server                        # stdio: Claude Code, Claude Desktop, any MCP client
    python -m chhaant.mcp_server --simulated-reviewer   # questions answered from the dataset labels, unattended

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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

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


class OrderLineIn(BaseModel):
    produce: str
    quantity: int = Field(ge=1)
    eat_in_days: float | None = Field(None, description="0.5 = tonight, 1 = tomorrow; null when no timing was given")
    eat_on: str | None = Field(None, description="a named day ('Saturday', 'next Wednesday'); the cell counts the days")


class ClientReviewer:
    """Answers a review from the form the MCP client's person filled in, a yes or no per item.

    The form is put to the client before the cell records the question (see ``form``); the cell then calls
    ``review_many`` and gets the answers. Anything not answered stays pending.
    """

    name = "person via MCP client"

    def __init__(self, photo_roots: dict[str, str]):
        self.photo_roots = photo_roots
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

    def __init__(self, inspectors, crate, runs_dir: str, today, reviewer, faults: dict | None = None):
        self.inspectors, self.crate, self.runs_dir, self.today = inspectors, crate, runs_dir, today
        self.reviewer, self.faults = reviewer, faults
        self.cell: Cell | None = None
        self.run_dir = ""
        self.lock = anyio.Lock()

    def new(self, seed: int = 0, camera_faults: bool = False) -> Cell:
        self.run_dir = os.path.join(self.runs_dir, f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-seed{seed}")
        trace = Trace(os.path.join(self.run_dir, "trace.jsonl"))
        inspectors = self.inspectors.with_faults(self.faults) if camera_faults and self.faults else self.inspectors
        self.cell = Cell(self.crate(seed), inspectors, trace=trace, reviewer=self.reviewer)
        self.cell.today = self.today()
        trace.log("start", backend="mcp client", seed=seed, faults=camera_faults, reviewer=self.reviewer.name,
                  today=self.cell.today.isoformat())
        return self.cell

    async def run(self, name: str, args: dict, review=None, note: str = "") -> dict:
        async with self.lock:
            cell = self.cell or self.new()
            if cell.finished and name != "list_crate":
                return {"ok": False, "error": "this job is finished: call new_crate to start another"}
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
            return out


def build_server(desk: Desk) -> MCPServer:
    instructions = ("Chhaant is a produce-picking cell. The customer's order comes from the person you work with. "
                    "Call new_crate to start a job (a crate with seed 0 is used if you do not), then work the order "
                    "with these rules, which the cell enforces in code.\n\n" + system_prompt(desk.today()))
    server = MCPServer("chhaant", title="Chhaant picking cell", instructions=instructions)

    @server.tool(description=("Start a new job on a fresh crate of real produce photos: three tomatoes, a mango and "
                              "four avocados (the web app's crate). Returns the crate and today's date."),
                 annotations=FIXED)
    async def new_crate(seed: Annotated[int, Field(ge=0, le=9999, description="which crate; the same seed is the same crate")] = 0,
                        camera_faults: Annotated[bool, Field(description="spoil some photos with blur, glare and "
                                                                         "cropping, to see the capture checks work")] = False) -> dict:
        async with desk.lock:
            cell = desk.new(seed, camera_faults)
            return {**cell.list_crate(), "today": f"{cell.today:%A %d %B %Y}"}

    @server.tool(description=DESCRIPTIONS["read_order"], annotations=FIXED)
    async def read_order(lines: list[OrderLineIn]) -> dict:
        return await desk.run("read_order", {"lines": [ln.model_dump() for ln in lines]})

    @server.tool(description=DESCRIPTIONS["list_crate"], annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    async def list_crate() -> dict:
        return await desk.run("list_crate", {})

    @server.tool(description=DESCRIPTIONS["inspect"], annotations=FIXED)
    async def inspect(item_id: str) -> dict:
        return await desk.run("inspect", {"item_id": item_id})

    @server.tool(description=DESCRIPTIONS["look_closer"], annotations=FIXED)
    async def look_closer(item_id: str, azimuth: Annotated[float, Field(ge=0, le=360)]) -> dict:
        return await desk.run("look_closer", {"item_id": item_id, "azimuth": azimuth})

    async def review_form(ctx: Context, kind: str, question: str, item_id: str | None, item_ids: list[str] | None,
                          order_line: int | None) -> Elicit[BaseModel] | None:
        """Put the review to the client's person before the cell records it; re-run on each protocol round."""
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
                         order_line: int | None = None) -> dict:
        note = "" if _can_ask(ctx) else ("this MCP client cannot show a form to its person, so the question stays "
                                         "pending; nothing that needs a person can be packed or discarded")
        return await desk.run("ask_person", {"kind": kind, "question": question, "item_id": item_id,
                                             "item_ids": item_ids, "order_line": order_line}, review, note)

    @server.tool(description=DESCRIPTIONS["place"], annotations=ToolAnnotations(destructiveHint=True, openWorldHint=False))
    async def place(item_id: str, destination: Literal["order", "reject", "sell_today", "crate"], reason: str,
                    order_line: int | None = None) -> dict:
        return await desk.run("place", {"item_id": item_id, "destination": destination,
                                        "order_line": order_line, "reason": reason})

    @server.tool(description=DESCRIPTIONS["finish"], annotations=FIXED)
    async def finish(summary: str) -> dict:
        return await desk.run("finish", {"summary": summary})

    return server


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
    reviewer = SimulatedReviewer() if args.simulated_reviewer else ClientReviewer({"tr6": tr6, "avocado": avocado})
    cell_tz = timezone(timedelta(hours=float(env("CHHAANT_UTC_OFFSET_H", "5.5"))))
    spec = args.crate

    def crate(seed: int):
        if spec is None:
            return demo_crate(tr6, avocado, seed)
        return (tr6_items(tr6, [tuple(pick) for pick in spec.get("tr6", [])], spec["seed"])
                + avocado_items(avocado, spec.get("avocado", []), spec["seed"]))

    desk = Desk(inspectors, crate, env("CHHAANT_MCP_RUNS", str(ROOT / "data/mcp_runs")),
                (lambda: args.today) if args.today else (lambda: datetime.now(cell_tz).date()), reviewer, DEMO_FAULTS)
    build_server(desk).run()


if __name__ == "__main__":
    main()
