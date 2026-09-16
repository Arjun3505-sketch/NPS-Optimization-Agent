#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -d .venv ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate

if [[ ! -f .venv/.requirements-installed ]]; then
  echo "== Install Python dependencies =="
  python -m pip install -r requirements.txt
  touch .venv/.requirements-installed
else
  echo "== Python dependencies already installed; skipping =="
fi

echo "== Fetch and clean NAV data =="
python -m src.data.fetch_nav
python -m src.data.clean_nav

PLFS_PDF="data/raw/PLFS_AnnualReport_2023-24.pdf"
PLFS_TXT="data/raw/PLFS_AnnualReport_2023-24.txt"

if [[ ! -f "$PLFS_PDF" ]]; then
  echo "Missing $PLFS_PDF"
  echo "Download PLFS Annual Report 2023-24 and save it at that path, then rerun."
  exit 1
fi

if ! command -v pdftotext >/dev/null 2>&1; then
  echo "Missing pdftotext. Install Poppler first: brew install poppler or sudo apt install poppler-utils"
  exit 1
fi

echo "== Extract and calibrate PLFS data =="
pdftotext -layout "$PLFS_PDF" "$PLFS_TXT"
python -m src.data.plfs_calibration

echo "== Generate synthetic income paths =="
python -m src.simulation.income_paths

echo "== Run PFRDA baseline =="
python -m src.simulation.market

echo "== Run glide-path optimizer =="
python -m src.optimization.glide_path_optimizer

echo "Pipeline complete."
