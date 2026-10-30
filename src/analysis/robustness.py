"""Robustness of the 'allocation is tier-blind' finding (Phase 2 Day 2/3).

For each scenario (a perturbation of one labelled income assumption) and equity-premium haircut:
  - regenerate the synthetic population, pick the success-maximizing glide path per tier and for the pooled
    (tier-blind) population on a search seed, and
  - evaluate both out-of-sample on a different seed, reporting the PAIRED tier-vs-pooled success gain with a
    bootstrap CI over market trials (both policies see identical market paths, so resampling trials is paired).

A gain whose CI contains 0 means tier-conditioning is not distinguishable from tier-blind allocation.
Usage: python -m src.analysis.robustness
"""
from __future__ import annotations

import contextlib
import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd

from src.optimization.glide_path_optimizer import build_weight_path
from src.optimization.risk_budget import (
    MARKET_SEED_SEARCH, MARKET_SEED_VALIDATE, PARAM_COLS, TIERS, VALIDATION_TRIALS,
    evaluate_candidates, pooled_table, tier_target,
)
from src.simulation import income_paths as ip
from src.simulation.market import simulate_path_dependent_metrics_for_weight_path

SEARCH_TRIALS = 100
N_BOOT = 2000
CANDS = [
    (s, e, a)
    for s in [0.15, 0.30, 0.45, 0.60, 0.75]
    for e, a in [(0.05, 30), (0.10, 35), (0.20, 40), (0.30, 45)]
    if e <= s
]
INFORMAL = ("self_employed", "casual_labour")

# name -> (informal disruption multiplier x, informal propensity x, target-CV x (all cohorts), floor Rs)
SCENARIOS = {
    "baseline": (1.0, 1.0, 1.0, None),
    "disruption_x2": (2.0, 1.0, 1.0, None),
    "disruption_x0.5": (0.5, 1.0, 1.0, None),
    "propensity_x0.5": (1.0, 0.5, 1.0, None),
    "propensity_x1.5": (1.0, 1.5, 1.0, None),
    "dispersion_x1.5": (1.0, 1.0, 1.5, None),
    "dispersion_x0.67": (1.0, 1.0, 0.67, None),
    "floor_3000": (1.0, 1.0, 1.0, 3000.0),
    "floor_8000": (1.0, 1.0, 1.0, 8000.0),
}


@contextlib.contextmanager
def perturbed_income(disruption_x=1.0, propensity_x=1.0, cv_x=1.0, floor=None):
    """Temporarily perturb the labelled assumptions in income_paths (restored on exit)."""
    old_assump, old_floor, old_load = dict(ip.ASSUMPTIONS), ip.SUBSISTENCE_FLOOR_RS, ip.load_calibration
    try:
        for k in INFORMAL:
            a = old_assump[k]
            ip.ASSUMPTIONS[k] = dataclasses.replace(
                a,
                disruption_rate_multiplier=a.disruption_rate_multiplier * disruption_x,
                contribution_propensity=a.contribution_propensity * propensity_x,
            )
        if floor is not None:
            ip.SUBSISTENCE_FLOOR_RS = floor

        def load():
            c = old_load().copy()
            c["target_individual_cv"] = c["target_individual_cv"] * cv_x
            return c

        ip.load_calibration = load
        yield
    finally:
        ip.ASSUMPTIONS.clear(); ip.ASSUMPTIONS.update(old_assump)
        ip.SUBSISTENCE_FLOOR_RS, ip.load_calibration = old_floor, old_load


def matrices_from_df(df: pd.DataFrame):
    meta = df.drop_duplicates("subscriber_id")[["subscriber_id", "employment_type", "volatility_tier"]]
    meta = meta.sort_values("subscriber_id").reset_index(drop=True)
    piv = lambda col: df.pivot(index="subscriber_id", columns="month_index", values=col).reindex(
        meta["subscriber_id"]).to_numpy()
    return piv("contribution"), piv("is_disruption_month").astype(bool), meta


def paired_gain_ci(tier_corpus: np.ndarray, pooled_corpus: np.ndarray, target: float, seed=0):
    """Mean paired success gain (tier-conditioned minus pooled) with 95% bootstrap CI over market trials."""
    per_trial = (tier_corpus >= target).mean(axis=1) - (pooled_corpus >= target).mean(axis=1)
    rng = np.random.default_rng(seed)
    boots = rng.choice(per_trial, size=(N_BOOT, per_trial.size)).mean(axis=1)
    return per_trial.mean(), np.percentile(boots, 2.5), np.percentile(boots, 97.5)


def run_scenario(name: str, haircut: float, income_df: pd.DataFrame | None = None) -> list[dict]:
    contributions, _, meta = matrices_from_df(income_df)
    kw = {"equity_shift_annual": haircut}
    masks = {t: (meta["volatility_tier"] == t).to_numpy() for t in TIERS}
    tables, targets, sizes = {}, {}, {}
    for t in TIERS:
        c = contributions[masks[t]]
        targets[t] = tier_target(c, MARKET_SEED_SEARCH, SEARCH_TRIALS, 0.9, kw)
        tables[t] = evaluate_candidates(c, targets[t], MARKET_SEED_SEARCH, SEARCH_TRIALS, candidates=CANDS, sim_kwargs=kw)
        sizes[t] = int(masks[t].sum())
    pooled = pooled_table(tables, sizes)
    pp = pooled.loc[pooled["success_prob"].idxmax()]
    rows = []
    for t in TIERS:
        c = contributions[masks[t]]
        pick = tables[t].loc[tables[t]["success_prob"].idxmax()]
        run = lambda p: simulate_path_dependent_metrics_for_weight_path(
            build_weight_path(p["equity_start"], p["equity_end"], int(p["inflection_age"])), c,
            n_market_trials=VALIDATION_TRIALS, seed=MARKET_SEED_VALIDATE, compute_xirr=False, **kw)["terminal_corpus"]
        tc, pc = run(pick), run(pp)
        g, lo, hi = paired_gain_ci(tc, pc, targets[t])
        rows.append({
            "scenario": name, "haircut": haircut, "tier": t, "n": sizes[t],
            **{f"tier_{k}": pick[k] for k in PARAM_COLS}, **{f"pooled_{k}": pp[k] for k in PARAM_COLS},
            "gain": g, "ci_lo": lo, "ci_hi": hi, "ci_excludes_0": bool(lo > 0 or hi < 0),
        })
    return rows


def main(haircuts=(0.0, 0.02)) -> None:
    out = Path(__file__).resolve().parents[2] / "data" / "processed" / "robustness.csv"
    rows = []
    for name, (dx, px, cx, fl) in SCENARIOS.items():
        with perturbed_income(dx, px, cx, fl):
            df = ip.simulate_income_paths()
        for h in haircuts:
            rows += run_scenario(name, h, df)
            pd.DataFrame(rows).to_csv(out, index=False)
            print(f"done {name} haircut={h}", flush=True)
    res = pd.DataFrame(rows)
    print(res[["scenario", "haircut", "tier", "tier_equity_start", "pooled_equity_start", "gain", "ci_lo", "ci_hi",
               "ci_excludes_0"]].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
