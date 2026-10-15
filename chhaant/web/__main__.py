"""Run the web app:  python -m chhaant.web  (then open http://127.0.0.1:8000)

Settings come from the environment:
    CHHAANT_TR6, CHHAANT_AVOCADO   data folders (default data/tr6, data/avocado)
    CHHAANT_MODEL, CHHAANT_SHELF   quality model and avocado forecaster
    CHHAANT_RUNS                   where run traces are written (default data/runs)
    CHHAANT_BACKEND                bedrock (default) or nemotron
    CHHAANT_BEDROCK_MODEL, AWS_REGION
    NEBIUS_API_KEY, NEBIUS_MODEL   for the Nemotron backend on Nebius Token Factory
    CHHAANT_RUNS_PER_HOUR, CHHAANT_DAILY_RUNS, HOST, PORT
    CHHAANT_EVIDENCE_BUCKET        if set, each run's trace goes to S3 and metrics to CloudWatch
    CHHAANT_UTC_OFFSET_H           the cell's time zone, for the date the agent is told (default 5.5, India)
"""

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import uvicorn

from chhaant.agent.cell import Cell
from chhaant.agent.crate import avocado_items, tr6_items
from chhaant.agent.inspectors import CellInspectors
from chhaant.agent.llm import BedrockBackend, OpenAICompatBackend
from chhaant.decide.shelf import ShelfLife
from chhaant.vision.model import QualityModel
from chhaant.web.app import create_app
from chhaant.web.runs import RunManager

TOKEN_FACTORY = "https://api.tokenfactory.nebius.com/v1"
TR6_PICKS = [("Tomato", 0), ("Tomato", 1), ("Tomato", 0), ("Mango", 1)]
AVOCADO_DAYS_LEFT = [6, 2, 1, 0]


def build_app():
    env = os.environ.get
    tr6, avocado = env("CHHAANT_TR6", "data/tr6"), env("CHHAANT_AVOCADO", "data/avocado")
    inspectors = CellInspectors(QualityModel(env("CHHAANT_MODEL", "models/chhaant_quality_v1.onnx")), tr6, avocado,
                                ShelfLife.load(env("CHHAANT_SHELF", "models/shelf_avocado.json")))

    @lru_cache(maxsize=16)
    def crate(seed: int):
        return tuple(tr6_items(tr6, TR6_PICKS, seed) + avocado_items(avocado, AVOCADO_DAYS_LEFT, seed))

    try:  # the 3D twin needs MuJoCo (present on the Linux server; blocked on some Windows setups)
        from chhaant.sim.twin import SimTwin, TwinActuator, TwinInspectors
        from chhaant.sim.web_scene import scene_meshes
    except Exception:
        SimTwin = None

    def make_cell(trace, reviewer, seed):
        items = list(crate(seed))
        if SimTwin is None:
            return Cell(items, inspectors, trace=trace, reviewer=reviewer)
        twin = SimTwin([(i.item_id, i.produce) for i in items])
        cell = Cell(items, TwinInspectors(inspectors, twin), trace=trace, reviewer=reviewer, actuator=TwinActuator(twin))
        cell.twin = twin
        return cell

    sim_meshes = None
    if SimTwin is not None:
        @lru_cache(maxsize=1)
        def sim_meshes():
            return scene_meshes(SimTwin([("x", "Tomato")]).cell.model)

    backend_kind = env("CHHAANT_BACKEND", "bedrock")
    if backend_kind == "nemotron":
        model = env("NEBIUS_MODEL", "nvidia/nemotron-3-super-120b-a12b")
        label = f"Nemotron on Nebius Token Factory ({model})"

        def make_backend():
            return OpenAICompatBackend(TOKEN_FACTORY, env("NEBIUS_API_KEY", ""), model)
    else:
        model = env("CHHAANT_BEDROCK_MODEL", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
        label = f"Amazon Bedrock ({model.split('.')[-1].split('-v1')[0]})"

        def make_backend():
            return BedrockBackend(model, env("AWS_REGION", "ap-south-1"))

    hooks = []
    if env("CHHAANT_EVIDENCE_BUCKET"):
        from chhaant.web.aws import AwsReporter
        hooks.append(AwsReporter(env("CHHAANT_EVIDENCE_BUCKET"), env("AWS_REGION", "ap-south-1")))
    # A fixed offset, not a zone name: India keeps no daylight saving, and Windows has no tz database.
    cell_tz = timezone(timedelta(hours=float(env("CHHAANT_UTC_OFFSET_H", "5.5"))))
    manager = RunManager(make_cell, make_backend, env("CHHAANT_RUNS", "data/runs"),
                         per_ip_per_hour=int(env("CHHAANT_RUNS_PER_HOUR", "6")), daily_cap=int(env("CHHAANT_DAILY_RUNS", "150")),
                         on_finish=hooks, today=lambda: datetime.now(cell_tz).date())
    return create_app(manager, {"tr6": tr6, "avocado": avocado}, lambda seed: list(crate(seed)), label, sim_meshes)


if __name__ == "__main__":
    uvicorn.run(build_app(), host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
