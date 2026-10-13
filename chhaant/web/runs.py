"""Agent runs for the web app: one at a time, each in a background thread.

Visitors watch the active run instead of starting a second one, and runs are
rate limited (per visitor per hour, plus a daily cap) because each one calls a
paid language model. Snapshots are cheap to poll: events come back from a
cursor, so the page only fetches what it has not seen.
"""

import json
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass

from chhaant.agent.approval import PersonReviewer, SimulatedReviewer
from chhaant.agent.loop import run as run_agent
from chhaant.agent.trace import Trace


class Busy(Exception):
    def __init__(self, active_id: str):
        super().__init__(active_id)
        self.active_id = active_id


class RateLimited(Exception):
    pass


@dataclass
class Run:
    id: str
    order: str
    reviewer_mode: str
    seed: int
    cell: object
    reviewer: object
    started_at: float
    status: str = "running"   # "running", "done" or "error"
    result: dict | None = None
    error: str = ""
    finished_at: float | None = None


def _forecast(f) -> dict | None:
    return None if f is None else {"days": round(f.days, 2), "low": round(f.low, 2), "high": round(f.high, 2)}


def thumb_ref(item) -> str:
    return f"tr6:{item.session.files[0]}" if item.kind == "tr6" else f"avocado:{item.photos[0]}"


class RunManager:
    def __init__(self, make_cell, make_backend, runs_dir: str, per_ip_per_hour: int = 6,
                 daily_cap: int = 150, person_timeout_s: float = 300.0):
        self.make_cell = make_cell          # (trace, reviewer, seed) -> Cell
        self.make_backend = make_backend    # () -> language-model backend
        self.runs_dir = runs_dir
        self.per_ip_per_hour, self.daily_cap = per_ip_per_hour, daily_cap
        self.person_timeout_s = person_timeout_s
        self.runs: dict[str, Run] = {}
        self.active: str | None = None
        self._lock = threading.Lock()
        self._hits: dict[str, deque] = defaultdict(deque)
        self._day, self._day_count = time.strftime("%Y-%m-%d"), 0

    # ---- starting and finishing ---------------------------------------------
    def _check_limits(self, ip: str) -> None:
        now = time.time()
        hits = self._hits[ip]
        while hits and now - hits[0] > 3600:
            hits.popleft()
        today = time.strftime("%Y-%m-%d")
        if today != self._day:
            self._day, self._day_count = today, 0
        if len(hits) >= self.per_ip_per_hour:
            raise RateLimited(f"at most {self.per_ip_per_hour} runs per hour per visitor")
        if self._day_count >= self.daily_cap:
            raise RateLimited("the daily run budget is used up; watch the latest run instead")
        hits.append(now)
        self._day_count += 1

    def start(self, order: str, reviewer_mode: str, ip: str, seed: int = 3) -> Run:
        if reviewer_mode not in ("person", "simulated"):
            raise ValueError("reviewer must be 'person' or 'simulated'")
        with self._lock:
            if self.active and self.runs[self.active].status == "running":
                raise Busy(self.active)
            self._check_limits(ip)
            run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
            trace = Trace(os.path.join(self.runs_dir, run_id, "trace.jsonl"))
            reviewer = PersonReviewer(self.person_timeout_s) if reviewer_mode == "person" else SimulatedReviewer()
            run = Run(run_id, order, reviewer_mode, seed, self.make_cell(trace, reviewer, seed), reviewer, time.time())
            self.runs[run_id], self.active = run, run_id
        threading.Thread(target=self._go, args=(run,), daemon=True).start()
        return run

    def _go(self, run: Run) -> None:
        try:
            run.result = run_agent(run.order, run.cell, self.make_backend())
            run.status = "done"
        except Exception as err:  # report the failure in the run instead of losing the thread
            run.status, run.error = "error", f"{type(err).__name__}: {err}"
            run.cell.trace.log("error", error=run.error)
        finally:
            run.finished_at = time.time()
            with open(os.path.join(self.runs_dir, run.id, "result.json"), "w") as fh:
                json.dump({"order": run.order, "status": run.status, "error": run.error, "result": run.result,
                           "reviewer": run.reviewer_mode, "seed": run.seed}, fh, indent=1, default=str)

    def answer(self, run_id: str, request_id: str, approved: bool, answer: str) -> bool:
        run = self.runs.get(run_id)
        if run is None or not isinstance(run.reviewer, PersonReviewer):
            return False
        return run.reviewer.answer(request_id, approved, answer.strip() or ("approved" if approved else "declined"))

    def latest(self) -> str | None:
        done = [r for r in self.runs.values() if r.status != "running"]
        return max(done, key=lambda r: r.started_at).id if done else None

    # ---- what the page polls -------------------------------------------------
    def snapshot(self, run_id: str, after: int = 0) -> dict:
        run = self.runs[run_id]
        cell = run.cell
        waiting = set(run.reviewer.waiting) if isinstance(run.reviewer, PersonReviewer) else set()
        events = cell.trace.events
        return {
            "id": run.id, "status": run.status, "error": run.error, "order_text": run.order,
            "reviewer": run.reviewer_mode, "elapsed_s": round((run.finished_at or time.time()) - run.started_at, 1),
            "order": [{"line": ln.line, "produce": ln.produce, "quantity": ln.quantity,
                       "eat_in_days": ln.eat_in_days, "packed": list(ln.packed)} for ln in cell.order],
            "items": [self._item_row(cell, i) for i in cell.items],
            "waiting": [{"request_id": r.id, "item_id": r.item_id, "kind": r.kind, "question": r.question}
                        for r in cell.queue.requests if r.id in waiting],
            "events": events[after:], "next": len(events),
            "result": run.result,
        }

    def _item_row(self, cell, item_id: str) -> dict:
        item, st = cell.items[item_id], cell.state[item_id]
        insp = st.inspection
        return {"item_id": item_id, "produce": item.produce, "location": st.location, "thumb": thumb_ref(item),
                "inspected": insp is not None, "verdict": None if insp is None else insp["verdict"],
                "forecast": None if insp is None else _forecast(insp["forecast"])}

    def evidence(self, run_id: str, item_id: str) -> dict:
        cell = self.runs[run_id].cell
        if item_id not in cell.items:
            raise KeyError(item_id)
        item, st = cell.items[item_id], cell.state[item_id]
        insp = st.inspection
        return {
            "item_id": item_id, "produce": item.produce, "storage_temp_c": item.temp_c, "location": st.location,
            "inspection": None if insp is None else {**{k: v for k, v in insp.items() if k != "forecast"},
                                                     "forecast": _forecast(insp["forecast"])},
            "extra_looks": st.extra_looks,
            "routing_for_open_lines": cell._routings(item_id),
            "requests": [{"id": r.id, "kind": r.kind, "question": r.question, "status": r.status,
                          "answer": r.answer, "by": r.by} for r in cell.queue.requests if r.item_id == item_id],
            "actions": [e for e in cell.trace.events if e["kind"] in ("action", "guardrail") and e.get("item_id") == item_id],
        }
