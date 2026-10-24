#!/usr/bin/env bash
# One-time setup ON the Tokyo instance (Ubuntu 24.04), after:
#   git clone https://github.com/justinalick/hypermirage ~/hypermirage
#   bash ~/hypermirage/scripts/tokyo/bootstrap.sh
#
# Installs zstd, AWS CLI v2 and a Python venv, then asks for the read-only data credentials
# and the node-data config (bucket, prefix, sources). The secret is hidden; nothing is written
# into the repo.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

sudo apt-get update -qq
sudo apt-get install -y -qq zstd unzip python3-venv curl rsync >/dev/null

if ! command -v aws >/dev/null; then
  curl -sSLo /tmp/awscliv2.zip "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip"
  unzip -q -o /tmp/awscliv2.zip -d /tmp && sudo /tmp/aws/install --update >/dev/null
fi

python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install -q --upgrade pip
"$ROOT/.venv/bin/pip" install -q pyarrow orjson

if aws configure get aws_access_key_id --profile hydromancer >/dev/null 2>&1; then
  echo "using existing 'hydromancer' credentials in ~/.aws/credentials"
else
  echo
  echo "Read-only data credentials (input is hidden for the secret):"
  read -rp "  Access key ID: " K; read -rsp "  Secret: " S; echo
  aws configure set aws_access_key_id "$K" --profile hydromancer
  aws configure set aws_secret_access_key "$S" --profile hydromancer
  unset K S
fi
aws configure set region ap-northeast-1 --profile hydromancer
chmod 600 ~/.aws/credentials
grep -q 'AWS_PROFILE=hydromancer' ~/.bashrc || echo 'export AWS_PROFILE=hydromancer' >> ~/.bashrc

if [[ -s ~/.hm-node.env ]]; then
  echo "using existing ~/.hm-node.env"
else
  echo "Node-data config (values from your local private/node.env):"
  read -rp "  HM_NODE_BUCKET (no s3://): " B
  read -rp "  HM_NODE_PREFIX: " P
  read -rp "  HM_NODE_SOURCES (one line): " S
  printf 'HM_NODE_BUCKET=%s\nHM_NODE_PREFIX=%s\nHM_NODE_SOURCES="%s"\n' "$B" "$P" "$S" > ~/.hm-node.env
  unset B P S
fi
chmod 600 ~/.hm-node.env

clear
aws sts get-caller-identity --profile hydromancer --query Arn --output text
echo "ready. next: cd ~/hypermirage && scripts/node_extract_day.sh order_statuses 20261020 [20261026]"
