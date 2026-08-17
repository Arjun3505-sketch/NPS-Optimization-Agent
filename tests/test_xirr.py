"""Validate the vectorized Newton XIRR solver (src/simulation/market.py::_xirr_annualized) against
hand-computable, closed-form cases before trusting it on real Monte Carlo output.

Usage:
    python -m pytest tests/test_xirr.py -v
    (or, if pytest isn't installed: python tests/test_xirr.py)
"""

from __future__ import annotations

import numpy as np

from src.simulation.market import _xirr_annualized


def test_single_contribution_single_payoff():
    """Contribute C once at t=0, receive terminal value V at the end of month n-1, no other cash
    flows. Closed form: (1+r)^(n-1) = V/C -> r = (V/C)^(1/(n-1)) - 1, annualized (1+r)^12 - 1."""
    n_months = 12
    contributions = np.zeros((1, n_months))
    contributions[0, 0] = 1000.0
    terminal_corpus = np.array([[1200.0]])

    expected_monthly_r = (1200.0 / 1000.0) ** (1 / (n_months - 1)) - 1
    expected_annualized = (1 + expected_monthly_r) ** 12 - 1

    result = _xirr_annualized(contributions, terminal_corpus, n_months)
    assert result.shape == (1, 1)
    assert abs(result[0, 0] - expected_annualized) < 1e-6, (result[0, 0], expected_annualized)


def test_pure_compounding_recovers_exact_rate():
    """Contribute C once at t=0, let it compound at a KNOWN monthly rate r0 with no further
    contributions: terminal = C * (1+r0)^(n-1). The solver should recover r0 (annualized) exactly."""
    n_months = 24
    r0 = 0.02  # 2%/month
    C = 1000.0
    terminal = C * (1 + r0) ** (n_months - 1)

    contributions = np.zeros((1, n_months))
    contributions[0, 0] = C
    terminal_corpus = np.array([[terminal]])

    expected_annualized = (1 + r0) ** 12 - 1
    result = _xirr_annualized(contributions, terminal_corpus, n_months)
    assert abs(result[0, 0] - expected_annualized) < 1e-6, (result[0, 0], expected_annualized)


def test_zero_return_breaks_even():
    """Level contributions summing exactly to the terminal value (no growth at all) should solve to
    ~0% monthly/annualized return."""
    n_months = 12
    monthly_contribution = 100.0
    contributions = np.full((1, n_months), monthly_contribution)
    terminal_corpus = np.array([[monthly_contribution * n_months]])  # exactly what was put in, no growth

    result = _xirr_annualized(contributions, terminal_corpus, n_months)
    assert abs(result[0, 0]) < 1e-6, result[0, 0]


def test_vectorizes_correctly_across_trials_and_subscribers():
    """Two subscribers with different contribution schedules, three trials with different terminal
    values each -- confirm every (trial, subscriber) cell is solved independently and correctly,
    not accidentally broadcast/mixed across the grid."""
    n_months = 12
    n_subscribers = 2
    n_trials = 3

    contributions = np.zeros((n_subscribers, n_months))
    contributions[0, 0] = 1000.0  # subscriber 0: single contribution
    contributions[1, :] = 50.0  # subscriber 1: level contributions

    # Build terminal values so each (trial, subscriber) has a distinct, independently-verifiable answer.
    terminal_corpus = np.zeros((n_trials, n_subscribers))
    known_monthly_rates = np.array([[0.01, 0.0], [0.02, 0.005], [0.03, -0.01]])  # (trial, subscriber)
    for trial in range(n_trials):
        r_sub0 = known_monthly_rates[trial, 0]
        terminal_corpus[trial, 0] = 1000.0 * (1 + r_sub0) ** (n_months - 1)
        r_sub1 = known_monthly_rates[trial, 1]
        # level contributions compounding at r_sub1: future value of an ordinary annuity
        if abs(r_sub1) < 1e-12:
            terminal_corpus[trial, 1] = 50.0 * n_months
        else:
            fv_factor = sum((1 + r_sub1) ** (n_months - 1 - t) for t in range(n_months))
            terminal_corpus[trial, 1] = 50.0 * fv_factor

    result = _xirr_annualized(contributions, terminal_corpus, n_months)
    expected_annualized = (1 + known_monthly_rates) ** 12 - 1
    assert np.allclose(result, expected_annualized, atol=1e-5), (result, expected_annualized)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS: {name}")
    print("\nAll XIRR solver validation tests passed.")
