"""The tools the language model sees, and a dispatcher that never lets a tool crash the run."""

TOOLS = [
    {"name": "read_order",
     "description": ("Record your reading of the customer's order as lines. Call this first. "
                     "When the customer says when in words ('today', 'tonight', 'tomorrow', 'Saturday', 'next "
                     "Wednesday'), put those words in eat_on and leave eat_in_days null: the cell counts the days. "
                     "Use eat_in_days only for a number of days ('in three days' = 3). Leave both null when the "
                     "customer gave no timing for that item, and never assume one."),
     "schema": {"type": "object", "properties": {"lines": {"type": "array", "items": {
         "type": "object",
         "properties": {"produce": {"type": "string"}, "quantity": {"type": "integer", "minimum": 1},
                        "eat_in_days": {"type": ["number", "null"]}, "eat_on": {"type": ["string", "null"]}},
         "required": ["produce", "quantity", "eat_in_days"]}}}, "required": ["lines"]}},
    {"name": "list_crate",
     "description": "List the items in the crate with their produce type, where each one is now, and any verdict so far.",
     "schema": {"type": "object", "properties": {}}},
    {"name": "inspect",
     "description": ("Inspect one item with the cell's camera and OpenCV 5 vision. Returns the verdict "
                     "(clean, defective or escalate), what was measured and from how many views, any shelf-life "
                     "forecast, and the routing for each open order line it could fill. Inspect before placing."),
     "schema": {"type": "object", "properties": {"item_id": {"type": "string"}}, "required": ["item_id"]}},
    {"name": "look_closer",
     "description": ("Turn a 16-angle item to a chosen angle (0-360 degrees) and read defect and ripeness there. "
                     "Use it to check a suspicion before deciding."),
     "schema": {"type": "object", "properties": {"item_id": {"type": "string"}, "azimuth": {"type": "number"}},
                "required": ["item_id", "azimuth"]}},
    {"name": "ask_person",
     "description": ("Ask a person to decide instead of guessing. kind 'pack' asks permission to pack an item its "
                     "routing does not clear into one order line (give order_line; the approval covers that line "
                     "only); 'reject' asks permission to discard an item that looks sound; 'sell_today' asks "
                     "permission to mark a sound item down for sale today when its forecast is not already under a "
                     "day; 'question' for anything else (a yes to a question permits no move). To put several items "
                     "to the person in one review, pass item_ids instead of item_id: they see all of them at once "
                     "and answer each. The answers may be pending."),
     "schema": {"type": "object", "properties": {
         "item_id": {"type": "string"}, "item_ids": {"type": "array", "items": {"type": "string"}},
         "kind": {"type": "string", "enum": ["pack", "reject", "sell_today", "question"]},
         "question": {"type": "string"}, "order_line": {"type": ["integer", "null"]}},
                "required": ["kind", "question"]}},
    {"name": "place",
     "description": ("Move an item: 'order' (give order_line), 'reject', 'sell_today', or 'crate' (put it back). "
                     "The cell refuses moves its rules do not allow and says why."),
     "schema": {"type": "object", "properties": {
         "item_id": {"type": "string"},
         "destination": {"type": "string", "enum": ["order", "reject", "sell_today", "crate"]},
         "order_line": {"type": ["integer", "null"]}, "reason": {"type": "string"}},
         "required": ["item_id", "destination", "reason"]}},
    {"name": "finish",
     "description": ("End the job with a short summary for the person: what was packed, rejected and sold today, "
                     "which lines are short, and anything waiting for them."),
     "schema": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}},
]

NAMES = {t["name"] for t in TOOLS}
NULLISH = {"", "none", "null"}


def _nullish(v) -> bool:
    """Some models send null as the string "None" (one did, ten times in one run)."""
    return v is None or (isinstance(v, str) and v.strip().lower() in NULLISH)


def _optional_int(v) -> int | None:
    return None if _nullish(v) else int(v)


def _order_lines(lines) -> list:
    out = []
    for ln in lines or []:
        ln = dict(ln)
        if _nullish(ln.get("eat_in_days")):
            ln["eat_in_days"] = None
        elif isinstance(ln.get("eat_in_days"), str):
            ln["eat_in_days"] = float(ln["eat_in_days"])
        if isinstance(ln.get("quantity"), str) and ln["quantity"].strip().isdigit():
            ln["quantity"] = int(ln["quantity"])
        out.append(ln)
    return out


def call(cell, name: str, args: dict) -> dict:
    """Run one tool. Unknown tools and bad arguments come back as errors the model can read."""
    if name not in NAMES:
        return {"ok": False, "error": f"unknown tool {name}"}
    try:
        if name == "read_order":
            return cell.read_order(_order_lines(args.get("lines")))
        if name == "list_crate":
            return cell.list_crate()
        if name == "inspect":
            return cell.inspect(str(args["item_id"]))
        if name == "look_closer":
            return cell.look_closer(str(args["item_id"]), float(args["azimuth"]))
        if name == "ask_person":
            ids = args.get("item_ids")
            if isinstance(ids, str):  # a model may send one id, or a comma list, as a string
                ids = [x.strip() for x in ids.split(",") if x.strip()]
            return cell.ask_person(None if args.get("item_id") is None else str(args["item_id"]), str(args["kind"]),
                                   str(args.get("question", "")), _optional_int(args.get("order_line")),
                                   [str(x) for x in ids] if ids else None)
        if name == "place":
            return cell.place(str(args["item_id"]), str(args["destination"]),
                              _optional_int(args.get("order_line")), str(args.get("reason", "")))
        return cell.finish(str(args.get("summary", "")))
    except (KeyError, TypeError, ValueError) as err:
        return {"ok": False, "error": f"bad arguments for {name}: {err}"}
