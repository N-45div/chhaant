import pytest

from chhaant.agent.approval import SimulatedReviewer
from chhaant.agent.cell import Cell, canonical_produce
from chhaant.agent.crate import CrateItem
from chhaant.decide.forecast import Forecast


class FakeInspectors:
    def __init__(self, results):
        self.results = results

    def inspect(self, item):
        return self.results[item.item_id]

    def look(self, item, azimuth):
        if item.kind != "tr6":
            raise ValueError("only 16-angle items can be turned to a chosen angle")
        return {"azimuth": azimuth, "defect": 0.9, "ripeness": 0.5, "photo": "tr6:x.jpg"}


def inspection(verdict, forecast=None):
    return {"capability": "test", "verdict": verdict, "reason": "test", "defect_score": 0.1, "ripeness": 0.5,
            "coverage": 0.6, "unseen_share": 0.4, "side_views": 4, "forecast": forecast, "looks": []}


@pytest.fixture
def cell():
    items = [
        CrateItem("T1", "Tomato", "tr6", 30.0, truth={"defective": False, "days_left": None}),
        CrateItem("T2", "Tomato", "tr6", 30.0, truth={"defective": True, "days_left": None}),
        CrateItem("T3", "Tomato", "tr6", 30.0, truth={"defective": False, "days_left": None}),
        CrateItem("A1", "Avocado", "avocado", 20.0, truth={"defective": False, "days_left": 5.0}),
        CrateItem("A2", "Avocado", "avocado", 20.0, truth={"defective": False, "days_left": 0.0}),
    ]
    results = {"T1": inspection("clean"), "T2": inspection("defective"), "T3": inspection("escalate"),
               "A1": inspection("clean", Forecast(4.5, 3.5, 5.6)), "A2": inspection("clean", Forecast(0.3, 0.1, 0.7))}
    c = Cell(items, FakeInspectors(results))
    c.read_order([{"produce": "tomato", "quantity": 1, "eat_in_days": None},
                  {"produce": "Avocado", "quantity": 1, "eat_in_days": 3}])
    return c


def test_nothing_is_placed_before_inspection(cell):
    r = cell.place("T1", "order", 1)
    assert not r["ok"] and "inspect" in r["error"]
    assert cell.trace.of_kind("guardrail")


def test_clean_item_packs_into_a_quality_only_line(cell):
    cell.inspect("T1")
    assert cell.place("T1", "order", 1)["ok"]
    assert cell.score()["packed_ok"] == 1


def test_defective_item_never_goes_into_an_order_even_with_approval(cell):
    cell.inspect("T2")
    cell.queue.answer(cell.queue.ask("T2", "pack", "pack anyway?", {}).id, True, "yes", by="test")
    r = cell.place("T2", "order", 1)
    assert not r["ok"] and "never" in r["error"]
    assert cell.place("T2", "reject")["ok"]


def test_undecided_item_needs_a_person_before_packing(cell):
    cell.inspect("T3")
    assert not cell.place("T3", "order", 1)["ok"]
    answer = cell.ask_person("T3", "pack", "Inspection undecided. Pack it?")
    assert answer["status"] == "pending"  # no reviewer attached: it waits for a real person
    assert not cell.place("T3", "order", 1)["ok"]


def test_simulated_reviewer_answers_from_the_truth():
    items = [CrateItem("T3", "Tomato", "tr6", 30.0, truth={"defective": False, "days_left": None})]
    c = Cell(items, FakeInspectors({"T3": inspection("escalate")}), reviewer=SimulatedReviewer())
    c.read_order([{"produce": "Tomato", "quantity": 1, "eat_in_days": None}])
    c.inspect("T3")
    ans = c.ask_person("T3", "pack", "Pack it?")
    assert ans["status"] == "approved" and ans["by"] == "simulated reviewer"
    assert c.place("T3", "order", 1)["ok"]


def test_firm_avocado_is_packed_for_later_and_ripe_one_sold_today(cell):
    a1 = cell.inspect("A1")
    assert a1["routing_for_open_lines"][0]["action"] == "pack"
    assert cell.place("A1", "order", 2)["ok"]
    cell.inspect("A2")
    assert not cell.place("A2", "reject")["ok"]  # sound: discarding needs a person
    assert cell.place("A2", "sell_today")["ok"]


def test_items_cannot_be_placed_twice(cell):
    cell.inspect("T1")
    cell.place("T1", "order", 1)
    assert not cell.place("T1", "reject")["ok"]


def test_order_lines_are_validated(cell):
    assert not cell.read_order([{"produce": "Tomato", "quantity": 0}])["ok"]
    assert not cell.read_order([{"produce": "Tomato", "quantity": 2, "eat_in_days": -1}])["ok"]


def test_order_produce_uses_the_crates_names(cell):
    # Live run 20261014-194352: the model wrote "avocados", every placement was refused.
    out = cell.read_order([{"produce": "avocados", "quantity": 1, "eat_in_days": 0.5},
                           {"produce": "TOMATOES", "quantity": 1, "eat_in_days": None},
                           {"produce": "amla", "quantity": 1, "eat_in_days": None}])
    assert [r["produce"] for r in out["order"]] == ["Avocado", "Tomato", "Indian_Gooseberry"]
    assert [r["in_crate"] for r in out["order"]] == [2, 3, 0]
    assert "note" not in out["order"][0] and "holds Avocado, Tomato" in out["order"][2]["note"]
    cell.inspect("T1")
    placed = cell.place("T1", "order", 2, "clean tomato")  # the line was asked for as "TOMATOES"
    assert placed["ok"], placed


@pytest.mark.parametrize("name,expected", [("Avocado", "Avocado"), ("avocados", "Avocado"), ("tomatoes", "Tomato"),
                                           ("Indian gooseberry", "Indian_Gooseberry"), ("mangoes", "Mango"),
                                           ("bananas", "Banana"), ("apples", None), ("s", None)])
def test_canonical_produce(name, expected):
    known = {"Avocado", "Tomato", "Indian_Gooseberry", "Mango", "Banana"}
    assert canonical_produce(name, known) == expected


def test_look_closer_only_for_turntable_items(cell):
    assert cell.look_closer("T1", 90)["ok"]
    assert not cell.look_closer("A1", 90)["ok"]


def test_finish_reports_each_line_once_everything_is_explored(cell):
    for item_id in ("T1", "T2", "T3", "A1", "A2"):
        cell.inspect(item_id)
    cell.place("T1", "order", 1)
    cell.place("A1", "order", 2)
    out = cell.finish("done")
    assert out["ok"] and cell.finished
    assert [ln["short_by"] for ln in out["order"]] == [0, 0]


def test_cannot_finish_short_while_a_candidate_is_untried(cell):
    r = cell.finish("done")
    assert not r["ok"] and "not been inspected" in r["error"] and not cell.finished


def test_cannot_finish_short_without_asking_about_an_ask_item():
    items = [CrateItem("A1", "Avocado", "avocado", 20.0, truth={"defective": False, "days_left": 2.0})]
    c = Cell(items, FakeInspectors({"A1": inspection("clean", Forecast(0.6, 0.2, 1.3))}))
    c.read_order([{"produce": "Avocado", "quantity": 1, "eat_in_days": 0.5}])
    c.inspect("A1")
    r = c.finish("short, nothing suitable")
    assert not r["ok"] and "no person was asked" in r["error"]
    c.ask_person("A1", "pack", "Pack for tonight?")
    assert c.finish("short; asked about A1, waiting")["ok"]


def two_avocado_lines():
    items = [CrateItem("A1", "Avocado", "avocado", 20.0, truth={"defective": False, "days_left": 5.0})]
    c = Cell(items, FakeInspectors({"A1": inspection("clean", Forecast(5.0, 3.6, 6.4))}), reviewer=SimulatedReviewer())
    c.read_order([{"produce": "avocado", "quantity": 1, "eat_in_days": 0.5},
                  {"produce": "avocado", "quantity": 1, "eat_in_days": 4}])
    c.inspect("A1")
    return c


def test_a_pack_question_is_about_the_line_whose_routing_asked():
    # Too firm for tonight (skip), maybe right for day 4 (ask): the question is about line 2,
    # and the reviewer judges line 2. Before, it was judged against tonight and declined.
    c = two_avocado_lines()
    out = c.ask_person("A1", "pack", "Can A1 go into the day-4 line?")
    assert out["order_line"] == 2 and out["status"] == "approved"


def test_an_approval_covers_only_its_own_line():
    c = two_avocado_lines()
    c.ask_person("A1", "pack", "Can A1 go into the day-4 line?", order_line=2)
    assert not c.place("A1", "order", 1, "tonight")["ok"]  # approved for line 2, not tonight
    assert c.place("A1", "order", 2, "day 4")["ok"]


def test_a_pack_question_needs_an_open_line_for_that_produce():
    c = two_avocado_lines()
    assert not c.ask_person("A1", "pack", "?", order_line=7)["ok"]


def test_the_cell_counts_days_to_a_named_day():
    from datetime import date
    from chhaant.agent.cell import days_until
    thursday = date(2026, 10, 15)
    got = {d: days_until(d, thursday) for d in ("Saturday", "monday", "next Wednesday", "Thursday", "next Thursday",
                                                "Sat", "tomorrow", "tonight", "today", "for today", "for next Thursday",
                                                "someday")}
    assert got == {"Saturday": 2, "monday": 4, "next Wednesday": 6, "Thursday": 0.5, "next Thursday": 7, "Sat": 2,
                   "tomorrow": 1, "tonight": 0.5, "today": 0.5, "for today": 0.5, "for next Thursday": 7,
                   "someday": None}  # a live run on a Saturday read "Saturday" as 7; Nova read "for today" as 1


def test_read_order_turns_a_named_day_into_days(cell):
    from datetime import date
    cell.today = date(2026, 10, 15)  # Thursday; Haiku had read "Monday" as 3 days
    out = cell.read_order([{"produce": "avocado", "quantity": 2, "eat_in_days": None, "eat_on": "Monday"}])
    assert out["ok"] and out["order"][0]["eat_in_days"] == 4.0
    assert not cell.read_order([{"produce": "avocado", "quantity": 1, "eat_in_days": None, "eat_on": "soon"}])["ok"]


def test_finish_will_not_call_a_short_order_complete(cell):
    for item_id in ("T1", "T2", "T3", "A1", "A2"):
        cell.inspect(item_id)
    cell.place("T1", "order", 1)  # line 2 (avocado) stays short
    r = cell.finish("Order complete: one tomato packed.")
    assert not r["ok"] and "short by 1" in r["error"] and not cell.finished
    assert cell.finish("Order incomplete: line 2 is short by one avocado.")["ok"]


def test_verdicts_are_acted_on_alone_only_where_validated():
    from chhaant.agent.inspectors import gate, load_validation
    v = load_validation()
    assert gate("Tomato", "clean", "nothing seen", v)[0] == "escalate"  # missed 10 of 10 spoiled
    assert "missed 10 of 10 spoiled" in gate("Tomato", "clean", "nothing seen", v)[1]
    assert gate("Tomato", "defective", "spot", v) == ("defective", "spot")  # rejected 0 of 122 fresh
    assert gate("Banana", "defective", "spot", v)[0] == "escalate"  # rejected 9 of 9 fresh
    assert gate("Guava", "clean", "nothing seen", v) == ("clean", "nothing seen")  # missed 0 of 18
    assert gate("Dragon_Fruit", "clean", "nothing seen", v)[0] == "escalate"  # never validated
    assert gate("Mango", "escalate", "undecided", v) == ("escalate", "undecided")


def test_cannot_finish_short_with_an_approved_item_left_in_the_crate():
    # Found in iteration 2: a person said "fine to pack" and the item was never placed.
    c = two_avocado_lines()
    c.ask_person("A1", "pack", "Can A1 go into the day-4 line?", order_line=2)
    r = c.finish("Line 2 is short.")
    assert not r["ok"] and "approved A1 for it: place it there" in r["error"]
    assert c.place("A1", "order", 2, "approved")["ok"]


def test_a_question_about_one_line_does_not_clear_another():
    items = [CrateItem("A1", "Avocado", "avocado", 20.0, truth={"defective": False, "days_left": 3.0})]
    c = Cell(items, FakeInspectors({"A1": inspection("clean", Forecast(3.0, 1.0, 5.0))}), reviewer=SimulatedReviewer())
    c.read_order([{"produce": "avocado", "quantity": 1, "eat_in_days": 0.5},
                  {"produce": "avocado", "quantity": 1, "eat_in_days": 2}])
    c.inspect("A1")  # "ask" for both lines
    c.ask_person("A1", "pack", "For tonight?", order_line=1)  # asked about line 1 only
    r = c.finish("Both lines short.")
    assert not r["ok"] and "no person was asked about this line" in r["error"]


def test_one_review_covers_several_items_each_judged_on_its_own():
    c = Cell([CrateItem("T1", "Tomato", "tr6", 30.0, truth={"defective": False}),
              CrateItem("T2", "Tomato", "tr6", 30.0, truth={"defective": True}),
              CrateItem("T3", "Tomato", "tr6", 30.0, truth={"defective": False})],
             FakeInspectors({i: inspection("escalate") for i in ("T1", "T2", "T3")}), reviewer=SimulatedReviewer())
    c.read_order([{"produce": "tomato", "quantity": 2, "eat_in_days": None}])
    for i in ("T1", "T2", "T3"):
        c.inspect(i)
    out = c.ask_person(None, "pack", "Pack these tomatoes for line 1?", order_line=1, item_ids=["T1", "T2", "T3"])
    assert out["ok"] and out["batch"] == "B1"
    assert {a["item_id"]: a["status"] for a in out["answers"]} == {"T1": "approved", "T2": "declined", "T3": "approved"}
    assert not c.place("T2", "order", 1)["ok"]  # declined in the batch: still refused
    assert c.place("T1", "order", 1)["ok"] and c.place("T3", "order", 1)["ok"]
    s = c.score()
    assert s["person_requests"] == 3 and s["person_reviews"] == 1


def test_a_batch_with_an_unknown_item_is_refused_whole():
    c = two_avocado_lines()
    assert not c.ask_person(None, "pack", "?", order_line=2, item_ids=["A1", "A9"])["ok"]
    assert c.queue.requests == []


def test_an_escalated_item_says_why_a_person_decides():
    from chhaant.agent.inspectors import gate, load_validation
    verdict, reason = gate("Tomato", "clean", "57% inspected, nothing agreed on", load_validation())
    c = Cell([CrateItem("T1", "Tomato", "tr6", 30.0, truth={"defective": False})],
             FakeInspectors({"T1": dict(inspection(verdict), reason=reason)}))
    c.read_order([{"produce": "tomato", "quantity": 1, "eat_in_days": None}])
    r = c.inspect("T1")["routing_for_open_lines"][0]
    assert r["action"] == "ask" and r["reason"].startswith("A person confirms: for tomato this inspection missed")


def test_a_yes_to_a_general_question_does_not_mark_an_item_down(cell):
    # Found by an outside agent over MCP: "Can A2 work for tonight?" answered yes let A1 go to sell-today.
    cell.inspect("A1")
    cell.queue.answer(cell.queue.ask("A1", "question", "Can A2 work for tonight? A1 seems firm.", {}).id, True, "yes", by="test")
    r = cell.place("A1", "sell_today")
    assert not r["ok"] and "sell_today" in r["error"]
    cell.queue.answer(cell.queue.ask("A1", "sell_today", "Mark A1 down for today?", {}).id, True, "yes", by="test")
    assert cell.place("A1", "sell_today")["ok"]
    assert cell.score()["sold_early"] == 1  # 5 true days left: it could have waited for another order


def test_the_simulated_reviewer_is_asked_with_the_days_left():
    items = [CrateItem("A1", "Avocado", "avocado", 20.0, truth={"defective": False, "days_left": 6.0})]
    c = Cell(items, FakeInspectors({"A1": inspection("clean", Forecast(4.5, 3.1, 6.8))}), reviewer=SimulatedReviewer())
    c.read_order([{"produce": "Avocado", "quantity": 1, "eat_in_days": 0.5}])
    c.inspect("A1")
    assert c.ask_person("A1", "sell_today", "Too firm for tonight; sell it today?")["status"] == "declined"
    assert not c.place("A1", "sell_today")["ok"]
