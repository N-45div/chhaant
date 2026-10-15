#!/bin/bash
# User data for one evaluation instance; deploy/eval_job.sh fills in @BUCKET@, @REGION@, @RUN@
# and @COMMAND@. Runs the command with COOL's OpenCV, packs every result file it wrote,
# uploads them to runs/evals/@RUN@/ and powers off (the instance terminates on shutdown).
set -euxo pipefail
exec > /var/log/chhaant-eval.log 2>&1
shutdown -h +120  # safety net: never left running if a step hangs
BUCKET=@BUCKET@
REGION=@REGION@
RUN=@RUN@
PY=/opt/cool/venvs/python_3.12/bin/python
export PYTHONPATH=/opt/cool/python_3.12/site-packages/cv2/python-3.12  # what the COOL venv's activate sets
export LD_LIBRARY_PATH=/opt/cool/cpp_sdk/lib:/opt/ffmpeg/lib

upload() {  # the results and this log, whatever happened; then power off
  cd /srv/chhaant && find eval/results -type f -newer /tmp/started > /tmp/new-results || true
  tar czf /tmp/results.tar.gz -T /tmp/new-results || true
  $PY - <<PYEOF || true
import boto3
s3 = boto3.client("s3", region_name="$REGION")
for path, key in [("/tmp/results.tar.gz", "results.tar.gz"), ("/var/log/chhaant-eval.log", "eval.log")]:
    try:
        s3.upload_file(path, "$BUCKET", "runs/evals/$RUN/" + key)
    except Exception as err:
        print("upload failed", key, err)
PYEOF
  shutdown -h now
}

$PY -m pip install -q boto3==1.42.29
trap upload EXIT
mkdir -p /srv/chhaant/data/tr6 /srv/chhaant/data/avocado /srv/chhaant/models
cd /srv/chhaant
$PY - <<PYEOF
import boto3
s3 = boto3.client("s3", region_name="$REGION")
for key, path in [("artifacts/eval/chhaant.tar.gz", "/tmp/code.tar.gz"), ("artifacts/tr6_512.tar.gz", "/tmp/tr6.tar.gz"),
                  ("artifacts/avocado.tar.gz", "/tmp/avocado.tar.gz"),
                  ("artifacts/chhaant_quality_v1.onnx", "models/chhaant_quality_v1.onnx")]:
    s3.download_file("$BUCKET", key, path)
PYEOF
tar xzf /tmp/code.tar.gz
tar xzf /tmp/tr6.tar.gz -C data/tr6
tar xzf /tmp/avocado.tar.gz -C data
touch /tmp/started
@COMMAND@
