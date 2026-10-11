import math

import pytest

from chhaant.decide.lot import Inspector, LotInspection, LotPlan, binom_cdf, fixed_plan


def run(plan, outcomes, by_person=False):
    lot = LotInspection(plan)
    for d in outcomes:
        state = lot.add(d, by_person)
        if lot.done:
            return state
    return lot.state


def test_wald_bounds():
    plan = LotPlan(alpha=0.05, beta=0.05)
    assert plan.reject_bound == pytest.approx(math.log(19))
    assert plan.accept_bound == pytest.approx(-math.log(19))


def test_a_clean_crate_is_accepted_early():
    plan = LotPlan()
    # each clean item adds log(0.80/0.95); 18 of them cross log(1/19)
    expected = math.ceil(plan.accept_bound / plan.step(False, True))
    state = run(plan, [False] * 100, by_person=True)
    assert state.decision == "accept" and state.items == expected == 18


def test_a_bad_crate_is_rejected_after_a_few_defects():
    state = run(LotPlan(), [True, False, True, True, False, True] * 10, by_person=True)
    assert state.decision == "reject" and state.items <= 8


def test_the_cap_stops_an_endless_run():
    plan = LotPlan(max_items=20)
    state = run(plan, [False, False, False, False, False, False, True] * 10, by_person=True)
    assert state.items <= 20 and state.decision in ("accept", "reject")


def test_an_imperfect_inspector_needs_more_items():
    perfect = run(LotPlan(), [False] * 200, by_person=True)
    shaky = run(LotPlan(inspector=Inspector(sensitivity=0.8, specificity=0.9)), [False] * 200)
    assert shaky.decision == perfect.decision == "accept"
    assert shaky.items > perfect.items


def test_useless_inspector_is_refused():
    with pytest.raises(ValueError):
        LotPlan(inspector=Inspector(sensitivity=0.3, specificity=0.6))  # calls defects more on good crates


def test_fixed_plan_meets_both_risks():
    plan = LotPlan()
    n, c = fixed_plan(plan)
    assert binom_cdf(c, n, plan.p0) >= 0.95 and binom_cdf(c, n, plan.p1) <= 0.05
    assert (n, c) == (50, 5)  # the classic matched plan for 5% vs 20% at 5%/5%


def test_no_items_after_the_decision():
    lot = LotInspection(LotPlan())
    for _ in range(18):
        lot.add(False, True)
    with pytest.raises(RuntimeError):
        lot.add(False, True)


def test_hand_offs_alone_carry_no_bias_when_the_robot_is_perfect():
    plan = LotPlan(inspector=Inspector(escalate_defective=0.3, escalate_clean=0.1))
    # a perfect robot on the items it keeps: its verdicts are as informative as a person's
    assert plan.step(True, False) == pytest.approx(plan.step(True, True))
    assert plan.step(False, False) == pytest.approx(math.log((0.8 * 0.9) / (0.95 * 0.9)))


def test_robot_outcomes_account_for_what_was_handed_off():
    insp = Inspector(sensitivity=0.67, specificity=0.92, escalate_defective=0.29, escalate_clean=0.11)
    total = sum(insp.outcome_prob(0.1, d, h) for d in (True, False) for h in (True, False))
    assert total == pytest.approx(1.0)
