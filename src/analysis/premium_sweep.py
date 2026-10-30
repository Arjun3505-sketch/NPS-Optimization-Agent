"""Equity-premium break-even sweep (Phase 2 Day 2).

Day 1 found that, over the real 2009-2026 NAV window, maximum equity wins for EVERY income-volatility tier
under every objective tried (terminal wealth, shortfall, forced withdrawals), so a tier-conditioned glide
path adds nothing over a tier-blind one. That could simply be because the window's equity premium is large.
This sweep subtracts a constant annual haircut from every bootstrapped equity month (volatility, correlation
and regime structure unchanged) and asks, per haircut and tier:

  1. what is the success-maximizing glide path?
  2. does a tier-CONDITIONED policy beat the tier-BLIND pooled policy (out-of-sample, different seed)?
  3. where, if anywhere, does the optimum leave the max-equity corner?

Each haircut world uses its own LC50-median target (same relative convention as Phase 1).
Usage: python -m src.analysis.premium_sweep
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.optimization.risk_budget import (
    MARKET_SEED_SEARCH, PARAM_COLS, TIERS, evaluate_candidates, pooled_table, tier_target, validate_policy,
)
from src.simulation.market import load_contribution_matrix, load_disruption_matrix, load_monthly_returns

SHIFTS = [0.0, 0.01, 0.02, 0.03, 0.04, 0.06]  # annual haircut to equity returns
SEARCH_TRIALS = 100
CANDS = [
    (s, e, a)
    for s in [0.15, 0.30, 0.45, 0.60, 0.75]
    for e, a in [(0.05, 30), (0.10, 35), (0.20, 40), (0.30, 45)]
    if e <= s
]


def run(withdrawal_prob: float = 0.0) -> pd.DataFrame:
    contributions, meta = load_contribution_matrix()
    disruption = load_disruption_matrix()
    mr = load_monthly_returns()
    rows = []
    for shift in SHIFTS:
        e_ann, g_ann = mr["E"].mean() * 12 - shift, mr["G"].mean() * 12
        tables, targets, sizes, masks = {}, {}, {}, {}
        for tier in TIERS:
            m = (meta["volatility_tier"] == tier).to_numpy()
            masks[tier] = m
            kw = {"equity_shift_annual": shift}
            if withdrawal_prob:
                kw.update(disruption=disruption[m], withdrawal_prob=withdrawal_prob)
            targets[tier] = tier_target(contributions[m], MARKET_SEED_SEARCH, SEARCH_TRIALS, 0.9, kw)
            tables[tier] = evaluate_candidates(
                contributions[m], targets[tier], MARKET_SEED_SEARCH, SEARCH_TRIALS, candidates=CANDS, sim_kwargs=kw
            )
            sizes[tier] = int(m.sum())
        pooled = pooled_table(tables, sizes)
        pooled_pick = pooled.loc[pooled["success_prob"].idxmax()]
        for tier in TIERS:
            m = masks[tier]
            kw = {"equity_shift_annual": shift}
            if withdrawal_prob:
                kw.update(disruption=disruption[m], withdrawal_prob=withdrawal_prob)
            pick = tables[tier].loc[tables[tier]["success_prob"].idxmax()]
            # validate_policy builds its own masks from meta; pass sim_kwargs sliced to the tier
            tv = validate_policy(pick, tier, targets[tier], contributions, meta, sim_kwargs=_tier_kw(kw, m))
            pv = validate_policy(pooled_pick, tier, targets[tier], contributions, meta, sim_kwargs=_tier_kw(kw, m))
            rows.append(
                {
                    "withdrawal_prob": withdrawal_prob, "equity_haircut": shift,
                    "equity_ann_return": round(e_ann, 4), "equity_minus_G_premium": round(e_ann - g_ann, 4),
                    "tier": tier,
                    **{f"tier_{k}": pick[k] for k in PARAM_COLS},
                    **{f"pooled_{k}": pooled_pick[k] for k in PARAM_COLS},
                    "tier_val_success": tv["success_prob"], "pooled_val_success": pv["success_prob"],
                    "gain_tier_vs_pooled": tv["success_prob"] - pv["success_prob"],
                }
            )
    return pd.DataFrame(rows)


def _tier_kw(kw: dict, mask: np.ndarray) -> dict:
    return kw  # disruption already sliced to the tier by the caller


def main() -> None:
    out_dir = Path(__file__).resolve().parents[2] / "data" / "processed"
    res = run(0.0)
    res.to_csv(out_dir / "premium_sweep.csv", index=False)
    cols = ["equity_haircut", "equity_minus_G_premium", "tier", "tier_equity_start", "tier_equity_end",
            "tier_inflection_age", "pooled_equity_start", "tier_val_success", "pooled_val_success",
            "gain_tier_vs_pooled"]
    print(res[cols].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
