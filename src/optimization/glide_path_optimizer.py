"""First-cut volatility-conditioned glide-path optimizer (Phase 1 scope).

For each PLFS volatility tier (low/medium/high, from Day 3), grid-searches a minimally-parametrized
equity glide path to maximize P(Corpus_T >= target) -- the fraction of Monte Carlo trials in which
that tier's synthetic subscribers reach a target terminal corpus -- and compares the result against
the PFRDA LC50/LC75 defaults for the same tier.

Glide-path parametrization (3 free params, per the plan's "2-3 free params per tier" scope):
  - equity_start: equity weight held flat from the simulation's start age up to `inflection_age`
  - equity_end:   equity weight held flat from age 55 onward (matching PFRDA's own "55 & above" plateau)
  - inflection_age: age at which the linear decline from equity_start to equity_end begins
Between inflection_age and 55, equity declines linearly (same shape as PFRDA's own tables, just with
tunable start/end/inflection instead of PFRDA's fixed 75/50/25 %, fixed age-35 inflection). The
non-equity remainder is split between corporate debt and government securities using a FIXED
assumption (not optimized in Phase 1 -- richer, jointly-optimized C/G parametrization is explicit
Phase 2 scope, see docs/phase1_status.md and the build plan's Week 2).

Utility and the "downturn-liquidation" mechanism: the plan calls for penalizing glide paths where a
subscriber's contribution is skipped/reduced in the same period as a market downturn (forced
liquidation risk). This is NOT implemented as a separate penalty term added to the objective --
because the Monte Carlo engine already runs each tier's REAL synthetic contribution timing (which
already contains PLFS-calibrated disruption months) against REAL bootstrapped market paths, jointly:
a glide path that keeps high equity exposure for a volatile-income tier already pays for it directly
in P(Corpus_T >= target), since a disruption month coinciding with a bad market month means both no
new contribution AND a negative return applied to an equity-heavy balance. Bolting on a second,
separate penalty term would double-count a risk the joint simulation already prices in. This is a
deliberate implementation choice, not an oversight -- documented here rather than left implicit.

FINDING (important, not a bug -- see docs/phase1_status.md Day 6 and the pre-Day-8 review-pass section
for full detail and diagnostics): running this grid search produces the SAME optimal parameters
(near-max equity: equity_start=0.75, held to age 45) for all three volatility tiers -- i.e. this
first-cut setup does not yet show the volatility-CONDITIONED differentiation that is the paper's
central claim. Diagnostics (median-target P(success), P75-target P(success), CVaR-10% of terminal
wealth, and a tier-independent 1.5x-total-contributions floor target) all confirm this is not a bug:
over the real 207-month 2009-2026 bootstrap window, MORE equity dominates on every one of these
metrics for every tier, because the window's realized equity risk premium was strong enough that even
worst-decile bootstrapped outcomes still favour higher equity. This motivates, and is direct evidence
for, the CVaR-adjusted objective already planned for Phase 2 Week 1 -- and suggests the more promising
differentiator may be intra-horizon shortfall/sequence risk (being unable to add money, or needing to
draw down, at exactly the wrong time) rather than terminal-wealth distribution shape, which is worth
testing explicitly in Phase 2 rather than assumed to already be captured here. RE-TESTED, not assumed,
after N_YEARS was extended from 30 to 36 (age 25-60) specifically so this grid search would reach and
exercise PFRDA's own "55 & above" plateau, previously never reached -- the finding held.

Usage:
    python -m src.optimization.glide_path_optimizer
"""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from src.optimization.pfrda_default import glide_path
from src.simulation.market import (
    load_contribution_matrix,
    simulate_path_dependent_metrics_for_weight_path,
    simulate_terminal_corpus_for_weight_path,
)

ROOT = Path(__file__).resolve().parents[2]
FIGURES_DIR = ROOT / "docs" / "paper" / "figures"

START_AGE = 25
# 36 years reaches age 60 (NPS standard retirement age) and actually exercises PFRDA's "55 & above"
# plateau -- the prior 30yr/age-54 horizon never reached it, silently making the equity_end parameter
# below dead code under this module's own defaults.
N_YEARS = 36
MONTHS_PER_YEAR = 12

# ASSUMPTION: fixed corporate-debt share of the non-equity remainder, not jointly optimized in
# Phase 1 (see module docstring). Chosen to roughly track LC50's own C:G mix at mid-career.
CORP_DEBT_SHARE_OF_REMAINDER = 0.35

# Grid search space -- coarse, deliberately small for a Phase 1 first-cut (Phase 2 Week 2 upgrades to
# piecewise-linear knots + proper constrained optimization, per the build plan).
EQUITY_START_GRID = [0.15, 0.30, 0.45, 0.60, 0.75]
EQUITY_END_GRID = [0.05, 0.10, 0.20, 0.30]
INFLECTION_AGE_GRID = [30, 35, 40, 45]

GRID_SEARCH_TRIALS = 60  # market trials per grid point (speed) -- best point re-validated at 200
VALIDATION_TRIALS = 200  # matches the Day 5 baseline for a fair, like-for-like comparison


def build_weight_path(
    equity_start: float, equity_end: float, inflection_age: int, start_age: int = START_AGE, n_years: int = N_YEARS
) -> np.ndarray:
    """(n_months, 3) weight path for a custom 3-parameter glide path, monthly-expanded."""
    ages = start_age + np.arange(n_years)
    w_e = np.empty(n_years)
    for i, age in enumerate(ages):
        if age <= inflection_age:
            w_e[i] = equity_start
        elif age >= 55:
            w_e[i] = equity_end
        else:
            frac = (age - inflection_age) / (55 - inflection_age)
            w_e[i] = equity_start + frac * (equity_end - equity_start)
    remainder = 1 - w_e
    w_c = remainder * CORP_DEBT_SHARE_OF_REMAINDER
    w_g = remainder * (1 - CORP_DEBT_SHARE_OF_REMAINDER)
    yearly = np.stack([w_e, w_c, w_g], axis=1)
    return np.repeat(yearly, MONTHS_PER_YEAR, axis=0)


def success_probability(terminal_corpus: np.ndarray, target: float) -> float:
    return float((terminal_corpus >= target).mean())


def grid_search_tier(
    tier_contributions: np.ndarray, target: float, seed: int
) -> tuple[dict, float]:
    """Grid search over (equity_start, equity_end, inflection_age) for one tier's subscribers.

    Returns (best_params, best_success_prob) using GRID_SEARCH_TRIALS market trials per point.
    """
    best_params = None
    best_prob = -1.0
    for equity_start, equity_end, inflection_age in itertools.product(
        EQUITY_START_GRID, EQUITY_END_GRID, INFLECTION_AGE_GRID
    ):
        if equity_end > equity_start:
            continue  # only consider monotonically non-increasing (or flat) equity glide paths
        weight_path = build_weight_path(equity_start, equity_end, inflection_age)
        terminal_corpus = simulate_terminal_corpus_for_weight_path(
            weight_path, tier_contributions, n_market_trials=GRID_SEARCH_TRIALS, seed=seed
        )
        prob = success_probability(terminal_corpus, target)
        if prob > best_prob:
            best_prob = prob
            best_params = {
                "equity_start": equity_start,
                "equity_end": equity_end,
                "inflection_age": inflection_age,
            }
    return best_params, best_prob


def run_all_tiers(seed: int = 1) -> pd.DataFrame:
    contributions, meta = load_contribution_matrix()
    rows = []

    for tier in ["low", "medium", "high"]:
        tier_mask = (meta["volatility_tier"] == tier).to_numpy()
        tier_contributions = contributions[tier_mask]

        # Target: LC50 baseline's median terminal corpus for this tier (see Day 5) -- an
        # interpretable, tier-grounded target rather than an arbitrary absolute number. By
        # construction, LC50 itself should land close to 50% success against its own median.
        lc50_weight_path = _pfrda_weight_path("LC50")
        lc50_corpus = simulate_terminal_corpus_for_weight_path(
            lc50_weight_path, tier_contributions, n_market_trials=VALIDATION_TRIALS, seed=seed
        )
        target = float(np.median(lc50_corpus))

        lc75_weight_path = _pfrda_weight_path("LC75")
        lc75_corpus = simulate_terminal_corpus_for_weight_path(
            lc75_weight_path, tier_contributions, n_market_trials=VALIDATION_TRIALS, seed=seed
        )

        best_params, _ = grid_search_tier(tier_contributions, target, seed=seed)
        opt_weight_path = build_weight_path(**best_params)
        opt_corpus = simulate_terminal_corpus_for_weight_path(
            opt_weight_path, tier_contributions, n_market_trials=VALIDATION_TRIALS, seed=seed
        )

        rows.append(
            {
                "volatility_tier": tier,
                "n_subscribers": int(tier_mask.sum()),
                "target_corpus_rs": round(target, 0),
                "lc50_success_prob": success_probability(lc50_corpus, target),
                "lc75_success_prob": success_probability(lc75_corpus, target),
                "optimized_success_prob": success_probability(opt_corpus, target),
                "optimized_equity_start": best_params["equity_start"],
                "optimized_equity_end": best_params["equity_end"],
                "optimized_inflection_age": best_params["inflection_age"],
            }
        )

    return pd.DataFrame(rows)


def grid_search_tier_shortfall(tier_contributions: np.ndarray, seed: int) -> tuple[dict, float]:
    """Phase 2 Week 1: grid search minimizing P(intra-horizon shortfall) instead of Phase 1's
    terminal-wealth success probability -- the objective the Day 6 finding motivated. Uses
    `compute_xirr=False` for speed (XIRR is only computed for the final reported candidates in
    `run_all_tiers_path_dependent`, not inside this search -- see docs/phase2_status.md Week 1 for the
    ~0.3s-vs-~20s timing measurement that motivates the split).
    """
    best_params = None
    best_shortfall_prob = 2.0  # worse than any real probability, so the first candidate always wins
    for equity_start, equity_end, inflection_age in itertools.product(
        EQUITY_START_GRID, EQUITY_END_GRID, INFLECTION_AGE_GRID
    ):
        if equity_end > equity_start:
            continue
        weight_path = build_weight_path(equity_start, equity_end, inflection_age)
        result = simulate_path_dependent_metrics_for_weight_path(
            weight_path, tier_contributions, n_market_trials=GRID_SEARCH_TRIALS, seed=seed,
            compute_xirr=False,
        )
        shortfall_prob = float(result["ever_shortfall"].mean())
        if shortfall_prob < best_shortfall_prob:
            best_shortfall_prob = shortfall_prob
            best_params = {
                "equity_start": equity_start,
                "equity_end": equity_end,
                "inflection_age": inflection_age,
            }
    return best_params, best_shortfall_prob


def run_all_tiers_path_dependent(seed: int = 1) -> pd.DataFrame:
    """Phase 2 Week 1's central question: does optimizing against a path-dependent risk metric
    (intra-horizon shortfall probability) produce tier-DIFFERENTIATED glide paths, where Phase 1's
    terminal-wealth objective (`run_all_tiers`, above) did not? This must be TESTED, not assumed to
    resolve Day 6's finding -- report exactly what this shows, whichever way it goes (see
    docs/phase2_status.md Week 1).

    Uses the same seed across LC50/LC75/optimized within a tier (common random numbers, matching
    `run_all_tiers`'s convention) so the comparison isn't confounded by different bootstrapped market
    draws.
    """
    contributions, meta = load_contribution_matrix()
    rows = []

    for tier in ["low", "medium", "high"]:
        tier_mask = (meta["volatility_tier"] == tier).to_numpy()
        tier_contributions = contributions[tier_mask]

        lc50_result = simulate_path_dependent_metrics_for_weight_path(
            _pfrda_weight_path("LC50"), tier_contributions,
            n_market_trials=VALIDATION_TRIALS, seed=seed, compute_xirr=True,
        )
        lc75_result = simulate_path_dependent_metrics_for_weight_path(
            _pfrda_weight_path("LC75"), tier_contributions,
            n_market_trials=VALIDATION_TRIALS, seed=seed, compute_xirr=True,
        )

        best_params, _ = grid_search_tier_shortfall(tier_contributions, seed=seed)
        opt_result = simulate_path_dependent_metrics_for_weight_path(
            build_weight_path(**best_params), tier_contributions,
            n_market_trials=VALIDATION_TRIALS, seed=seed, compute_xirr=True,
        )

        rows.append(
            {
                "volatility_tier": tier,
                "n_subscribers": int(tier_mask.sum()),
                "lc50_shortfall_prob": float(lc50_result["ever_shortfall"].mean()),
                "lc75_shortfall_prob": float(lc75_result["ever_shortfall"].mean()),
                "optimized_shortfall_prob": float(opt_result["ever_shortfall"].mean()),
                "lc50_xirr_median": float(np.nanmedian(lc50_result["annualized_xirr"])),
                "lc75_xirr_median": float(np.nanmedian(lc75_result["annualized_xirr"])),
                "optimized_xirr_median": float(np.nanmedian(opt_result["annualized_xirr"])),
                "optimized_equity_start": best_params["equity_start"],
                "optimized_equity_end": best_params["equity_end"],
                "optimized_inflection_age": best_params["inflection_age"],
            }
        )

    return pd.DataFrame(rows)


def plot_path_dependent_comparison(results: pd.DataFrame, out_path: Path) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    x = np.arange(len(results))
    width = 0.25
    ax.bar(x - width, results["lc50_shortfall_prob"], width, label="LC50 (default)")
    ax.bar(x, results["lc75_shortfall_prob"], width, label="LC75")
    ax.bar(x + width, results["optimized_shortfall_prob"], width, label="Shortfall-minimizing (ours)")
    ax.set_xticks(x)
    ax.set_xticklabels(results["volatility_tier"])
    ax.set_ylabel("P(corpus < 90% of cumulative contributions, at any point)")
    ax.set_xlabel("PLFS income-volatility tier")
    ax.set_title("Intra-horizon shortfall probability (lower is better)")
    ax.legend()

    ax = axes[1]
    ax.bar(x - width, results["lc50_xirr_median"], width, label="LC50 (default)")
    ax.bar(x, results["lc75_xirr_median"], width, label="LC75")
    ax.bar(x + width, results["optimized_xirr_median"], width, label="Shortfall-minimizing (ours)")
    ax.set_xticks(x)
    ax.set_xticklabels(results["volatility_tier"])
    ax.set_ylabel("Median annualized XIRR")
    ax.set_xlabel("PLFS income-volatility tier")
    ax.set_title("Money-weighted return (context, not the search objective)")
    ax.legend()

    fig.suptitle("Phase 2 Week 1: path-dependent objective vs PFRDA defaults, by volatility tier")
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"wrote {out_path}")


# ASSUMPTION (Phase 2 Week 1 follow-up): weight on the shortfall-probability penalty in the combined
# objective below. Both terms are probabilities in [0,1], so lambda=1.0 (equal weight) is the simplest
# defensible starting point -- NOT a fitted/tuned hyperparameter. Revisit with Phase 2 Week 2's proper
# constrained optimization (e.g. an explicit Pareto frontier, or a hard shortfall-probability
# constraint via scipy.optimize) rather than this ad hoc scalarization.
COMBINED_OBJECTIVE_LAMBDA = 1.0


def grid_search_tier_combined(
    tier_contributions: np.ndarray, target: float, seed: int, lam: float = COMBINED_OBJECTIVE_LAMBDA
) -> tuple[dict, float]:
    """Phase 2 Week 1 follow-up: BOTH pure objectives tried so far were degenerate corner solutions --
    Phase 1's terminal-wealth-only objective always picked near-max equity (run_all_tiers), and this
    module's shortfall-only objective always picked near-min equity (run_all_tiers_path_dependent) --
    identically across all three tiers in both cases, because neither objective captures the actual
    growth-vs-safety tradeoff a real investor faces. This combines them:
    `score = P(terminal_corpus >= target) - lam * P(shortfall)`, maximized. Uses `compute_xirr=False`
    (terminal_corpus is already computed for free by the path-dependent engine; XIRR isn't needed for
    this objective) -- same speed as the shortfall-only search.
    """
    best_params = None
    best_score = -np.inf
    for equity_start, equity_end, inflection_age in itertools.product(
        EQUITY_START_GRID, EQUITY_END_GRID, INFLECTION_AGE_GRID
    ):
        if equity_end > equity_start:
            continue
        weight_path = build_weight_path(equity_start, equity_end, inflection_age)
        result = simulate_path_dependent_metrics_for_weight_path(
            weight_path, tier_contributions, n_market_trials=GRID_SEARCH_TRIALS, seed=seed,
            compute_xirr=False,
        )
        success_prob = success_probability(result["terminal_corpus"], target)
        shortfall_prob = float(result["ever_shortfall"].mean())
        score = success_prob - lam * shortfall_prob
        if score > best_score:
            best_score = score
            best_params = {
                "equity_start": equity_start,
                "equity_end": equity_end,
                "inflection_age": inflection_age,
            }
    return best_params, best_score


def run_all_tiers_combined(seed: int = 1, lam: float = COMBINED_OBJECTIVE_LAMBDA) -> pd.DataFrame:
    """Does a combined growth-vs-shortfall objective differentiate the glide path by tier, where
    neither pure objective did? Tested here, not assumed -- report exactly what this shows."""
    contributions, meta = load_contribution_matrix()
    rows = []

    for tier in ["low", "medium", "high"]:
        tier_mask = (meta["volatility_tier"] == tier).to_numpy()
        tier_contributions = contributions[tier_mask]

        lc50_result = simulate_path_dependent_metrics_for_weight_path(
            _pfrda_weight_path("LC50"), tier_contributions,
            n_market_trials=VALIDATION_TRIALS, seed=seed, compute_xirr=False,
        )
        target = float(np.median(lc50_result["terminal_corpus"]))  # same convention as run_all_tiers

        lc75_result = simulate_path_dependent_metrics_for_weight_path(
            _pfrda_weight_path("LC75"), tier_contributions,
            n_market_trials=VALIDATION_TRIALS, seed=seed, compute_xirr=False,
        )

        best_params, best_score = grid_search_tier_combined(tier_contributions, target, seed=seed, lam=lam)
        opt_result = simulate_path_dependent_metrics_for_weight_path(
            build_weight_path(**best_params), tier_contributions,
            n_market_trials=VALIDATION_TRIALS, seed=seed, compute_xirr=False,
        )

        rows.append(
            {
                "volatility_tier": tier,
                "n_subscribers": int(tier_mask.sum()),
                "target_corpus_rs": round(target, 0),
                "lc50_success_prob": success_probability(lc50_result["terminal_corpus"], target),
                "lc50_shortfall_prob": float(lc50_result["ever_shortfall"].mean()),
                "lc75_success_prob": success_probability(lc75_result["terminal_corpus"], target),
                "lc75_shortfall_prob": float(lc75_result["ever_shortfall"].mean()),
                "optimized_success_prob": success_probability(opt_result["terminal_corpus"], target),
                "optimized_shortfall_prob": float(opt_result["ever_shortfall"].mean()),
                "optimized_combined_score": best_score,
                "optimized_equity_start": best_params["equity_start"],
                "optimized_equity_end": best_params["equity_end"],
                "optimized_inflection_age": best_params["inflection_age"],
            }
        )

    return pd.DataFrame(rows)


def plot_combined_comparison(results: pd.DataFrame, out_path: Path) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    x = np.arange(len(results))
    width = 0.25
    ax.bar(x - width, results["lc50_success_prob"], width, label="LC50 (default)")
    ax.bar(x, results["lc75_success_prob"], width, label="LC75")
    ax.bar(x + width, results["optimized_success_prob"], width, label="Combined objective (ours)")
    ax.set_xticks(x)
    ax.set_xticklabels(results["volatility_tier"])
    ax.set_ylabel("P(terminal corpus >= tier's LC50-median target)")
    ax.set_xlabel("PLFS income-volatility tier")
    ax.set_title("Terminal-wealth success probability")
    ax.axhline(0.5, color="grey", linestyle="--", linewidth=0.8)
    ax.legend()

    ax = axes[1]
    ax.bar(x - width, results["lc50_shortfall_prob"], width, label="LC50 (default)")
    ax.bar(x, results["lc75_shortfall_prob"], width, label="LC75")
    ax.bar(x + width, results["optimized_shortfall_prob"], width, label="Combined objective (ours)")
    ax.set_xticks(x)
    ax.set_xticklabels(results["volatility_tier"])
    ax.set_ylabel("P(intra-horizon shortfall)")
    ax.set_xlabel("PLFS income-volatility tier")
    ax.set_title("Shortfall probability")
    ax.legend()

    fig.suptitle(
        "Phase 2 Week 1 follow-up: combined growth+shortfall objective vs PFRDA defaults, by tier"
    )
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"wrote {out_path}")


def _pfrda_weight_path(fund: str) -> np.ndarray:
    yearly = glide_path(START_AGE, N_YEARS, fund)[["w_E", "w_C", "w_G"]].to_numpy()
    return np.repeat(yearly, MONTHS_PER_YEAR, axis=0)


def plot_comparison(results: pd.DataFrame, out_path: Path) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(results))
    width = 0.25
    ax.bar(x - width, results["lc50_success_prob"], width, label="LC50 (default)")
    ax.bar(x, results["lc75_success_prob"], width, label="LC75")
    ax.bar(x + width, results["optimized_success_prob"], width, label="Volatility-conditioned (ours)")
    ax.set_xticks(x)
    ax.set_xticklabels(results["volatility_tier"])
    ax.set_ylabel("P(terminal corpus >= tier's LC50-median target)")
    ax.set_xlabel("PLFS income-volatility tier")
    ax.set_title("First-cut glide path vs PFRDA defaults, by volatility tier (Phase 1)")
    ax.axhline(0.5, color="grey", linestyle="--", linewidth=0.8, label="50% (LC50 vs its own target)")
    ax.legend()
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"wrote {out_path}")


def main() -> None:
    print("=" * 88)
    print("Phase 1: terminal-wealth objective (P(corpus >= target))")
    print("=" * 88)
    results = run_all_tiers()
    print(results.to_string(index=False))
    plot_comparison(results, FIGURES_DIR / "day6_glide_path_comparison.png")

    # Verification per the Phase 1 plan: the optimized path should beat both LC50 and LC75 for at
    # least the highest-volatility tier -- if not, this is a modeling bug to fix, not a result to
    # present as-is.
    high = results[results["volatility_tier"] == "high"].iloc[0]
    ok = high["optimized_success_prob"] >= max(high["lc50_success_prob"], high["lc75_success_prob"])
    print(
        f"\nVerification (high tier): optimized {high['optimized_success_prob']:.3f} vs "
        f"LC50 {high['lc50_success_prob']:.3f} / LC75 {high['lc75_success_prob']:.3f} "
        f"-> {'PASS' if ok else 'FAIL -- investigate before presenting'}"
    )

    print("\n" + "=" * 88)
    print("Phase 2 Week 1: path-dependent objective (P(intra-horizon shortfall), XIRR)")
    print("=" * 88)
    pd_results = run_all_tiers_path_dependent()
    print(pd_results.to_string(index=False))
    plot_path_dependent_comparison(pd_results, FIGURES_DIR / "week1_path_dependent_comparison.png")

    # The actual question Week 1 exists to answer: does this objective differentiate the optimal
    # glide path by tier, where Phase 1's terminal-wealth objective did not? Report what's true, don't
    # assume either answer.
    param_cols = ["optimized_equity_start", "optimized_equity_end", "optimized_inflection_age"]
    distinct_params = pd_results[param_cols].drop_duplicates()
    differentiated = len(distinct_params) > 1
    print(
        f"\nTier differentiation check: {len(distinct_params)} distinct parameter set(s) across the "
        f"3 tiers under the path-dependent objective -> "
        f"{'DIFFERENTIATED (new finding vs Phase 1 Day 6)' if differentiated else 'STILL IDENTICAL (Day 6 finding persists under this objective too)'}"
    )
    print(pd_results[["volatility_tier", *param_cols]].to_string(index=False))

    print("\n" + "=" * 88)
    print("Phase 2 Week 1 follow-up: combined objective (P(success) - lambda * P(shortfall))")
    print("=" * 88)
    combined_results = run_all_tiers_combined()
    print(combined_results.to_string(index=False))
    plot_combined_comparison(combined_results, FIGURES_DIR / "week1_combined_objective_comparison.png")

    distinct_combined = combined_results[param_cols].drop_duplicates()
    print(
        f"\nTier differentiation check (combined objective): {len(distinct_combined)} distinct "
        f"parameter set(s) across the 3 tiers -> "
        f"{'DIFFERENTIATED' if len(distinct_combined) > 1 else 'STILL IDENTICAL'}"
    )
    print(combined_results[["volatility_tier", *param_cols]].to_string(index=False))


if __name__ == "__main__":
    main()
