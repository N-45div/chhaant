"""Run the web app:  python -m chhaant.web  (then open http://127.0.0.1:8000)

Settings come from the environment:
    CHHAANT_TR6, CHHAANT_AVOCADO   data folders (default data/tr6, data/avocado)
    CHHAANT_MODEL, CHHAANT_SHELF   quality model and avocado forecaster
    CHHAANT_RUNS                   where run traces are written (default data/runs)
    CHHAANT_AGENT, AWS_REGION      the default agent on Amazon Bedrock: nova-2-lite or claude-haiku-4-5
    CHHAANT_RUNS_PER_HOUR, CHHAANT_DAILY_RUNS, HOST, PORT
    CHHAANT_EVIDENCE_BUCKET        if set, each run's trace goes to S3 and metrics to CloudWatch
    CHHAANT_UTC_OFFSET_H           the cell's time zone, for the date the agent is told (default 5.5, India)
    CHHAANT_MCP                    0 turns off the MCP server at /mcp (default on)
    CHHAANT_MCP_RUNS               where MCP jobs' traces are written (default data/mcp_runs)
    CHHAANT_PUBLIC_URL             the site's public address, so MCP forms can link the evidence photos
"""

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import uvicorn

from chhaant.agent.cell import Cell
from chhaant.agent.crate import demo_crate
from chhaant.agent.inspectors import CellInspectors
from chhaant.agent.llm import BedrockBackend
from chhaant.decide.shelf import ShelfLife
from chhaant.robot.faults import DEMO_FAULTS
from chhaant.vision.model import QualityModel
from chhaant.web.app import create_app
from chhaant.web.runs import RunManager

AGENTS = {  # key -> (Bedrock model or inference profile, label)
    "nova-2-lite": ("global.amazon.nova-2-lite-v1:0", "Amazon Nova 2 Lite"),
    "claude-haiku-4-5": ("global.anthropic.claude-haiku-4-5-20251001-v1:0", "Claude Haiku 4.5"),
}


def build_app():
    env = os.environ.get
    tr6, avocado = env("CHHAANT_TR6", "data/tr6"), env("CHHAANT_AVOCADO", "data/avocado")
    inspectors = CellInspectors(QualityModel(env("CHHAANT_MODEL", "models/chhaant_quality_v1.onnx")), tr6, avocado,
                                ShelfLife.load(env("CHHAANT_SHELF", "models/shelf_avocado.json")))

    @lru_cache(maxsize=16)
    def crate(seed: int):
        return tuple(demo_crate(tr6, avocado, seed))

    try:  # the 3D twin needs MuJoCo (present on the Linux server; blocked on some Windows setups)
        from chhaant.sim.twin import SimTwin, TwinActuator, TwinInspectors
        from chhaant.sim.web_scene import scene_meshes
    except Exception:
        SimTwin = None

    def make_cell(trace, reviewer, seed, faults=False):
        items = list(crate(seed))
        insp = inspectors.with_faults(DEMO_FAULTS) if faults else inspectors
        if SimTwin is None:
            return Cell(items, insp, trace=trace, reviewer=reviewer)
        twin = SimTwin([(i.item_id, i.produce) for i in items])
        cell = Cell(items, TwinInspectors(insp, twin), trace=trace, reviewer=reviewer, actuator=TwinActuator(twin))
        cell.twin = twin
        return cell

    sim_meshes = None
    if SimTwin is not None:
        @lru_cache(maxsize=1)
        def sim_meshes():
            return scene_meshes(SimTwin([("x", "Tomato")]).cell.model)

    # Both on Amazon Bedrock, both measured on the same 32 orders (eval/results/cell_runs_*_iter6.md).
    default = env("CHHAANT_AGENT", "nova-2-lite")
    agents = {k: AGENTS[k] for k in sorted(AGENTS, key=lambda k: k != default)}
    label = "Amazon Bedrock"

    def make_backend(agent: str):
        return BedrockBackend(AGENTS[agent][0], env("AWS_REGION", "ap-south-1"))

    hooks = []
    if env("CHHAANT_EVIDENCE_BUCKET"):
        from chhaant.web.aws import AwsReporter
        hooks.append(AwsReporter(env("CHHAANT_EVIDENCE_BUCKET"), env("AWS_REGION", "ap-south-1")))
    # A fixed offset, not a zone name: India keeps no daylight saving, and Windows has no tz database.
    cell_tz = timezone(timedelta(hours=float(env("CHHAANT_UTC_OFFSET_H", "5.5"))))
    today = lambda: datetime.now(cell_tz).date()  # noqa: E731
    manager = RunManager(make_cell, make_backend, env("CHHAANT_RUNS", "data/runs"),
                         per_ip_per_hour=int(env("CHHAANT_RUNS_PER_HOUR", "6")), daily_cap=int(env("CHHAANT_DAILY_RUNS", "150")),
                         on_finish=hooks, today=today, agents={k: v[1] for k, v in agents.items()})
    mcp = None
    if env("CHHAANT_MCP", "1") != "0":  # bring your own agent: no model is called here, the client brings it
        from chhaant.mcp_server import hosted
        mcp = hosted(inspectors, lambda seed: list(crate(seed)), env("CHHAANT_MCP_RUNS", "data/mcp_runs"), today,
                     {"tr6": tr6, "avocado": avocado}, photo_url=env("CHHAANT_PUBLIC_URL", ""), faults=DEMO_FAULTS,
                     on_finish=hooks[0].mcp_job if hooks else None)
    return create_app(manager, {"tr6": tr6, "avocado": avocado}, lambda seed: list(crate(seed)), label, sim_meshes, mcp)


if __name__ == "__main__":
    uvicorn.run(build_app(), host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
