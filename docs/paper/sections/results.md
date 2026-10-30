# 4. Results

All numbers: 2,000 synthetic subscribers, ages 25-60, SBI bootstrap (207 months); reproducible via
`python -m src.optimization.risk_budget`, `src.analysis.premium_sweep`, `src.analysis.robustness`.

## 4.1 Income volatility changes accumulation, not (apparently) allocation
Zero-contribution months: regular salaried 0.07%, casual labour 10.05%, self-employed 10.20% (emergent from
PLFS-calibrated volatility and disruption, not imposed). Under LC50, median terminal corpus by tier (low /
medium / high): Rs 25.0M / 2.7M / 6.1M. With forced withdrawals at probability 1.0 the high tier's median falls
from Rs 6.4M to 1.3M (LC75), the low tier's from 26.2M to 17.9M.

## 4.2 Every pure objective is tier-blind
Max terminal wealth -> 75% start equity in all tiers. Min shortfall -> 15% start equity in all tiers (the
mirror-image corner). A combined objective P(success) - 1.0 x P(shortfall) first appeared to split tiers
(60/60/45%); a full-grid frontier analysis showed this was the scalarized optimum falling between grid
points. **Retracted.** Frontiers are nearly identical across tiers (shortfall at 75% start equity:
0.172 / 0.173 / 0.180).

## 4.3 Risk-budget policy
Maximizing success subject to P(shortfall) <= epsilon gives the same start equity for every tier: 45% at
epsilon = 0.02, 55% at 0.05, 65% at 0.10, 75% at 0.20 (Table `risk_budget_results.csv`). The tier-blind pooled
policy matches or differs only through grid discreteness, with out-of-sample success differences within noise.

## 4.4 Allocation follows the equity premium (break-even)
Realized equity-minus-G premium is +2.9%/yr. Subtracting a constant haircut from bootstrapped equity returns:
optimal start equity is 75% at premiums +2.9% and +1.9%, 60% at +0.9%, and 15% at -0.1%, -1.1%, -3.1%, in every
tier. The max-to-min flip occurs at a premium of roughly 0-1%/yr. Tier-conditioned minus pooled success gain is
<= 0.0015 (`premium_sweep.csv`); with withdrawal probability 0.5 the pattern is unchanged
(`premium_sweep_wd05.csv`).

## 4.5 Robustness (54 cells)
Nine scenarios (baseline; informal disruption rate x2 / x0.5; informal propensity x0.5 / x1.5; PLFS dispersion
x1.5 / x0.67; subsistence floor Rs 3,000 / 8,000) x two haircuts (0%, 2%) x three tiers. Paired bootstrap 95%
CIs for the tier-conditioned minus tier-blind success gain **exclude zero in 0 of 54 cells**; the largest
|gain| is 0.004 (`robustness.csv`). In most cells both policies are identical (gain exactly 0).
