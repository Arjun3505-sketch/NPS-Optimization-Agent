"""Generate all paper figures (vector PDF) and print the numbers quoted in paper/main.tex.

Reads data/processed/*.csv (produced by risk_budget, premium_sweep, robustness) and re-simulates only the cheap
panels (accumulation by tier, withdrawal effect). Headline numbers are asserted so the paper cannot silently
drift from the data.   Usage: python -m src.analysis.paper_figures
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch

from src.optimization.glide_path_optimizer import _pfrda_weight_path
from src.optimization.risk_budget import MARKET_SEED_VALIDATE, TIERS, pareto_frontier
from src.simulation.market import (
    expand_glide_path_to_monthly, load_contribution_matrix, load_disruption_matrix,
    simulate_path_dependent_metrics_for_weight_path,
)

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "processed"
OUT = ROOT / "paper" / "figures"
COL = {"low": "#1b6ca8", "medium": "#e08a00", "high": "#b2182b"}
LAB = {"low": "Low (salaried)", "medium": "Medium (casual)", "high": "High (self-emp.)"}
plt.rcParams.update({"font.family": "serif", "font.size": 8, "axes.labelsize": 8, "legend.fontsize": 7,
                     "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42})
W1, W2 = 3.45, 7.1  # IEEE single / double column width (in)
NUM: dict = {}


def save(fig, name):
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


def fig_pipeline():
    fig, ax = plt.subplots(figsize=(W2, 2.0)); ax.axis("off"); ax.set_xlim(0, 100); ax.set_ylim(0, 30)
    boxes = [(1, "Real NPS NAV\n(SBI Tier I E/C/G,\n207 months)", "#dce9f5"),
             (21, "Block bootstrap\nmarket paths\n(12-month blocks)", "#dce9f5"),
             (41, "PLFS Annual Report\n2023-24 calibration\n(3 cohorts / tiers)", "#fde8c8"),
             (61, "Synthetic subscribers\n(income, disruption,\ncontributions)", "#fde8c8"),
             (81, "Glide-path\nevaluation &\nrisk-budget policy", "#e3f1e0")]
    for x, t, c in boxes:
        ax.add_patch(FancyBboxPatch((x, 12), 17, 14, boxstyle="round,pad=0.4", fc=c, ec="k", lw=0.7))
        ax.text(x + 8.5, 19, t, ha="center", va="center", fontsize=6.5)
    for x in (18.6, 38.6, 58.6, 78.6):
        ax.annotate("", (x + 2.4, 19), (x, 19), arrowprops=dict(arrowstyle="->", lw=0.9))
    ax.text(50, 6.2, "Outcomes: terminal-corpus success, intra-horizon shortfall, XIRR, withdrawal channel  "
            r"$\rightarrow$  premium sweep, tier-blind benchmark, 54-cell robustness  $\rightarrow$  "
            "risk-budget recommender (API)", ha="center", fontsize=6.5)
    ax.text(50, 1.5, "blue = real data   orange = calibrated synthetic (labelled assumptions)   green = analysis",
            ha="center", fontsize=6, style="italic")
    save(fig, "fig1_pipeline")


def accumulation():
    contributions, meta = load_contribution_matrix()
    res = {}
    for t in TIERS:
        c = contributions[(meta["volatility_tier"] == t).to_numpy()]
        r = simulate_path_dependent_metrics_for_weight_path(
            _pfrda_weight_path("LC50"), c, 200, MARKET_SEED_VALIDATE, compute_xirr=False)
        tc = r["terminal_corpus"]
        res[t] = {"skip": (c == 0).mean() * 100, "pcts": np.percentile(tc, [10, 50, 90]) / 1e6, "n": c.shape[0]}
    NUM["accumulation"] = res
    fig, ax = plt.subplots(2, 1, figsize=(W1, 4.3))
    x = np.arange(3)
    ax[0].bar(x, [res[t]["skip"] for t in TIERS], color=[COL[t] for t in TIERS])
    for i, t in enumerate(TIERS):
        ax[0].text(i, res[t]["skip"] + 0.2, f'{res[t]["skip"]:.2f}%', ha="center", fontsize=7)
    ax[0].set_xticks(x, [LAB[t] for t in TIERS], fontsize=6.5); ax[0].set_ylabel("Zero-contribution months (%)")
    ax[0].set_title("Contribution irregularity", fontsize=8)
    for i, t in enumerate(TIERS):
        p10, p50, p90 = res[t]["pcts"]
        ax[1].errorbar(i, p50, yerr=[[p50 - p10], [p90 - p50]], fmt="o", color=COL[t], capsize=4, ms=5)
        ax[1].text(i + 0.12, p50, f"{p50:.1f}", fontsize=7, va="center")
    ax[1].set_yscale("log"); ax[1].set_xticks(x, [LAB[t] for t in TIERS], fontsize=6.5); ax[1].set_xlim(-0.5, 2.7)
    ax[1].set_ylabel("Terminal corpus, LC50 (Rs million)"); ax[1].set_title("Accumulation: median and P10-P90", fontsize=8)
    fig.tight_layout(); save(fig, "fig2_accumulation")
    assert abs(res["high"]["skip"] - 10.2) < 0.2 and abs(res["low"]["skip"] - 0.067) < 0.01


def cand():
    return {t: pd.read_csv(D / f"candidate_table_{t}.csv") for t in TIERS}


def fig_objective_ladder():
    C = cand(); rows = []
    for t in TIERS:
        c = C[t]
        rows.append({"tier": t, "terminal wealth": c.loc[c.success_prob.idxmax(), "equity_start"],
                     "shortfall only": c.loc[c.shortfall_prob.idxmin(), "equity_start"],
                     "success - 1.0 x shortfall": c.loc[(c.success_prob - c.shortfall_prob).idxmax(), "equity_start"]})
    df = pd.DataFrame(rows).set_index("tier"); NUM["ladder"] = df
    fig, ax = plt.subplots(figsize=(W1, 2.3)); w = 0.26
    for j, t in enumerate(TIERS):
        ax.bar(np.arange(3) + (j - 1) * w, df.loc[t].to_numpy() * 100, w, color=COL[t], label=LAB[t])
    ax.set_xticks(range(3), ["Max terminal\nwealth", "Min\nshortfall", r"Success $-\,1.0\times$"+"\nshortfall"], fontsize=6.5)
    ax.set_ylabel("Optimal starting equity (%)"); ax.set_ylim(0, 90); ax.legend(frameon=False, loc="upper center", ncol=1, fontsize=6)
    fig.tight_layout(); save(fig, "fig3_objective_ladder")


def fig_frontiers():
    C = cand(); fig, ax = plt.subplots(2, 1, figsize=(W1, 4.6))
    for t in TIERS:
        f = pareto_frontier(C[t])
        ax[0].plot(f.equity_start * 100, f.shortfall_prob, "o-", color=COL[t], ms=3.5, lw=1, alpha=0.9, label=LAB[t])
        ax[1].plot(f.shortfall_prob, f.success_prob, "o-", color=COL[t], ms=3, lw=1, label=LAB[t])
    NUM["frontier_end"] = {t: pareto_frontier(C[t]).iloc[-1][["equity_start", "shortfall_prob"]].tolist() for t in TIERS}
    ax[0].set_xlabel("Starting equity on the frontier (%)"); ax[0].set_ylabel("P(intra-horizon shortfall)")
    ax[0].set_title("Risk-allocation map is tier-invariant", fontsize=8); ax[0].legend(frameon=False)
    ax[1].set_xlabel("P(intra-horizon shortfall)"); ax[1].set_ylabel("Success probability\n(vs own LC50-median target)")
    ax[1].set_title("Frontiers (levels differ: tier-specific targets)", fontsize=8)
    fig.tight_layout(); save(fig, "fig4_frontiers")
    NUM["short75"] = {t: float(C[t][(C[t].equity_start == 0.75) & (C[t].equity_end == 0.3) & (C[t].inflection_age == 45)].shortfall_prob.iloc[0]) for t in TIERS}


def fig_withdrawal():
    contributions, meta = load_contribution_matrix(); d = load_disruption_matrix(); wp = expand_glide_path_to_monthly(25, 36, "LC75")
    ps = [0, 0.25, 0.5, 1.0]; med = {}
    for t in TIERS:
        k = (meta["volatility_tier"] == t).to_numpy()
        med[t] = [np.median(simulate_path_dependent_metrics_for_weight_path(
            wp, contributions[k], 60, 1, compute_xirr=False, disruption=d[k], withdrawal_prob=p)["terminal_corpus"]) / 1e6 for p in ps]
    NUM["withdrawal"] = med
    fig, ax = plt.subplots(figsize=(W1, 2.4))
    for t in TIERS:
        ax.plot(ps, np.array(med[t]) / med[t][0] * 100, "o-", color=COL[t], ms=3.5, label=LAB[t])
    ax.set_xlabel("Withdrawal probability in a disruption month"); ax.set_ylabel("Median terminal corpus\n(% of no-withdrawal level)")
    ax.legend(frameon=False); fig.tight_layout(); save(fig, "fig5_withdrawal")


def fig_premium():
    s0, s5 = pd.read_csv(D / "premium_sweep.csv"), pd.read_csv(D / "premium_sweep_wd05.csv")
    fig, ax = plt.subplots(1, 2, figsize=(W2, 2.4))
    for t in TIERS:
        a = s0[s0.tier == t].sort_values("equity_minus_G_premium")
        ax[0].plot(a.equity_minus_G_premium * 100, a.tier_equity_start * 100, "o-", color=COL[t], ms=4 + (t == "low") * 1.5, lw=1,
                   alpha=0.85, label=LAB[t])
    ax[0].axvline(0, color="grey", lw=0.6, ls=":"); ax[0].set_xlabel("Equity minus G-sec premium (% p.a.)")
    ax[0].set_ylabel("Optimal starting equity (%)"); ax[0].legend(frameon=False, fontsize=6); ax[0].set_title("(a) Allocation follows the premium", fontsize=8)
    for lab, s, m in [("no withdrawals", s0, "o"), ("withdrawal prob. 0.5", s5, "s")]:
        for t in TIERS:
            a = s[s.tier == t].sort_values("equity_minus_G_premium")
            ax[1].plot(a.equity_minus_G_premium * 100, a.gain_tier_vs_pooled, m, color=COL[t], ms=3.5, mfc="none" if m == "s" else COL[t])
    ax[1].axhline(0, color="k", lw=0.6); ax[1].set_xlabel("Equity minus G-sec premium (% p.a.)"); ax[1].set_ylabel("Tier-conditioned minus tier-blind\nsuccess probability")
    ax[1].set_title("(b) No gain from conditioning (filled: p=0; open: p=0.5)", fontsize=7.5)
    ax[1].set_ylim(-0.02, 0.02); fig.tight_layout(); save(fig, "fig6_premium")
    NUM["premium_gain_max"] = float(max(s0.gain_tier_vs_pooled.abs().max(), s5.gain_tier_vs_pooled.abs().max()))


def fig_robust():
    r = pd.read_csv(D / "robustness.csv"); assert len(r) == 54 and not r.ci_excludes_0.any()
    NUM["robust"] = {"cells": len(r), "excl": int(r.ci_excludes_0.sum()), "max_gain": float(r.gain.abs().max()),
                     "n_identical": int((r.tier_equity_start.eq(r.pooled_equity_start) & r.tier_equity_end.eq(r.pooled_equity_end)
                                         & r.tier_inflection_age.eq(r.pooled_inflection_age)).sum())}
    r["lab"] = r.scenario + np.where(r.haircut > 0, " (2% haircut)", " (no haircut)")
    labs = list(dict.fromkeys(r.lab)); fig, ax = plt.subplots(figsize=(W1, 4.4))
    for i, l in enumerate(labs):
        for j, t in enumerate(TIERS):
            q = r[(r.lab == l) & (r.tier == t)].iloc[0]; y = len(labs) - i + (j - 1) * 0.22
            ax.errorbar(q.gain, y, xerr=[[q.gain - q.ci_lo], [q.ci_hi - q.gain]], fmt="o", ms=2.5, color=COL[t], lw=0.8, capsize=1.5)
    ax.axvline(0, color="k", lw=0.6); ax.set_yticks(range(len(labs), 0, -1), [l.replace("_", " ") for l in labs], fontsize=5.5)
    ax.set_xlabel("Tier-conditioned minus tier-blind success (95% CI)"); ax.set_xlim(-0.015, 0.015)
    for t in TIERS: ax.plot([], [], "o", color=COL[t], label=LAB[t], ms=3)
    ax.legend(frameon=False, fontsize=6, loc="lower center", bbox_to_anchor=(0.4, 1.0), ncol=3,
              handlelength=0.8, columnspacing=0.8)
    fig.tight_layout(); save(fig, "fig7_robustness")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    fig_pipeline(); accumulation(); fig_objective_ladder(); fig_frontiers(); fig_withdrawal(); fig_premium(); fig_robust()
    for k, v in NUM.items():
        print(f"\n== {k} ==\n{v}")
