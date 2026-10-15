#!/bin/bash
# Run one heavy evaluation on a throwaway Graviton4 instance (COOL AMI), never the laptop:
#   deploy/eval_job.sh c8g.4xlarge '$PY eval/capture_failures.py'
# The command runs in a checkout of HEAD with data/tr6, data/avocado and the model in place;
# $PY is COOL's Python. Result files it writes under eval/results/ come back into this
# checkout. The instance terminates itself (and after 2 hours regardless).
set -euo pipefail
TYPE=${1:?instance type, e.g. c8g.4xlarge}
COMMAND=${2:?command, e.g. '\$PY eval/capture_failures.py'}
REGION=${AWS_REGION:-ap-south-1}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET=${CHHAANT_BUCKET:-chhaant-$ACCOUNT-$REGION}
STACK=${CHHAANT_STACK:-chhaant}
COOL_AMI=ami-05a336eb12c47d427
cd "$(dirname "$0")/.."
RUN=$(date -u +%Y%m%d-%H%M%S)

mkdir -p data/deploy
git -c core.autocrlf=false archive --format=tar.gz -o data/deploy/eval-code.tar.gz HEAD
aws s3 cp data/deploy/eval-code.tar.gz "s3://$BUCKET/artifacts/eval/chhaant.tar.gz" --region "$REGION" --only-show-errors
if ! aws s3api head-object --bucket "$BUCKET" --key artifacts/avocado.tar.gz --region "$REGION" >/dev/null 2>&1; then
  tar czf data/deploy/avocado.tar.gz -C data avocado  # ~0.5 GB, once
  aws s3 cp data/deploy/avocado.tar.gz "s3://$BUCKET/artifacts/avocado.tar.gz" --region "$REGION" --only-show-errors
fi

PROFILE=$(aws cloudformation describe-stack-resource --stack-name "$STACK" --region "$REGION" \
  --logical-resource-id InstanceProfile --query StackResourceDetail.PhysicalResourceId --output text)
# From the committed script, so a Windows checkout's CRLF never reaches bash on the instance.
git show HEAD:deploy/eval_node.sh | python -c "
import sys
s = sys.stdin.read()
for k, v in (('@BUCKET@', sys.argv[1]), ('@REGION@', sys.argv[2]), ('@RUN@', sys.argv[3]), ('@COMMAND@', sys.argv[4])):
    s = s.replace(k, v)
sys.stdout.write(s)" "$BUCKET" "$REGION" "$RUN" "$COMMAND" > data/deploy/eval-userdata.sh
aws ec2 run-instances --region "$REGION" --image-id "$COOL_AMI" --instance-type "$TYPE" \
  --iam-instance-profile Name="$PROFILE" --instance-initiated-shutdown-behavior terminate \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --user-data file://data/deploy/eval-userdata.sh \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=chhaant-eval},{Key=project,Value=opencv-comp}]" \
  --query "Instances[0].InstanceId" --output text

echo "waiting for s3://$BUCKET/runs/evals/$RUN/"
for _ in $(seq 1 400); do
  aws s3 ls "s3://$BUCKET/runs/evals/$RUN/eval.log" --region "$REGION" >/dev/null 2>&1 && break
  sleep 20
done
mkdir -p "data/evals/$RUN"
aws s3 cp "s3://$BUCKET/runs/evals/$RUN/" "data/evals/$RUN/" --recursive --region "$REGION" --only-show-errors
[ -f "data/evals/$RUN/results.tar.gz" ] && tar xzf "data/evals/$RUN/results.tar.gz" && tar tzf "data/evals/$RUN/results.tar.gz"
tail -5 "data/evals/$RUN/eval.log"
