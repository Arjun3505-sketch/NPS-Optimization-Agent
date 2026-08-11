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

FINDING (important, not a bug -- see docs/phase1_status.md Day 6 for full detail and diagnostics):
running this grid search produces the SAME optimal parameters (near-max equity: equity_start=0.75,
held to age 45) for all three volatility tiers -- i.e. this first-cut setup does not yet show the
volatility-CONDITIONED differentiation that is the paper's central claim. Diagnostics (median-target
P(success), P75-target P(success), CVaR-10% of terminal wealth, and a tier-independent 1.5x-total-
contributions floor target) all confirm this is not a bug: over the real 208-month 2009-2026
bootstrap window, MORE equity dominates on every one of these metrics for every tier, because the
window's realized equity risk premium was strong enough that even worst-decile bootstrapped outcomes
still favour higher equity. This motivates, and is direct evidence for, the CVaR-adjusted objective
already planned for Phase 2 Week 1 -- and suggests the more promising differentiator may be
intra-horizon shortfall/sequence risk (being unable to add money, or needing to draw down, at exactly
the wrong time) rather than terminal-wealth distribution shape, which is worth testing explicitly in
Phase 2 rather than assumed to already be captured here.

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
    simulate_terminal_corpus_for_weight_path,
)

ROOT = Path(__file__).resolve().parents[2]
FIGURES_DIR = ROOT / "docs" / "paper" / "figures"

START_AGE = 25
N_YEARS = 30
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
    results = run_all_tiers()
    print(results.to_string(index=False))
    plot_comparison(results, FIGURES_DIR / "day6_glide_path_comparison.png")

    # Verification per the build plan: the optimized path should beat both LC50 and LC75 for at
    # least the highest-volatility tier -- if not, this is a modeling bug to fix, not a result to
    # present as-is.
    high = results[results["volatility_tier"] == "high"].iloc[0]
    ok = high["optimized_success_prob"] >= max(high["lc50_success_prob"], high["lc75_success_prob"])
    print(
        f"\nVerification (high tier): optimized {high['optimized_success_prob']:.3f} vs "
        f"LC50 {high['lc50_success_prob']:.3f} / LC75 {high['lc75_success_prob']:.3f} "
        f"-> {'PASS' if ok else 'FAIL -- investigate before presenting'}"
    )


if __name__ == "__main__":
    main()
