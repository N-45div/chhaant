#!/bin/bash
# User data for one benchmark instance; deploy/bench.sh fills in @BUCKET@, @REGION@ and @RUN@.
# Times the cell's vision under every OpenCV build this machine has (COOL's and the PyPI
# wheel on the COOL AMI; the wheel elsewhere), uploads the reports to runs/bench/@RUN@/,
# then powers off. The instance is launched to terminate on shutdown.
set -euxo pipefail
exec > /var/log/chhaant-bench.log 2>&1
shutdown -h +60  # safety net: never left running if a step hangs
BUCKET=@BUCKET@
REGION=@REGION@
RUN=@RUN@
TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
TYPE=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-type)

upload() {  # the reports and this log, whatever happened; then power off
  $PY - <<PYEOF || true
import boto3, glob, os
s3 = boto3.client("s3", region_name="$REGION")
for p in glob.glob("/tmp/bench-*.json") + ["/var/log/chhaant-bench.log"]:
    s3.upload_file(p, "$BUCKET", "runs/bench/$RUN/$TYPE-" + os.path.basename(p))
PYEOF
  shutdown -h now
}

COOL=/opt/cool/venvs/python_3.12/bin/python
if [ -x $COOL ]; then
  PY=$COOL
  FLAVOURS="cool pip"
else
  export DEBIAN_FRONTEND=noninteractive
  apt-get -o DPkg::Lock::Timeout=300 update -q
  # libGL and glib: the opencv-python wheel the project pins (not -headless) links them
  apt-get -o DPkg::Lock::Timeout=300 install -y -q python3-venv libgl1 libglib2.0-0t64
  python3 -m venv /opt/bench
  PY=/opt/bench/bin/python
  $PY -m pip install -q numpy==2.4.3
  FLAVOURS="pip"
fi
$PY -m pip install -q boto3==1.42.29
trap upload EXIT
# The PyPI wheel goes into its own folder, so it never shadows (or replaces) COOL's build.
$PY -m pip install -q --no-deps --target /opt/pipcv opencv-python==5.0.0.93

mkdir -p /srv/chhaant/data/tr6 /srv/chhaant/models
cd /srv/chhaant
$PY - <<PYEOF
import boto3
s3 = boto3.client("s3", region_name="$REGION")
for key, path in [("artifacts/bench/chhaant.tar.gz", "/tmp/code.tar.gz"), ("artifacts/tr6_512.tar.gz", "/tmp/tr6.tar.gz"),
                  ("artifacts/tr6_full.tar.gz", "/tmp/full.tar.gz"),
                  ("artifacts/chhaant_quality_v1.onnx", "models/chhaant_quality_v1.onnx")]:
    s3.download_file("$BUCKET", key, path)
PYEOF
tar xzf /tmp/code.tar.gz
tar xzf /tmp/tr6.tar.gz -C data/tr6
tar xzf /tmp/full.tar.gz -C data

for F in $FLAVOURS; do
  if [ "$F" = cool ]; then  # what the COOL venv's bin/activate exports
    BUILD="PYTHONPATH=/opt/cool/python_3.12/site-packages/cv2/python-3.12 LD_LIBRARY_PATH=/opt/cool/cpp_sdk/lib:/opt/ffmpeg/lib"
  else
    BUILD="PYTHONPATH=/opt/pipcv"
  fi
  env $BUILD $PY eval/bench_cool.py --label "${TYPE%%.*}-$F" --out "/tmp/bench-$F.json"
done
