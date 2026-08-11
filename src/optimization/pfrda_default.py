"""PFRDA Auto Choice default glide paths: LC75 (Aggressive), LC50 (Moderate/default), LC25 (Conservative).

Transcribed from a real PFM's investor document reproducing PFRDA's official age-wise Equity /
Corporate-Bonds / Govt-Securities allocation table (see docs/data_sources.md, section 4) -- verified
against a primary source rather than trusted from memory, per the Day 5 plan requirement.

One correction to the source table: it has a duplicated "53" age row where "54" is clearly intended
(the surrounding sequence is unambiguous: 53, [53->should be 54], 55&above). Corrected here.

Rule: allocation is fixed at the "up to 35" row for age <= 35, follows the per-age table for 36-54,
and is fixed at the "55 & above" row for age >= 55. Weights are E (equity) / C (corporate bonds) /
G (government securities), always summing to 100.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# age -> (E, C, G), for ages 36-54. Ages <=35 and >=55 are handled separately below (flat allocation).
LC75_TABLE = {
    36: (71, 11, 18), 37: (67, 12, 21), 38: (63, 13, 24), 39: (59, 14, 27), 40: (55, 15, 30),
    41: (51, 16, 33), 42: (47, 17, 36), 43: (43, 18, 39), 44: (39, 19, 42), 45: (35, 20, 45),
    46: (32, 20, 48), 47: (29, 20, 51), 48: (26, 20, 54), 49: (23, 20, 57), 50: (20, 20, 60),
    51: (19, 18, 63), 52: (18, 16, 66), 53: (17, 14, 69), 54: (16, 12, 72),
}
LC75_UP_TO_35 = (75, 10, 15)
LC75_55_PLUS = (15, 10, 75)

LC50_TABLE = {
    36: (48, 29, 23), 37: (46, 28, 26), 38: (44, 27, 29), 39: (42, 26, 32), 40: (40, 25, 35),
    41: (38, 24, 38), 42: (36, 23, 41), 43: (34, 22, 44), 44: (32, 21, 47), 45: (30, 20, 50),
    46: (28, 19, 53), 47: (26, 18, 56), 48: (24, 17, 59), 49: (22, 16, 62), 50: (20, 15, 65),
    51: (18, 14, 68), 52: (16, 13, 71), 53: (14, 12, 74), 54: (12, 11, 77),
}
LC50_UP_TO_35 = (50, 30, 20)
LC50_55_PLUS = (10, 10, 80)

LC25_TABLE = {
    36: (24, 43, 33), 37: (23, 41, 36), 38: (22, 39, 39), 39: (21, 37, 42), 40: (20, 35, 45),
    41: (19, 33, 48), 42: (18, 31, 51), 43: (17, 29, 54), 44: (16, 27, 57), 45: (15, 25, 60),
    46: (14, 23, 63), 47: (13, 21, 66), 48: (12, 19, 69), 49: (11, 17, 72), 50: (10, 15, 75),
    51: (9, 13, 78), 52: (8, 11, 81), 53: (7, 9, 84), 54: (6, 7, 87),
}
LC25_UP_TO_35 = (25, 45, 30)
LC25_55_PLUS = (5, 5, 90)

FUNDS = {
    "LC75": (LC75_UP_TO_35, LC75_TABLE, LC75_55_PLUS),
    "LC50": (LC50_UP_TO_35, LC50_TABLE, LC50_55_PLUS),
    "LC25": (LC25_UP_TO_35, LC25_TABLE, LC25_55_PLUS),
}

# LC50 is PFRDA's default when a subscriber doesn't actively choose (per the source doc: "In case
# subscriber fails to select any investment pattern then all the investments would be made to default
# choice i.e. LC_50 Moderate Life-cycle fund").
DEFAULT_FUND = "LC50"


def equity_weights_for_age(age: int, fund: str = DEFAULT_FUND) -> tuple[float, float, float]:
    """Return (w_E, w_C, w_G) as fractions (summing to 1.0) for a subscriber of given age."""
    up_to_35, table, plus_55 = FUNDS[fund]
    if age <= 35:
        e, c, g = up_to_35
    elif age >= 55:
        e, c, g = plus_55
    else:
        e, c, g = table[age]
    return e / 100, c / 100, g / 100


def glide_path(start_age: int, n_years: int, fund: str = DEFAULT_FUND) -> pd.DataFrame:
    """Full year-by-year glide path from start_age for n_years, as a DataFrame with columns
    [year, age, w_E, w_C, w_G]."""
    ages = start_age + np.arange(n_years)
    weights = [equity_weights_for_age(int(age), fund) for age in ages]
    df = pd.DataFrame(weights, columns=["w_E", "w_C", "w_G"])
    df.insert(0, "age", ages)
    df.insert(0, "year", np.arange(n_years))
    return df


if __name__ == "__main__":
    for fund in FUNDS:
        print(f"\n{fund} glide path, start age 25, 35 years:")
        print(glide_path(25, 35, fund).iloc[[0, 10, 15, 20, 25, 29, 30, 34]].to_string(index=False))
