"""Accept or reject a supplier's crate, inspecting as few items as the risk allows.

Today's inspection rules take a fixed sample; the OECD rule for a borderline
lot is to take a second sample and average. There is no stated risk. Here the
crate is judged with Wald's sequential probability ratio test: items are
inspected one at a time and the test stops as soon as the evidence clears

    H0: defect rate <= p0 (a good crate)   vs   H1: defect rate >= p1 (a bad one)

with at most ``alpha`` chance of rejecting a good crate and ``beta`` of
accepting a bad one. A cap on items stops the open-ended run that ISO 28591
warns about; at the cap the evidence decides by which bound it is nearer.

The robot is not a perfect inspector, so its calls carry its measured error
rates: it calls a defect with probability q = p*se + (1-p)*(1-sp) when the
true rate is p. Items it cannot decide go to a person, whose verdict counts as
the truth.
"""

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Inspector:
    sensitivity: float = 1.0   # P(robot calls "defective" | item is defective), among items it decides
    specificity: float = 1.0   # P(robot calls "clean" | item is clean), among items it decides

    def call_rate(self, p: float) -> float:
        """Share of decided items the robot calls defective when the true defect rate is p."""
        return p * self.sensitivity + (1.0 - p) * (1.0 - self.specificity)


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
        lo, hi = (self.p0, self.p1) if by_person else (self.inspector.call_rate(self.p0), self.inspector.call_rate(self.p1))
        return math.log(hi / lo) if defective else math.log((1 - hi) / (1 - lo))


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
