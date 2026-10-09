"""Run the full inspection loop on one recorded TR-6 session and print its trace.

Real photos (virtual turntable) -> segmentation -> OpenCV 5 DNN quality model
-> rotate-until-sure policy -> verdict, with every look explained.

Usage:
    python scripts/inspect_session.py --fruit Banana --pick spoiled
    python scripts/inspect_session.py --fruit Mango --pick fresh --t-defect 0.7 --t-clean 0.1
"""

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from chhaant.data.tr6 import load_sessions  # noqa: E402
from chhaant.decide.camera import TurntableCamera  # noqa: E402
from chhaant.decide.policy import InspectionPolicy, PolicyConfig  # noqa: E402
from chhaant.robot.turntable import VirtualTurntable  # noqa: E402
from chhaant.vision.model import QualityModel  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/tr6")
    ap.add_argument("--model", default="models/chhaant_quality_v1.onnx")
    ap.add_argument("--fruit", default="Banana")
    ap.add_argument("--pick", choices=("spoiled", "fresh", "any"), default="any")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--t-defect", type=float, default=0.7)
    ap.add_argument("--t-clean", type=float, default=0.1)
    args = ap.parse_args()

    pool = [s for s in load_sessions(args.data) if s.fruit == args.fruit and len(s.side_views) == 16
            and (args.pick == "any" or s.spoiled == (args.pick == "spoiled"))]
    if not pool:
        sys.exit(f"no {args.pick} {args.fruit} sessions")
    session = random.Random(args.seed).choice(pool)
    camera = TurntableCamera(VirtualTurntable(session, args.data), QualityModel(args.model))
    verdict = InspectionPolicy(PolicyConfig(t_defect=args.t_defect, t_clean=args.t_clean)).inspect(camera)

    print(f"{session.fruit} {session.date} session {session.slot} (dataset label: {'spoiled' if session.spoiled else 'fresh'})")
    for n, s in enumerate(verdict.steps):
        where = "overhead" if s.azimuth is None else f"{s.azimuth:6.1f} deg"
        print(f"  look {n}: {where:>10s}  defect {s.p_defect:.2f}  ripeness {s.p_ripeness:.2f}  <- {s.why}")
    print(f"VERDICT: {verdict.decision.upper()} after {verdict.side_views} side views: {verdict.reason}")


if __name__ == "__main__":
    main()
