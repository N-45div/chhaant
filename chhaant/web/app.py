"""HTTP API and page for Chhaant.

    GET  /                               the page
    GET  /api/health                     liveness, active run, model backend
    GET  /api/crate?seed=3               the crate a run would get (no model call)
    POST /api/runs                       start a run {order, reviewer: person|simulated, seed}
    GET  /api/runs/active | /latest      which run to watch
    GET  /api/runs/{id}?after=N          snapshot, with trace events from cursor N
    POST /api/runs/{id}/answer           a person's answer {request_id, approved, answer}
    GET  /api/runs/{id}/items/{item}     the item's evidence pack
    GET  /api/photo?ref=tr6:...&w=256    a dataset photo (only from the two data folders)
    GET  /api/sim/meshes                 the arm's simplified meshes (static, cacheable)
    GET  /api/runs/{id}/sim/scene        the run's 3D twin: geoms, moving bodies, start poses
    GET  /api/runs/{id}/sim?after=N      twin body poses from frame N, with captions
"""

import os
import platform
from functools import lru_cache

import cv2
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from chhaant.web.runs import Busy, RateLimited, RunManager, thumb_ref

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
IMAGE_EXT = (".jpg", ".jpeg", ".png")


class StartRun(BaseModel):
    order: str = Field(min_length=3, max_length=600)
    reviewer: str = "person"
    seed: int = Field(default=3, ge=0, le=999)


class Answer(BaseModel):
    request_id: str
    approved: bool
    answer: str = Field(default="", max_length=300)


def safe_photo_path(ref: str, roots: dict[str, str]) -> str:
    """Resolve 'tr6:<rel>' or 'avocado:<rel>' inside its data folder; refuse anything else."""
    prefix, _, rel = ref.partition(":")
    root = roots.get(prefix)
    if root is None or not rel:
        raise HTTPException(404, "unknown photo")
    base = os.path.realpath(root)
    path = os.path.realpath(os.path.join(base, rel))
    if not path.startswith(base + os.sep) or not path.lower().endswith(IMAGE_EXT) or not os.path.isfile(path):
        raise HTTPException(404, "unknown photo")
    return path


def create_app(manager: RunManager, photo_roots: dict[str, str], crate_preview, backend_name: str = "",
               sim_meshes=None) -> FastAPI:
    app = FastAPI(title="Chhaant", docs_url=None, redoc_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    # Which OpenCV build is doing the vision: on the COOL AMI the HAL line names KleidiCV.
    build = {line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip()
             for line in cv2.getBuildInformation().splitlines() if ":" in line and ("HAL" in line or "Baseline" in line)}
    opencv = {"version": cv2.__version__, "build": build, "machine": platform.machine()}
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @lru_cache(maxsize=512)
    def photo_bytes(path: str, width: int) -> bytes:
        img = cv2.imread(path)
        if img is None:
            raise HTTPException(404, "unreadable photo")
        if width and img.shape[1] > width:
            img = cv2.resize(img, (width, round(img.shape[0] * width / img.shape[1])), interpolation=cv2.INTER_AREA)
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return enc.tobytes()

    def client_ip(request: Request) -> str:
        fwd = request.headers.get("x-forwarded-for", "")
        return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC, "index.html"))

    @app.get("/api/health")
    def health():
        return {"ok": True, "active": manager.active, "backend": backend_name, "opencv": opencv}

    @app.get("/api/crate")
    def crate(seed: int = 3):
        return {"seed": seed, "items": [{"item_id": i.item_id, "produce": i.produce, "kind": i.kind, "thumb": thumb_ref(i)}
                                        for i in crate_preview(seed)]}

    @app.post("/api/runs", status_code=202)
    def start(body: StartRun, request: Request):
        try:
            run = manager.start(body.order, body.reviewer, client_ip(request), body.seed)
        except Busy as busy:
            return JSONResponse({"error": "a run is in progress; watch it", "active": busy.active_id}, status_code=409)
        except RateLimited as limited:
            return JSONResponse({"error": str(limited)}, status_code=429)
        except ValueError as err:
            raise HTTPException(400, str(err))
        return {"id": run.id}

    @app.get("/api/runs/active")
    def active():
        return {"id": manager.active if manager.active and manager.runs[manager.active].status == "running" else None}

    @app.get("/api/runs/latest")
    def latest():
        return {"id": manager.latest()}

    @app.get("/api/runs/{run_id}")
    def snapshot(run_id: str, after: int = 0):
        if run_id not in manager.runs:
            raise HTTPException(404, "no such run")
        return JSONResponse(manager.snapshot(run_id, max(0, after)), headers={"Cache-Control": "no-store"})

    @app.post("/api/runs/{run_id}/answer")
    def answer(run_id: str, body: Answer):
        if not manager.answer(run_id, body.request_id, body.approved, body.answer):
            raise HTTPException(409, "that question is not waiting for an answer")
        return {"ok": True}

    @app.get("/api/runs/{run_id}/items/{item_id}")
    def evidence(run_id: str, item_id: str):
        try:
            return manager.evidence(run_id, item_id)
        except KeyError:
            raise HTTPException(404, "no such run or item")

    @app.get("/api/sim/meshes")
    def meshes():
        if sim_meshes is None:
            raise HTTPException(404, "the 3D cell runs only where MuJoCo is installed (the deployed server)")
        return JSONResponse(sim_meshes(), headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/api/runs/{run_id}/sim/scene")
    def sim_scene(run_id: str):
        try:
            return manager.sim_scene(run_id)
        except KeyError:
            raise HTTPException(404, "no 3D twin for this run")

    @app.get("/api/runs/{run_id}/sim")
    def sim_frames(run_id: str, after: int = 0):
        try:
            return JSONResponse(manager.sim_frames(run_id, max(0, after)), headers={"Cache-Control": "no-store"})
        except KeyError:
            raise HTTPException(404, "no 3D twin for this run")

    @app.get("/api/photo")
    def photo(ref: str, w: int = 0):
        path = safe_photo_path(ref, photo_roots)
        return Response(photo_bytes(path, max(0, min(w, 1024))), media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})

    return app
