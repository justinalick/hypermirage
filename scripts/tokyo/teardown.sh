#!/usr/bin/env bash
# Terminate the extraction instance(s). Run in AWS CloudShell.
# usage: bash teardown.sh          terminate instances tagged hypermirage-extract
#        bash teardown.sh --all    also delete the security group and key pair
set -euo pipefail
export AWS_REGION=ap-northeast-1 AWS_DEFAULT_REGION=ap-northeast-1
NAME=hypermirage-extract

IDS=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=$NAME" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[].Instances[].InstanceId' --output text)
if [[ -n "$IDS" ]]; then
  echo "terminating: $IDS"
  aws ec2 terminate-instances --instance-ids $IDS >/dev/null
  aws ec2 wait instance-terminated --instance-ids $IDS
  echo "terminated."
else
  echo "no running $NAME instances."
fi

if [[ "${1:-}" == --all ]]; then
  SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NAME" \
    --query 'SecurityGroups[0].GroupId' --output text)
  [[ $SG != None ]] && aws ec2 delete-security-group --group-id "$SG" && echo "deleted security group"
  aws ec2 delete-key-pair --key-name "$NAME" 2>/dev/null && echo "deleted key pair"
fi
