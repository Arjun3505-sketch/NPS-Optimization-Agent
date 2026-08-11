"""Block-bootstrap Monte Carlo market engine over real NAV returns, and the baseline corpus simulator.

Uses the real, historical SBI Tier I E/C/G monthly return series (2009-05 -> 2026-08, ~207 months,
see docs/data_sources.md) as the bootstrap source. SBI is used rather than a blend with HDFC because
it has the longer history (back to 2009 vs HDFC's 2013) and Day 2's EDA showed >0.99 correlation
between PFMs for the same scheme class (E especially) -- blending would mostly just discard the extra
2009-2013 years (including the 2013 taper-tantrum drawdown) for little diversification benefit. HDFC
remains available as a Phase 2 robustness check.

Block bootstrap (not IID resampling of individual months) is used specifically to preserve real
autocorrelation/regime structure -- a bad month is more likely to be followed by another bad month in
the resampled path, matching how real drawdowns actually unfold, which a naive IID bootstrap would
destroy.

Usage:
    python -m src.simulation.market
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from src.optimization.pfrda_default import glide_path

ROOT = Path(__file__).resolve().parents[2]
NAV_RETURNS_PATH = ROOT / "data" / "processed" / "nav_returns.parquet"
INCOME_PATHS_PATH = ROOT / "data" / "processed" / "synthetic_income_paths.parquet"

BOOTSTRAP_PFM = "SBI"  # see module docstring
BLOCK_SIZE_MONTHS = 12  # 1-year blocks -- preserves within-year seasonal/momentum structure
MONTHS_PER_YEAR = 12


@lru_cache(maxsize=4)
def load_monthly_returns(pfm: str = BOOTSTRAP_PFM) -> pd.DataFrame:
    """Real historical monthly SIMPLE returns for E/C/G from one PFM's daily NAV series.

    Returns a DataFrame indexed by calendar month (Period[M]) with columns E, C, G. Cached: the Day 6
    grid-search optimizer calls this hundreds of times and the underlying parquet never changes within
    a process.
    """
    df = pd.read_parquet(NAV_RETURNS_PATH)
    df = df[df["pfm"] == pfm].copy()
    df["month"] = df["date"].dt.to_period("M")
    # Monthly log return = sum of daily log returns within the month (correct compounding); convert
    # to simple return only at the end, for use directly in the corpus recursion.
    monthly_log = df.groupby(["month", "scheme_class"])["log_return"].sum().unstack("scheme_class")
    monthly_log = monthly_log.dropna()  # drop partial first month (NaN from the very first daily diff)
    monthly_simple = np.exp(monthly_log) - 1
    return monthly_simple[["E", "C", "G"]]


def block_bootstrap_path(
    monthly_returns: pd.DataFrame, n_months: int, block_size: int, rng: np.random.Generator
) -> np.ndarray:
    """One bootstrapped path of n_months, built from randomly-placed contiguous historical blocks.

    Returns an (n_months, 3) array of simple returns [E, C, G]. All three columns are drawn from the
    SAME sampled historical months in each block, preserving real cross-asset correlation.
    """
    values = monthly_returns.to_numpy()
    m = len(values)
    if block_size > m:
        raise ValueError(f"block_size ({block_size}) exceeds available history ({m} months)")
    blocks = []
    months_so_far = 0
    while months_so_far < n_months:
        start = rng.integers(0, m - block_size + 1)
        blocks.append(values[start : start + block_size])
        months_so_far += block_size
    path = np.concatenate(blocks, axis=0)[:n_months]
    return path


def expand_glide_path_to_monthly(start_age: int, n_years: int, fund: str) -> np.ndarray:
    """Yearly PFRDA glide-path weights, held constant within each year (reallocation happens once a
    year, on the subscriber's birthday, per how Auto Choice actually works) -- expanded to (n_months, 3)."""
    yearly = glide_path(start_age, n_years, fund)[["w_E", "w_C", "w_G"]].to_numpy()
    return np.repeat(yearly, MONTHS_PER_YEAR, axis=0)


def load_contribution_matrix() -> tuple[np.ndarray, pd.DataFrame]:
    """Pivot the synthetic income-paths long table into a (n_subscribers, n_months) contribution
    matrix, plus the subscriber metadata (employment_type, volatility_tier) aligned to its rows."""
    df = pd.read_parquet(INCOME_PATHS_PATH)
    meta = df.drop_duplicates("subscriber_id")[["subscriber_id", "employment_type", "volatility_tier"]]
    meta = meta.sort_values("subscriber_id").reset_index(drop=True)
    pivot = df.pivot(index="subscriber_id", columns="month_index", values="contribution")
    pivot = pivot.reindex(meta["subscriber_id"]).sort_index()
    return pivot.to_numpy(), meta


def simulate_terminal_corpus(
    fund: str,
    start_age: int = 25,
    n_years: int = 30,
    n_market_trials: int = 200,
    seed: int = 0,
) -> tuple[np.ndarray, pd.DataFrame]:
    """Run n_market_trials bootstrapped market paths against every synthetic subscriber's real
    contribution path under a given PFRDA fund's age-based glide path.

    Returns (terminal_corpus, meta): terminal_corpus is (n_market_trials, n_subscribers) of ending
    corpus values (Rs); meta has each subscriber's employment_type/volatility_tier, row-aligned to
    terminal_corpus's second axis.
    """
    n_months = n_years * MONTHS_PER_YEAR
    contributions, meta = load_contribution_matrix()
    assert contributions.shape[1] == n_months, (
        f"contribution matrix has {contributions.shape[1]} months, expected {n_months} "
        "-- regenerate data/processed/synthetic_income_paths.parquet with matching n_years"
    )
    weight_path = expand_glide_path_to_monthly(start_age, n_years, fund)  # (n_months, 3), same for all
    terminal_corpus = simulate_terminal_corpus_for_weight_path(
        weight_path, contributions, n_market_trials=n_market_trials, seed=seed
    )
    return terminal_corpus, meta


def simulate_terminal_corpus_for_weight_path(
    weight_path: np.ndarray,
    contributions: np.ndarray,
    n_market_trials: int = 200,
    seed: int = 0,
) -> np.ndarray:
    """Low-level engine shared by the PFRDA baseline runner and the Day 6 optimizer: given an
    explicit (n_months, 3) glide-path weight array (same for every subscriber, matching how Auto
    Choice actually works -- allocation is a pure function of age) and a (n_subscribers, n_months)
    contribution matrix, run n_market_trials bootstrapped market paths and return the
    (n_market_trials, n_subscribers) terminal corpus array.
    """
    n_months, n_assets = weight_path.shape
    assert n_assets == 3, "weight_path must have 3 columns: [w_E, w_C, w_G]"
    assert contributions.shape[1] == n_months, "contributions and weight_path month counts must match"
    n_subscribers = contributions.shape[0]

    rng = np.random.default_rng(seed)
    monthly_returns = load_monthly_returns()

    terminal_corpus = np.zeros((n_market_trials, n_subscribers))
    for trial in range(n_market_trials):
        r_path = block_bootstrap_path(monthly_returns, n_months, BLOCK_SIZE_MONTHS, rng)  # (n_months,3)
        port_return = (r_path * weight_path).sum(axis=1)  # (n_months,)

        corpus = np.zeros(n_subscribers)
        for t in range(n_months):
            corpus = corpus * (1 + port_return[t]) + contributions[:, t]
        terminal_corpus[trial] = corpus

    return terminal_corpus


def summarize_by_tier(terminal_corpus: np.ndarray, meta: pd.DataFrame) -> pd.DataFrame:
    """Mean/median/P10/P90 of terminal corpus, pooled across all (trial, subscriber) pairs, by tier."""
    flat = terminal_corpus.ravel()  # (n_trials * n_subscribers,) via broadcasting below
    tier_repeated = np.tile(meta["volatility_tier"].to_numpy(), terminal_corpus.shape[0])
    df = pd.DataFrame({"volatility_tier": tier_repeated, "terminal_corpus": flat})
    summary = df.groupby("volatility_tier")["terminal_corpus"].agg(
        mean="mean", median="median",
        p10=lambda s: s.quantile(0.10), p90=lambda s: s.quantile(0.90),
    )
    return summary.round(0)


def main() -> None:
    for fund in ["LC50", "LC75"]:
        terminal_corpus, meta = simulate_terminal_corpus(fund=fund, n_market_trials=200)
        print(f"\n=== {fund} baseline (start age 25, 30yr, 200 market trials) ===")
        print(summarize_by_tier(terminal_corpus, meta).to_string())


if __name__ == "__main__":
    main()
