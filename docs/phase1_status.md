# Phase 1 Status — real data vs. modeling assumption

Living document, updated daily through Phase 1 (2026-08-11 → 2026-08-18). Purpose: keep an honest,
running distinction between what's backed by real data and what's a documented modeling assumption —
both for eval credibility and for the paper's limitations section later.

## Day 1 (2026-08-11/12) — done

- **Real:** confirmed live access to NPS NAV history (npsnav.in, ~5yr daily, 2 PFMs × E/C/G resolved —
  see `docs/data_sources.md`) and PLFS Annual Report 2023-24 (published tables, downloaded).
- **Real:** confirmed PFRDA Annual Report 2023-24 downloaded, to be used to verify exact LC50/LC75
  tables against an authoritative source rather than memory (Day 5).
- **Known limitation, flagged now:** npsnav.in's historical depth is ~5 years (since 2021-08), not
  NPS's full history since 2004/2009. Block-bootstrap Monte Carlo (Day 5) will therefore sample from a
  5-year real-return window — reasonable for Phase 1, worth expanding sources in Phase 2 if a
  longer-history source is found.
- **Known limitation, flagged now:** PLFS calibration for Phase 1 uses published Annual Report *tables*
  (aggregate, pre-tabulated), not unit-level microdata — a legitimate, citable, but coarser calibration
  source than microdata.gov.in/NADA would give. Documented as a deliberate choice given the 1-week
  timeline; NADA registration (needs the user's own account) is a Phase 2 upgrade path, not a Phase 1
  blocker.
- Not yet done: nothing in this file is a modeling assumption yet, because no modeling has started —
  this section will grow starting Day 3 (PLFS calibration) and Day 4 (synthetic income generator),
  where real PLFS statistics get combined with necessary simplifying assumptions (e.g. seasonal-swing
  magnitude if quarterly CWS data isn't extractable in time).
