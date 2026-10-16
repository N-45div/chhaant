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
               "A1": inspection("clean", Forecast(5.0, 3.6, 6.4)), "A2": inspection("clean", Forecast(0.3, 0.1, 0.7))}
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
