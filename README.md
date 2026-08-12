# NPS Volatility-Conditioned Glide Path

A glide path for India's National Pension System (NPS) that conditions the equity/corporate-debt/gov-sec
split on **income volatility**, not just age — benchmarked against the PFRDA default "Auto Choice"
(LC50/LC75), which uses a fixed age-based schedule regardless of a subscriber's contribution capacity.

**Core claim:** the fixed age-based glide path fits salaried workers reasonably but is a poor fit for
informal-sector workers (gig, small trade, contract labor) whose contribution capacity is irregular
rather than steadily rising with age. A volatility-conditioned glide path should do better for this
population, measured via Monte Carlo simulation over real NPS NAV return series and PLFS-calibrated
synthetic income trajectories.

## Status (Phase 1, build week ending 2026-08-18)

The full pipeline runs end to end — see [`notebooks/00_phase1_demo.ipynb`](notebooks/00_phase1_demo.ipynb):
real NAV data → real PLFS calibration → synthetic PLFS-calibrated income population → real LC50/LC75
Monte Carlo baseline → first-cut volatility-conditioned optimizer.

Two results worth knowing up front:

1. The paper's core claim is an **emergent** property of the simulation: informal-sector cohorts skip
   NPS contributions in ~11% of months vs. ~0.07% for regular-salaried subscribers — a ~150x gap,
   driven entirely by PLFS-calibrated volatility, not hardcoded.
2. The first-cut optimizer does **not yet** show tier-differentiated glide paths — investigated, not
   hidden; see [`docs/phase1_status.md`](docs/phase1_status.md) (Day 6) for the diagnostic and why it's
   a genuine finding about this data, not a bug.

See [`docs/phase1_status.md`](docs/phase1_status.md) for the full day-by-day real-data-vs-assumption
record, and [`docs/data_sources.md`](docs/data_sources.md) for data provenance.

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
brew install poppler   # provides pdftotext, needed to parse the PLFS report -- see data/README.md
```

## Run the Phase 1 demo

```bash
# 1. NAV data (real, downloaded from npsnav.in)
python -m src.data.fetch_nav
python -m src.data.clean_nav

# 2. PLFS calibration (see data/README.md for the manual PDF download step first)
python -m src.data.plfs_calibration

# 3. Synthetic income population (PLFS-calibrated, fixed seed = reproducible)
python -m src.simulation.income_paths

# 4. PFRDA LC50/LC75 baseline
python -m src.simulation.market

# 5. First-cut volatility-conditioned optimizer
python -m src.optimization.glide_path_optimizer

# Or run the whole chain as one notebook:
jupyter execute notebooks/00_phase1_demo.ipynb
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
