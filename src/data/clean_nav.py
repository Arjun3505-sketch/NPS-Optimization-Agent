"""Clean raw NPS NAV JSON into a tidy, return-bearing table.

Reads data/raw/nav/{scheme_code}.json (written by fetch_nav.py), aligns each scheme's series by date,
computes daily log returns, and writes a single long-format parquet:

    date | pfm | scheme_class | scheme_code | nav | log_return

Usage:
    python -m src.data.clean_nav
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.fetch_nav import SCHEMES

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "nav"
PROCESSED_DIR = ROOT / "data" / "processed"
OUT_PATH = PROCESSED_DIR / "nav_returns.parquet"


def load_scheme_series(scheme_code: str) -> pd.DataFrame:
    """Load one scheme's raw JSON into a date-sorted DataFrame with columns [date, nav]."""
    raw = json.loads((RAW_DIR / f"{scheme_code}.json").read_text())
    df = pd.DataFrame(raw)
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y")
    df = df.sort_values("date").drop_duplicates(subset="date").reset_index(drop=True)
    return df[["date", "nav"]]


def build_long_table() -> pd.DataFrame:
    """Combine all configured schemes into one long-format table with daily log returns."""
    frames = []
    for pfm, classes in SCHEMES.items():
        for scheme_class, code in classes.items():
            df = load_scheme_series(code)
            df["log_return"] = np.log(df["nav"] / df["nav"].shift(1))
            df["pfm"] = pfm
            df["scheme_class"] = scheme_class
            df["scheme_code"] = code
            frames.append(df)
    long_df = pd.concat(frames, ignore_index=True)
    return long_df[["date", "pfm", "scheme_class", "scheme_code", "nav", "log_return"]]


def summarize(long_df: pd.DataFrame) -> pd.DataFrame:
    """Per-scheme summary: date range, n obs, annualized mean/vol of daily log returns."""
    rows = []
    for (pfm, scheme_class), g in long_df.groupby(["pfm", "scheme_class"]):
        r = g["log_return"].dropna()
        rows.append(
            {
                "pfm": pfm,
                "scheme_class": scheme_class,
                "start": g["date"].min().date(),
                "end": g["date"].max().date(),
                "n_obs": len(g),
                "annualized_mean_return": r.mean() * 252,
                "annualized_vol": r.std() * np.sqrt(252),
            }
        )
    return pd.DataFrame(rows).sort_values(["pfm", "scheme_class"]).reset_index(drop=True)


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    long_df = build_long_table()
    long_df.to_parquet(OUT_PATH, index=False)
    print(f"wrote {len(long_df)} rows -> {OUT_PATH}")
    print()
    print(summarize(long_df).to_string(index=False))


if __name__ == "__main__":
    main()
