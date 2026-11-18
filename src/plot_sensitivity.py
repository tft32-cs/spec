"""Figure: how much sooner the best continuous arm alerts than a monthly audit, per variant.

Reads results/sensitivity_summary.csv (sensitivity.py --summarize). For each
variant and failure type, takes the fastest continuous arm (threshold, CUSUM or
EWMA) at <= 0.05 false alarms per site-year and plots its gap to a monthly
audit with the bootstrap 95% CI. Protocol lag is left out: no arm detects it
reliably under calibration (reported in the table instead).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RES = Path(__file__).resolve().parent.parent / "results"
ORDER = [("calibrated", "Calibrated (41 sites, 7 pts/site)"),
         ("sites_18", "18 sites"), ("sites_93", "93 sites"),
         ("pps_4", "4 patients per site"), ("pps_14", "14 patients per site"),
         ("mild", "Milder failures"), ("severe", "More severe failures")]
TYPES = [("missing_attestation", "Missing attestation"), ("adherence_decay", "Adherence decay")]
ARM_NAMES = {"threshold": "threshold", "cusum": "CUSUM", "ewma": "EWMA"}
CONT, INK, MUTED, GRID, BG = "#2a78d6", "#1f1f1e", "#5f5e5a", "#e8e7e1", "#ffffff"

s = pd.read_csv(RES / "sensitivity_summary.csv")
best = (s[s.family.isin(ARM_NAMES)].dropna(subset=["median_latency"])
        .sort_values("median_latency").groupby(["variant", "failure_type"]).head(1))

fig, axes = plt.subplots(1, 2, figsize=(10, 3.9), dpi=200, sharey=True)
fig.patch.set_facecolor(BG)
for ax, (ft, label) in zip(axes, TYPES):
    ax.set_facecolor(BG)
    ax.axvline(0, color="#c3c2b7", lw=1)
    for i, (v, _) in enumerate(ORDER):
        r = best[(best.variant == v) & (best.failure_type == ft)]
        if r.empty:
            ax.annotate("no qualifying setting", (1, i), va="center", fontsize=8, color=MUTED)
            continue
        r = r.iloc[0]
        ax.plot([r.gap_ci_low, r.gap_ci_high], [i, i], color=CONT, lw=2, solid_capstyle="round")
        ax.plot(r.days_faster_than_monthly_audit, i, "o", ms=8, color=CONT,
                markeredgecolor=BG, markeredgewidth=1.5)
        ax.annotate(f"{r.days_faster_than_monthly_audit:+.0f} d ({ARM_NAMES[r.family]})",
                    (max(r.gap_ci_high, r.days_faster_than_monthly_audit), i),
                    xytext=(6, 0), textcoords="offset points", va="center", fontsize=8, color=MUTED)
    ax.set_title(label, loc="left", fontsize=10, color=INK)
    ax.set_xlim(-10, 55)
    ax.grid(axis="x", color=GRID, lw=0.7); ax.set_axisbelow(True)
    for sp in ["top", "right", "left"]:
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.tick_params(colors=MUTED, labelsize=8, left=False)
    ax.set_xlabel("Days sooner than a monthly audit (best continuous arm)", fontsize=8, color=MUTED)
axes[0].set_yticks(range(len(ORDER)))
axes[0].set_yticklabels([n for _, n in ORDER], fontsize=9, color=INK)
axes[0].invert_yaxis()
fig.suptitle("Sensitivity: continuous monitoring vs monthly audit at ≤0.05 false alarms per site-year "
             "(50 simulated trials per variant; lines are 95% CIs)", x=0.01, ha="left", fontsize=10, color=INK)
fig.tight_layout(rect=(0, 0, 1, 0.93))
fig.savefig(RES / "sensitivity_gap.png")
print("saved", RES / "sensitivity_gap.png")
