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
    # The fund's very first calendar month is its NFO (new-fund-offer) period: NAV is pegged flat, so
    # every day after the first produces a real 0.0 log-return (not NaN), and the whole month SURVIVES
    # a plain .dropna() (groupby().sum() defaults to skipna=True) -- verified against real data (SBI's
    # NAV is flat at 10.0 for the rest of May 2009). That's a fabricated, zero-volatility,
    # zero-correlation "month," not a real market observation, so exclude it explicitly rather than
    # relying on dropna(), which only ever drops the single first day's NaN, not the month it's in.
    first_month = df["month"].min()
    monthly_log = monthly_log.loc[monthly_log.index != first_month]
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
    n_years: int = 36,  # age 25 -> 60 (NPS standard retirement age), reaches PFRDA's "55 & above" plateau
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


# ASSUMPTION (Phase 2 Week 1): a subscriber is considered to have started "meaningfully accumulating"
# once cumulative contributions reach this level -- below it, corpus/cumulative_contributions is noisy
# and not economically meaningful (e.g. a single partial first month), so the shortfall check is
# skipped until this floor is crossed. A round, illustrative number, not a cited statistic.
MIN_CUM_CONTRIB_FOR_SHORTFALL_CHECK_RS = 1000.0

# ASSUMPTION (Phase 2 Week 1): "shortfall" means the corpus has fallen to less than this fraction of
# cumulative contributions to date, at ANY point in the horizon. Chosen deliberately above 1.0 (pure
# break-even) because a break-even threshold triggers near-universally in early months for every glide
# path (before returns have had time to compound past a run of real, block-bootstrapped drawdown
# months), which would saturate the metric near 100% regardless of tier -- uninformative. 0.9
# represents "a meaningfully painful shortfall," not point-in-time noise. See docs/phase1_status.md
# Phase 2 Week 1 for the full reasoning.
DEFAULT_SHORTFALL_THRESHOLD = 0.9


def simulate_path_dependent_metrics_for_weight_path(
    weight_path: np.ndarray,
    contributions: np.ndarray,
    n_market_trials: int = 200,
    seed: int = 0,
    shortfall_threshold: float = DEFAULT_SHORTFALL_THRESHOLD,
    min_cum_contrib_for_shortfall_check: float = MIN_CUM_CONTRIB_FOR_SHORTFALL_CHECK_RS,
    compute_xirr: bool = True,
) -> dict[str, np.ndarray]:
    """Phase 2 Week 1: path-dependent risk metrics, motivated directly by the Phase 1 Day 6 finding
    that terminal-wealth-only objectives (including CVaR-10% of terminal wealth) never differentiate
    the optimal glide path by volatility tier -- see docs/phase1_status.md and this module's sibling
    `glide_path_optimizer.py` docstring for the full diagnostic. This function does NOT assume that
    path-dependent metrics will differentiate either -- that must be tested (see
    src/optimization/glide_path_optimizer.py's path-dependent objective), not presumed here.

    Extends `simulate_terminal_corpus_for_weight_path`'s exact corpus recursion (same block-bootstrap
    engine, same month-by-month loop) with two additional, INCREMENTALLY computed metrics -- the full
    (n_trials, n_subscribers, n_months) corpus path is deliberately never materialized (it would be
    ~1.3GB at the full 2,000-subscriber population, ~800MB even for just the largest volatility tier);
    everything below is an O(1)-per-month running update instead.

    1. Intra-horizon shortfall: whether corpus/cumulative_contributions ever drops below
       `shortfall_threshold` at any point after `min_cum_contrib_for_shortfall_check` has been reached
       (see the two ASSUMPTION constants above for why these specific values). Also tracks the worst
       funded ratio reached, a richer severity diagnostic beyond the binary breach flag.
    2. Money-weighted return (XIRR): solves for the monthly rate r such that
       `NPV(r) = -sum_t contributions[t]*(1+r)^-t + terminal_corpus*(1+r)^-(n_months-1) = 0`,
       annualized as `(1+r)^12 - 1`. Unlike terminal wealth or CAGR, XIRR is sensitive to WHEN
       contributions land relative to returns -- a contribution added right before a rally counts more
       than one added right before a crash -- which is exactly the sequence-risk channel Phase 1's
       diagnostic pointed to. Solved via a manual vectorized Newton's method (see `_xirr_annualized`
       below for why, not `numpy_financial`). `compute_xirr=False` skips this (the more expensive) step
       for callers (e.g. a grid search's inner loop) that only need the cheaper shortfall metric.

    Returns a dict: {"terminal_corpus", "ever_shortfall" (bool), "worst_funded_ratio",
    "annualized_xirr" (or None if compute_xirr=False)}, all shaped (n_market_trials, n_subscribers)
    except annualized_xirr which is (n_market_trials, n_subscribers) too, computed once after all
    trials (it only needs the trial-invariant contribution timing plus each trial's terminal value, not
    the intermediate path -- see `_xirr_annualized`).
    """
    n_months, n_assets = weight_path.shape
    assert n_assets == 3, "weight_path must have 3 columns: [w_E, w_C, w_G]"
    assert contributions.shape[1] == n_months, "contributions and weight_path month counts must match"
    n_subscribers = contributions.shape[0]

    rng = np.random.default_rng(seed)
    monthly_returns = load_monthly_returns()

    # Trial-invariant (contributions don't depend on the market path) -- compute once, not per trial.
    cum_contributions = np.cumsum(contributions, axis=1)  # (n_subscribers, n_months)

    terminal_corpus = np.zeros((n_market_trials, n_subscribers))
    ever_shortfall = np.zeros((n_market_trials, n_subscribers), dtype=bool)
    worst_funded_ratio = np.full((n_market_trials, n_subscribers), np.inf)

    for trial in range(n_market_trials):
        r_path = block_bootstrap_path(monthly_returns, n_months, BLOCK_SIZE_MONTHS, rng)
        port_return = (r_path * weight_path).sum(axis=1)

        corpus = np.zeros(n_subscribers)
        trial_worst = np.full(n_subscribers, np.inf)
        trial_breach = np.zeros(n_subscribers, dtype=bool)
        for t in range(n_months):
            corpus = corpus * (1 + port_return[t]) + contributions[:, t]
            cum_t = cum_contributions[:, t]
            eligible = cum_t >= min_cum_contrib_for_shortfall_check
            if eligible.any():
                funded_ratio = np.divide(
                    corpus, cum_t, out=np.full(n_subscribers, np.inf), where=eligible
                )
                trial_worst = np.where(eligible, np.minimum(trial_worst, funded_ratio), trial_worst)
                trial_breach |= eligible & (funded_ratio < shortfall_threshold)
        terminal_corpus[trial] = corpus
        worst_funded_ratio[trial] = trial_worst
        ever_shortfall[trial] = trial_breach

    annualized_xirr = (
        _xirr_annualized(contributions, terminal_corpus, n_months) if compute_xirr else None
    )

    return {
        "terminal_corpus": terminal_corpus,
        "ever_shortfall": ever_shortfall,
        "worst_funded_ratio": worst_funded_ratio,
        "annualized_xirr": annualized_xirr,
    }


# Per-iteration clip bounds on the MONTHLY rate during Newton's method. Tighter than the economically
# plausible range on purpose: with n_months up to 432, a discount factor (1+r)^-t computed at r near
# -0.99 overflows float64 well before t=432 (e.g. 0.01^-431 vastly exceeds float64's ~1.8e308 max),
# corrupting that iteration's npv/dnpv and, empirically, sending some (trial, subscriber) cells to wild
# non-convergent values that then dominate any aggregate (mean) computed over the output -- this was
# caught by comparing the median (sane, ~0.10) against the mean (78.6!) on a real test run, not assumed
# safe. +-0.3/month (-95.5% to +2,229% annualized) is already far wider than any realistic outcome in
# this simulation and keeps (1+r)^-432 comfortably representable (~1e66 at the boundary).
_XIRR_MONTHLY_RATE_CLIP = 0.3


def _xirr_annualized(
    contributions: np.ndarray,
    terminal_corpus: np.ndarray,
    n_months: int,
    max_iter: int = 100,
    tol: float = 1e-9,
) -> np.ndarray:
    """Solve monthly money-weighted return (XIRR) per (trial, subscriber) via vectorized Newton's
    method, then annualize. Cells that fail to converge within `max_iter` (or whose solved rate sits
    exactly at the numerical safety clip -- a sign of a pathological cash-flow shape rather than a real
    answer) are returned as NaN, not silently included as if they were valid -- callers should report
    the NaN count/rate as an honest caveat (see `simulate_path_dependent_metrics_for_weight_path`).

    Why a manual solver instead of `numpy_financial.irr`: numpy_financial's IRR is a general
    polynomial-root solver (via `numpy.roots`) meant for arbitrary cash-flow sequences, and is known to
    be numerically unstable / return spurious roots on many-term sequences. Here the cash-flow shape is
    known and constrained in advance (up to `n_months` contribution outflows of a known sign, one
    terminal inflow), so a purpose-built Newton solver on `NPV(r)=0` is simpler to reason about and,
    critically, vectorizes over all (trial, subscriber) pairs simultaneously via a month-loop-per-
    iteration structure -- avoiding ever materializing a (n_trials, n_subscribers, n_months) discount
    array (which would reintroduce the exact memory problem this module's docstring above avoids).
    Validated against hand-computable closed-form cases before use on real data -- see
    tests/test_xirr.py.

    Sign convention: contributions are cash OUTFLOWS from the subscriber's perspective (negative in the
    NPV), terminal_corpus is the one cash INFLOW, realized at the end of the last month (n_months-1).
    """
    n_trials, n_subscribers = terminal_corpus.shape
    r = np.full((n_trials, n_subscribers), 0.01)  # initial guess: 1%/month (~12.7%/year)
    converged_mask = np.zeros((n_trials, n_subscribers), dtype=bool)  # overwritten each iteration below

    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        for _ in range(max_iter):
            npv = np.zeros((n_trials, n_subscribers))
            dnpv = np.zeros((n_trials, n_subscribers))
            disc = np.ones((n_trials, n_subscribers))
            for t in range(n_months):
                c_t = contributions[:, t][None, :]  # (1, n_subs) broadcasts to (n_trials, n_subs)
                npv += -c_t * disc
                dnpv += c_t * t * disc / (1 + r)
                if t == n_months - 1:
                    npv += terminal_corpus * disc
                    dnpv += -terminal_corpus * t * disc / (1 + r)
                disc = disc / (1 + r)

            dnpv_safe = np.where(dnpv == 0, np.nan, dnpv)
            step = np.nan_to_num(npv / dnpv_safe, nan=0.0, posinf=0.0, neginf=0.0)
            r_new = np.clip(r - step, -_XIRR_MONTHLY_RATE_CLIP, _XIRR_MONTHLY_RATE_CLIP)
            converged_mask = np.abs(r_new - r) < tol
            r = r_new
            if converged_mask.all():
                break

    # A cell sitting exactly at the clip boundary never actually converged -- it was pinned there by
    # the safety clamp, not solved. Treat both non-convergence and boundary-pinning as failures.
    at_boundary = np.isclose(np.abs(r), _XIRR_MONTHLY_RATE_CLIP, atol=1e-6)
    valid = converged_mask & ~at_boundary

    n_failed = int((~valid).sum())
    if n_failed > 0:
        print(
            f"  [xirr] {n_failed}/{r.size} ({100*n_failed/r.size:.2f}%) cells did not converge to a "
            "valid rate -- returned as NaN, excluded from any downstream mean/median."
        )

    annualized = (1 + r) ** 12 - 1
    return np.where(valid, annualized, np.nan)


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
        print(f"\n=== {fund} baseline (start age 25, 36yr, 200 market trials) ===")
        print(summarize_by_tier(terminal_corpus, meta).to_string())


if __name__ == "__main__":
    main()
