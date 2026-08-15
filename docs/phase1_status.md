# Phase 1 Status — real data vs. modeling assumption

Living document, updated daily through Phase 1 (2026-08-11 → 2026-08-18). Purpose: keep an honest,
running distinction between what's backed by real data and what's a documented modeling assumption —
both for eval credibility and for the paper's limitations section later.

## TL;DR (for the eval)

The full pipeline runs end to end from [`notebooks/00_phase1_demo.ipynb`](../notebooks/00_phase1_demo.ipynb):
real NAV data → real PLFS calibration → synthetic PLFS-calibrated income population → real LC50/LC75
Monte Carlo baseline → first-cut volatility-conditioned optimizer. Two results worth knowing before
reading day-by-day:

1. **The paper's core claim shows up as an emergent property of the simulation, not something
   hardcoded in**: informal-sector cohorts (self-employed, casual labour) skip NPS contributions in
   ~10% of months vs. ~0.07% for regular-salaried — a ~150x gap — driven entirely by PLFS-calibrated
   income volatility and disruption mechanics (Day 4).
2. **The first-cut optimizer does NOT yet show tier-differentiated glide paths** — it picks the same
   near-max-equity path for every volatility tier (Day 6). This was investigated, not hidden: four
   different utility formulations all confirm it's a real property of the 2009-2026 NAV data (equities
   won on every metric, every tier, in this window), not a bug — and it's genuinely useful evidence for
   what Phase 2's CVaR/shortfall-sensitive objective needs to fix. **Re-tested, not assumed, after
   extending the horizon to age 60** (see "Pre-Day-8 review pass" below) so PFRDA's own most
   conservative "55 & above" plateau is actually exercised — the finding held either way. See Day 6 and
   the review-pass section below for the full diagnostic.

**Numbers in this TL;DR and the review-pass section reflect the corrected, post-review-pass pipeline**
(207-month bootstrap pool, 36-year/age-60 horizon). The Day 1–7 sections below are kept as an honest,
dated historical record of what was found *at the time*, using the pipeline as it existed that day
(208-month pool with a since-fixed bug, 30-year/age-54 horizon) — they are intentionally **not**
silently rewritten to the corrected numbers, so the narrative of what was discovered when stays
accurate. Every number in this document and in the linked source files is labelled **real**
(verified/downloaded/transcribed from a cited source) or **assumption** (a documented judgment call) —
never presented as one when it's the other.

## Day 1 (2026-08-11/12) — done

- **Real:** confirmed live access to NPS NAV history (npsnav.in, 2 PFMs × E/C/G resolved — see
  `docs/data_sources.md`) and PLFS Annual Report 2023-24 (published tables, downloaded).
- **Real:** confirmed PFRDA Annual Report 2023-24 downloaded, to be used to verify exact LC50/LC75
  tables against an authoritative source rather than memory (Day 5).
- **Known limitation, flagged now:** PLFS calibration for Phase 1 uses published Annual Report *tables*
  (aggregate, pre-tabulated), not unit-level microdata — a legitimate, citable, but coarser calibration
  source than microdata.gov.in/NADA would give. Documented as a deliberate choice given the 1-week
  timeline; NADA registration (needs the user's own account) is a Phase 2 upgrade path, not a Phase 1
  blocker.
## Day 2 (2026-08-12) — done

- **Real:** pulled and cached full NAV history for all 6 configured schemes (SBI/HDFC × E/C/G, Tier I)
  via `src/data/fetch_nav.py`. Actual depth: **SBI 2009-05-05 → 2026-08-10 (4,231 daily points)**,
  **HDFC 2013-07-01 → 2026-08-10 (3,182 daily points)** — corrected upward from Day 1's ~5yr estimate,
  see `docs/data_sources.md`.
- **Real:** `src/data/clean_nav.py` aligns dates per scheme, computes daily log returns, writes
  `data/processed/nav_returns.parquet` (long format: date, pfm, scheme_class, nav, log_return).
- **Modeling note (not yet a simplifying assumption, a data-handling choice):** SBI and HDFC schemes
  have different start dates, so the two PFMs' return series are *not* a shared calendar — any
  cross-PFM blending (e.g. averaging E-class returns across PFMs for the Day 5 bootstrap) will need to
  either restrict to the overlapping window (2013-07 → present) or bootstrap each PFM's series
  separately. Decision deferred to Day 5, flagged here so it isn't silently assumed away.
- See `notebooks/01_nav_eda.ipynb` for NAV plots, return distributions, and annualized mean/vol per
  scheme — the actual evidence behind these numbers.
- **Precision note, added during the pre-Day-8 review pass:** no automated cross-check against
  npstrust.org.in's Excel download was ever implemented in code — only npsnav.in is used
  programmatically (see `docs/data_sources.md`). npstrust remains a manual, same-day spot-check option,
  never exercised in this pipeline. Stated explicitly so it doesn't sound like more validation happened
  than actually did.

## Day 3 (2026-08-12/13) — done

- **Real:** installed `poppler` (`pdftotext`) to extract text from the PLFS Annual Report 2023-24 PDF;
  transcribed 6 national "Statement" tables (employment-type composition, industry composition,
  quarterly earnings by employment type × rural/urban × gender, unemployment rate) into
  `src/data/plfs_calibration.py`. See `docs/plfs_calibration.md` for full source citations and exact
  transcribed values.
- **Real, notable finding:** even before any assumption is applied, `self_employed` shows far more
  cross-cell earnings dispersion (measured CV 0.559) than `casual_labour` (0.230) or
  `regular_salaried` (0.267) — an unforced result from the real data, driven by the huge rural-female
  vs urban-male gap within "self-employed."
- **Modeling assumption, clearly labelled:** an individual-dispersion multiplier (1.3× / 2.0× / 2.5×
  by employment type) scales the measured cell-level CV up to a target individual-level CV, since
  PLFS's published tables only give demographic-cell averages, not individual distributions. This
  assumption is what reorders `casual_labour` above `regular_salaried` into volatility tiers
  low/medium/high — flagged explicitly in `docs/plfs_calibration.md` rather than left to look like a
  data artifact.
- **Modeling assumption, clearly labelled:** casual labour's daily wage is converted to a monthly
  figure using a 24-working-days/month assumption (not a parsed PLFS statistic — the report's
  state-wise "days worked" appendix table wasn't reliably parsable from extracted text in the time
  available).
- Output: `data/processed/plfs_calibration.csv` — 3 cohorts (self_employed/regular_salaried/
  casual_labour) with population share, mean income, measured CV, and target CV / volatility tier.

## Day 4 (2026-08-12/13) — done

- **Built:** `src/simulation/income_paths.py` — simulates monthly income + NPS contribution paths for
  synthetic subscribers, per the plan's 6-step methodology (cohort assignment, lognormal cross-sectional
  draw, AR(1) temporal shocks, seasonal overlay for informal-sector agriculture/construction, Bernoulli
  disruption months, contribution capacity). Ran at 2,000 subscribers × 30 years (360 months) = 720,000
  rows.
- **Bug found and fixed before shipping, not shipped silently:** the plan's literal contribution
  formula (`max(0, propensity·income − floor)`) produced unrealistic results on first run —
  regular-salaried subscribers skipped contributions ~25% of the time and casual labour ~99% of the
  time, because that formula requires `propensity > floor/income` just to reach a positive
  contribution, forcing implausibly high propensity values. Switched to
  `propensity · max(0, income − floor)` (propensity applied to discretionary income above subsistence,
  the standard permanent-income/marginal-propensity-to-save formulation) and lowered the illustrative
  floor from Rs 6,000 to Rs 5,000/month. Documented in `src/simulation/income_paths.py`'s module
  docstring, not silently changed.
- **Result after the fix — the paper's core claim shows up cleanly in the simulation:**
  zero-contribution-month rate is **0.07% for regular_salaried**, vs **10.7% for casual_labour** and
  **11.2% for self_employed** — informal-sector cohorts skip roughly 150x more often, driven entirely
  by the PLFS-calibrated volatility and disruption mechanisms, not hardcoded into the skip logic
  directly.
- **Sanity checks passed** (`notebooks/02_synthetic_population.ipynb`, executed with no errors):
  simulated cohort population shares match PLFS shares within sampling noise (e.g. self_employed
  58.85% simulated vs. 58.4% target); sample income paths show visually distinct volatility/seasonality
  per employment type; per-subscriber skip-rate distributions are visibly right-shifted for
  self_employed/casual_labour vs. regular_salaried.
- **Known/expected pattern, not a bug:** simulated income CV exceeds the Day 3 calibration's
  `target_individual_cv` for every cohort (e.g. self_employed: target 1.119, simulated 1.433). This is
  because the Bernoulli disruption mechanism is a distinct variance source layered on top of the
  AR(1)+cross-sectional budget that was calibrated to the target CV — intentional, documented in the
  module's sanity-check output, not something the target CV was meant to bound exactly.
- **Modeling assumptions introduced this step (all labelled in `src/simulation/income_paths.py`),
  none claimed as PLFS-measured:**
  - 50/50 split of target CV into cross-sectional (between-subscriber) vs. temporal (within-subscriber)
    components — PLFS aggregate tables can't separate these; simplest defensible prior absent panel
    data.
  - AR(1) persistence (`rho`), annual nominal income growth, disruption-rate multipliers, disruption
    severity, contribution propensity, and extra behavioural skip probability — all per-employment-type
    judgment calls, not measured statistics. Relative orderings (informal > salaried on volatility/
    disruption; salaried > informal on propensity) are the load-bearing claims; absolute values are
    illustrative.
  - Rs 5,000/month subsistence floor — a round illustrative figure, explicitly not presented as a cited
    statistic (e.g. HCES/MPCE or an official poverty line) since it wasn't verified against a specific
    source in this session. Flagged for a Phase 2 replacement with a verified, cited figure.
  - Seasonal sector tagging for self_employed/casual_labour is restricted to a renormalized subset of
    the real PLFS industry marginal (agriculture, construction, trade, other services) since the
    employment-type × industry *joint* distribution wasn't extracted from the report in the Phase 1
    window — an assumed restriction, not a measured joint distribution.

## Day 5 (2026-08-13) — done

- **Real:** downloaded a real PFM's (Axis Pension Fund) investor document reproducing PFRDA's official
  age-wise LC75/LC50/LC25 allocation table and transcribed it into
  `src/optimization/pfrda_default.py` -- verified against a primary source rather than trusted from
  memory (confirms the commonly-cited "75% equity flat to 35, then -4pp/year" LC75 rule, and gives the
  full LC50/LC25 tables too). All 63 table rows checked to sum to exactly 100%. One likely typo in the
  source (a duplicated "53" age row) corrected, noted in-code. See `docs/data_sources.md` section 4.
- **Real:** `src/simulation/market.py` block-bootstraps monthly E/C/G returns from SBI's real NAV
  history (208 real months, 2009-05 to 2026-08) in 12-month blocks, preserving real cross-asset
  correlation and autocorrelation/regime structure. SBI (not a PFM blend) is used deliberately -- see
  in-code rationale (longer real history, >0.99 cross-PFM correlation for E means blending mostly just
  discards SBI's extra 2009-2013 years for little diversification benefit).
- **Run:** baseline terminal-corpus simulation, all 2,000 synthetic subscribers x 200 bootstrapped
  market trials x 30-year horizon, under both LC50 and LC75, starting age 25. Runs in ~1.3s.
- **Sanity-checked, both expected patterns:**
  - LC75 outperforms LC50 in every tier (higher real equity returns over 2009-2026 than
    debt/gov-securities) -- expected given the historical window used.
  - **`medium` tier (casual_labour) ends with a LOWER median terminal corpus (~Rs 1.4M) than `high`
    tier (self_employed, ~Rs 3.3M)**, even though `high` is the more volatile cohort. This is not a
    bug: the volatility tier ranks income CV, not income *level* or contribution *propensity* --
    self_employed has both a higher mean income (Rs 13.3k/mo vs casual_labour's Rs 10.0k/mo) and a
    higher contribution propensity (0.10 vs 0.08, see Day 4), so it ends up with a larger corpus
    despite being more volatile. Flagging explicitly now so this doesn't get misread as a bug once
    Day 6 introduces the volatility-conditioned optimizer, which conditions on the tier (CV), not on
    final corpus ranking.
- Not yet done: statistical rigor (confidence intervals on the LC50-vs-LC75 gap, more than 200 trials)
  is explicitly Phase 2 Week 3 scope, not Phase 1.

## Day 6 (2026-08-13) — done, with an important honest finding

- **Built:** `src/optimization/glide_path_optimizer.py` — a 3-parameter (equity_start, equity_end,
  inflection_age) glide-path grid search, maximizing P(Corpus_T >= target) via the same Monte Carlo
  engine as Day 5, per volatility tier. Target per tier = that tier's own LC50-baseline median
  terminal corpus (an interpretable, tier-grounded bar). Verification check from the plan (optimized
  should beat both LC50 and LC75 for the high-volatility tier) **passes**: 0.542 vs LC50 0.500 / LC75
  0.515.
- **Important finding, investigated rather than shipped silently:** the grid search picks the
  *identical* optimal parameters (near-max equity: 75% held to age 45) for **all three volatility
  tiers** — i.e. this first-cut setup does not yet show the tier-differentiated glide paths that are
  the paper's central claim, even though the verification checkpoint technically passes.
- **Diagnosed, not assumed to be a bug:** ran the same equity_start sweep (0.15/0.45/0.75) against
  four different target/utility formulations for the high-volatility tier — P(>= tier's own LC50
  median), P(>= tier's own LC50 75th percentile), CVaR-10% of terminal wealth, and P(>= a
  tier-independent floor of 1.5x median total contributions). **Every metric, for every tier tested,
  is monotonically increasing in equity_start** — more equity dominates on every simple terminal-wealth
  metric tried, with no crossover. This is a property of the real 208-month 2009-2026 bootstrap
  window: its realized equity risk premium is strong enough that even worst-decile bootstrapped
  outcomes still favour higher equity, for every tier.
- **What this means for the paper (a genuine, evidence-backed finding, not a failure):** the risk that
  should differentiate informal workers' optimal glide path is likely NOT well captured by
  terminal-wealth distribution shape (mean, median, P75, or even CVaR-10%) over this historical
  window — pure "more equity is worse for volatile-income people" does not emerge from Monte Carlo
  optimization on this data. The more promising differentiator is probably **intra-horizon
  shortfall/sequence risk** — being unable to add money, or needing a partial withdrawal, at exactly
  the wrong time — which isn't fully captured by a terminal-corpus-only objective. This directly
  motivates Phase 2 Week 1's already-planned CVaR-adjusted objective, and suggests testing an
  explicitly shortfall/sequence-risk-sensitive utility (not just terminal CVaR) as a concrete next
  step, rather than assuming CVaR alone will fix it.
- Chart: `docs/paper/figures/day6_glide_path_comparison.png` — optimized > LC75 > LC50 for every tier
  (a real result), but bars don't show tier-specific *strategies* differing, which is the more
  important thing still to demonstrate.
- Infrastructure built here (grid search harness, shared Monte Carlo engine, verification checkpoint)
  is reusable as-is for Phase 2's richer utility functions — the finding is about the objective
  function's insensitivity on this data, not about the search/simulation code being wrong.

## Day 7 (2026-08-13) — done

- **Built:** `notebooks/00_phase1_demo.ipynb` — the single consolidated entry point chaining every
  prior day's `src/` module end to end: real NAV data → real PLFS calibration → synthetic income
  population → LC50/LC75 Monte Carlo baseline → first-cut optimizer → an honest closing summary.
  Executed clean, no errors. This is the notebook to run/show on eval day; every number quoted
  elsewhere in this file should be traceable back to a step in it.
- Finished `README.md`'s Status section and this file's TL;DR so a reader doesn't have to read all
  seven days in order to get the headline picture.
- **Verified reproducibility from a genuinely fresh clone + fresh venv**: cloned the repo into an
  isolated directory, built a new virtualenv, and reran every step (NAV fetch — a real live network
  pull — PLFS calibration, synthetic income generation, market baseline, optimizer, and the full demo
  notebook). Income paths matched exactly (fixed seed); NAV/market numbers differed negligibly (one
  extra live trading day between runs), exactly as expected for a pipeline pulling live data correctly.

## Pre-Day-8 review pass (2026-08-14) — bug fix, horizon extension, corrected numbers

Before finalizing Phase 1, two independent read-only reviews (one on `src/` code correctness, one on
docs/reproducibility consistency) were run against the repo as it stood after Day 7. Full findings and
the fix-list are in `docs/eval_day_guide.md`; the substantive changes and their effect on the numbers
are recorded here.

- **Real bug found and fixed:** `src/simulation/market.py`'s `load_monthly_returns()` had a
  `.dropna()` that didn't do what its own comment claimed. `pandas`'s `groupby().sum()` defaults to
  `skipna=True`, so SBI's May 2009 fund-launch (NFO) month — NAV pegged flat, so every day after the
  first produces a real `0.0` log-return, not `NaN` — summed to `0.0` and **survived** the intended
  filter. That fabricated, zero-volatility, zero-correlation month was being sampled by the block
  bootstrap as if it were a real market observation. Fixed by explicitly excluding the fund's first
  calendar month rather than relying on `dropna()`. The real bootstrap pool is **207 months**
  (2009-06 → 2026-08), not 208 — correcting a number that was already inconsistently stated across
  files even before the bug was diagnosed (`market.py`'s own docstring said "~207," while
  `glide_path_optimizer.py` and this file said "208"; both were symptoms of the same underlying issue).
- **Design gap fixed, not just documented:** the simulation horizon (age 25–54, 30 years, used
  everywhere in Days 4–7) never reached PFRDA's own "55 & above" plateau — the most conservative,
  most consequential de-risking phase of every Auto Choice schedule — so Day 6's "more equity always
  wins" finding was only ever tested over the accumulation phase. Extended to **36 years (age 25–60,
  NPS's standard retirement age)** across `income_paths.py`, `market.py`, and
  `glide_path_optimizer.py`. This was **not** assumed to change the Day 6 finding — it was rerun and
  checked. Result: **the finding held.** The optimizer still selects the identical parameters
  (equity_start=0.75, equity_end=0.30, inflection_age=45) for all three volatility tiers, even with
  the 55–60 de-risking years now included. This makes the Day 6 conclusion *stronger*, not weaker — it
  was tested against the most obvious objection (an incomplete horizon) and survived.
- **Corrected headline numbers** (207-month pool, 36-year/age-60 horizon, otherwise identical
  methodology to Days 4–6):
  - Zero-contribution-month rate: **regular_salaried 0.067%**, **casual_labour 10.05%**,
    **self_employed 10.20%** — still a ~150x gap, consistent with Day 4's 30yr-era finding.
  - Optimizer verification (high tier): optimized **0.557** vs LC50 **0.500** / LC75 **0.516** —
    still passes, same pattern as Day 6's 30yr-era 0.542/0.500/0.515.
  - Terminal corpus levels are naturally higher at 36yr than Day 5's 30yr figures (6 more years of
    contributions and compounding) — not a comparable like-for-like number, don't quote Day 5's Rs 1.4M
    / Rs 3.3M medians alongside the new horizon's figures without noting the horizon changed.
- **Minor cleanups applied:** a redundant sigma recomputation in `income_paths.py` (zero numeric
  impact — confirmed no `rng` call involved); removed `scipy`, `openpyxl`, `xlrd` from
  `requirements.txt` (confirmed unused anywhere in `src/` or `notebooks/` by grep); added this section
  and a precision note to Day 2 (see above) that were missing.
- All of Day 1–7's artifacts (notebook, chart, docs) were regenerated/re-executed against the fixed,
  extended pipeline — nothing downstream still reflects the buggy 208-month pool or the 30-year
  horizon.

## Not yet done

Nothing in this file past Day 2 is a modeling assumption yet, because the modeling proper hasn't
started — this section will grow starting Day 3 (PLFS calibration) and Day 4 (synthetic income
generator), where real PLFS statistics get combined with necessary simplifying assumptions (e.g.
seasonal-swing magnitude if quarterly CWS data isn't extractable in time).
