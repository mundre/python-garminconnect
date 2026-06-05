#!/usr/bin/env bash
# Cron/OpenClaw wrapper for Conda + Cairo (only needed for --format email_dashboard).
# Sets up Conda, then delegates to run_dashboard.sh.
#
# Usage:
#   export HOME=/Users/you          # required when cron omits HOME
#   export GARMINTOKENS=$HOME/.garminconnect   # optional; this is the default
#   ./run_dashboard_cron.sh weekly
#   ./run_dashboard_cron.sh monthly
#   ./run_dashboard_cron.sh weekly --format email_dashboard
#
# Optional overrides:
#   CONDA_BASE      Miniforge/Miniconda root (auto-detected under $HOME if unset)
#   CONDA_ENV_NAME  Conda env name (default: garmin)
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

if [[ -z "${HOME:-}" ]]; then
  echo "Set HOME before running (cron often omits it). Example: export HOME=/Users/you" >&2
  exit 1
fi

export GARMINTOKENS="${GARMINTOKENS:-$HOME/.garminconnect}"

CONDA_ENV_NAME="${CONDA_ENV_NAME:-garmin}"
if [[ -z "${CONDA_BASE:-}" ]]; then
  if [[ -d "$HOME/miniforge3" ]]; then
    CONDA_BASE="$HOME/miniforge3"
  elif [[ -d "$HOME/miniconda3" ]]; then
    CONDA_BASE="$HOME/miniconda3"
  else
    echo "Conda not found under \$HOME. Set CONDA_BASE or install Miniforge (see GARMIN_EXPORT.md)." >&2
    exit 1
  fi
fi

CONDA_ENV="$CONDA_BASE/envs/$CONDA_ENV_NAME"
CONDA_SH="$CONDA_BASE/etc/profile.d/conda.sh"

if [[ ! -f "$CONDA_SH" ]]; then
  echo "Missing $CONDA_SH — check CONDA_BASE ($CONDA_BASE)." >&2
  exit 1
fi

if [[ ! -d "$CONDA_ENV" ]]; then
  cat >&2 <<EOF
Conda environment '$CONDA_ENV_NAME' not found at:
  $CONDA_ENV

One-time setup (run in a terminal):

  source "$CONDA_SH"
  conda create -n $CONDA_ENV_NAME python=3.12 -y
  conda activate $CONDA_ENV_NAME
  conda install -c conda-forge cairo pango pkg-config -y
  cd "$ROOT"
  python -m venv .venv
  source .venv/bin/activate
  pip install -e ".[example]"
  python3 -c "import cairosvg; print('ok')"

See GARMIN_EXPORT.md (Option 3 — Cairo via Conda).
EOF
  exit 1
fi

# shellcheck disable=SC1091
source "$CONDA_SH"
conda activate "$CONDA_ENV_NAME"

export PKG_CONFIG_PATH="$CONDA_ENV/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export DYLD_FALLBACK_LIBRARY_PATH="$CONDA_ENV/lib${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"

exec "$ROOT/run_dashboard.sh" "$@"
