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
