"""Fetch NPS scheme-wise historical NAV data from npsnav.in.

Source verified 2026-08-11 (see docs/data_sources.md): npsnav.in is a free, no-auth JSON API with
~5 years of daily NAV history per scheme (2021-08-05 -> present at time of writing). Data is
CC BY-NC 4.0 -- cite the source, don't redistribute commercially.

Usage:
    python -m src.data.fetch_nav
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

# Tier I scheme codes resolved on Day 1 for two PFMs (see docs/data_sources.md).
# Using two PFMs bounds scope for Phase 1; more can be added in Phase 2 for robustness.
SCHEMES: dict[str, dict[str, str]] = {
    "SBI": {
        "E": "SM001003",  # SBI Pension Fund Scheme E - Tier I (equity)
        "C": "SM001004",  # SBI Pension Fund Scheme C - Tier I (corporate debt)
        "G": "SM001005",  # SBI Pension Fund Scheme G - Tier I (government securities)
    },
    "HDFC": {
        "E": "SM008001",  # HDFC Pension Fund Scheme E - Tier I
        "C": "SM008002",  # HDFC Pension Fund Scheme C - Tier I
        "G": "SM008003",  # HDFC Pension Fund Scheme G - Tier I
    },
}

BASE_URL = "https://npsnav.in/api/historical/{scheme_code}"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "nav"
REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = 1.0  # be polite to a free third-party API


def fetch_scheme_history(scheme_code: str) -> list[dict]:
    """Fetch full historical NAV series for one scheme code. Returns list of {date, nav} dicts."""
    url = BASE_URL.format(scheme_code=scheme_code)
    resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "nps-glidepath-research/0.1"})
    resp.raise_for_status()
    payload = resp.json()
    # npsnav.in wraps the series under a "data" key based on Day 1 verification of /api/latest-min;
    # be defensive in case the historical endpoint's shape differs slightly.
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    if isinstance(payload, list):
        return payload
    raise ValueError(f"Unexpected response shape for {scheme_code}: {type(payload)}")


def fetch_all(force: bool = False) -> None:
    """Fetch and cache raw NAV history for every scheme in SCHEMES to data/raw/nav/{code}.json."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for pfm, classes in SCHEMES.items():
        for scheme_class, code in classes.items():
            out_path = RAW_DIR / f"{code}.json"
            if out_path.exists() and not force:
                print(f"skip  {pfm} {scheme_class} ({code}) — already cached at {out_path}")
                continue
            print(f"fetch {pfm} {scheme_class} ({code}) ...", end=" ", flush=True)
            history = fetch_scheme_history(code)
            out_path.write_text(json.dumps(history))
            print(f"{len(history)} points -> {out_path}")
            time.sleep(REQUEST_DELAY_SECONDS)


if __name__ == "__main__":
    fetch_all()
