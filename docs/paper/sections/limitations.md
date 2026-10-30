# Limitations

- **Synthetic population.** No subscriber-level NPS data is public. Cohort means/CVs come from PLFS
  Annual Report 2023-24 aggregates (cell-level, not individual-level dispersion). The individual
  dispersion multipliers (1.3x/2.0x/2.5x), AR(1) persistence, growth, disruption multipliers, contribution
  propensity, the Rs 5,000 subsistence floor, the 10% withdrawal fraction and the Rs 1,000 / 0.9 shortfall
  settings are labelled judgment calls, not measurements. Robustness to the main ones is in `robustness.csv`.
- **Single return source and window.** Bootstrap from SBI Tier I monthly returns, 207 months (2009-06 to
  2026-08), one strong-equity regime. The equity-premium sweep partly addresses window dependence by
  construction (constant haircut) but cannot add regimes the data lack. HDFC (2013+) not used.
- **Coarse policy class.** Three-parameter glide path, fixed 35/65 corporate-debt/gov-securities split of
  the non-equity remainder, 20-candidate grid. A richer policy class or a different objective could
  differentiate tiers; we claim only that the tested ones do not.
- **Targets are relative.** Success is measured against each scenario's own LC50-median corpus, not a
  replacement-rate goal; corpus values are nominal; no annuitization or decumulation phase.
- **Withdrawal model.** A single stylized rule (probability p of withdrawing 10% of the corpus in a
  disruption month); no behavioral response, taxes or NPS withdrawal-rule detail.
- **Statistical.** 100 search / 200 validation bootstrap market trials; confidence intervals resample
  trials only; candidate selection is in-sample on one seed (validation uses another).
