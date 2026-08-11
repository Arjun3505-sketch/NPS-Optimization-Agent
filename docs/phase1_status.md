# Phase 1 Status — real data vs. modeling assumption

Living document, updated daily through Phase 1 (2026-08-11 → 2026-08-18). Purpose: keep an honest,
running distinction between what's backed by real data and what's a documented modeling assumption —
both for eval credibility and for the paper's limitations section later.

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

## Not yet done

Nothing in this file past Day 2 is a modeling assumption yet, because the modeling proper hasn't
started — this section will grow starting Day 3 (PLFS calibration) and Day 4 (synthetic income
generator), where real PLFS statistics get combined with necessary simplifying assumptions (e.g.
seasonal-swing magnitude if quarterly CWS data isn't extractable in time).
