# Data

`data/raw/` is gitignored — nothing here is committed. To reproduce:

```bash
python -m src.data.fetch_nav      # pulls NAV history from npsnav.in into data/raw/
python -m src.data.fetch_plfs     # pulls/prepares PLFS calibration inputs into data/raw/
python -m src.data.clean_nav      # writes data/processed/nav_returns.parquet
```

See [`docs/data_sources.md`](../docs/data_sources.md) for exactly which sources were used, what worked,
what didn't, and the fallback chain — and [`docs/plfs_calibration.md`](../docs/plfs_calibration.md) for
how PLFS statistics are turned into the synthetic income-volatility calibration table.

`data/processed/` holds small, derived, reproducible artifacts (parquet/csv) — safe to version once
they're finalized; kept out of git for now while the pipeline is still being built.
