# Data Sources — verified 2026-08-11/12

This records exactly what was checked, what worked, what didn't, and the chosen primary/fallback for
each dataset. This is the paper's data-provenance record — kept factual and dated, not aspirational.

## 1. NPS scheme-wise historical NAV (market/return data)

**Primary: [npsnav.in](https://npsnav.in)** — free, no-auth JSON API. Verified live:
- `GET /api/latest` — all 282 active schemes, `[scheme_code, nav]` pairs, updated daily (metadata
  timestamp confirmed current).
- `GET /api/historical/{scheme_code}` — actually pulled (Day 2) for the 6 scheme codes below. Real
  depth is much better than the initial spot-check suggested: **SBI Tier I schemes go back to
  2009-05-05 (4,231 points)**, **HDFC Tier I schemes go back to 2013-07-01 (3,182 points)** — i.e.
  ~17 and ~13 years of daily history respectively, not just ~5 years. (An earlier automated single-URL
  check under-read the response and reported ~5 years; corrected here after actually fetching and
  inspecting the full series on Day 2 — see `docs/phase1_status.md`.) This is a much stronger basis for
  block-bootstrap Monte Carlo (Day 5): it spans multiple real market regimes (2013 taper tantrum,
  2015-16 slide, 2020 COVID crash, 2022 rate-hike drawdown), not just one recent window.
- License: code AGPL-3.0, **data CC BY-NC 4.0** (non-commercial). Fine for this academic project; cite
  explicitly in the paper, do not redistribute commercially. GitHub mirror
  (`github.com/rishikeshsreehari/npsnav`) also exists for reproducibility if the live API changes.

**Scheme codes resolved for two PFMs (Tier I, the tier this project models)**, needed for
`src/data/fetch_nav.py`:

| PFM | Scheme E (equity) | Scheme C (corp debt) | Scheme G (gov securities) |
|---|---|---|---|
| SBI Pension Funds | `SM001003` | `SM001004` | `SM001005` |
| HDFC Pension Fund Mgmt | `SM008001` | `SM008002` | `SM008003` |

Using these two PFMs for Phase 1 (bounds scope per plan); can expand to more PFMs in Phase 2 for
robustness.

**Validation source: [npstrust.org.in/nav-report-excel](https://npstrust.org.in/nav-report-excel)** —
verified live, returns a real downloadable `.xls` (confirmed: 263 scheme rows, `DATE OF NAV / PFM NAME /
SCHEME ID / SCHEME NAME / NAV VALUE` columns, current day only). Useful for spot-checking a handful of
dates against npsnav.in, **not** a historical bulk source — it's a daily snapshot only.

**Not usable: [npstrust.org.in/return-of-nps-scheme-archive](https://npstrust.org.in/return-of-nps-scheme-archive)**
— checked live, page shows "Coming Soon," no controls or export of any kind. Dropped from the pipeline;
npsnav.in is the sole historical source, npstrust the sole (same-day) validation source.

**Not pursued: individual PFM sites** (e.g. dsppension.com) — not needed since npsnav.in already covers
both PFMs used.

## 2. PLFS (income-volatility calibration)

**Primary for Phase 1: PLFS Annual Report PDFs (published tables), downloaded directly:**
- `data/raw/PLFS_AnnualReport_2023-24.pdf` — from `mospi.gov.in/sites/default/files/publication_reports/AnnualReport_PLFS2023-24L2.pdf`
  (~26.9 MB, confirmed valid PDF, HTTP 200).
- **Access note:** `mospi.gov.in` (both bare and `www.`) serves a TLS certificate that fails standard
  validation (self-signed cert in chain) — a known issue with NIC-hosted Indian `.gov.in` sites, not
  specific to this file. Downloaded with certificate verification disabled (`curl -k`), with the user's
  explicit confirmation before doing so. Anyone reproducing this pipeline on a machine with a stricter
  TLS policy should expect the same and may need the same workaround, or to fetch the PDF manually via
  a browser.
- Table extraction (earnings/CV by sector × employment type) happens in Day 3 — this file is downloaded
  and confirmed valid, not yet parsed.

**Fallback/upgrade path, not used in Phase 1: [microdata.gov.in/NADA](https://microdata.gov.in/NADA)**
unit-level PLFS microdata — confirmed to exist and be a real, catalogued source (e.g. PLFS 2023-24
catalog entry), but requires **free account registration** + a per-dataset access request + `.rar`
download, which is an account-creation step the user needs to do themselves (not something to automate).
**Recommendation:** register on Day 1-2 of Phase 2 (not blocking Phase 1) if unit-level microdata would
materially improve the calibration; the published Annual Report tables are a legitimate, citable
calibration source on their own and this fallback is documented as a deliberate methodological choice,
not a shortcut.

**Not pursued in Phase 1: `esankhyiki.mospi.gov.in`** pre-tabulated dashboard — checked, loads but no
navigable PLFS table content surfaced in a quick check; the Annual Report PDF already provides what's
needed, so not pursued further. Worth revisiting in Phase 2 if the PDF tables turn out to be harder to
parse than expected.

## 3. PFRDA context/calibration (AUM, subscriber stats)

**Primary:** [pfrda.org.in](https://www.pfrda.org.in) — reachable, standard HTTPS (no TLS issue, unlike
mospi.gov.in). Annual reports listed at
`pfrda.org.in/web/pfrda/research-publications/annual-reports`. Downloaded:
- `data/raw/PFRDA_AnnualReport_2023-24.pdf` — from
  `www.pfrda.org.in/documents/33652/146225/Annual_Report_2023-24_English-c.pdf` (~63.4 MB, confirmed
  valid PDF, HTTP 200, same FY as the PLFS report above for consistency).

Used for paper context (AUM/subscriber/sector stats) and as a source to verify the exact LC50/LC75
Auto Choice equity-by-age tables against (Day 5), rather than trusting memory.

## 4. PFRDA Auto Choice (LC75/LC50/LC25) exact age-wise allocation table

**Source: Axis Pension Fund Management's investor-facing "Investment Choices under NPS" PDF**
(`axispensionfund.com/wordpress/wp-content/uploads/2022/10/Investment-Choices-under-NPS-2.pdf`,
downloaded Day 5, saved to `data/raw/AxisPensionFund_NPS_InvestmentChoices.pdf`) — a real PFM
reproducing PFRDA's official age-wise Equity/Corporate-Bonds/Govt-Securities table for all three Auto
Choice life-cycle funds (LC75 Aggressive, LC50 Moderate/default, LC25 Conservative), age "up to 35"
through "55 & above," in 1-year steps. Confirms the commonly-cited LC75 rule (75% equity capped until
35, reducing ~4pp/year) against an authoritative-looking primary table rather than trusting memory, per
the plan's Day 5 verification requirement. Full table transcribed into
`src/optimization/pfrda_default.py`. One apparent typo in the source PDF (a duplicated "53" row where
"54" is clearly meant, based on the surrounding sequence) was corrected — noted in-code.

## Summary of Day 1 decisions

| Dataset | Primary | Fallback/validation | Status |
|---|---|---|---|
| NAV history | npsnav.in historical API | npstrust nav-report-excel (same-day spot-check) | ✅ verified working |
| PLFS income volatility | Annual Report 2023-24 PDF (published tables) | microdata.gov.in/NADA unit-level (Phase 2, needs user registration) | ✅ PDF downloaded, parsing is Day 3 |
| PFRDA context/LC50-LC75 verification | PFRDA Annual Report 2023-24 PDF | — | ✅ PDF downloaded |
