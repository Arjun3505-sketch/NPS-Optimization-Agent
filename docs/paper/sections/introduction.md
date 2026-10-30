# 1. Introduction

India's National Pension System (NPS) places subscribers who make no active choice into an age-based
"Auto Choice" life-cycle fund (LC50 by default; LC75 and LC25 optional) whose equity, corporate-debt and
government-securities weights are a fixed function of age only. The design implicitly assumes steady,
rising contributions, as for a salaried worker. Self-employed and casual workers, who make up 78.2% of the
Indian workforce in the Periodic Labour Force Survey (PLFS) 2023-24, contribute irregularly. The natural
hypothesis is that an allocation conditioned on income volatility should serve them better than an
age-only schedule.

We test that hypothesis and find it is **not supported**. Using a simulation built from real NPS NAV
history (SBI Tier I, 2009-2026) and a synthetic subscriber population calibrated to published PLFS
statistics, we show that (i) income volatility has a large effect on *accumulation* (informal cohorts skip
roughly 10% of contribution months versus 0.07% for salaried; forced withdrawals shrink the median
corpus of the most disruption-prone cohort by up to 80%), but (ii) it has no measurable effect on the
*optimal allocation*. The optimal glide path is governed by the equity premium over government
securities, flipping from maximum to minimum equity at a premium of roughly 0-1% per year, identically
across volatility tiers; a tier-blind policy is statistically indistinguishable from a tier-conditioned one.

Contributions: (1) a reproducible, openly documented pipeline combining real NAV data with a PLFS-calibrated
synthetic population, with every non-measured assumption labelled; (2) path-dependent risk metrics
(intra-horizon shortfall, money-weighted return) and a liquidity (forced-withdrawal) channel tied to
calibrated disruption months; (3) a risk-budget formulation - maximize the probability of reaching a target
corpus subject to a cap on intra-horizon shortfall - with Pareto frontiers by tier; (4) a break-even
equity-premium analysis showing where, and that, allocation decouples from income volatility; (5) a
documented chain of negative results (terminal-wealth, shortfall, combined and withdrawal objectives all
fail to differentiate tiers), including one retracted apparent positive.
