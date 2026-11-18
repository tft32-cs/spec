"""Figure: days from onset to alert, by failure type, at a strict false-alarm budget."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RES = Path(__file__).resolve().parent.parent / "results"
SCEN = sys.argv[1] if len(sys.argv) > 1 else "base"
BUDGET = 0.02
ARMS = [("ewma", "EWMA chart"), ("cusum", "CUSUM chart"), ("threshold", "Threshold rule"),
        ("audit_28d", "Audit every 4 wks"), ("audit_56d", "Audit every 8 wks"), ("audit_84d", "Audit every 12 wks")]
TYPES = [("missing_attestation", "Missing attestation"), ("adherence_decay", "Adherence decay"),
         ("protocol_lag", "Protocol-version lag")]
CONT, AUD = "#2a78d6", "#eb6834"
INK, MUTED, GRID, BG = "#1f1f1e", "#5f5e5a", "#e8e7e1", "#ffffff"

d = pd.read_csv(RES / "cc_by_type.csv")
d = d[(d.scenario == SCEN) & (d.fp_budget == BUDGET)]
fig, axes = plt.subplots(1, 3, figsize=(10, 3.6), dpi=200, sharey=True)
fig.patch.set_facecolor(BG)
for ax, (ft, label) in zip(axes, TYPES):
    ax.set_facecolor(BG)
    for i, (arm, name) in enumerate(ARMS):
        r = d[(d.family == arm) & (d.failure_type == ft)].iloc[0]
        c = AUD if arm.startswith("audit") else CONT
        ax.plot([r.ci_low, r.ci_high], [i, i], color=c, lw=2, solid_capstyle="round")
        ax.plot(r.median_latency, i, "o", ms=8, color=c, markeredgecolor=BG, markeredgewidth=1.5)
        ax.annotate(f"{r.median_latency:.0f}", (r.ci_high, i), xytext=(5, 0), textcoords="offset points",
                    va="center", fontsize=8, color=MUTED)
    ax.set_title(label, loc="left", fontsize=10, color=INK)
    ax.set_xlim(0, 135)
    ax.grid(axis="x", color=GRID, lw=0.7); ax.set_axisbelow(True)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.tick_params(colors=MUTED, labelsize=8, left=False)
    ax.set_xlabel("Median days, onset to alert", fontsize=8, color=MUTED)
axes[0].set_yticks(range(len(ARMS)))
axes[0].set_yticklabels([n for _, n in ARMS], fontsize=9, color=INK)
axes[0].invert_yaxis()
fig.suptitle(f"Detection speed at ≤{BUDGET} false alarms per site-year "
             f"({'base' if SCEN == 'base' else 'high-amendment'} scenario, 100 simulated trials; lines are 95% CIs)",
             x=0.01, ha="left", fontsize=10, color=INK)
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(RES / f"cc_by_type_{SCEN}.png")
print("saved", RES / f"cc_by_type_{SCEN}.png")
