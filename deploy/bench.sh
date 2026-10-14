#!/bin/bash
# The COOL benchmark, on fresh instances (never the live server):
#   c8g.large, Graviton4, from the COOL AMI: COOL's OpenCV and the PyPI wheel on one machine
#   c7i.large, Sapphire Rapids, Ubuntu 24.04: the PyPI wheel
# Each runs deploy/bench_node.sh, uploads its reports to S3 and terminates itself.
# Needs the stack (its instance role reads artifacts/ and writes runs/) and data/tr6_full
# (scripts/fetch_tr6_originals.py). Reports land in eval/results/bench/.
set -euo pipefail
REGION=${AWS_REGION:-ap-south-1}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET=${CHHAANT_BUCKET:-chhaant-$ACCOUNT-$REGION}
STACK=${CHHAANT_STACK:-chhaant}
COOL_AMI=ami-05a336eb12c47d427
cd "$(dirname "$0")/.."
RUN=$(date -u +%Y%m%d-%H%M%S)

mkdir -p data/deploy eval/results/bench
git -c core.autocrlf=false archive --format=tar.gz -o data/deploy/bench-code.tar.gz HEAD
aws s3 cp data/deploy/bench-code.tar.gz "s3://$BUCKET/artifacts/bench/chhaant.tar.gz" --region "$REGION" --only-show-errors
if ! aws s3api head-object --bucket "$BUCKET" --key artifacts/tr6_full.tar.gz --region "$REGION" >/dev/null 2>&1; then
  [ -d data/tr6_full ] || { echo "run scripts/fetch_tr6_originals.py first"; exit 1; }
  tar czf data/deploy/tr6_full.tar.gz -C data tr6_full
  aws s3 cp data/deploy/tr6_full.tar.gz "s3://$BUCKET/artifacts/tr6_full.tar.gz" --region "$REGION" --only-show-errors
fi

PROFILE=$(aws cloudformation describe-stack-resource --stack-name "$STACK" --region "$REGION" \
  --logical-resource-id InstanceProfile --query StackResourceDetail.PhysicalResourceId --output text)
UBUNTU_AMI=$(aws ssm get-parameter --region "$REGION" --query Parameter.Value --output text \
  --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id)
# From the committed script, so a Windows checkout's CRLF never reaches bash on the instance.
git show HEAD:deploy/bench_node.sh | sed -e "s/@BUCKET@/$BUCKET/" -e "s/@REGION@/$REGION/" -e "s/@RUN@/$RUN/" \
  > data/deploy/bench-userdata.sh
for SPEC in "c8g.large $COOL_AMI" "c7i.large $UBUNTU_AMI"; do
  set -- $SPEC
  aws ec2 run-instances --region "$REGION" --image-id "$2" --instance-type "$1" \
    --iam-instance-profile Name="$PROFILE" --instance-initiated-shutdown-behavior terminate \
    --metadata-options HttpTokens=required,HttpEndpoint=enabled \
    --user-data file://data/deploy/bench-userdata.sh \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=chhaant-bench-$1},{Key=project,Value=opencv-comp}]" \
    --query "Instances[0].InstanceId" --output text
done

echo "waiting for 3 reports in s3://$BUCKET/runs/bench/$RUN/ (about 10 minutes)"
for _ in $(seq 1 90); do
  [ "$(aws s3 ls "s3://$BUCKET/runs/bench/$RUN/" --region "$REGION" | grep -c 'chhaant-bench.log')" -ge 2 ] && break
  sleep 20
done
aws s3 cp "s3://$BUCKET/runs/bench/$RUN/" "eval/results/bench/$RUN/" --recursive --region "$REGION" --only-show-errors
ls "eval/results/bench/$RUN/"
