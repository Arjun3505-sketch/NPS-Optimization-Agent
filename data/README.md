# Data

`data/raw/` is gitignored — nothing here is committed. To reproduce:

```bash
python -m src.data.fetch_nav          # pulls NAV history from npsnav.in into data/raw/
python -m src.data.clean_nav          # writes data/processed/nav_returns.parquet

# PLFS: no bulk API exists (see docs/data_sources.md). Manually download the PLFS Annual Report
# 2023-24 PDF (mospi.gov.in serves a cert chain that fails standard validation -- see data_sources.md)
# into data/raw/PLFS_AnnualReport_2023-24.pdf, then:
brew install poppler                              # provides pdftotext
pdftotext -layout data/raw/PLFS_AnnualReport_2023-24.pdf data/raw/PLFS_AnnualReport_2023-24.txt
python -m src.data.plfs_calibration               # writes data/processed/plfs_calibration.csv
```

See [`docs/data_sources.md`](../docs/data_sources.md) for exactly which sources were used, what worked,
what didn't, and the fallback chain — and [`docs/plfs_calibration.md`](../docs/plfs_calibration.md) for
how PLFS statistics are turned into the synthetic income-volatility calibration table.

`data/processed/` holds small, derived, reproducible artifacts (parquet/csv) — safe to version once
they're finalized; kept out of git for now while the pipeline is still being built.
