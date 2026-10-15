"""Rotate until sure: the per-item inspection loop.

Each step the cell looks at the item from one angle and the vision model scores
that view. After every look the policy decides:

* DEFECTIVE when neighbouring views agree on a defect (see ``fusion.agreement``);
* CLEAN only when enough of the surface has been inspected, every suspicious
  view has been cross-checked from a neighbouring angle, and the agreed score
  is low;
* otherwise it looks again: first beside any suspicious view that nobody has
  confirmed or refuted yet, else wherever inspects the most new surface;
* ESCALATE to a person when the view budget runs out undecided.

A look whose photo failed the capture checks (blur, glare, exposure, no item,
item cut off; ``chhaant.vision.capture``) is recorded with its problem but is
never evidence: no score, no coverage. It still uses up the view budget, and
three failed captures in a row stop the inspection, since that points at the
cell (empty turntable, a dead light) rather than at one unlucky angle.

The underside is not inspectable in TR-6 replay (no photos of it), so
``min_coverage`` must be reachable from above; the report states the uninspected
share with every clean call.
"""

from dataclasses import dataclass, field
from typing import Protocol

from chhaant.decide.fusion import DEFAULT_WINDOW_DEG, MIN_SUPPORT, agreement, angular_gap, neighbours
from chhaant.vision.views import CoverageMap

SIDE_STEPS = 16
MAX_FAILED_IN_A_ROW = 3


@dataclass
class Look:
    azimuth: float
    elevation: float
    p_defect: float
    p_ripeness: float
    source: str = ""
    problem: str = ""        # why the photo cannot count as evidence; empty when it can


class Camera(Protocol):
    def look_down(self) -> Look: ...
    def look_at(self, azimuth: float) -> Look: ...


@dataclass
class PolicyConfig:
    t_defect: float = 0.7        # agreed score at or above this: defective
    t_clean: float = 0.35        # a view at or above this is suspicious; agreed score below it: clean
    min_coverage: float = 0.55   # share of the surface inspected before a clean call
    max_views: int = 8           # side views; beyond this a person decides
    window_deg: float = DEFAULT_WINDOW_DEG
    use_top_view: bool = True


@dataclass
class Step:
    azimuth: float | None   # None for the overhead view
    p_defect: float
    p_ripeness: float
    why: str                # why the cell looked here
    source: str = ""
    problem: str = ""       # the capture problem that kept this look out of the evidence


@dataclass
class Verdict:
    decision: str           # "defective", "clean" or "escalate"
    score: float            # agreed defect score
    coverage: float         # inspected share of the surface
    ripeness: float | None  # mean ripeness over the usable looks (None if there were none)
    side_views: int
    reason: str
    steps: list[Step] = field(default_factory=list)


class InspectionPolicy:
    def __init__(self, config: PolicyConfig | None = None):
        self.cfg = config or PolicyConfig()
        self.candidates = [360.0 * i / SIDE_STEPS for i in range(SIDE_STEPS)]

    def _unresolved(self, views: dict[float, float]) -> list[float]:
        """Suspicious views with no captured neighbour yet to confirm or refute them."""
        return [a for a, p in views.items()
                if p >= self.cfg.t_clean and len(neighbours(views, a, self.cfg.window_deg)) < MIN_SUPPORT]

    def _next(self, views: dict[float, float], cov: CoverageMap, failed: set[float]) -> tuple[float, str]:
        free = [a for a in self.candidates if a not in views and a not in failed]
        unresolved = self._unresolved(views)
        if unresolved:
            target = max(unresolved, key=lambda a: views[a])
            near = [a for a in free if angular_gap(a, target) <= self.cfg.window_deg]
            if near:
                # closest first; between the two sides, the one that has been checked less
                def side_seen(a: float) -> int:
                    sign = 1 if (a - target) % 360.0 < 180.0 else -1
                    return sum(1 for v in views if v != target and angular_gap(v, target) <= self.cfg.window_deg
                               and (1 if (v - target) % 360.0 < 180.0 else -1) == sign)
                best = min(near, key=lambda a: (angular_gap(a, target), side_seen(a)))
                return best, f"cross-check the suspicious view at {target:.1f} deg"
        az, _, gain = cov.best_next_view([(a, 40.0) for a in free])
        return az, f"inspect new surface (+{gain:.0%})"

    @staticmethod
    def _failures(steps: list[Step]) -> str:
        bad = [st.problem.split(" (")[0] for st in steps if st.problem]
        if not bad:
            return ""
        kinds = sorted(set(bad), key=bad.index)
        return f"; {len(bad)} photo{'s' if len(bad) > 1 else ''} unusable ({', '.join(f'{k} x{bad.count(k)}' for k in kinds)})"

    def inspect(self, camera: Camera) -> Verdict:
        cfg = self.cfg
        cov = CoverageMap()
        views: dict[float, float] = {}
        failed: set[float] = set()
        ripeness: list[float] = []
        steps: list[Step] = []

        def mean_ripe() -> float | None:
            return sum(ripeness) / len(ripeness) if ripeness else None

        top_suspicious = False
        if cfg.use_top_view:
            top = camera.look_down()
            if top.problem:
                steps.append(Step(None, top.p_defect, top.p_ripeness, "overhead camera, no rotation needed", top.source, top.problem))
            else:
                cov.add_view(0.0, top.elevation)
                ripeness.append(top.p_ripeness)
                steps.append(Step(None, top.p_defect, top.p_ripeness, "overhead camera, no rotation needed", top.source))
                top_suspicious = top.p_defect >= cfg.t_clean  # needs side views before any clean call

        azimuth, why = 0.0, "first side view"
        in_a_row = 0
        while True:
            look = camera.look_at(azimuth)
            if look.problem:
                failed.add(look.azimuth)
                steps.append(Step(look.azimuth, look.p_defect, look.p_ripeness, why, look.source, look.problem))
                in_a_row += 1
                score, _ = agreement(views, cfg.window_deg) if views else (0.0, 0)
                if in_a_row >= MAX_FAILED_IN_A_ROW:
                    return Verdict("escalate", score, cov.covered_frac, mean_ripe(), len(views),
                                   f"{in_a_row} captures in a row unusable; check the cell before trusting it"
                                   f"{self._failures(steps)}", steps)
                if len(views) + len(failed) >= cfg.max_views:
                    return Verdict("escalate", score, cov.covered_frac, mean_ripe(), len(views),
                                   f"undecided after {len(views) + len(failed)} looks{self._failures(steps)}; "
                                   "a person should look", steps)
                azimuth, why = self._next(views, cov, failed)
                why = f"{why} (the photo at {look.azimuth:.1f} deg was unusable)"
                continue
            in_a_row = 0
            views[look.azimuth] = look.p_defect
            cov.add_view(look.azimuth, look.elevation)
            ripeness.append(look.p_ripeness)
            steps.append(Step(look.azimuth, look.p_defect, look.p_ripeness, why, look.source))

            score, support = agreement(views, cfg.window_deg)
            note = self._failures(steps)
            if score >= cfg.t_defect:
                return Verdict("defective", score, cov.covered_frac, mean_ripe(), len(views),
                               f"{support} neighbouring views agree on a defect ({score:.2f}){note}", steps)
            unresolved = self._unresolved(views)
            top_open = top_suspicious and len(views) < MIN_SUPPORT
            if (cov.covered_frac >= cfg.min_coverage and not unresolved and not top_open
                    and score < cfg.t_clean):
                return Verdict("clean", score, cov.covered_frac, mean_ripe(), len(views),
                               f"{cov.covered_frac:.0%} of the surface inspected, nothing agreed on "
                               f"({score:.2f}); {1 - cov.covered_frac:.0%} unseen (underside){note}", steps)
            if len(views) + len(failed) >= cfg.max_views:
                return Verdict("escalate", score, cov.covered_frac, mean_ripe(), len(views),
                               f"undecided after {len(views) + len(failed)} looks (agreed score {score:.2f}, "
                               f"{len(unresolved)} unresolved){note}; a person should look", steps)
            azimuth, why = self._next(views, cov, failed)
