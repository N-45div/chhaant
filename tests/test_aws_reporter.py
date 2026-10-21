from types import SimpleNamespace

from chhaant.web.aws import AwsReporter


class StubS3:
    def __init__(self, fail=False):
        self.uploads, self.fail = [], fail

    def upload_file(self, path, bucket, key):
        if self.fail:
            raise RuntimeError("network down")
        self.uploads.append((bucket, key))


class StubCloudWatch:
    def __init__(self):
        self.calls = []

    def put_metric_data(self, Namespace, MetricData):
        self.calls.append((Namespace, MetricData))


def run(tmp_path, reviewer="simulated", status="done"):
    d = tmp_path / "r1"
    d.mkdir(parents=True, exist_ok=True)
    (d / "trace.jsonl").write_text("{}\n")
    (d / "result.json").write_text("{}")
    result = {"turns": 6, "usage": {"input": 100, "output": 20},
              "score": {"refused_moves": 2, "person_requests": 1, "inspected": 5, "views": 14, "packed_bad": 1}}
    return SimpleNamespace(id="r1", reviewer_mode=reviewer, status=status, result=result, started_at=10.0, finished_at=35.5)


def test_evidence_goes_to_s3_and_metrics_to_cloudwatch(tmp_path):
    s3, cw = StubS3(), StubCloudWatch()
    AwsReporter("bucket", "ap-south-1", s3=s3, cloudwatch=cw)(run(tmp_path), str(tmp_path))
    assert s3.uploads == [("bucket", "runs/r1/trace.jsonl"), ("bucket", "runs/r1/result.json")]
    ns, data = cw.calls[0]
    metrics = {m["MetricName"]: m["Value"] for m in data}
    assert ns == "Chhaant" and metrics["RunSeconds"] == 25.5 and metrics["RefusedMoves"] == 2 and metrics["PackedWrong"] == 1


def test_packed_wrong_is_only_reported_when_answers_came_from_the_labels(tmp_path):
    cw = StubCloudWatch()
    AwsReporter("b", "ap-south-1", s3=StubS3(), cloudwatch=cw)(run(tmp_path, reviewer="person"), str(tmp_path))
    assert "PackedWrong" not in {m["MetricName"] for m in cw.calls[0][1]}


def test_a_failed_upload_never_breaks_the_run(tmp_path):
    cw = StubCloudWatch()
    AwsReporter("b", "ap-south-1", s3=StubS3(fail=True), cloudwatch=cw)(run(tmp_path), str(tmp_path))
    assert cw.calls  # metrics still published


def test_a_camera_faults_demo_never_feeds_the_camera_alarm(tmp_path):
    cw = StubCloudWatch()
    r = run(tmp_path)
    r.result["score"]["unusable_photos"] = 5
    alarm_feed = lambda calls: [m for m in calls[-1][1] if m["MetricName"] == "UnusablePhotos" and "Dimensions" not in m]  # noqa: E731
    AwsReporter("bucket", "ap-south-1", s3=StubS3(), cloudwatch=cw)(r, str(tmp_path))
    assert alarm_feed(cw.calls)[0]["Value"] == 5.0
    r.faults = True
    AwsReporter("bucket", "ap-south-1", s3=StubS3(), cloudwatch=cw)(r, str(tmp_path))
    assert alarm_feed(cw.calls) == []
    assert any(m["MetricName"] == "UnusablePhotos" and "Dimensions" in m for m in cw.calls[-1][1])  # still on the dashboard


def test_a_finished_mcp_job_goes_to_s3_with_its_own_metrics(tmp_path):
    d = tmp_path / "20261021T101500Z-seed0-abc"
    d.mkdir()
    (d / "trace.jsonl").write_text("{}\n")
    (d / "score.json").write_text('{"refused_moves": 3}')
    s3, cw = StubS3(), StubCloudWatch()
    AwsReporter("bucket", "ap-south-1", s3=s3, cloudwatch=cw).mcp_job(str(d))
    assert s3.uploads == [("bucket", "runs/mcp/20261021T101500Z-seed0-abc/trace.jsonl"),
                          ("bucket", "runs/mcp/20261021T101500Z-seed0-abc/score.json")]
    metrics = {m["MetricName"]: m for m in cw.calls[0][1]}
    assert metrics["McpJobs"]["Value"] == 1 and metrics["RefusedMoves"]["Value"] == 3
    assert metrics["RefusedMoves"]["Dimensions"] == [{"Name": "Source", "Value": "mcp"}]  # not the web runs' alarm
