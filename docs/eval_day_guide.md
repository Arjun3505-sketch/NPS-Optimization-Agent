# Eval Day Guide — Phase 1

One document for Day 8: what this project is, why it exists, what it found, and how to demo it live.
Part A is the narrative to present. Part B is the practical run-through — what to open, what to run,
and prepared answers to the questions most likely to come up.

All numbers below are from the **corrected, post-review-pass pipeline**: a 207-month real NAV
bootstrap pool (a bug that let a fabricated fund-launch month into the bootstrap sample was found and
fixed — see A5) and a 36-year, age-25-to-60 simulation horizon (extended from 30 years so PFRDA's own
most conservative "55 & above" allocation plateau is actually exercised — see A5). Full day-by-day
history, including the pre-fix numbers as they were found at the time, is in
[`docs/phase1_status.md`](phase1_status.md); this doc only states the current, correct numbers.

---

## Part A — Project rundown

### A1. The problem

India's NPS defaults most subscribers into **Auto Choice** — a fixed, age-based glide path (LC50 by
default, LC75/LC25 optional) that shifts a subscriber's savings from equity (E) toward corporate debt
(C) and government securities (G) purely as a function of age, identical for every subscriber
regardless of their actual financial situation.

That's a reasonable design for a salaried worker with steadily rising, predictable income. It's a much
weaker fit for **informal-sector workers** — gig workers, small traders, casual/contract labour —
whose contribution *capacity* doesn't rise steadily with age; it's irregular, tied to how much they
earn that particular month. Per PLFS 2023-24 (see A2), this isn't a small edge case: self-employed and
casual labour together are **78.2%** of India's workforce (58.4% + 19.8%).

**The hypothesis this project tests:** a glide path that conditions on income *volatility*, not just
age, should do better for this population than the fixed default. This is a hypothesis to test via
simulation, not an assumed truth — no real subscriber-level NPS data exists to test it directly (A2).

### A2. The data gap, and why a hybrid approach is the honest answer

PFRDA doesn't release subscriber-level data. There is no way to observe real informal-sector NPS
subscribers' actual contribution histories. Two options: fabricate data and pretend it's real, or
build something defensible from two things that *are* real:

1. **Real market data** — NPS scheme-wise historical NAV (equity/corp-debt/gov-sec), pulled from
   npsnav.in: SBI Tier I back to 2009-05-05 (4,231 daily points), HDFC back to 2013-07-01 (3,182
   points). This gives real return series, spanning multiple real market regimes (2013 taper tantrum,
   2015-16 slide, 2020 COVID crash, 2022 rate-hike drawdown).
2. **PLFS-calibrated synthetic demographic data** — income/contribution trajectories generated to
   match real, published income-volatility statistics from India's Periodic Labour Force Survey (PLFS)
   Annual Report 2023-24, not invented.

This real-market-data + calibrated-synthetic-population split is standard practice in retirement
research when subscriber microdata isn't available. It's documented rigorously
([`docs/plfs_calibration.md`](plfs_calibration.md)) precisely because the calibration methodology is
itself a contribution, not just a means to an end.

### A3. The pipeline, day by day

| Day | What was built | Key output |
|---|---|---|
| 1 | Repo scaffolding; verified data access (npsnav.in, PLFS/PFRDA Annual Reports) | `docs/data_sources.md` |
| 2 | Real NAV ingestion (`src/data/fetch_nav.py`, `clean_nav.py`) | `data/processed/nav_returns.parquet` |
| 3 | PLFS calibration — 6 national tables transcribed (`src/data/plfs_calibration.py`) | `data/processed/plfs_calibration.csv` |
| 4 | Synthetic income/contribution generator (`src/simulation/income_paths.py`) | `data/processed/synthetic_income_paths.parquet` |
| 5 | PFRDA LC50/LC75 tables + Monte Carlo baseline (`src/optimization/pfrda_default.py`, `src/simulation/market.py`) | baseline terminal-corpus distributions |
| 6 | First-cut volatility-conditioned optimizer (`src/optimization/glide_path_optimizer.py`) | comparison chart + verification check |
| 7 | Consolidated `notebooks/00_phase1_demo.ipynb` | the single reproducible demo artifact |
| pre-8 | Review pass: found and fixed a real bug, extended the horizon, re-verified findings | this doc + corrected numbers |

Each day's full detail, including what was real vs. a labelled assumption at the time, is in
[`docs/phase1_status.md`](phase1_status.md) — don't re-narrate it at length on eval day, point to it if
asked for depth.

### A4. Results (current, corrected numbers)

**PLFS calibration** (`data/processed/plfs_calibration.csv` — see `docs/plfs_calibration.md` for full
methodology and source citations):

| employment_type | population share | mean monthly income | measured cross-cell CV | target individual CV | volatility tier |
|---|---|---|---|---|---|
| regular_salaried | 21.7% | ₹20,702 | 0.267 | 0.347 | **low** |
| casual_labour | 19.8% | ₹10,032 | 0.230 | 0.576 | **medium** |
| self_employed | 58.4% | ₹13,279 | **0.559** | 1.119 | **high** |

Notable, unforced finding: `self_employed` has *far* more real, measured cross-cell dispersion than
the other two — even before any modeling assumption is applied.

**The core claim, emergent from the simulation** (2,000 synthetic subscribers, 36-year/age-60 horizon):
zero-contribution-month rate is **0.067%** for `regular_salaried` vs. **10.05%** for `casual_labour`
and **10.20%** for `self_employed` — roughly a **150x** gap, produced entirely by PLFS-calibrated
income volatility and disruption mechanics, not hardcoded into the skip logic.

**PFRDA LC50/LC75 baseline vs. the first-cut optimizer** — P(terminal corpus ≥ that tier's own
LC50-median target), 200 bootstrapped market trials per fund per tier:

| volatility tier | n subscribers | LC50 | LC75 | optimized (ours) | optimizer's chosen params |
|---|---|---|---|---|---|
| low | 447 | 0.500 | 0.540 | **0.627** | equity 75%→30%, inflection age 45 |
| medium | 376 | 0.500 | 0.525 | **0.584** | equity 75%→30%, inflection age 45 |
| high | 1,177 | 0.500 | 0.516 | **0.557** | equity 75%→30%, inflection age 45 |

The optimized path beats both PFRDA defaults in every tier — the verification checkpoint passes. But
notice the last column: **identical parameters in every row.**

### A5. How to interpret the "no differentiation" finding — this is a strength, not a weakness

The optimizer does **not** produce different glide paths for different volatility tiers, which is what
the paper's central hypothesis predicted it would do. Rather than hide this or quietly reframe the
project around a different claim, it was **investigated**:

- Swept equity exposure against **four different utility/target formulations** (the tier's own LC50
  median, its 75th percentile, CVaR of the worst 10% of outcomes, and a tier-independent contribution
  floor). **Every one was monotonically increasing in equity exposure, for every tier** — more equity
  wins on every simple terminal-wealth metric tried, no crossover.
- This turns out to be a genuine property of the real 2009–2026 NAV data: the realized equity risk
  premium over this window was strong enough that even the worst-decile bootstrapped outcomes still
  favoured more equity, for everyone.
- **Re-tested after extending the horizon** from 30 to 36 years specifically to reach PFRDA's own most
  conservative "55 & above" plateau (previously never exercised at all) — the finding held. This rules
  out "the horizon was just too short to see de-risking pay off" as an explanation.

**What this means:** the risk that should differentiate informal workers' optimal glide path is
probably **not** well captured by terminal-wealth distribution shape (mean, median, P75, even
CVaR-10%). The more likely differentiator is **intra-horizon shortfall/sequence risk** — being unable
to add money, or needing a partial withdrawal, at exactly the wrong time — which a terminal-corpus-only
objective doesn't fully capture. That's a concrete, falsifiable, evidence-backed direction for Phase 2,
not a vague "more work needed." **Frame this as evidence the methodology wasn't tuned to produce a
predetermined answer** — a positive result here would have been less convincing without this negative
result to contrast it against.

### A6. What was fixed in the pre-Day-8 review pass (worth mentioning proactively)

Two independent read-only reviews of the finished Day 1–7 work found:

1. **A real bug**: `src/simulation/market.py`'s NAV-cleaning step had a `.dropna()` that silently
   failed to drop a fabricated month — SBI's May 2009 fund-launch period, where NAV was pegged flat and
   every day produced a real `0.0` return (not `NaN`), so the month survived a filter meant to remove
   it. That fake, zero-volatility month was being sampled into the Monte Carlo bootstrap. Fixed by
   excluding it explicitly; real bootstrap pool is 207 months, not 208.
2. **A design gap**: the 30-year horizon never reached PFRDA's own "55 & above" plateau (fixed in A5).
3. Everything else — the lognormal/AR(1) math, the block-bootstrap sampling, the PFRDA table
   transcription, cross-module data contracts, and every other specific number in the docs — was
   independently verified correct.

Mentioning this proactively, not defensively: catching and documenting your own bugs before a reviewer
does is exactly the discipline this project tried to maintain all week (see the Day 4 contribution-
formula bug for another example) — it's evidence of process, not a confession.

### A7. Phase 2 plan

- **Week 1**: CVaR-adjusted / shortfall-sensitive objective — directly motivated by A5's finding.
- **Week 2**: richer glide-path parametrization (piecewise-linear knots), jointly-optimized corporate-
  debt/gov-securities split (currently fixed, not optimized), proper constrained optimization.
- **Week 3**: statistical rigor — confidence intervals on the LC50-vs-LC75 and optimized-vs-baseline
  gaps, more Monte Carlo trials, sensitivity analysis.
- **Week 4**: PostgreSQL schema + a thin FastAPI `/simulate` endpoint.
- **Week 5**: Streamlit dashboard (glide path over time, percentile-band corpus projection, vs-PFRDA
  comparison); React only if meaningfully ahead of schedule.
- **Week 6**: a scoped conversational agent (tool-calling, profile extraction, plain-language tradeoff
  explanation).
- **Week 7**: RL comparison, stretch goal only if Weeks 1–4 land solidly.
- **Week 8**: integration, paper finalization, reproducibility appendix.
- Also flagged for Phase 2: NADA unit-level PLFS microdata (replacing the cell-level calibration), a
  verified/cited subsistence-floor figure (currently an illustrative ₹5,000), and HDFC as a bootstrap
  robustness/blend check.

---

## Part B — Practical eval-day run-through

### B1. What to show, in order

1. **`notebooks/00_phase1_demo.ipynb`** — open first. It runs the entire pipeline top to bottom with
   real outputs and the comparison chart inline; this is the single consolidated artifact.
2. **`src/optimization/pfrda_default.py`** — short, shows the real transcribed PFRDA tables (every row
   sums to 100%; point out the corrected duplicate-"53" typo as a sign of verifying against the source
   rather than trusting memory).
3. **`src/simulation/income_paths.py`** module docstring — shows the labelled-assumption discipline
   (everything not PLFS-measured is flagged `ASSUMPTION` in code) and the Day 4 bug story as a worked
   example.
4. **`src/optimization/glide_path_optimizer.py`** module docstring — the Day 6 finding and its
   four-metric diagnostic, in the author's own words, already written down before this doc existed.
5. **`docs/phase1_status.md`** and **`docs/plfs_calibration.md`** — the rigor backup, if asked "where's
   this number from."

### B2. Commands to run live, if asked to demonstrate reproducibility

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
brew install poppler   # provides pdftotext

python -m src.data.fetch_nav
python -m src.data.clean_nav
python -m src.data.plfs_calibration     # needs the PLFS PDF already in data/raw/ -- see note below
python -m src.simulation.income_paths
python -m src.simulation.market
python -m src.optimization.glide_path_optimizer
jupyter execute notebooks/00_phase1_demo.ipynb --output=00_phase1_demo.ipynb
```

**Heads-up before running live:** the PLFS calibration step needs `data/raw/PLFS_AnnualReport_2023-24.pdf`,
which was downloaded manually on Day 1 (`mospi.gov.in` serves a TLS cert that fails standard
validation — a known issue with NIC-hosted `.gov.in` sites, documented in `docs/data_sources.md`). It
won't reproduce automatically from a bare clone without that one manual step. Mention this proactively
rather than let a live command fail unexpectedly.

### B3. Anticipated tough questions, with prepared answers

**"Why does the optimizer pick the same glide path for every tier?"**
Investigated in Day 6, re-tested at the extended horizon in the pre-Day-8 pass (A5). Real property of
this NAV data — more equity wins on every terminal-wealth metric, for every tier, over 2009–2026. Points
to shortfall/sequence risk, not terminal wealth, as the real differentiator — a concrete Phase 2
direction, not a dead end.

**"How do you know your synthetic population is realistic?"**
Cohort shares match PLFS population shares within sampling noise (`notebooks/02_synthetic_population.ipynb`).
Be upfront: "realistic" means "calibrated to real, published PLFS aggregates," not "validated against
real individual trajectories" — those don't exist publicly, which is exactly why this project exists.

**"Why trust PLFS aggregate tables instead of real subscriber data?"**
No real subscriber-level NPS data is public (A2). PLFS Annual Report tables are real, government-
published, citable data — coarser than unit-level microdata, but not fabricated. NADA microdata
registration is the documented Phase 2 upgrade path, not pursued in Phase 1 because it requires
individual account registration with an unknown approval lag.

**"Why SBI only for the bootstrap, not a blend with HDFC?"**
SBI has longer real history (2009 vs. 2013) and >0.99 cross-PFM correlation for equity — blending would
mostly discard SBI's extra pre-2013 years (including the 2013 taper-tantrum drawdown) for little
diversification benefit. HDFC remains available as a Phase 2 robustness check.

**"Is the individual-dispersion multiplier (1.3×/2.0×/2.5×) just made up?"**
Yes — say so directly. It's explicitly labelled economic reasoning, not a PLFS statistic
(`docs/plfs_calibration.md`), and it's the specific assumption that reorders `casual_labour` above
`regular_salaried` into the volatility tiers. Better to state this plainly than have it discovered.

**"Did you validate the NAV data against a second source?"**
Only npsnav.in is used programmatically. npstrust.org.in was checked and confirmed to serve daily
snapshots suitable for manual spot-checking, but no automated cross-check was implemented in code —
stated explicitly in `docs/phase1_status.md`, not glossed over.

**"What was actually wrong in the code before this pass, and how much did it change your results?"**
State the NFO-month bug plainly (A6): ~0.5% of bootstrapped 12-month blocks could have included one
fabricated zero-return month. Quantify if pushed: the headline skip-rate gap (~150x) and the Day 6
finding (identical optimizer output across tiers) were both robust to the fix — nothing qualitative
changed, but the numbers are now provably correct rather than provably-almost-correct.

### B4. What not to overclaim

- PLFS calibration is **cell-level** (rural/urban × gender × quarter), not individual-level dispersion.
- The ₹5,000/month subsistence floor is **illustrative**, not a cited statistic.
- Casual labour's daily-to-monthly conversion uses a **24-days/month assumption**, not a parsed PLFS
  statistic.
- No statistical confidence intervals yet on the LC50-vs-LC75 or optimized-vs-baseline gaps — 200
  Monte Carlo trials, not yet the rigor Phase 2 Week 3 adds.
- Say **207 months** and **36-year/age-60 horizon** — not the earlier 208-month/30-year figures that
  appear in the Day 4–6 sections of `docs/phase1_status.md` (kept there deliberately as historical
  record, not because they're still current).
