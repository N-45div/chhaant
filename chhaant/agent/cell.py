"""The inspection cell as the agent sees it: six tools, and the rules behind them.

The language model plans and calls tools; the rules live here, in code, so a
model cannot talk its way past them:

* nothing is placed before it has been inspected;
* a defective item never goes into an order (a person can still do that by hand);
* packing needs the routing to say "pack" for that order line, or a person's approval;
* discarding a sound item needs a person's approval (no silent food waste);
* "sell today" needs the forecast to say so, or a person;
* putting an item back in the crate is always allowed;
* the job cannot finish with a line short while an item that might fill it is
  uninspected, or routed "ask" and never put to a person.

A refused move comes back to the model as an explained error and is recorded
in the trace, so the model can adapt instead of crashing the run.
"""

from dataclasses import dataclass, field

from chhaant.agent.approval import ApprovalQueue
from chhaant.agent.trace import Trace
from chhaant.decide.route import RIPE_WINDOW_DAYS, route

DESTINATIONS = ("order", "reject", "sell_today", "crate")


@dataclass
class OrderLine:
    line: int
    produce: str
    quantity: int
    eat_in_days: float | None
    packed: list[str] = field(default_factory=list)

    @property
    def open(self) -> bool:
        return len(self.packed) < self.quantity


@dataclass
class ItemState:
    inspection: dict | None = None
    extra_looks: list[dict] = field(default_factory=list)
    location: str = "crate"


class RecordingActuator:
    """Stands in for the arm: records each move (the MuJoCo cell replays them as motion)."""

    def __init__(self):
        self.moves: list[tuple[str, str]] = []

    def move(self, item_id: str, destination: str) -> None:
        self.moves.append((item_id, destination))


ALIASES = {"amla": "Indian_Gooseberry", "gooseberry": "Indian_Gooseberry", "indian_gooseberries": "Indian_Gooseberry"}


def _produce_key(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def canonical_produce(name: str, known: set[str]) -> str | None:
    """The crate's own name for ``name``, ignoring case, spaces and plurals ("avocados",
    "tomatoes", "mangoes"), or None when the crate has nothing by that name."""
    key = _produce_key(name)
    by_key = {k.lower(): k for k in known}
    for cand in (key, ALIASES.get(key, "").lower(), key[:-2] if key.endswith("es") else "", key[:-1] if key.endswith("s") else ""):
        if cand and cand in by_key:
            return by_key[cand]
    return None


def _forecast(f) -> dict | None:
    return None if f is None else {"days": round(f.days, 2), "low": round(f.low, 2), "high": round(f.high, 2)}


class Cell:
    def __init__(self, items, inspectors, trace: Trace | None = None, reviewer=None, actuator=None):
        self.items = {i.item_id: i for i in items}
        self.state = {i.item_id: ItemState() for i in items}
        self.inspectors = inspectors
        self.trace = trace or Trace()
        self.reviewer = reviewer
        self.actuator = actuator or RecordingActuator()
        self.queue = ApprovalQueue()
        self.order: list[OrderLine] = []
        self.finished = False
        self.summary = ""

    # ---- helpers ----------------------------------------------------------
    def _refuse(self, tool: str, message: str, **ctx) -> dict:
        self.trace.log("guardrail", tool=tool, refused=message, **ctx)
        return {"ok": False, "error": message}

    def _routings(self, item_id: str) -> list[dict]:
        insp, item = self.state[item_id].inspection, self.items[item_id]
        if insp is None:
            return []
        out = []
        for ln in self.order:
            if ln.produce == item.produce and ln.open:
                r = self._route(insp, ln.eat_in_days)
                out.append({"line": ln.line, "eat_in_days": ln.eat_in_days, "action": r.action, "reason": r.reason})
        return out

    @staticmethod
    def _route(insp: dict, eat_in_days):
        # produce with a shelf-life forecast is bought to eat ripe: it must also be ready by then
        window = RIPE_WINDOW_DAYS if insp["forecast"] is not None else None
        return route(insp["verdict"], insp["forecast"], eat_in_days, window)

    def _line(self, n) -> OrderLine | None:
        return next((ln for ln in self.order if ln.line == n), None)

    # ---- tools ------------------------------------------------------------
    def read_order(self, lines: list[dict]) -> dict:
        if not lines:
            return self._refuse("read_order", "the order has no lines")
        order = []
        known = {it.produce for it in self.items.values()}
        for n, ln in enumerate(lines, 1):
            raw = str(ln.get("produce", "")).strip()
            # The crate's spelling, so "avocados" opens a line the avocados can fill.
            produce = canonical_produce(raw, known) or ALIASES.get(_produce_key(raw)) or raw.title().replace(" ", "_")
            qty, eat = ln.get("quantity"), ln.get("eat_in_days")
            if not produce or not isinstance(qty, int) or qty < 1:
                return self._refuse("read_order", f"line {n} needs a produce name and a whole quantity of at least 1")
            if eat is not None and (not isinstance(eat, (int, float)) or eat < 0):
                return self._refuse("read_order", f"line {n}: eat_in_days must be a non-negative number or null")
            order.append(OrderLine(n, produce, qty, None if eat is None else float(eat)))
        self.order = order
        in_crate = {}
        for it in self.items.values():
            in_crate[it.produce] = in_crate.get(it.produce, 0) + 1
        rows = []
        for ln in order:
            row = {"line": ln.line, "produce": ln.produce, "quantity": ln.quantity,
                   "eat_in_days": ln.eat_in_days, "in_crate": in_crate.get(ln.produce, 0)}
            if ln.produce not in known:
                row["note"] = f"no {ln.produce} in this crate; it holds {', '.join(sorted(known))}"
            rows.append(row)
        return {"ok": True, "order": rows}

    def list_crate(self) -> dict:
        rows = []
        for item_id, item in self.items.items():
            st = self.state[item_id]
            rows.append({"item_id": item_id, "produce": item.produce, "location": st.location,
                         "inspected": st.inspection is not None,
                         "verdict": None if st.inspection is None else st.inspection["verdict"]})
        return {"ok": True, "items": rows,
                "order": [{"line": ln.line, "produce": ln.produce, "quantity": ln.quantity,
                           "eat_in_days": ln.eat_in_days, "packed": list(ln.packed)} for ln in self.order]}

    def inspect(self, item_id: str) -> dict:
        if item_id not in self.items:
            return self._refuse("inspect", f"no item {item_id}")
        st = self.state[item_id]
        if st.inspection is None:
            st.inspection = self.inspectors.inspect(self.items[item_id])
        insp = st.inspection
        return {"ok": True, "item_id": item_id, "produce": self.items[item_id].produce,
                "capability": insp["capability"], "verdict": insp["verdict"], "reason": insp["reason"],
                "defect_score": insp.get("defect_score"), "ripeness": insp.get("ripeness"),
                "coverage": insp.get("coverage"), "unseen_share": insp.get("unseen_share"),
                "views_used": insp.get("side_views"), "forecast_days_left": _forecast(insp["forecast"]),
                "storage_temp_c": self.items[item_id].temp_c, "routing_for_open_lines": self._routings(item_id)}

    def look_closer(self, item_id: str, azimuth: float) -> dict:
        if item_id not in self.items:
            return self._refuse("look_closer", f"no item {item_id}")
        try:
            look = self.inspectors.look(self.items[item_id], float(azimuth))
        except ValueError as err:
            return self._refuse("look_closer", str(err), item_id=item_id)
        self.state[item_id].extra_looks.append(look)
        return {"ok": True, "item_id": item_id, **look}

    def ask_person(self, item_id: str, kind: str, question: str) -> dict:
        if item_id not in self.items:
            return self._refuse("ask_person", f"no item {item_id}")
        st = self.state[item_id]
        evidence = {"inspection": None if st.inspection is None else
                    {k: v for k, v in st.inspection.items() if k != "forecast"} | {"forecast": _forecast(st.inspection["forecast"])},
                    "extra_looks": st.extra_looks}
        try:
            req = self.queue.ask(item_id, kind, question, evidence)
        except ValueError as err:
            return self._refuse("ask_person", str(err))
        self.trace.log("ask_person", request=req.id, item_id=item_id, request_kind=kind, question=question)
        if self.reviewer is not None:
            item = self.items[item_id]
            eat = next((ln.eat_in_days for ln in self.order if ln.produce == item.produce and ln.open), None)
            verdict = self.reviewer.review(req, item.ok_to_pack(eat))
            if verdict is None:  # a person did not answer in time: the question stays pending
                self.trace.log("no_answer", request=req.id)
            else:
                approved, answer = verdict
                self.queue.answer(req.id, approved, answer, by=self.reviewer.name)
                self.trace.log("answer", request=req.id, approved=approved, answer=answer, by=self.reviewer.name)
        return {"ok": True, "request_id": req.id, "status": req.status, "answer": req.answer or None, "by": req.by or None}

    def place(self, item_id: str, destination: str, order_line: int | None = None, reason: str = "") -> dict:
        if item_id not in self.items:
            return self._refuse("place", f"no item {item_id}")
        if destination not in DESTINATIONS:
            return self._refuse("place", f"destination must be one of {DESTINATIONS}")
        st, item = self.state[item_id], self.items[item_id]
        if st.location != "crate":
            return self._refuse("place", f"{item_id} has already been placed ({st.location})")
        if destination != "crate" and st.inspection is None:
            return self._refuse("place", "inspect the item before placing it", item_id=item_id)
        insp = st.inspection
        if destination == "order":
            ln = self._line(order_line)
            if ln is None or not ln.open or ln.produce != item.produce:
                return self._refuse("place", f"order line {order_line} is not an open line for {item.produce}", item_id=item_id)
            if insp["verdict"] == "defective":
                return self._refuse("place", "a defective item never goes into an order", item_id=item_id)
            r = self._route(insp, ln.eat_in_days)
            if r.action != "pack" and not self.queue.approved(item_id, "pack"):
                return self._refuse("place", f"not packable without a person's approval: {r.reason}", item_id=item_id)
            ln.packed.append(item_id)
            st.location = f"order line {ln.line}"
        elif destination == "reject":
            if insp["verdict"] != "defective" and not self.queue.approved(item_id, "reject"):
                return self._refuse("place", "the item looks sound; discarding it needs a person's approval", item_id=item_id)
            st.location = "reject bin"
        elif destination == "sell_today":
            f = insp["forecast"]
            if not (f is not None and f.high < 1.0) and not self.queue.approved(item_id, "question"):
                return self._refuse("place", "sell-today needs a forecast under a day or a person's say-so", item_id=item_id)
            st.location = "sell today"
        self.actuator.move(item_id, destination)
        self.trace.log("action", item_id=item_id, destination=destination, order_line=order_line, reason=reason)
        return {"ok": True, "item_id": item_id, "now": st.location}

    def _unexplored(self) -> list[str]:
        """Why a short line is not yet allowed to stay short."""
        reasons = []
        asked = {r.item_id for r in self.queue.requests}
        for ln in self.order:
            if not ln.open:
                continue
            for item_id, item in self.items.items():
                st = self.state[item_id]
                if item.produce != ln.produce or st.location != "crate":
                    continue
                if st.inspection is None:
                    reasons.append(f"line {ln.line} is short but {item_id} ({item.produce}) has not been inspected")
                elif item_id not in asked and any(r["line"] == ln.line and r["action"] == "ask" for r in self._routings(item_id)):
                    reasons.append(f"line {ln.line} is short but {item_id}'s routing for it is 'ask' and no person was asked")
        return reasons

    def finish(self, summary: str) -> dict:
        blockers = self._unexplored()
        if blockers:
            return self._refuse("finish", "not yet: " + "; ".join(blockers))
        self.finished, self.summary = True, summary
        return {"ok": True, "order": [{"line": ln.line, "produce": ln.produce, "packed": ln.packed,
                                       "short_by": ln.quantity - len(ln.packed)} for ln in self.order],
                "pending_requests": [r.id for r in self.queue.pending]}

    # ---- scoring (uses hidden truth; never shown to the agent) -------------
    def score(self) -> dict:
        packed_ok = packed_bad = 0
        for ln in self.order:
            for item_id in ln.packed:
                if self.items[item_id].ok_to_pack(ln.eat_in_days):
                    packed_ok += 1
                else:
                    packed_bad += 1
        wasted = sum(1 for i, st in self.state.items() if st.location == "reject bin" and not self.items[i].truth.get("defective"))
        return {
            "lines_filled": sum(1 for ln in self.order if not ln.open), "lines": len(self.order),
            "packed_ok": packed_ok, "packed_bad": packed_bad, "wasted_sound_items": wasted,
            "inspected": sum(1 for st in self.state.values() if st.inspection is not None),
            "views": sum((st.inspection or {}).get("side_views") or 0 for st in self.state.values())
                     + sum(len(st.extra_looks) for st in self.state.values()),
            "person_requests": len(self.queue.requests),
            "refused_moves": len(self.trace.of_kind("guardrail")),
            "unusable_photos": sum((st.inspection or {}).get("unusable_photos") or 0 for st in self.state.values())
                               + sum(1 for st in self.state.values() for lk in st.extra_looks if lk.get("problem")),
        }
