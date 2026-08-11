# PLFS Income-Volatility Calibration — methodology and numbers

Source: `data/raw/PLFS_AnnualReport_2023-24.pdf` (downloaded Day 1 — see `docs/data_sources.md`),
text-extracted via `pdftotext -layout`. Built by `src/data/plfs_calibration.py`. Output:
`data/processed/plfs_calibration.csv`.

**No unit-level microdata was used.** This uses the published, pre-tabulated national "Statement"
tables from the report's Summary of Findings — the plan's documented fallback for a 1-week timeline.
NADA registration (unit-level microdata) is a Phase 2 upgrade path.

## What's directly transcribed from the report (real data, not fabricated)

| Statement | Page (approx.) | What it gives |
|---|---|---|
| Statement 6 | p.12-13 | % of workers by status in employment (self-employed / regular salaried / casual labour) |
| Statement 7 | p.14-15 | % of workers by broad industry division |
| Statement 10 | p.18 | Average monthly wage/salary earnings, regular wage/salaried employees, by quarter × rural/urban × gender |
| Statement 11 | p.18-19 | Average daily wage earnings, casual labour (non-public-works), by quarter × rural/urban × gender |
| Statement 12 | p.19 | Average monthly (last-30-days) gross earnings, self-employed, by quarter × rural/urban × gender |
| Statement 14 | p.21 | Unemployment rate, current weekly status (CWS), all-India |

All figures are all-India, PLFS 2023-24 survey year (July 2023 – June 2024). Exact transcribed values
are in the `QUARTERLY_CELLS`, `EMPLOYMENT_TYPE_SHARE_PCT`, `INDUSTRY_SHARE_PCT`, and
`UNEMPLOYMENT_RATE_CWS_PCT` constants in `src/data/plfs_calibration.py`.

## Employment-type composition (cohort weights)

From Statement 6 (rural+urban, person): **self-employed 58.4%**, **casual labour 19.8%**,
**regular wage/salaried 21.7%**. These are the population weights used when assigning a synthetic
subscriber to a cohort in Day 4.

## Earnings level and measured (cell-level) dispersion

For each employment type, `plfs_calibration.py` computes a CV across the **16 real data points**
available per type: 4 quarters × {rural-male, rural-female, urban-male, urban-female}. This is a real,
data-derived quantity — but it understates true individual-level volatility, because averaging over
millions of people into 4 demographic cells suppresses most person-to-person and month-to-month
variance. Call this the **measured cross-cell CV**.

| employment_type | mean monthly income (Rs) | measured cross-cell CV |
|---|---|---|
| regular_salaried | 20,702 | 0.267 |
| casual_labour | 10,032 (24 days/mo × Rs/day) | 0.230 |
| self_employed | 13,279 | **0.559** |

**Notable, unforced finding:** even before any assumption is applied, `self_employed` shows *far* more
cross-cell dispersion than the other two types — driven by the huge rural-female (~Rs 4,700-5,200/mo)
vs urban-male (~Rs 22,000-23,000/mo) gap within "self-employed." This makes economic sense: the
self-employed category spans everything from subsistence/unpaid-helper work to small urban business
ownership, and it's a real result worth keeping in the paper, not an artifact.

`casual_labour`'s measured CV (0.230) is actually *lower* than `regular_salaried`'s (0.267) at this
cell-resolution — day-wage rates don't vary as much by gender/location as one might expect. This is
the raw data; what happens next is a deliberate, labelled judgment call, not a data artifact.

## The individual-dispersion assumption (labelled, not measured)

`INDIVIDUAL_DISPERSION_MULTIPLIER` scales the measured cross-cell CV up to a **target individual-level
CV**, using multipliers of **1.3× (regular_salaried), 2.0× (self_employed), 2.5× (casual_labour)**.
This is economic reasoning, not a PLFS statistic: casual daily-wage work plausibly has the largest
person-to-person and day-to-day swing (some days no work at all; wage bargained per engagement), regular
salaried/contracted pay is the most stable by construction (fixed monthly figure, employer-set), and
self-employment sits in between *on top of* its already-large measured heterogeneity.

**This assumption is what reorders `casual_labour` above `regular_salaried`** (0.230→0.576 vs
0.267→0.347) — in the raw cross-cell numbers they're close, with casual labour slightly lower. Flagging
this explicitly so it doesn't read as a hidden data artifact: it's a judgment call, made because the
national cell-level averages plausibly compress casual labour's true day-to-day volatility (a single
day's wage, not a monthly salary) more than they compress a salaried person's already-stable monthly
figure. **The correct way to settle this rather than assume it is unit-level PLFS microdata (NADA,
Phase 2)** — flagged as a concrete, testable follow-up, not a settled claim.

## Resulting calibration table and volatility tiers

| employment_type | population share | mean monthly income (Rs) | target individual CV | volatility tier |
|---|---|---|---|---|
| regular_salaried | 21.7% | 20,702 | 0.347 | **low** |
| casual_labour | 19.8% | 10,032 | 0.576 | **medium** |
| self_employed | 58.4% | 13,279 | 1.119 | **high** |

A target CV > 1 for `self_employed` (i.e. standard deviation exceeds the mean) is unusual for a normal
distribution but normal for a lognormal fit of a heavy-tailed, real-world income distribution — this is
exactly the shape self-employment income is known to take (a large mass of low-earning
subsistence/informal workers plus a long right tail of successful traders/business owners), and matches
the fact that self-employed is ~58% of the entire workforce, i.e. the volatility-conditioning claim's
single largest and most consequential cohort.

## Unemployment / disruption rate

Statement 14: **unemployment rate (CWS, all-India, rural+urban, person, 2023-24) = 4.9%**. Used in
Day 4 as the base rate for the "zero/reduced income month" Bernoulli process, differentiated by
employment type via a documented assumption (self-employed/casual labour scaled up from this base
rate since PLFS's unemployment concept — actively seeking and not finding work — undercounts the
underemployment risk informal workers actually face; regular salaried scaled down, reflecting greater
job security). Exact scaling factors will be set and justified in `src/simulation/income_paths.py`
(Day 4), not invented here.

## Industry composition (context, used for Day 4 seasonality tagging)

From Statement 7 (rural+urban, person): agriculture 46.1%, trade/hotel/restaurant 12.2%, construction
12.0%, other services 11.9%, manufacturing 11.4%, transport/storage/comms 5.6%, electricity/water 0.5%,
mining/quarrying 0.2%. Agriculture and construction are the seasonally-exposed sectors flagged in the
build plan; their seasonal-swing magnitude (e.g. ±15%) remains a documented simplifying assumption for
Day 4 since PLFS's quarterly CWS indicators by industry were not cleanly extractable from the report
text in the Phase 1 window (see limitation note below).

## Known limitations (Phase 1, honestly flagged)

- **Cell-level, not individual-level, real dispersion.** The measured CV uses 4 demographic cells ×
  4 quarters, not a true individual-level distribution. NADA microdata (Phase 2) would fix this
  directly.
- **Individual-dispersion multipliers are assumptions**, not measurements — see above.
- **Casual-labour daily→monthly conversion uses a documented 24-days/month assumption**, not a parsed
  PLFS "average days worked" statistic (Table 41 in the report's state-wise appendix could not be
  reliably parsed from extracted text in the time available; worth revisiting in Phase 2).
- **Per-employment-type disruption/unemployment rates are not directly published** by PLFS at this
  aggregation (unemployment is defined against the whole labour force, not conditional on employment
  type by construction) — Day 4 will need a documented scaling assumption, flagged there rather than
  invented here.
