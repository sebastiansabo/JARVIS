#!/usr/bin/env bash
# Quick-fire a commit digest from the command line.
#
# Usage:
#   ./scripts/send-digest.sh              # daily (default)
#   ./scripts/send-digest.sh weekly
#   ./scripts/send-digest.sh monthly
#   ./scripts/send-digest.sh daily remote  # trigger via GitHub Actions instead of local

set -euo pipefail

PERIOD="${1:-daily}"
MODE="${2:-local}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$PERIOD" != "daily" && "$PERIOD" != "weekly" && "$PERIOD" != "monthly" ]]; then
  echo "Usage: $0 [daily|weekly|monthly] [local|remote]"
  exit 1
fi

if [[ "$MODE" == "remote" ]]; then
  echo "Triggering $PERIOD digest via GitHub Actions..."
  gh workflow run daily-digest.yml --field period="$PERIOD" --field force_run=true
  sleep 5
  RUN_ID=$(gh run list --workflow=daily-digest.yml --limit=1 --json databaseId -q '.[0].databaseId')
  echo "Run $RUN_ID started — watching..."
  gh run watch "$RUN_ID" --exit-status
else
  echo "Sending $PERIOD digest locally..."
  FORCE_RUN=1 \
  DIGEST_PERIOD="$PERIOD" \
  MOBILE_PATH="${MOBILE_PATH:-$REPO_ROOT/../jarvis-mobile}" \
  python3 "$REPO_ROOT/scripts/daily_digest.py"
fi
