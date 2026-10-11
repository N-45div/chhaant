"""Accept or reject a supplier's crate, inspecting as few items as the risk allows.

Today's inspection rules take a fixed sample; the OECD rule for a borderline
lot is to take a second sample and average. There is no stated risk. Here the
crate is judged with Wald's sequential probability ratio test: items are
inspected one at a time and the test stops as soon as the evidence clears

    H0: defect rate <= p0 (a good crate)   vs   H1: defect rate >= p1 (a bad one)

with at most ``alpha`` chance of rejecting a good crate and ``beta`` of
accepting a bad one. A cap on items stops the open-ended run that ISO 28591
warns about; at the cap the evidence decides by which bound it is nearer.

The robot is not a perfect inspector. Each inspected item ends in one of four
outcomes, whose probabilities under a true defect rate p use the robot's
measured rates (sensitivity se, specificity sp, and hand-off rates e_d for
defective and e_c for clean items; a person's verdict counts as the truth):

    person says defective   p * e_d
    person says clean       (1 - p) * e_c
    robot says defective    p * (1 - e_d) * se + (1 - p) * (1 - e_c) * (1 - sp)
    robot says clean        p * (1 - e_d) * (1 - se) + (1 - p) * (1 - e_c) * sp

Hand-offs change what the robot's own calls mean. It hands defective items to
a person more often than clean ones, so the items it keeps are skewed clean.
A test that read the robot's calls as if nothing were ever handed off broke
its promise (a good crate accepted 88% of the time instead of 95% in
simulation). For a person's verdict the hand-off rates cancel out.
"""

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Inspector:
    sensitivity: float = 1.0         # P(robot calls "defective" | defective item it decides)
    specificity: float = 1.0         # P(robot calls "clean" | clean item it decides)
    escalate_defective: float = 0.0  # P(handed to a person | defective item)
    escalate_clean: float = 0.0      # P(handed to a person | clean item)

    def outcome_prob(self, p: float, defective: bool, by_person: bool) -> float:
        """Probability of one item's outcome when the crate's true defect rate is p."""
        if by_person:
            return p * self.escalate_defective if defective else (1 - p) * self.escalate_clean
        robot_bad = p * (1 - self.escalate_defective)
        robot_good = (1 - p) * (1 - self.escalate_clean)
        if defective:
            return robot_bad * self.sensitivity + robot_good * (1 - self.specificity)
        return robot_bad * (1 - self.sensitivity) + robot_good * self.specificity

    def call_rate(self, p: float) -> float:
        """Share of all inspected items called defective (by the robot or a person)."""
        return self.outcome_prob(p, True, False) + self.outcome_prob(p, True, True)


PERFECT = Inspector()


@dataclass
class LotPlan:
    p0: float = 0.05     # acceptable defect rate
    p1: float = 0.20     # rejectable defect rate
    alpha: float = 0.05  # risk of rejecting a good crate
    beta: float = 0.05   # risk of accepting a bad crate
    max_items: int = 60
    inspector: Inspector = PERFECT

    def __post_init__(self):
        if not 0 < self.p0 < self.p1 < 1:
            raise ValueError("need 0 < p0 < p1 < 1")
        if self.inspector.call_rate(self.p1) <= self.inspector.call_rate(self.p0):
            raise ValueError("the inspector cannot tell good crates from bad ones")

    @property
    def reject_bound(self) -> float:
        return math.log((1 - self.beta) / self.alpha)

    @property
    def accept_bound(self) -> float:
        return math.log(self.beta / (1 - self.alpha))

    def step(self, defective: bool, by_person: bool) -> float:
        """Log-likelihood-ratio increment for one inspected item."""
        if by_person:  # a person's verdict is the truth; hand-off rates cancel in the ratio
            return math.log(self.p1 / self.p0) if defective else math.log((1 - self.p1) / (1 - self.p0))
        insp = self.inspector
        return math.log(insp.outcome_prob(self.p1, defective, False) / insp.outcome_prob(self.p0, defective, False))


@dataclass
class LotDecision:
    decision: str | None = None   # "accept", "reject", or None while still inspecting
    llr: float = 0.0
    items: int = 0
    defects_called: int = 0
    by_person: int = 0
    truncated: bool = False
    trace: list[tuple[int, bool, bool, float]] = field(default_factory=list)  # (item, defective, by person, llr)

    @property
    def reason(self) -> str:
        if self.decision is None:
            return f"still inspecting after {self.items} items"
        how = "hit the item cap; nearer bound decides" if self.truncated else "evidence crossed a bound"
        return f"{self.decision} after {self.items} items ({self.defects_called} defective, {self.by_person} checked by a person): {how}"


class LotInspection:
    """Feed it one verdict at a time; it says when to stop."""

    def __init__(self, plan: LotPlan):
        self.plan = plan
        self.state = LotDecision()

    @property
    def done(self) -> bool:
        return self.state.decision is not None

    def add(self, defective: bool, by_person: bool = False) -> LotDecision:
        if self.done:
            raise RuntimeError("the lot is already decided")
        s, p = self.state, self.plan
        s.items += 1
        s.defects_called += int(defective)
        s.by_person += int(by_person)
        s.llr += p.step(defective, by_person)
        s.trace.append((s.items, defective, by_person, round(s.llr, 4)))
        if s.llr >= p.reject_bound:
            s.decision = "reject"
        elif s.llr <= p.accept_bound:
            s.decision = "accept"
        elif s.items >= p.max_items:
            s.truncated = True
            s.decision = "reject" if s.llr >= (p.reject_bound + p.accept_bound) / 2 else "accept"
        return s


def binom_cdf(c: int, n: int, p: float) -> float:
    return sum(math.comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(c + 1))


def fixed_plan(plan: LotPlan, max_n: int = 400) -> tuple[int, int]:
    """Smallest single-sampling plan (n, c) with the same two risks: accept when defects called <= c."""
    q0, q1 = plan.inspector.call_rate(plan.p0), plan.inspector.call_rate(plan.p1)
    for n in range(1, max_n + 1):
        for c in range(n + 1):
            if binom_cdf(c, n, q0) >= 1 - plan.alpha:
                if binom_cdf(c, n, q1) <= plan.beta:
                    return n, c
                break  # a larger c only raises acceptance of bad crates
    raise ValueError("no fixed plan within max_n")
