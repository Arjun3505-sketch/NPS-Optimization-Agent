"""Generate synthetic subscriber income + NPS contribution trajectories, calibrated to PLFS.

Reads data/processed/plfs_calibration.csv (Day 3) for cohort weights, mean income, and target
individual-level CV per employment type, then simulates monthly income/contribution paths for N
synthetic subscribers over T years.

This module is the paper's core methodological contribution -- every number that is not directly
derived from data/processed/plfs_calibration.csv is a documented, labelled ASSUMPTION (see the
`Assumption` dataclass fields below and docs/plfs_calibration.md / docs/phase1_status.md for the
reasoning). Nothing here is fabricated data presented as real.

Methodology, per subscriber:
  1. Draw employment_type from PLFS population shares; draw a "typical" (career-baseline) monthly
     income from a lognormal fit (method-of-moments) to the cohort's PLFS mean and a CROSS-SECTIONAL
     share of its target CV (between-subscriber heterogeneity within a cohort).
  2. self_employed/casual_labour subscribers additionally get a `sector` tag (agriculture/
     construction/other) restricted to informal-leaning industries, used only for the seasonal
     overlay. regular_salaried is assumed non-seasonal (flat monthly pay).
  3. Month-to-month volatility is an AR(1) process on log-income, calibrated so its stationary CV
     matches a TEMPORAL share of the cohort's target CV (within-subscriber, over time).
  4. A Bernoulli "disruption month" (zero/severely-reduced income) is drawn each month, with
     probability anchored to PLFS's national CWS unemployment rate (4.9%) and scaled by employment
     type.
  5. Contribution capacity: contribution_t = propensity * max(0, income_t - subsistence_floor) --
     propensity applies to DISCRETIONARY income (above subsistence), not gross income. NOTE: the
     original plan wrote this as `max(0, propensity*income - floor)`; that formula was tried first and
     produced unrealistic results (regular-salaried subscribers skipping contributions ~25% of the
     time, casual labour ~99% of the time -- see docs/phase1_status.md Day 4 for the numbers), because
     it requires propensity > floor/income just to reach a positive contribution, which forces
     implausibly high "propensity" values to avoid near-total skipping. Applying propensity to
     discretionary income instead is the standard permanent-income/marginal-propensity-to-save
     formulation and produces plausible, realistic contribution levels -- documented here as a
     corrected implementation, not a silent deviation.
     This naturally produces a contribution "skip" whenever income falls below the floor -- i.e. the
     skip emerges from the affordability constraint acting on already-stochastic income, rather than
     from a separate independent coin-flip. An additional behavioural skip probability is applied
     specifically in disruption months, on top of the affordability floor.

Why the CV is split into cross-sectional and temporal components: PLFS's published tables give a
CV that blends between-person and across-quarter variation (see docs/plfs_calibration.md) -- there is
no way to cleanly separate "people differ" from "a given person's income fluctuates" from published
aggregate tables alone. CROSS_SECTIONAL_CV_SHARE below fixes an even 50/50 split as the simplest
defensible prior in the absence of panel data; unit-level PLFS microdata (Phase 2, NADA) would let
this be measured directly instead of assumed.

Usage:
    python -m src.simulation.income_paths
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_PATH = ROOT / "data" / "processed" / "plfs_calibration.csv"
OUT_PATH = ROOT / "data" / "processed" / "synthetic_income_paths.parquet"

# ASSUMPTION: how much of the PLFS-measured target CV is between-subscriber (cross-sectional) vs.
# within-subscriber-over-time (temporal). No PLFS aggregate table can separate these; 50/50 is the
# simplest defensible prior. See module docstring and docs/plfs_calibration.md.
CROSS_SECTIONAL_CV_SHARE = 0.5

# 36 years from a start age of 25 reaches age 60 exactly -- India's standard NPS retirement age --
# so the simulation actually exercises PFRDA's "55 & above" plateau (the most conservative, most
# consequential part of every Auto Choice schedule), which a shorter horizon would never reach.
N_YEARS_DEFAULT = 36
MONTHS_PER_YEAR = 12


@dataclass(frozen=True)
class EmploymentAssumptions:
    """Per-employment-type modeling assumptions. None of these are PLFS-measured; every value here
    is a labelled judgment call, documented in docs/plfs_calibration.md and docs/phase1_status.md."""

    # AR(1) persistence of month-to-month log-income shocks. Higher = a bad/good spell persists
    # longer. Salaried pay is contractually fixed month to month (low persistence in the residual
    # since there's little residual to persist); informal income swings are believed to cluster
    # (a slow season stays slow).
    ar1_rho: float
    # Annual nominal income growth (trend). ASSUMPTION, not measured from a multi-year PLFS series --
    # the extracted Statements 10/11/12 only cover the 2023-24 survey year (see docs/plfs_calibration.md).
    annual_growth: float
    # Multiplier on the PLFS national CWS unemployment rate (4.9%) used as this cohort's monthly
    # "disruption" (zero/severely-reduced income) probability base rate.
    disruption_rate_multiplier: float
    # Share of monthly income kept during a disruption month (uniform draw between this and 1.0).
    disruption_severity_floor: float
    # Share of (post-floor) income directed to NPS contributions, applied above subsistence_floor.
    contribution_propensity: float
    # Extra probability of skipping a contribution entirely in a disruption month, even if the
    # affordability formula would still allow a small positive contribution -- behavioural/liquidity
    # friction beyond pure affordability.
    extra_skip_prob_in_disruption: float


# ASSUMPTION block -- see docstring above and docs/plfs_calibration.md for the reasoning behind each
# cohort's relative ordering (not absolute values, which are illustrative judgment calls).
ASSUMPTIONS: dict[str, EmploymentAssumptions] = {
    "regular_salaried": EmploymentAssumptions(
        ar1_rho=0.10,
        annual_growth=0.06,
        disruption_rate_multiplier=0.3,
        disruption_severity_floor=0.7,
        contribution_propensity=0.20,
        extra_skip_prob_in_disruption=0.05,
    ),
    "self_employed": EmploymentAssumptions(
        ar1_rho=0.45,
        annual_growth=0.05,
        disruption_rate_multiplier=1.5,
        disruption_severity_floor=0.3,
        contribution_propensity=0.10,
        extra_skip_prob_in_disruption=0.30,
    ),
    "casual_labour": EmploymentAssumptions(
        ar1_rho=0.55,
        annual_growth=0.04,
        disruption_rate_multiplier=3.0,
        disruption_severity_floor=0.1,
        contribution_propensity=0.08,
        extra_skip_prob_in_disruption=0.40,
    ),
}

# ASSUMPTION: subsistence floor below which no income is directed to NPS. A round, illustrative
# monthly subsistence-expenditure figure -- deliberately NOT presented as a specific cited statistic,
# since it was not verified against a specific source (e.g. HCES/MPCE or an official poverty line) in
# this session. Flagged for Phase 2 replacement with a verified, cited figure.
SUBSISTENCE_FLOOR_RS = 5000.0

# ASSUMPTION: sector tagging (for seasonal overlay only) is restricted to informal-leaning industries
# for self_employed/casual_labour subscribers, since the PLFS employment-type x industry JOINT
# distribution was not extracted in the Phase 1 window (only each marginal was -- see
# docs/plfs_calibration.md). Shares below are renormalized from the real INDUSTRY_SHARE_PCT marginal
# in src/data/plfs_calibration.py, restricted to this subset -- not a real joint distribution.
INFORMAL_SECTOR_SHARE = {
    "agriculture": 46.1,
    "construction": 12.0,
    "trade_hotel_restaurant": 12.2,
    "other_services": 11.9,
}
SEASONAL_SECTORS = {"agriculture", "construction"}
# ASSUMPTION: log-space monthly seasonal multipliers, amplitude ~15% (per plan), normalized to zero
# mean so a cohort's annual average income is unaffected. Stylized from India's known agricultural
# (kharif harvest ~Oct-Nov, rabi harvest ~Mar-Apr) and monsoon-construction-slowdown (~Jun-Sep)
# calendars -- not fitted to a specific PLFS quarterly series (see docs/plfs_calibration.md).
SEASONAL_LOG_MULTIPLIERS = {
    # Jan  Feb  Mar   Apr   May   Jun   Jul   Aug   Sep   Oct   Nov   Dec
    "agriculture": [0.05, 0.05, 0.15, 0.10, -0.05, -0.15, -0.15, -0.10, -0.05, 0.10, 0.15, 0.05],
    "construction": [0.05, 0.05, 0.05, 0.05, 0.00, -0.15, -0.20, -0.20, -0.10, 0.05, 0.10, 0.10],
}
for _sector, _vals in SEASONAL_LOG_MULTIPLIERS.items():
    _vals = list(np.array(_vals) - np.mean(_vals))  # force exactly zero-mean
    SEASONAL_LOG_MULTIPLIERS[_sector] = _vals


def load_calibration() -> pd.DataFrame:
    return pd.read_csv(CALIBRATION_PATH).set_index("employment_type")


def lognormal_params(mean: float, cv: float) -> tuple[float, float]:
    """Method-of-moments fit: return (mu, sigma) of a lognormal with given mean and CV."""
    sigma2 = np.log(1 + cv**2)
    mu = np.log(mean) - sigma2 / 2
    return mu, np.sqrt(sigma2)


def assign_cohorts(n_subscribers: int, calibration: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Assign each subscriber an employment_type (PLFS-weighted) and, for informal types, a sector."""
    employment_types = calibration.index.to_numpy()
    weights = calibration["population_share_pct"].to_numpy(dtype=float)
    weights = weights / weights.sum()
    employment_type = rng.choice(employment_types, size=n_subscribers, p=weights)

    informal_sectors = list(INFORMAL_SECTOR_SHARE.keys())
    informal_weights = np.array(list(INFORMAL_SECTOR_SHARE.values()), dtype=float)
    informal_weights = informal_weights / informal_weights.sum()

    sector = np.full(n_subscribers, "", dtype=object)
    is_informal = np.isin(employment_type, ["self_employed", "casual_labour"])
    n_informal = int(is_informal.sum())
    sector[is_informal] = rng.choice(informal_sectors, size=n_informal, p=informal_weights)

    return pd.DataFrame(
        {
            "subscriber_id": np.arange(n_subscribers),
            "employment_type": employment_type,
            "sector": sector,
            "volatility_tier": calibration.loc[employment_type, "volatility_tier"].to_numpy(),
        }
    )


def simulate_income_paths(
    n_subscribers: int = 2000,
    n_years: int = N_YEARS_DEFAULT,
    seed: int = 42,
) -> pd.DataFrame:
    """Simulate monthly income + NPS contribution paths for n_subscribers over n_years.

    Returns a long-format DataFrame: subscriber_id, employment_type, sector, volatility_tier,
    month_index (0-based, 0 = first simulated month), income, is_disruption_month, contribution.
    """
    rng = np.random.default_rng(seed)
    calibration = load_calibration()
    cohorts = assign_cohorts(n_subscribers, calibration, rng)
    n_months = n_years * MONTHS_PER_YEAR

    all_frames = []
    for employment_type, group in cohorts.groupby("employment_type"):
        n = len(group)
        row = calibration.loc[employment_type]
        assumptions = ASSUMPTIONS[employment_type]

        # Step 1: cross-sectional draw of each subscriber's "typical" baseline monthly income.
        cross_cv = row["target_individual_cv"] * np.sqrt(CROSS_SECTIONAL_CV_SHARE)
        mu, sigma_cross = lognormal_params(row["mean_monthly_income_rs"], cross_cv)
        base_income = rng.lognormal(mean=mu, sigma=sigma_cross, size=n)

        # Step 3 setup: AR(1) temporal shock process calibrated to the temporal CV share.
        temporal_cv = row["target_individual_cv"] * np.sqrt(1 - CROSS_SECTIONAL_CV_SHARE)
        sigma_x = np.sqrt(np.log(1 + temporal_cv**2))  # stationary std of the AR(1) log-shock
        rho = assumptions.ar1_rho
        sigma_eps = sigma_x * np.sqrt(1 - rho**2)

        # AR(1) shocks: (n, n_months), start each series at its stationary distribution.
        shocks = np.zeros((n, n_months))
        shocks[:, 0] = rng.normal(0, sigma_x, size=n)
        eps = rng.normal(0, sigma_eps, size=(n, n_months - 1))
        for t in range(1, n_months):
            shocks[:, t] = rho * shocks[:, t - 1] + eps[:, t - 1]

        # Trend: monthly compounding of the annual nominal growth assumption.
        monthly_growth = (1 + assumptions.annual_growth) ** (1 / MONTHS_PER_YEAR) - 1
        trend = np.log(1 + monthly_growth) * np.arange(n_months)  # (n_months,), log-space

        # Seasonal overlay: zero unless subscriber's sector is in SEASONAL_SECTORS.
        seasonal = np.zeros((n, n_months))
        sectors = group["sector"].to_numpy()
        for i, sec in enumerate(sectors):
            if sec in SEASONAL_SECTORS:
                pattern = np.array(SEASONAL_LOG_MULTIPLIERS[sec])
                seasonal[i, :] = np.tile(pattern, n_months // MONTHS_PER_YEAR + 1)[:n_months]

        log_income = np.log(base_income)[:, None] + trend[None, :] + shocks + seasonal
        income = np.exp(log_income)

        # Step 4: disruption months. Base rate is PLFS's national CWS unemployment rate (4.9%,
        # Statement 14), scaled per employment type (see EmploymentAssumptions docstring).
        disruption_prob = min(0.95, 0.049 * assumptions.disruption_rate_multiplier)
        is_disruption = rng.random((n, n_months)) < disruption_prob
        severity = rng.uniform(assumptions.disruption_severity_floor, 1.0, size=(n, n_months))
        income = np.where(is_disruption, income * severity, income)

        # Step 5: contribution capacity (propensity applied to discretionary income above the
        # subsistence floor -- see module docstring for why this differs from the plan's original
        # literal formula), with an extra behavioural skip in disruption months.
        contribution = assumptions.contribution_propensity * np.maximum(0.0, income - SUBSISTENCE_FLOOR_RS)
        extra_skip = is_disruption & (rng.random((n, n_months)) < assumptions.extra_skip_prob_in_disruption)
        contribution = np.where(extra_skip, 0.0, contribution)

        frame = pd.DataFrame(
            {
                "subscriber_id": np.repeat(group["subscriber_id"].to_numpy(), n_months),
                "employment_type": employment_type,
                "sector": np.repeat(sectors, n_months),
                "volatility_tier": row["volatility_tier"],
                "month_index": np.tile(np.arange(n_months), n),
                "income": income.ravel(),
                "is_disruption_month": is_disruption.ravel(),
                "contribution": contribution.ravel(),
            }
        )
        all_frames.append(frame)

    return pd.concat(all_frames, ignore_index=True)


def main() -> None:
    df = simulate_income_paths()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    print(f"wrote {len(df)} rows ({df.subscriber_id.nunique()} subscribers x "
          f"{df.month_index.nunique()} months) -> {OUT_PATH}")

    print("\nPer-cohort sanity check (target CV from calibration vs. simulated CV of monthly income):")
    print("(simulated CV > target CV is expected: the disruption/Bernoulli shock mechanism adds a")
    print(" distinct source of variance not included in the AR(1)+cross-sectional CV budget -- the")
    print(" calibration target is a floor, not an exact match. See docs/phase1_status.md Day 4.)")
    calibration = load_calibration()
    for employment_type, g in df.groupby("employment_type"):
        target_cv = calibration.loc[employment_type, "target_individual_cv"]
        sim_cv = g["income"].std() / g["income"].mean()
        pct_zero_contribution = (g["contribution"] == 0).mean() * 100
        mean_contribution = g.loc[g["contribution"] > 0, "contribution"].mean()
        print(
            f"  {employment_type:18s} target_cv={target_cv:.3f}  simulated_cv={sim_cv:.3f}  "
            f"pct_zero_contribution_months={pct_zero_contribution:5.1f}%  "
            f"mean_contribution_when_positive={mean_contribution:8.0f}"
        )


if __name__ == "__main__":
    main()
