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

import re
from dataclasses import dataclass, field
from datetime import date

from chhaant.agent.approval import ApprovalQueue
from chhaant.agent.trace import Trace
from chhaant.decide.route import RIPE_WINDOW_DAYS, Routing, route

DESTINATIONS = ("order", "reject", "sell_today", "crate")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def days_until(day: str, today: date) -> float | None:
    """'Saturday', 'next Wednesday', 'tomorrow', 'tonight' -> days from today; None if not a named day.

    A weekday means the coming one (1-6 days ahead), and today's own weekday means
    today, as a shopper means "for Saturday" on a Saturday; "next" pushes today's
    weekday to a week out (a live run read "Saturday" on a Saturday as 7 days).
    """
    key = re.sub(r"[^a-z ]", "", str(day).lower()).strip()
    is_next = key.startswith("next ")
    key = re.sub(r"^(this|next|on|coming|the)\s+", "", key).strip()
    if key in ("tonight", "today", "this evening"):
        return 0.5
    if key == "tomorrow":
        return 1.0
    match = [d for d in WEEKDAYS if len(key) >= 3 and (d.startswith(key) or key.rstrip("s") == d)]
    if len(match) == 1:  # "sat", "saturday", "saturdays"
        ahead = (WEEKDAYS.index(match[0]) - today.weekday()) % 7
        return float(ahead) if ahead else (7.0 if is_next else 0.5)
    return None


def claims_complete(summary: str) -> bool:
    """Does a summary call the order done ("Order complete", "all complete")?"""
    return bool(re.search(r"\b(order|all)\b[^.]{0,40}\bcomplete\b", summary, re.I)) and not re.search(
        r"\b(in|not )complete\b", summary, re.I)


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
        self.today: date | None = None  # set by the agent loop; named days in the order count from it
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
        r = route(insp["verdict"], insp["forecast"], eat_in_days, window)
        if insp["verdict"] == "escalate":  # say why a person decides, not just that the inspection did not
            gated = re.search(r"A person confirms[^.]*", insp.get("reason", ""))
            r = Routing("ask", gated.group(0) if gated else f"inspection could not decide: {insp.get('reason', '')}")
        return r

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
            if ln.get("eat_on"):  # a named day: the cell counts, not the model
                eat = days_until(ln["eat_on"], self.today or date.today())
                if eat is None:
                    return self._refuse("read_order", f"line {n}: eat_on {ln['eat_on']!r} is not a day the cell knows "
                                        "(use a weekday, 'tomorrow' or 'tonight'), or give eat_in_days instead")
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
                **({"vision_verdict": insp["vision_verdict"]} if insp.get("vision_verdict") not in (None, insp["verdict"]) else {}),
                "defect_score": insp.get("defect_score"), "ripeness": insp.get("ripeness"),
                "coverage": insp.get("coverage"), "unseen_share": insp.get("unseen_share"),
                "views_used": insp.get("side_views"), "unusable_photos": insp.get("unusable_photos", 0),
                "forecast_days_left": _forecast(insp["forecast"]),
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

    def _pack_line(self, item_id: str, order_line: int | None) -> OrderLine | None:
        """The line a pack question is about: the one named, else the open line whose routing said "ask"."""
        item = self.items[item_id]
        if order_line is not None:
            return self._line(order_line)
        open_lines = [ln for ln in self.order if ln.produce == item.produce and ln.open]
        asks = [ln for ln in open_lines if any(r["line"] == ln.line and r["action"] == "ask" for r in self._routings(item_id))]
        return (asks or open_lines or [None])[0]

    def ask_person(self, item_id: str | None, kind: str, question: str, order_line: int | None = None,
                   item_ids: list[str] | None = None) -> dict:
        """One question, or one review of several items (``item_ids``): all shown at once, answered item by item."""
        ids = list(dict.fromkeys(item_ids or ([item_id] if item_id else [])))
        if not ids:
            return self._refuse("ask_person", "name the item (item_id) or items (item_ids) to ask about")
        lines = {}
        for i in ids:
            if i not in self.items:
                return self._refuse("ask_person", f"no item {i}")
            lines[i] = None
            if kind == "pack":
                line = self._pack_line(i, order_line)
                if line is None or line.produce != self.items[i].produce or not line.open:
                    return self._refuse("ask_person", f"a pack question needs an open order line for {self.items[i].produce}"
                                        + (f"; line {order_line} is not one" if order_line is not None else ""), item_id=i)
                lines[i] = line
        batch = self.queue.new_batch() if len(ids) > 1 else None
        reqs = []
        for i in ids:
            st, line = self.state[i], lines[i]
            evidence = {"inspection": None if st.inspection is None else
                        {k: v for k, v in st.inspection.items() if k != "forecast"} | {"forecast": _forecast(st.inspection["forecast"])},
                        "extra_looks": st.extra_looks}
            if line is not None:
                evidence["order_line"] = {"line": line.line, "produce": line.produce, "eat_in_days": line.eat_in_days}
            try:
                req = self.queue.ask(i, kind, question, evidence, order_line=line.line if line else None, batch=batch)
            except ValueError as err:
                return self._refuse("ask_person", str(err))
            self.trace.log("ask_person", request=req.id, item_id=i, request_kind=kind, question=question,
                           order_line=req.order_line, eat_in_days=line.eat_in_days if line else None,
                           **({"batch": batch, "batch_size": len(ids)} if batch else {}))
            reqs.append(req)
        if self.reviewer is not None:
            truths = []
            for req in reqs:  # the simulated reviewer judges each item against its own line
                item, line = self.items[req.item_id], lines[req.item_id]
                if line is None:  # not a pack question: the item's most pressing open line
                    line = next((ln for ln in self.order if ln.produce == item.produce and ln.open), None)
                truths.append((item.ok_to_pack(line.eat_in_days if line else None), bool(item.truth.get("defective"))))
            for req, verdict in zip(reqs, self.reviewer.review_many(reqs, truths)):
                if verdict is None:  # a person did not answer in time: the question stays pending
                    self.trace.log("no_answer", request=req.id)
                else:
                    approved, answer = verdict
                    self.queue.answer(req.id, approved, answer, by=self.reviewer.name)
                    self.trace.log("answer", request=req.id, approved=approved, answer=answer, by=self.reviewer.name)
        answers = [{"item_id": r.item_id, "request_id": r.id, "status": r.status, "answer": r.answer or None,
                    "by": r.by or None, **({"order_line": r.order_line} if r.order_line is not None else {})} for r in reqs]
        if batch is None:
            return {"ok": True, **answers[0]}
        return {"ok": True, "batch": batch, "answers": answers}

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
            if r.action != "pack" and not self.queue.approved(item_id, "pack", ln.line):
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
        # A pack question is about one line; any other kind of question covers the item as a whole.
        asked = {(r.item_id, r.order_line if r.kind == "pack" else None) for r in self.queue.requests}
        for ln in self.order:
            if not ln.open:
                continue
            for item_id, item in self.items.items():
                st = self.state[item_id]
                if item.produce != ln.produce or st.location != "crate":
                    continue
                if st.inspection is None:
                    reasons.append(f"line {ln.line} is short but {item_id} ({item.produce}) has not been inspected")
                elif self.queue.approved(item_id, "pack", ln.line):
                    reasons.append(f"line {ln.line} is short but a person approved {item_id} for it: place it there")
                elif ((item_id, ln.line) not in asked and (item_id, None) not in asked
                      and any(r["line"] == ln.line and r["action"] == "ask" for r in self._routings(item_id))):
                    reasons.append(f"line {ln.line} is short but {item_id}'s routing for it is 'ask' and no person "
                                   "was asked about this line")
        return reasons

    def finish(self, summary: str) -> dict:
        blockers = self._unexplored()
        if blockers:
            return self._refuse("finish", "not yet: " + "; ".join(blockers))
        short = [f"line {ln.line} is short by {ln.quantity - len(ln.packed)}" for ln in self.order if ln.open]
        if short and claims_complete(summary):
            return self._refuse("finish", "the summary calls the order complete, but " + "; ".join(short)
                                + ". Say which lines are short.")
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
            "person_reviews": self.queue.reviews,  # interruptions: a batch counts once
            "refused_moves": len(self.trace.of_kind("guardrail")),
            "unusable_photos": sum((st.inspection or {}).get("unusable_photos") or 0 for st in self.state.values())
                               + sum(1 for st in self.state.values() for lk in st.extra_looks if lk.get("problem")),
        }
