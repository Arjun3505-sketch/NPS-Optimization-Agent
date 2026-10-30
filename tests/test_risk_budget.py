"""Unit checks for the selection logic in src/optimization/risk_budget.py (no simulation needed).

Usage: PYTHONPATH=. python tests/test_risk_budget.py
"""

from __future__ import annotations

import pandas as pd

from src.optimization.risk_budget import best_scalarized, best_under_budget, pareto_frontier


def _table():
    return pd.DataFrame(
        {
            "equity_start": [0.15, 0.30, 0.45, 0.60, 0.75, 0.45],
            "equity_end": [0.05] * 6,
            "inflection_age": [30] * 6,
            "success_prob": [0.30, 0.45, 0.55, 0.60, 0.62, 0.40],  # last row is dominated by row 3
            "shortfall_prob": [0.00, 0.01, 0.04, 0.10, 0.20, 0.08],
            "median_corpus": [1, 2, 3, 4, 5, 6],
        }
    )


def test_pareto_drops_dominated():
    f = pareto_frontier(_table())
    assert 0.40 not in f["success_prob"].tolist()
    assert len(f) == 5
    assert f["shortfall_prob"].is_monotonic_increasing and f["success_prob"].is_monotonic_increasing


def test_budget_selects_max_success_among_feasible():
    t = _table()
    assert best_under_budget(t, 0.05)["success_prob"] == 0.55
    assert best_under_budget(t, 0.25)["success_prob"] == 0.62
    assert best_under_budget(t, -1.0) is None


def test_budget_monotone_in_epsilon():
    t = _table()
    vals = [best_under_budget(t, e)["success_prob"] for e in [0.01, 0.05, 0.1, 0.2]]
    assert vals == sorted(vals)


def test_scalarized_corner_solutions():
    t = _table()
    assert best_scalarized(t, 0.0)["success_prob"] == 0.62  # pure growth -> max-equity corner
    assert best_scalarized(t, 100.0)["shortfall_prob"] == 0.0  # pure safety -> min-equity corner


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("PASS:", n)
