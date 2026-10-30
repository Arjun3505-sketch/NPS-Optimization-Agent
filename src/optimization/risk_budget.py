"""Risk-budget glide-path policy (Phase 2 core method).

Phase 1 and Week 1 showed that both pure objectives -- maximize terminal wealth, minimize shortfall --
collapse to corner solutions (max / min equity) identical across volatility tiers. This module instead
treats allocation as a growth-vs-sequence-risk tradeoff:

    maximize  P(terminal corpus >= target)
    subject to P(intra-horizon shortfall) <= epsilon        (epsilon = the subscriber's "risk budget")

Every candidate glide path in the grid is simulated ONCE per tier (common random numbers: one seed), giving
a table of (success_prob, shortfall_prob). Everything downstream -- the Pareto frontier, epsilon-constrained
optima, lambda-scalarized optima, and the tier-blind pooled baseline -- is selection over that table, so
sweeps are free. Only changing the shortfall *threshold* needs re-simulation.

Selection and validation use different seeds, so reported numbers are out-of-sample w.r.t. the search.

Usage:
    python -m src.optimization.risk_budget
"""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from src.optimization.glide_path_optimizer import (
    CORP_DEBT_SHARE_OF_REMAINDER,  # noqa: F401  (documented fixed assumption, see glide_path_optimizer)
    _pfrda_weight_path,
    build_weight_path,
)
from src.simulation.market import (
    DEFAULT_SHORTFALL_THRESHOLD,
    load_contribution_matrix,
    simulate_path_dependent_metrics_for_weight_path,
)

# Shared seed convention for ALL Phase 2 analyses: candidate selection uses MARKET_SEED_SEARCH, reporting
# uses MARKET_SEED_VALIDATE. Import these rather than hardcoding literals, so comparisons across
# objectives/scenarios always use identical bootstrapped market draws (common random numbers).
MARKET_SEED_SEARCH = 1
MARKET_SEED_VALIDATE = 2
SEARCH_TRIALS = 100
VALIDATION_TRIALS = 200
TIERS = ["low", "medium", "high"]

EQUITY_START_GRID = [0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75]
EQUITY_END_GRID = [0.05, 0.10, 0.20, 0.30]
INFLECTION_AGE_GRID = [30, 35, 40, 45]
EPSILON_GRID = [0.01, 0.02, 0.05, 0.10, 0.15, 0.20]
PARAM_COLS = ["equity_start", "equity_end", "inflection_age"]


def candidate_grid() -> list[tuple[float, float, int]]:
    return [
        (s, e, a)
        for s, e, a in itertools.product(EQUITY_START_GRID, EQUITY_END_GRID, INFLECTION_AGE_GRID)
        if e <= s
    ]


def tier_target(
    tier_contribs: np.ndarray, seed: int, trials: int, threshold: float, sim_kwargs: dict | None = None
) -> float:
    """Tier-specific target: median terminal corpus under LC50 (same convention as Phase 1)."""
    r = simulate_path_dependent_metrics_for_weight_path(
        _pfrda_weight_path("LC50"), tier_contribs, n_market_trials=trials, seed=seed,
        shortfall_threshold=threshold, compute_xirr=False, **(sim_kwargs or {}),
    )
    return float(np.median(r["terminal_corpus"]))


def evaluate_candidates(
    tier_contribs: np.ndarray,
    target: float,
    seed: int,
    trials: int,
    threshold: float = DEFAULT_SHORTFALL_THRESHOLD,
    candidates: list[tuple[float, float, int]] | None = None,
    sim_kwargs: dict | None = None,
) -> pd.DataFrame:
    """Success / shortfall / median-corpus for every candidate glide path (one seed = CRN)."""
    rows = []
    for s, e, a in candidates or candidate_grid():
        r = simulate_path_dependent_metrics_for_weight_path(
            build_weight_path(s, e, a), tier_contribs, n_market_trials=trials, seed=seed,
            shortfall_threshold=threshold, compute_xirr=False, **(sim_kwargs or {}),
        )
        rows.append(
            {
                "equity_start": s, "equity_end": e, "inflection_age": a,
                "success_prob": float((r["terminal_corpus"] >= target).mean()),
                "shortfall_prob": float(r["ever_shortfall"].mean()),
                "median_corpus": float(np.median(r["terminal_corpus"])),
            }
        )
    return pd.DataFrame(rows)


def pareto_frontier(table: pd.DataFrame) -> pd.DataFrame:
    """Candidates not dominated (higher success AND lower shortfall) by any other candidate."""
    t = table.sort_values(["shortfall_prob", "success_prob"], ascending=[True, False])
    keep, best = [], -np.inf
    for idx, row in t.iterrows():
        if row["success_prob"] > best + 1e-12:
            keep.append(idx)
            best = row["success_prob"]
    return table.loc[keep].sort_values("shortfall_prob")


def best_under_budget(table: pd.DataFrame, epsilon: float) -> pd.Series | None:
    """Max success subject to shortfall <= epsilon (None if no candidate is feasible)."""
    feasible = table[table["shortfall_prob"] <= epsilon]
    if feasible.empty:
        return None
    return feasible.loc[feasible["success_prob"].idxmax()]


def best_scalarized(table: pd.DataFrame, lam: float) -> pd.Series:
    return table.loc[(table["success_prob"] - lam * table["shortfall_prob"]).idxmax()]


def pooled_table(tier_tables: dict[str, pd.DataFrame], sizes: dict[str, int]) -> pd.DataFrame:
    """Tier-blind objective: subscriber-count-weighted average of the tier tables (equivalent to
    pooling all subscribers, each judged against their own tier's target)."""
    total = sum(sizes.values())
    out = tier_tables[TIERS[0]][PARAM_COLS].copy()
    for col in ["success_prob", "shortfall_prob", "median_corpus"]:
        out[col] = sum(tier_tables[t][col].to_numpy() * sizes[t] / total for t in TIERS)
    return out


def build_tier_tables(
    seed: int = MARKET_SEED_SEARCH, trials: int = SEARCH_TRIALS,
    threshold: float = DEFAULT_SHORTFALL_THRESHOLD, contributions=None, meta=None,
) -> tuple[dict[str, pd.DataFrame], dict[str, float], dict[str, int]]:
    if contributions is None:
        contributions, meta = load_contribution_matrix()
    tables, targets, sizes = {}, {}, {}
    for tier in TIERS:
        c = contributions[(meta["volatility_tier"] == tier).to_numpy()]
        targets[tier] = tier_target(c, seed, trials, threshold)
        tables[tier] = evaluate_candidates(c, targets[tier], seed, trials, threshold)
        sizes[tier] = c.shape[0]
    return tables, targets, sizes


def validate_policy(
    params: pd.Series | dict, tier: str, target: float, contributions, meta,
    threshold: float = DEFAULT_SHORTFALL_THRESHOLD, sim_kwargs: dict | None = None,
) -> dict:
    """Out-of-sample (different seed, more trials) success/shortfall of one policy on one tier."""
    c = contributions[(meta["volatility_tier"] == tier).to_numpy()]
    r = simulate_path_dependent_metrics_for_weight_path(
        build_weight_path(params["equity_start"], params["equity_end"], int(params["inflection_age"])),
        c, n_market_trials=VALIDATION_TRIALS, seed=MARKET_SEED_VALIDATE,
        shortfall_threshold=threshold, compute_xirr=False, **(sim_kwargs or {}),
    )
    return {
        "success_prob": float((r["terminal_corpus"] >= target).mean()),
        "shortfall_prob": float(r["ever_shortfall"].mean()),
    }


def main() -> None:
    contributions, meta = load_contribution_matrix()
    tables, targets, sizes = build_tier_tables(contributions=contributions, meta=meta)
    pooled = pooled_table(tables, sizes)

    out_dir = Path(__file__).resolve().parents[2] / "data" / "processed"
    for tier in TIERS:
        tables[tier].to_csv(out_dir / f"candidate_table_{tier}.csv", index=False)

    print("Pareto frontier per tier (shortfall_prob, success_prob, params):")
    for tier in TIERS:
        print(f"\n[{tier}]")
        print(pareto_frontier(tables[tier]).round(4).to_string(index=False))

    rows = []
    for eps in EPSILON_GRID:
        pooled_pick = best_under_budget(pooled, eps)
        for tier in TIERS:
            pick = best_under_budget(tables[tier], eps)
            row = {"epsilon": eps, "tier": tier}
            if pick is not None:
                v = validate_policy(pick, tier, targets[tier], contributions, meta)
                row.update({f"tier_{k}": pick[k] for k in PARAM_COLS})
                row.update({"tier_val_success": v["success_prob"], "tier_val_shortfall": v["shortfall_prob"]})
            if pooled_pick is not None:
                v = validate_policy(pooled_pick, tier, targets[tier], contributions, meta)
                row.update({f"pooled_{k}": pooled_pick[k] for k in PARAM_COLS})
                row.update({"pooled_val_success": v["success_prob"], "pooled_val_shortfall": v["shortfall_prob"]})
            rows.append(row)
    res = pd.DataFrame(rows)
    res.to_csv(out_dir / "risk_budget_results.csv", index=False)
    print("\nEpsilon-constrained policies: tier-conditioned vs pooled (out-of-sample validation)")
    print(res.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
