# NPS Volatility-Conditioned Glide Path

A glide path for India's National Pension System (NPS) that conditions the equity/corporate-debt/gov-sec
split on **income volatility**, not just age — benchmarked against the PFRDA default "Auto Choice"
(LC50/LC75), which uses a fixed age-based schedule regardless of a subscriber's contribution capacity.

**Core claim:** the fixed age-based glide path fits salaried workers reasonably but is a poor fit for
informal-sector workers (gig, small trade, contract labor) whose contribution capacity is irregular
rather than steadily rising with age. A volatility-conditioned glide path should do better for this
population, measured via Monte Carlo simulation over real NPS NAV return series and PLFS-calibrated
synthetic income trajectories.

## Status

Phase 1 (build week ending 2026-08-18): data pipeline, PLFS-calibrated synthetic population, baseline
Monte Carlo under LC50/LC75, and a first-cut volatility-conditioned glide path. See
[`docs/phase1_status.md`](docs/phase1_status.md) for what's real data vs. modeling assumption at any
given point, and [`docs/data_sources.md`](docs/data_sources.md) for data provenance.

Full build plan: `/Users/Ajay/.claude/plans/1-problem-framing-sharpen-golden-sutherland.md`.

## Why this hybrid data approach

No real subscriber-level NPS data is publicly available. This project combines:
- **Real market data** — NPS scheme-wise historical NAV (equity/corp-debt/gov-sec), giving real return
  series for simulation.
- **PLFS-calibrated synthetic demographic data** — income/contribution trajectories generated to match
  real, published income-volatility statistics from India's Periodic Labour Force Survey (PLFS), not
  fabricated.

This split is standard in retirement-planning research and is documented rigorously in
`docs/plfs_calibration.md` since the calibration methodology is itself a contribution.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Repository layout

```
data/           raw (gitignored) and processed NAV/PLFS data
docs/           data provenance, calibration methodology, paper drafts
notebooks/      exploratory + the Phase 1 demo notebook
src/data/       NAV/PLFS fetch + cleaning
src/simulation/ synthetic income paths + Monte Carlo market engine
src/optimization/  PFRDA default rules + the volatility-conditioned optimizer
src/api/        FastAPI wrapper (Phase 2)
src/db/         Postgres models (Phase 2)
src/agent/      tool-calling agent (Phase 2)
app/            Streamlit dashboard (Phase 2)
tests/          unit tests
```

## Reproducing the data

See [`data/README.md`](data/README.md).
