#!/usr/bin/env bash
# Fetch Garmin data and generate a dashboard HTML file.
#
# Usage:
#   ./run_dashboard.sh weekly              # email format (default)
#   ./run_dashboard.sh monthly             # email format (default)
#   ./run_dashboard.sh weekly --format dashboard
#
set -euo pipefail

usage() {
  echo "Usage: $0 weekly|monthly [garmin_dashboard.py options...]" >&2
  echo "  e.g. $0 weekly --format dashboard" >&2
  exit 1
}

MODE="${1:-}"
[[ "$MODE" == "weekly" || "$MODE" == "monthly" ]] || usage
shift

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Missing .venv — run one-time setup first (see GARMIN_EXPORT.md)." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python3 garmin_dashboard.py --mode "$MODE" --fetch "$@"
