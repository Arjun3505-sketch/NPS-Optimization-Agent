"""Build the PLFS income-volatility calibration table from the PLFS Annual Report 2023-24.

Source: data/raw/PLFS_AnnualReport_2023-24.pdf (downloaded Day 1, see docs/data_sources.md), text
extracted via `pdftotext -layout` to data/raw/PLFS_AnnualReport_2023-24.txt. No unit-level microdata
was used (NADA registration is a Phase 2 upgrade path, not a Phase 1 blocker) -- this uses the
published, pre-tabulated national "Statement" tables from the report's Summary of Findings section,
which is the plan's documented fallback for a 1-week timeline.

All figures below are TRANSCRIBED, not fabricated, from these exact tables (all all-India, PLFS
2023-24 survey year = July 2023 - June 2024):
  - Statement 6  (p.12-13): % distribution of workers by status in employment
  - Statement 7  (p.14-15): % distribution of workers by broad industry division
  - Statement 10 (p.18):    average monthly wage/salary earnings, regular wage/salaried employees
  - Statement 11 (p.18-19): average daily wage earnings, casual labour (non-public-works)
  - Statement 12 (p.19):    average monthly (last-30-days) gross earnings, self-employed
  - Statement 14 (p.21):    unemployment rate, current weekly status (CWS)

Every number that is NOT a direct transcription (unit conversions, dispersion multipliers) is labelled
ASSUMPTION in-line and explained in docs/plfs_calibration.md -- do not add unlabelled assumptions here.

Usage:
    python -m src.data.plfs_calibration
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
OUT_PATH = PROCESSED_DIR / "plfs_calibration.csv"

# --- Statement 6: % distribution of workers by status in employment, rural+urban, PLFS 2023-24 ------
# (own-account+employer and unpaid-helper sub-categories are summed into "self_employed")
EMPLOYMENT_TYPE_SHARE_PCT = {
    "self_employed": 39.0 + 19.4,  # 58.4
    "regular_salaried": 21.7,
    "casual_labour": 19.8,
}

# --- Statement 7: % distribution of workers by broad industry division, rural+urban, PLFS 2023-24 ----
INDUSTRY_SHARE_PCT = {
    "agriculture": 46.1,
    "manufacturing": 11.4,
    "construction": 12.0,
    "trade_hotel_restaurant": 12.2,
    "transport_storage_comms": 5.6,
    "other_services": 11.9,
    "mining_quarrying": 0.2,
    "electricity_water_etc": 0.5,
}

# --- Statements 10/11/12: quarterly earnings, [rural_male, rural_female, urban_male, urban_female] --
# regular_salaried and self_employed are already monthly Rs; casual_labour is per-day Rs.
# Quarters: Q1=Jul-Sep23, Q2=Oct-Dec23, Q3=Jan-Mar24, Q4=Apr-Jun24.
QUARTERLY_CELLS = {
    "regular_salaried": {  # Statement 10, monthly Rs
        "Q1": [17791, 11071, 24739, 19363],
        "Q2": [17636, 12557, 25261, 19575],
        "Q3": [18489, 11631, 25901, 20020],
        "Q4": [18200, 12396, 26105, 19879],
    },
    "casual_labour": {  # Statement 11, per-day Rs
        "Q1": [423, 289, 520, 345],
        "Q2": [435, 287, 530, 348],
        "Q3": [437, 286, 529, 358],
        "Q4": [444, 299, 537, 364],
    },
    "self_employed": {  # Statement 12, monthly (last-30-days) Rs
        "Q1": [13269, 4719, 22371, 8600],
        "Q2": [13501, 4810, 22793, 8323],
        "Q3": [14295, 4883, 23077, 8541],
        "Q4": [14564, 5218, 23480, 8492],
    },
}

# Official, population-weighted all-India "person" monthly mean per quarter (rural+urban), as
# published directly in Statements 10/12 (already the correct weighted aggregate, not our own mean of
# the 4 cells above). Casual labour's official figure is per-day; converted to monthly separately below.
OFFICIAL_QUARTERLY_MEAN = {
    "regular_salaried": {"Q1": 20095, "Q2": 20575, "Q3": 21036, "Q4": 21103},  # Rs/month
    "casual_labour": {"Q1": 404, "Q2": 416, "Q3": 419, "Q4": 433},  # Rs/day
    "self_employed": {"Q1": 12685, "Q2": 13044, "Q3": 13487, "Q4": 13900},  # Rs/month
}

# ASSUMPTION: casual labour is converted from per-day to per-month using 24 working days/month
# (~6 days/week when work is available). Not sourced from a specific PLFS table -- the report's
# state-wise "average days worked per week" appendix table (Table 41) could not be reliably parsed
# from the extracted text in the Phase 1 window; this is a standard, commonly-used approximation in
# informal-labour literature, documented here rather than hidden. Revisit in Phase 2 if Table 41 can
# be parsed cleanly, or once unit-level microdata is available.
CASUAL_LABOUR_WORKING_DAYS_PER_MONTH = 24

# ASSUMPTION: individual-level dispersion multiplier. The cross-cell CV computed below (across
# rural/urban x male/female x 4 quarters = 16 real data points) is a REAL but understated proxy for
# individual-level income volatility -- averaging over millions of people into 4 demographic cells
# suppresses most person-to-person and month-to-month variance. These multipliers scale the measured
# cell-level CV up to a target individual-level CV, ranked by economic reasoning (casual daily-wage
# work has the most person-to-person and day-to-day swing; self-employment is next; regular
# salaried/contracted pay is the most stable by construction). NOT measured from PLFS tables --
# unit-level microdata (NADA, Phase 2) is the correct way to measure this directly and should replace
# this assumption once available.
INDIVIDUAL_DISPERSION_MULTIPLIER = {
    "regular_salaried": 1.3,
    "self_employed": 2.0,
    "casual_labour": 2.5,
}

# Statement 14: unemployment rate, current weekly status (CWS), all-India, rural+urban, person, 2023-24
UNEMPLOYMENT_RATE_CWS_PCT = 4.9


def cross_cell_cv(employment_type: str) -> float:
    """CV computed across the 16 real (quarter x rural/urban x male/female) data points."""
    values = np.array(
        [v for quarter_cells in QUARTERLY_CELLS[employment_type].values() for v in quarter_cells],
        dtype=float,
    )
    return float(values.std(ddof=1) / values.mean())


def official_mean_monthly_income(employment_type: str) -> float:
    """Mean of the 4 official quarterly national means, converted to a monthly figure."""
    quarters = OFFICIAL_QUARTERLY_MEAN[employment_type]
    values = np.array(list(quarters.values()), dtype=float)
    if employment_type == "casual_labour":
        values = values * CASUAL_LABOUR_WORKING_DAYS_PER_MONTH
    return float(values.mean())


def build_calibration_table() -> pd.DataFrame:
    rows = []
    for employment_type in QUARTERLY_CELLS:
        cell_cv = cross_cell_cv(employment_type)
        multiplier = INDIVIDUAL_DISPERSION_MULTIPLIER[employment_type]
        target_cv = cell_cv * multiplier
        rows.append(
            {
                "employment_type": employment_type,
                "population_share_pct": EMPLOYMENT_TYPE_SHARE_PCT[employment_type],
                "mean_monthly_income_rs": round(official_mean_monthly_income(employment_type), 0),
                "measured_cross_cell_cv": round(cell_cv, 4),
                "individual_dispersion_multiplier_assumption": multiplier,
                "target_individual_cv": round(target_cv, 4),
            }
        )
    df = pd.DataFrame(rows).sort_values("target_individual_cv").reset_index(drop=True)

    # Volatility tier assignment, ranked by target_individual_cv (low/medium/high).
    tier_order = ["low", "medium", "high"]
    df["volatility_tier"] = tier_order[: len(df)]
    return df


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df = build_calibration_table()
    df.to_csv(OUT_PATH, index=False)
    print(f"wrote {len(df)} rows -> {OUT_PATH}\n")
    print(df.to_string(index=False))
    print(f"\nUnemployment rate (CWS, all-India, 2023-24): {UNEMPLOYMENT_RATE_CWS_PCT}%")
    print("\nIndustry composition (rural+urban, person, PLFS 2023-24):")
    for industry, pct in sorted(INDUSTRY_SHARE_PCT.items(), key=lambda kv: -kv[1]):
        print(f"  {industry:28s} {pct:5.1f}%")


if __name__ == "__main__":
    main()
