#!/bin/bash
# Set up the Chhaant server on the COOL AMI. Run once by the instance's user data
# (and safe to re-run). Expects CHHAANT_BUCKET and AWS_REGION in the environment.
set -euxo pipefail
PY=/opt/cool/venvs/python_3.12/bin/python
# What the COOL venv's bin/activate exports: its cv2 lives outside the venv, with
# the C++ SDK beside it. Non-login shells (user data, SSM) never run activate.
export PYTHONPATH=/opt/cool/python_3.12/site-packages/cv2/python-3.12
export LD_LIBRARY_PATH=/opt/cool/cpp_sdk/lib:/opt/ffmpeg/lib
cd /srv/chhaant

# App dependencies go into COOL's Python. Never install the PyPI OpenCV wheel here:
# it would replace the COOL build, and the competition's COOL claim with it.
grep -v -E '^(opencv-python|numpy|pytest|awscrt|botocore)' requirements.txt > /tmp/requirements-server.txt
$PY -m pip install --quiet -r /tmp/requirements-server.txt
$PY -c "import cv2; info = cv2.getBuildInformation(); assert 'KleidiCV' in info, 'COOL OpenCV is not the one loaded'; print(cv2.__version__)"

# The quality model comes from the training run's artifact in S3.
$PY -c "import boto3; boto3.client('s3', region_name='$AWS_REGION').download_file('$CHHAANT_BUCKET', 'artifacts/chhaant_quality_v1.onnx', 'models/chhaant_quality_v1.onnx')"

# Data straight from the original sources (idempotent: present files are kept).
if [ ! -f data/tr6/tr6_manifest.csv ]; then
  CHHAANT_PREP_OUT=/srv/chhaant/data/tr6 CHHAANT_PREP_ZIP=0 $PY kaggle/prep/prep.py
fi
$PY scripts/fetch_avocado.py --out data/avocado --workers 16
$PY scripts/fetch_so101.py

id chhaant >/dev/null 2>&1 || useradd --system --home-dir /srv/chhaant --shell /usr/sbin/nologin chhaant
mkdir -p data/runs
chown -R chhaant:chhaant /srv/chhaant
cat > /etc/chhaant.env <<EOF
AWS_REGION=$AWS_REGION
CHHAANT_EVIDENCE_BUCKET=$CHHAANT_BUCKET
CHHAANT_BEDROCK_MODEL=${CHHAANT_BEDROCK_MODEL:-global.anthropic.claude-haiku-4-5-20251001-v1:0}
EOF
install -m 644 deploy/chhaant.service /etc/systemd/system/chhaant.service
systemctl daemon-reload
systemctl enable chhaant
systemctl restart chhaant
echo "chhaant bootstrap done"
