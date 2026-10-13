#!/bin/bash
# Deploy or update Chhaant on AWS from a checkout. Needs the AWS CLI signed in.
#   deploy/deploy.sh            first deploy: bucket, artifacts, CloudFormation stack
#   deploy/deploy.sh update     ship the current commit to the running instance and restart
set -euo pipefail
REGION=${AWS_REGION:-ap-south-1}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET=${CHHAANT_BUCKET:-chhaant-$ACCOUNT-$REGION}
STACK=${CHHAANT_STACK:-chhaant}
cd "$(dirname "$0")/.."

# Code: exactly the committed tree, nothing else from the working copy.
mkdir -p data/deploy
# autocrlf off: on Windows, git archive would otherwise write CRLF scripts that bash on the server rejects
git -c core.autocrlf=false archive --format=tar.gz -o data/deploy/chhaant.tar.gz HEAD

if [ "${1:-}" != "update" ]; then
  aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null || {
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" --create-bucket-configuration LocationConstraint="$REGION"
    aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
      BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
    aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
      '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  }
  aws s3 cp models/chhaant_quality_v1.onnx "s3://$BUCKET/artifacts/chhaant_quality_v1.onnx" --region "$REGION"
fi
aws s3 cp data/deploy/chhaant.tar.gz "s3://$BUCKET/artifacts/chhaant.tar.gz" --region "$REGION"

if [ "${1:-}" = "update" ]; then
  INSTANCE=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)
  aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE" --document-name AWS-RunShellScript \
    --comment "chhaant update $(git rev-parse --short HEAD)" --parameters commands="[
      \"/opt/cool/venvs/python_3.12/bin/python -c \\\"import boto3; boto3.client('s3', region_name='$REGION').download_file('$BUCKET', 'artifacts/chhaant.tar.gz', '/tmp/chhaant.tar.gz')\\\"\",
      \"tar xzf /tmp/chhaant.tar.gz -C /srv/chhaant\",
      \"CHHAANT_BUCKET=$BUCKET AWS_REGION=$REGION bash /srv/chhaant/deploy/bootstrap.sh\"]" --query "Command.CommandId" --output text
  exit 0
fi

aws cloudformation deploy --region "$REGION" --stack-name "$STACK" --template-file deploy/chhaant.yaml \
  --capabilities CAPABILITY_IAM --parameter-overrides ArtifactBucket="$BUCKET"
aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" --query "Stacks[0].Outputs" --output table
