"""After each run: archive its evidence to S3 and publish CloudWatch metrics.

Best effort by design: a failed upload is logged and never breaks a run or
the page. Metrics (namespace ``Chhaant``) let an operator watch the deployed
cell: how long runs take, how often the cell refused a move, how often the
agent asked a person, how many photos failed the capture checks, and, for
simulated-reviewer runs, how many items were packed wrong against the hidden
labels. The health metrics are also published without a dimension, so one
alarm covers every run; a camera-faults demo run (photos spoiled on purpose)
leaves UnusablePhotos out of that copy, so a visitor's demo never pages anyone.
"""

import logging
import os

log = logging.getLogger("chhaant.aws")


class AwsReporter:
    def __init__(self, bucket: str, region: str, namespace: str = "Chhaant", s3=None, cloudwatch=None):
        if s3 is None or cloudwatch is None:
            import boto3
            s3 = s3 or boto3.client("s3", region_name=region)
            cloudwatch = cloudwatch or boto3.client("cloudwatch", region_name=region)
        self.bucket, self.namespace = bucket, namespace
        self.s3, self.cloudwatch = s3, cloudwatch

    def __call__(self, run, runs_dir: str) -> None:
        try:
            for name in ("trace.jsonl", "result.json"):
                path = os.path.join(runs_dir, run.id, name)
                if os.path.exists(path):
                    self.s3.upload_file(path, self.bucket, f"runs/{run.id}/{name}")
        except Exception as err:  # never let the archive break the app
            log.warning("evidence upload failed for %s: %s", run.id, err)
        try:
            self.cloudwatch.put_metric_data(Namespace=self.namespace, MetricData=self.metrics(run))
        except Exception as err:
            log.warning("metrics failed for %s: %s", run.id, err)

    @staticmethod
    def metrics(run) -> list[dict]:
        dims = [{"Name": "Reviewer", "Value": run.reviewer_mode}]
        res = run.result or {}
        score, usage = res.get("score", {}), res.get("usage", {})
        values = {
            "RunSeconds": (run.finished_at or run.started_at) - run.started_at,
            "RunFailed": 1.0 if run.status == "error" else 0.0,
            "Turns": res.get("turns", 0), "InputTokens": usage.get("input", 0), "OutputTokens": usage.get("output", 0),
            "RefusedMoves": score.get("refused_moves", 0), "PersonRequests": score.get("person_requests", 0),
            "ItemsInspected": score.get("inspected", 0), "PhotosUsed": score.get("views", 0),
            "UnusablePhotos": score.get("unusable_photos", 0),
        }
        if run.reviewer_mode == "simulated":  # only meaningful when answers came from the labels
            values["PackedWrong"] = score.get("packed_bad", 0)
        unit = {"RunSeconds": "Seconds"}
        data = [{"MetricName": k, "Value": float(v), "Unit": unit.get(k, "Count"), "Dimensions": dims} for k, v in values.items()]
        health = ["RunSeconds", "RunFailed", "RefusedMoves"] + ([] if getattr(run, "faults", False) else ["UnusablePhotos"])
        return data + [{"MetricName": k, "Value": float(values[k]), "Unit": unit.get(k, "Count")} for k in health]
