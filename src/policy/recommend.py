"""Risk-budget glide-path recommender (Phase 2 deliverable).

Given a volatility tier (or employment type) and a risk budget epsilon -- the maximum tolerated probability
that the account ever falls below 90% of cumulative contributions -- returns the success-maximizing glide
path from the precomputed candidate tables (`python -m src.optimization.risk_budget`), together with
simulated outcomes for that cohort against PFRDA LC50/LC75.

Scope/honesty notes (also surfaced in the response):
  * Phase 2 found allocation is driven by the equity premium, not by income-volatility tier: the policy for a
    given epsilon is (near-)identical across tiers. The tier matters for the PROJECTION (accumulation levels,
    skipped-contribution rate), which is what this tool personalizes.
  * Candidate tables assume the historical 2009-2026 equity premium and a fixed 25->60 horizon.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from src.optimization.glide_path_optimizer import _pfrda_weight_path, build_weight_path
from src.optimization.risk_budget import MARKET_SEED_VALIDATE, TIERS, best_under_budget
from src.simulation.market import load_contribution_matrix, simulate_path_dependent_metrics_for_weight_path

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
EMPLOYMENT_TO_TIER = {"regular_salaried": "low", "casual_labour": "medium", "self_employed": "high"}
START_AGE, RETIRE_AGE = 25, 60
PERCENTILES = [10, 25, 50, 75, 90]


@lru_cache(maxsize=None)
def _candidates(tier: str) -> pd.DataFrame:
    return pd.read_csv(PROCESSED / f"candidate_table_{tier}.csv")


@lru_cache(maxsize=1)
def _population():
    contributions, meta = load_contribution_matrix()
    return contributions, meta


def resolve_tier(tier: str | None = None, employment_type: str | None = None) -> str:
    if tier is None and employment_type is None:
        raise ValueError("provide tier or employment_type")
    t = tier or EMPLOYMENT_TO_TIER.get(employment_type or "")
    if t not in TIERS:
        raise ValueError(f"unknown tier/employment_type: {tier or employment_type}")
    return t


def recommend(tier: str | None = None, employment_type: str | None = None, epsilon: float = 0.05,
              n_trials: int = 200) -> dict:
    t = resolve_tier(tier, employment_type)
    if not 0 <= epsilon <= 1:
        raise ValueError("epsilon must be in [0, 1]")
    pick = best_under_budget(_candidates(t), epsilon)
    if pick is None:
        feasible_min = float(_candidates(t)["shortfall_prob"].min())
        raise ValueError(f"no candidate meets epsilon={epsilon}; minimum achievable is {feasible_min:.4f}")

    contributions, meta = _population()
    c = contributions[(meta["volatility_tier"] == t).to_numpy()]
    paths = {
        "recommended": build_weight_path(pick["equity_start"], pick["equity_end"], int(pick["inflection_age"])),
        "LC50": _pfrda_weight_path("LC50"),
        "LC75": _pfrda_weight_path("LC75"),
    }
    results = {
        k: simulate_path_dependent_metrics_for_weight_path(
            w, c, n_market_trials=n_trials, seed=MARKET_SEED_VALIDATE, compute_xirr=False)
        for k, w in paths.items()
    }
    target = float(np.median(results["LC50"]["terminal_corpus"]))  # same convention as Phase 1/2

    def summary(r):
        tc = r["terminal_corpus"]
        return {
            "terminal_corpus_percentiles_rs": {f"p{p}": float(np.percentile(tc, p)) for p in PERCENTILES},
            "p_reach_lc50_median": float((tc >= target).mean()),
            "p_shortfall": float(r["ever_shortfall"].mean()),
        }

    yearly = paths["recommended"].reshape(-1, 12, 3)[:, 0, :]
    return {
        "tier": t,
        "epsilon": epsilon,
        "params": {k: float(pick[k]) for k in ["equity_start", "equity_end", "inflection_age"]},
        "glide_path": [
            {"age": START_AGE + i, "equity": float(w[0]), "corporate_debt": float(w[1]), "govt_securities": float(w[2])}
            for i, w in enumerate(yearly)
        ],
        "outcomes": {k: summary(r) for k, r in results.items()},
        # epsilon is enforced on the search seed (in-sample); fresh market draws can exceed it slightly.
        "budget_met_out_of_sample": bool(results["recommended"]["ever_shortfall"].mean() <= epsilon),
        "skipped_contribution_months_pct": float((c == 0).mean() * 100),
        "notes": [
            "Allocation is driven by the equity premium and risk budget, not income-volatility tier (Phase 2 finding).",
            f"Projection assumes ages {START_AGE}-{RETIRE_AGE} and the historical 2009-2026 equity premium.",
            "Synthetic PLFS-calibrated population; corpus values are nominal rupees; not financial advice.",
            "epsilon is enforced on the search seed; see budget_met_out_of_sample for fresh market draws.",
        ],
    }
