#!/usr/bin/env bash
# Fetch Garmin data and generate a dashboard HTML file.
#
# Usage:
#   ./run_dashboard.sh weekly    # last Mon–Sun (run on Mondays)
#   ./run_dashboard.sh monthly   # previous calendar month (run on the 1st)
#
set -euo pipefail

usage() {
  echo "Usage: $0 weekly|monthly" >&2
  exit 1
}

MODE="${1:-}"
[[ "$MODE" == "weekly" || "$MODE" == "monthly" ]] || usage

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Missing .venv — run one-time setup first (see GARMIN_EXPORT.md)." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python3 garmin_dashboard.py --mode "$MODE" --fetch
