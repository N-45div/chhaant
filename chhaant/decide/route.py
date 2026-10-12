"""What the robot does with an inspected item, given when the order will be eaten.

An order says when the food will be eaten ("tonight" = 0.5 days, "Thursday" =
3 days). The inspection verdict says whether the item is sound; the shelf-life
forecast says how long it stays good, with an interval. Together:

* defective                          -> reject
* undecided inspection               -> a person decides
* sound but good for under a day     -> sell today (too ripe to hold for anyone later)
* sound and surely good until eaten  -> pack for this order
* sound but gone before it is eaten  -> skip for this order (keep it for a sooner one)
* the interval straddles that day    -> a person decides
* an order line with no eat-by date   -> sound items are packed (quality only)

A clean inspection alone never packs an item: an over-ripe mango with no
visible defect is clean, but it should not go into Thursday's order.
"""

from dataclasses import dataclass

from chhaant.decide.forecast import Forecast

SELL_TODAY_DAYS = 1.0


@dataclass
class Routing:
    action: str   # "pack", "reject", "sell_today", "skip", "ask"
    reason: str


def route(decision: str, forecast: Forecast | None, eat_in_days: float | None) -> Routing:
    if decision == "defective":
        return Routing("reject", "inspection found a defect")
    if decision == "escalate":
        return Routing("ask", "inspection could not decide")
    if eat_in_days is None and (forecast is None or forecast.high >= SELL_TODAY_DAYS):
        return Routing("pack", "sound, and this order line has no eat-by date")
    if forecast is None:
        return Routing("ask", "sound, but no shelf-life forecast for this produce")
    window = f"forecast {forecast.days:.1f} days ({forecast.low:.1f}-{forecast.high:.1f})"
    if forecast.high < SELL_TODAY_DAYS:
        return Routing("sell_today", f"sound but past its best within a day; {window}")
    if forecast.low >= eat_in_days:
        return Routing("pack", f"stays good past the {eat_in_days:g}-day mark; {window}")
    if forecast.high < eat_in_days:
        return Routing("skip", f"will be past its best before it is eaten in {eat_in_days:g} days; {window}")
    return Routing("ask", f"may not last {eat_in_days:g} days; {window}")
