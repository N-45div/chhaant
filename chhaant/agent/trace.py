"""The decision trace: one JSON line per event, written as it happens.

Every model message, tool call, tool result, refused move and person's answer
is recorded with a timestamp, so any packed or rejected item can be traced
back to the photos and readings that caused it.
"""

import json
import os
import time
from datetime import datetime, timezone


class Trace:
    def __init__(self, path: str | None = None):
        self.path = path
        self.events: list[dict] = []
        self._t0 = time.perf_counter()
        if path:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            open(path, "w").close()

    def log(self, kind: str, **data) -> dict:
        event = {"t": round(time.perf_counter() - self._t0, 3),
                 "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "kind": kind, **data}
        self.events.append(event)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, default=str) + "\n")
        return event

    def of_kind(self, kind: str) -> list[dict]:
        return [e for e in self.events if e["kind"] == kind]
