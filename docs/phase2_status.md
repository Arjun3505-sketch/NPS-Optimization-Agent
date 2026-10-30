# Phase 2 Status — real data vs. modeling assumption vs. tested finding

Living document for Phase 2, same discipline as `docs/phase1_status.md`: real data, labelled
assumptions, and honestly-reported findings (including negative ones) are never presented as each
other. All work here happens on the `phase2` branch — `main` stays exactly at `v0.1-phase1`.

## Week 1 — path-dependent risk metrics

**Motivation, not a generic restatement of the pre-Phase-1 plan:** Phase 1's Day 6 finding was that a
pure terminal-wealth objective — tested four ways (median target, P75 target, CVaR-10% of terminal
wealth, a contribution-floor target) — never differentiates the optimal glide path by volatility tier.
Week 1 responds to that directly by building metrics sensitive to the *timing* of contributions and
returns (sequence risk), not just the terminal number.

- **Built:** `src/simulation/market.py::simulate_path_dependent_metrics_for_weight_path()` — extends
  the existing corpus recursion with two new metrics, computed incrementally (no full
  `(trials × subscribers × months)` array is ever materialized — that would be ~1.3GB at full
  population):
  1. **Intra-horizon shortfall**: `P(∃ month t : corpus(t)/cumulative_contributions(t) < 0.9)`, checked
     only once cumulative contributions exceed Rs 1,000 (an illustrative, labelled `ASSUMPTION`, not a
     cited figure — guards against noise from a subscriber's first partial month). 0.9, not 1.0
     (break-even), specifically because a break-even threshold saturates near 100% for everyone in
     early months regardless of tier — uninformative. Also tracks worst funded ratio reached, a
     severity diagnostic beyond the binary flag.
  2. **XIRR (money-weighted return)**: solves `NPV(r) = -Σ contributions[t]·(1+r)^-t +
     terminal_corpus·(1+r)^-(n-1) = 0` via a manual vectorized Newton's method (not `numpy_financial`
     — see `_xirr_annualized`'s docstring for why). Sensitive to *when* contributions land relative to
     returns, unlike terminal wealth or CAGR.

- **Bug found and fixed before trusting the numbers, not shipped silently** (same discipline as Phase
  1's Day 4 contribution-formula bug and the pre-Day-8 NFO-month bug): the first version of the Newton
  solver clipped the monthly rate to `[-0.99, 1.0]` during iteration. On real data, a small fraction of
  (trial, subscriber) cells drove the rate near -0.99, and `(1+r)^-t` at `t` up to 431 overflowed
  float64 (`0.01^-431` vastly exceeds `~1.8e308`), corrupting those cells' results with extreme,
  non-convergent values. This wasn't subtle in the output: annualized XIRR's **mean was 78.6** against
  a **median of 0.096** on the first real-data test run — an obvious sign of outlier corruption, caught
  by comparing the two rather than trusting either alone. Fixed by tightening the per-iteration clip to
  `[-0.3, 0.3]` (still far wider than any realistic outcome here, but keeps the discount factor
  representable across the full horizon) and explicitly flagging non-convergent/boundary-pinned cells
  as `NaN`, excluded from aggregates, with the failure rate printed rather than hidden. After the fix,
  on the same real test (LC50, high tier, 1,177 subscribers × 200 trials): mean and median both ~9.6%
  annualized XIRR, consistent with each other; **2.33% of cells (5,494 / 235,400) failed to converge**
  and are reported as `NaN`, not swept into the average.
- **Validated the solver before trusting it on real data**: `tests/test_xirr.py` — four hand-computable
  closed-form cases (single contribution + terminal payoff, pure compounding at a known rate, a
  break-even zero-return case, and a multi-trial/multi-subscriber case checking the vectorization
  doesn't accidentally mix cells) — all pass, including recovering a known 2%/month compounding rate to
  within 1e-6.
- **Performance, and why `compute_xirr` is a flag, not always-on:** XIRR is expensive — ~20s for one
  (weight_path, tier) call at 200 trials on the largest tier (1,177 subscribers), because the Newton
  solver's month-loop runs per iteration. The shortfall/terminal-corpus metrics alone are cheap (~0.3s
  at 60 trials, matching Phase 1's existing engine's speed). **Week 1b's grid search must use
  `compute_xirr=False`** for the search itself and compute XIRR only for final reported candidates
  (LC50, LC75, and the chosen optimum per tier) — tested and confirmed via direct timing, not assumed.

## Week 1b / Day 1 — objectives, risk-budget frontier, and a retraction

- **Shortfall-only objective** (`glide_path_optimizer.run_all_tiers_path_dependent`): collapses to the
  mirror-image corner (15%→5% equity, de-risk from age 30), identical across tiers — as degenerate as
  Phase 1's max-equity corner. Neither pure objective captures a growth-vs-safety tradeoff.
- **RETRACTION.** The combined objective `P(success) − λ·P(shortfall)` at λ=1 gave 60/60/45% starting
  equity (low/medium/high) and was first reported as the project's first tier differentiation. It was
  **not robust**: when the full candidate grid was evaluated once per tier and analysed as a Pareto
  frontier (`src/optimization/risk_budget.py`), the three tiers' frontiers are nearly identical (shortfall
  at 75% start equity: 0.172 / 0.173 / 0.180), and the ε-constrained optimum is the same for every tier
  (0.45 @ ε=0.02, 0.55 @ ε=0.05, 0.65 @ ε=0.10). The λ=1 split was the scalarized optimum falling between
  grid points. A tier-blind pooled policy matches the tier-conditioned one out-of-sample.
- **Why the shortfall metric cannot see income volatility:** corpus ÷ cumulative contributions is driven
  almost entirely by market returns; skipped months barely move it. This is a limit of the metric as
  defined, not evidence about informal workers.
- **Liquidity channel added** (`market.py`, `withdrawal_prob`/`withdrawal_frac`): in a PLFS-calibrated
  disruption month a subscriber withdraws 10% (ASSUMPTION, illustrative) of the corpus at prevailing
  prices; separate RNG stream so market paths are identical across settings. Effect on levels is large
  (high tier median corpus 6.4M → 1.3M at withdrawal prob 1.0; low tier 26.2M → 17.9M), but **max equity
  still maximizes target success for every tier** at withdrawal prob 0, 0.5, 1.0 (the medium tier's
  success collapses to ~0 at p≥0.5 whatever the allocation, so it carries no ranking information).
- **Net finding so far:** income volatility strongly affects accumulation *levels* but not the optimal
  *allocation*, over the 2009–2026 window, under terminal-wealth, shortfall and withdrawal channels.

## Day 2 — equity-premium break-even sweep (`src/analysis/premium_sweep.py`)

Constant annual haircut subtracted from every bootstrapped equity month (volatility/correlation/regimes
unchanged); each haircut world uses its own LC50-median target; success-maximizing glide path chosen on
seed 1, validated out-of-sample on seed 2. Realized 2009–2026 equity-minus-G premium is +2.9%/yr.

| equity − G premium | optimal start equity (every tier) | tier-conditioned gain over pooled |
|---|---|---|
| +2.9%, +1.9% | 75% (max) | 0.0000 |
| +0.9% | 60% (low/medium/high; high differs only in end-equity) | ≤ 0.0015 |
| −0.1%, −1.1%, −3.1% | 15% (min) | 0.0000 |

- **Result:** optimal allocation is governed by the market equity premium, flipping from max to min equity
  near a ~0–1% premium, **identically across income-volatility tiers**. Tier-conditioning never beats the
  tier-blind pooled policy by more than noise (max 0.0015 out-of-sample).
- **Withdrawal stress (p=0.5, 10% per disruption month, `premium_sweep_wd05.csv`):** same pattern. The one
  deviation (premium +0.9%: low tier drops to 60% while medium/high stay at 75%) is −0.0005 in the
  tier-vs-pooled gain, i.e. noise, and points the opposite way to the original hypothesis.
- **Defensible statement for the paper:** in this model, income volatility changes how much informal
  workers accumulate, but not how they should allocate; the allocation decision is a function of the
  equity premium. Caveats: coarse 20-candidate grid, one bootstrap source (SBI), assumptions labelled in
  `income_paths.py` (dispersion multiplier, propensity, disruption rates) not yet perturbed.
