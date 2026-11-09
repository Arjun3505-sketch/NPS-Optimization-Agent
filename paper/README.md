# Paper (IEEEtran conference format)

- `main.tex` — the paper (placeholders for authors/affiliation; no venue header). Compile with TeX Live or Overleaf
  (`pdflatex main.tex` twice). `figures/` holds the vector PDFs it includes.
- `python -m src.analysis.paper_figures` — regenerates all figures from `data/processed/*.csv` (also re-simulates
  the accumulation and withdrawal panels, ~1 min) and prints the numbers quoted in the text.
- `python paper/check_tex.py` — static checks (balanced environments, figures exist, refs/cites resolve).
  No LaTeX compiler is required for this check; the paper has NOT been compiled locally.
- Before submission: fill author block, verify every bibliography entry (volume/pages), choose venue header.
