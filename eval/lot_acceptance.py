"""Crate acceptance: how many items does the sequential test need, and does it keep its promises?

1. The robot's error rates are MEASURED, not assumed: the rotate-until-sure
   policy's leave-one-fruit-out verdicts on TR-6 (eval/rotate_until_sure.py)
   give, separately for spoiled and fresh items, how often it calls defective,
   calls clean, or hands the item to a person.
2. Simulated crates of 400 items with a known share of defects. Each inspected
   item draws the robot's verdict from those measured rates; hand-offs are
   resolved by a person (the truth).
3. Systems, all targeting a good crate (<= 5% defects) vs a bad one (>= 20%)
   at 5% risk each way:
   * sequential:  Wald's test, capped at the fixed plan's own sample size
   * fixed:       the smallest single-sampling plan (n, c) with the same risks
   both with the measured robot, plus the textbook perfect-inspector pair.

Usage:
    python eval/lot_acceptance.py --scores data/tr6_view_scores.csv
"""

import argparse
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from chhaant.decide.lot import Inspector, LotInspection, LotPlan, fixed_plan  # noqa: E402
import rotate_until_sure as rus  # noqa: E402

LOT_SIZE = 400
TRUE_RATES = (0.0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30)
LOTS_PER_RATE = 2000


def measured_inspector(scores_csv: str) -> dict:
    """Class-conditional verdict rates of the rotate-until-sure policy, pooled leave-one-fruit-out."""
    by_session = {}
    with open(scores_csv) as fh:
        for r in csv.DictReader(fh):
            by_session.setdefault(r["session"], []).append(r)
    sessions = [(sid, rows, int(rows[0]["spoiled"])) for sid, rows in by_session.items()
                if sum(r["kind"] == "side" for r in rows) == 16 and any(r["kind"] == "top" for r in rows)]
    grid = [(td, tc) for td in rus.T_DEFECT for tc in rus.T_CLEAN if tc < td]
    pooled = []
    for f in sorted({rows[0]["fruit"] for _, rows, _ in sessions}):
        train = [s for s in sessions if s[1][0]["fruit"] != f]
        test = [s for s in sessions if s[1][0]["fruit"] == f]
        cfg = min((rus.PolicyConfig(t_defect=td, t_clean=tc) for td, tc in grid), key=lambda c: rus.cost(rus.run_policy(train, c)))
        pooled += rus.run_policy(test, cfg)
    rates = {}
    for label, name in ((1, "defective"), (0, "clean")):
        ds = [d for d, y, _ in pooled if y == label]
        rates[name] = {k: ds.count(k) / len(ds) for k in ("defective", "clean", "escalate")}
    decided_bad = rates["defective"]["defective"] + rates["defective"]["clean"]
    decided_good = rates["clean"]["defective"] + rates["clean"]["clean"]
    return {
        "sensitivity": rates["defective"]["defective"] / decided_bad,
        "specificity": rates["clean"]["clean"] / decided_good,
        "escalate_defective": rates["defective"]["escalate"],
        "escalate_clean": rates["clean"]["escalate"],
        "n_sessions": len(pooled),
    }


def verdict(truth: bool, rng, insp: dict | None) -> tuple[bool, bool]:
    """(called defective, decided by a person) for one item."""
    if insp is None:
        return truth, True
    if rng.random() < (insp["escalate_defective"] if truth else insp["escalate_clean"]):
        return truth, True
    if truth:
        return rng.random() < insp["sensitivity"], False
    return rng.random() >= insp["specificity"], False


def simulate(rate: float, plan: LotPlan, fixed: tuple[int, int], insp: dict | None, rng) -> dict:
    n_fixed, c_fixed = fixed
    acc_seq = acc_fix = 0
    items_seq, persons_seq, persons_fix = [], [], []
    for _ in range(LOTS_PER_RATE):
        crate = np.zeros(LOT_SIZE, bool)
        crate[: round(rate * LOT_SIZE)] = True
        rng.shuffle(crate)
        lot = LotInspection(plan)
        for item in crate:
            called, person = verdict(bool(item), rng, insp)
            lot.add(called, person)
            if lot.done:
                break
        acc_seq += lot.state.decision == "accept"
        items_seq.append(lot.state.items)
        persons_seq.append(lot.state.by_person)
        calls = [verdict(bool(item), rng, insp) for item in crate[:n_fixed]]
        acc_fix += sum(c for c, _ in calls) <= c_fixed
        persons_fix.append(sum(p for _, p in calls))
    return {"p_accept_sequential": acc_seq / LOTS_PER_RATE, "p_accept_fixed": acc_fix / LOTS_PER_RATE,
            "items_sequential": float(np.mean(items_seq)), "items_fixed": n_fixed,
            "person_checks_sequential": float(np.mean(persons_seq)), "person_checks_fixed": float(np.mean(persons_fix))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default="data/tr6_view_scores.csv")
    ap.add_argument("--out", default="eval/results/lot_acceptance.csv")
    args = ap.parse_args()

    insp = measured_inspector(args.scores)
    print(f"measured inspector (TR-6, leave-one-fruit-out, {insp['n_sessions']} sessions): "
          f"sensitivity {insp['sensitivity']:.3f}, specificity {insp['specificity']:.3f}, "
          f"hand-offs {insp['escalate_defective']:.3f} of defective / {insp['escalate_clean']:.3f} of clean")

    rng = np.random.default_rng(0)
    rows = []
    for name, inspector, insp_rates in (("perfect inspector", Inspector(), None),
                                        ("Chhaant (measured)", Inspector(insp["sensitivity"], insp["specificity"],
                                                     insp["escalate_defective"], insp["escalate_clean"]), insp)):
        base = LotPlan(inspector=inspector)
        n, c = fixed_plan(base)
        plan = LotPlan(inspector=inspector, max_items=n)
        print(f"\n{name}: fixed plan n={n}, c={c}; sequential capped at {n}")
        print("  true defect rate   P(accept) seq / fixed   items seq / fixed   person checks seq / fixed")
        for rate in TRUE_RATES:
            r = simulate(rate, plan, (n, c), insp_rates, rng)
            rows.append({"inspector": name, "true_rate": rate, **{k: round(v, 3) for k, v in r.items()}})
            print(f"  {rate:5.2f}              {r['p_accept_sequential']:.3f} / {r['p_accept_fixed']:.3f}          "
                  f"{r['items_sequential']:6.1f} / {r['items_fixed']:4d}        "
                  f"{r['person_checks_sequential']:5.1f} / {r['person_checks_fixed']:5.1f}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)


if __name__ == "__main__":
    main()
