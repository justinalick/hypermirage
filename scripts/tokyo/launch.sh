#!/usr/bin/env bash
# Launch one EC2 instance in Tokyo (ap-northeast-1) for node-data extraction.
# Run in AWS CloudShell (needs EC2 permissions; the read-only data user cannot do this).
#
# usage: bash launch.sh <ssh-from-ip> <public-key-file> [instance-type]
#   ssh-from-ip      the machine you will SSH from (SSH is opened to this /32 only)
#   public-key-file  an OpenSSH public key (e.g. pasted into ~/hypermirage_tokyo.pub)
#   instance-type    default c7g.2xlarge (8 vCPU Graviton). Bigger = faster backfill.
#
# Env: SPOT=1 (default; set 0 for on-demand), MAX_HOURS=6 (instance self-terminates after
#      this many hours as a cost guard), DISK_GB=40.
set -euo pipefail

MYIP=${1:?ssh-from IP}; PUB=${2:?public key file}; TYPE=${3:-c7g.2xlarge}
export AWS_REGION=ap-northeast-1 AWS_DEFAULT_REGION=ap-northeast-1
NAME=hypermirage-extract
SPOT=${SPOT:-1}; MAX_HOURS=${MAX_HOURS:-6}; DISK_GB=${DISK_GB:-40}

case $TYPE in
  *g.*|*gd.*|*gn.*) ARCH=arm64 ;;
  *) ARCH=amd64 ;;
esac
AMI=$(aws ssm get-parameter \
  --name /aws/service/canonical/ubuntu/server/24.04/stable/current/$ARCH/hvm/ebs-gp3/ami-id \
  --query Parameter.Value --output text)

aws ec2 describe-key-pairs --key-names "$NAME" >/dev/null 2>&1 \
  || aws ec2 import-key-pair --key-name "$NAME" --public-key-material "fileb://$PUB" >/dev/null

SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NAME" \
  --query 'SecurityGroups[0].GroupId' --output text)
if [[ $SG == None ]]; then
  SG=$(aws ec2 create-security-group --group-name "$NAME" \
    --description "SSH for hypermirage extraction" --query GroupId --output text)
fi
aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 22 \
  --cidr "$MYIP/32" >/dev/null 2>&1 || true

MARKET=()
[[ $SPOT == 1 ]] && MARKET=(--instance-market-options \
  '{"MarketType":"spot","SpotOptions":{"SpotInstanceType":"one-time","InstanceInterruptionBehavior":"terminate"}}')

USERDATA=$(printf '#!/bin/bash\nshutdown -h +%d\n' $((MAX_HOURS * 60)))

ID=$(aws ec2 run-instances \
  --image-id "$AMI" --instance-type "$TYPE" --key-name "$NAME" --security-group-ids "$SG" \
  "${MARKET[@]}" \
  --instance-initiated-shutdown-behavior terminate \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":$DISK_GB,\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" \
  --user-data "$USERDATA" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
  --query 'Instances[0].InstanceId' --output text)

echo "launched $ID ($TYPE, $ARCH, spot=$SPOT); waiting for it to start..."
aws ec2 wait instance-running --instance-ids "$ID"
IP=$(aws ec2 describe-instances --instance-ids "$ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo
echo "instance: $ID"
echo "public IP: $IP"
echo "ssh:       ssh -i ~/.ssh/hypermirage_tokyo ubuntu@$IP"
echo "It terminates itself after $MAX_HOURS h. Terminate earlier with: bash teardown.sh"
