"""Per-failure-type comparison at matched false-alarm budgets, with bootstrap CIs.

Reads results/cc_points.csv and results/cc_failures.csv (from tradeoff_cc.py).
For each scenario, budget and arm, the operating point is the one tradeoff_cc
picked overall (fastest with >= 95% detection within the budget). Latency is
then reported separately for each failure type, because the pooled median sits
on whichever type is in the middle and hides the large per-type gaps.

CIs resample whole simulated trials (seeds), 2,000 draws.

Outputs:
    results/cc_by_type.csv   median latency + 95% CI per scenario/budget/arm/type
    results/cc_gap.csv       days faster than the monthly audit, with 95% CI
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
ARMS = ["cusum", "ewma", "threshold", "audit_28d", "audit_56d", "audit_84d"]
BUDGETS = [0.02, 0.05, 0.10]
N_BOOT = 2000


def main():
    matched = pd.read_csv(RES / "cc_matched.csv")
    fails = pd.read_csv(RES / "cc_failures.csv")
    rng = np.random.default_rng(0)
    by_type, gaps = [], []
    for (scen, b), mm in matched[matched.fp_budget.isin(BUDGETS)].groupby(["scenario", "fp_budget"]):
        mm = mm.set_index("family")
        sel = {a: fails[(fails.scenario == scen) & (fails.family == a)
                        & (fails.setting == mm.loc[a, "setting"])] for a in ARMS if a in mm.index}
        seeds = fails[fails.scenario == scen].seed.unique()
        for ftype in sorted(fails.failure_type.unique()):
            per_seed = {a: {s: g.latency_from_effective_onset.values
                            for s, g in d[d.failure_type == ftype].groupby("seed")}
                        for a, d in sel.items()}
            draws = {a: [] for a in sel}
            for _ in range(N_BOOT):
                ss = rng.choice(seeds, len(seeds))
                for a in sel:
                    draws[a].append(np.nanmedian(np.concatenate([per_seed[a].get(s, []) for s in ss])))
            for a in sel:
                lat = sel[a][sel[a].failure_type == ftype].latency_from_effective_onset
                lo, hi = np.percentile(draws[a], [2.5, 97.5])
                by_type.append({"scenario": scen, "fp_budget": b, "family": a, "failure_type": ftype,
                                "median_latency": lat.median(), "ci_low": lo, "ci_high": hi,
                                "detection_rate": lat.notna().mean()})
                if a != "audit_28d":
                    d = np.array(draws["audit_28d"]) - np.array(draws[a])
                    glo, ghi = np.percentile(d, [2.5, 97.5])
                    base = sel["audit_28d"][sel["audit_28d"].failure_type == ftype].latency_from_effective_onset
                    gaps.append({"scenario": scen, "fp_budget": b, "family": a, "failure_type": ftype,
                                 "days_faster_than_monthly_audit": base.median() - lat.median(),
                                 "ci_low": glo, "ci_high": ghi})
    bt, gp = pd.DataFrame(by_type), pd.DataFrame(gaps)
    bt.to_csv(RES / "cc_by_type.csv", index=False)
    gp.to_csv(RES / "cc_gap.csv", index=False)
    pd.set_option("display.width", 200)
    print(gp[gp.fp_budget == 0.02].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
