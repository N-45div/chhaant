"""The tools the language model sees, and a dispatcher that never lets a tool crash the run."""

TOOLS = [
    {"name": "read_order",
     "description": ("Record your reading of the customer's order as lines. Call this first. "
                     "eat_in_days is when the item will be eaten (0.5 = tonight, 3 = in three days); "
                     "use null when the customer gave no timing."),
     "schema": {"type": "object", "properties": {"lines": {"type": "array", "items": {
         "type": "object",
         "properties": {"produce": {"type": "string"}, "quantity": {"type": "integer", "minimum": 1},
                        "eat_in_days": {"type": ["number", "null"]}},
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
                     "routing does not clear; 'reject' asks permission to discard an item that looks sound; "
                     "'question' for anything else. The answer may be pending."),
     "schema": {"type": "object", "properties": {
         "item_id": {"type": "string"}, "kind": {"type": "string", "enum": ["pack", "reject", "question"]},
         "question": {"type": "string"}}, "required": ["item_id", "kind", "question"]}},
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


def call(cell, name: str, args: dict) -> dict:
    """Run one tool. Unknown tools and bad arguments come back as errors the model can read."""
    if name not in NAMES:
        return {"ok": False, "error": f"unknown tool {name}"}
    try:
        if name == "read_order":
            return cell.read_order(args.get("lines") or [])
        if name == "list_crate":
            return cell.list_crate()
        if name == "inspect":
            return cell.inspect(str(args["item_id"]))
        if name == "look_closer":
            return cell.look_closer(str(args["item_id"]), float(args["azimuth"]))
        if name == "ask_person":
            return cell.ask_person(str(args["item_id"]), str(args["kind"]), str(args.get("question", "")))
        if name == "place":
            line = args.get("order_line")
            return cell.place(str(args["item_id"]), str(args["destination"]),
                              None if line is None else int(line), str(args.get("reason", "")))
        return cell.finish(str(args.get("summary", "")))
    except (KeyError, TypeError, ValueError) as err:
        return {"ok": False, "error": f"bad arguments for {name}: {err}"}
