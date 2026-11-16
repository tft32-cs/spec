"""Sensitivity of the calibrated result to trial shape and failure severity.

One-at-a-time variations around the calibrated scenario
(config/scenario_calibrated.yaml), using the interquartile range of the
ClinicalTrials.gov sample for trial shape:

  sites_18 / sites_93    number of sites at the 25th / 75th percentile
  pps_4 / pps_14         patients per site at the 25th / 75th percentile
  mild / severe          weaker or stronger failures:
                           adherence floor     0.75 / 0.40   (calibrated 0.55)
                           attestation rate    0.80 / 0.40   (calibrated 0.60)
                           extra protocol lag  100 / 300 d   (calibrated 200)

Every variant runs the same arms and sweeps as tradeoff_cc.py, picks each
arm's fastest operating point within the false-alarm budget (>= 95% detection
of adherence decay and missing attestation; protocol lag reported separately,
as in the calibrated scenario), and reports per-failure-type latency and the
gap to a monthly audit with seed-bootstrap 95% CIs.

Usage:
    python src/sensitivity.py --replications 50 --variants sites_18 sites_93
Outputs (one set per variant, merged by summarize step):
    results/sens_<variant>_points.csv, results/sens_<variant>_failures.csv
    python src/sensitivity.py --summarize   ->  results/sensitivity_summary.csv
"""

import argparse
import copy
from pathlib import Path

import numpy as np
import pandas as pd

from detect_control_chart import estimate_reference
from run import load_config
from sweep import ALL_SCENARIOS
from tradeoff_cc import matched, run_seed

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
CRITERION = ["adherence_decay", "missing_attestation"]
BUDGET = 0.05
ARMS = ["cusum", "ewma", "threshold", "audit_28d", "audit_56d", "audit_84d"]


def variants(base):
    def v(**edits):
        c = copy.deepcopy(base)
        for path, val in edits.items():
            node = c
            keys = path.split("__")
            for k in keys[:-1]:
                node = node[k]
            node[keys[-1]] = val
        return c

    return {
        "calibrated": v(),
        "sites_18": v(trial__n_sites=18, failures__n_affected_sites=5),
        "sites_93": v(trial__n_sites=93, failures__n_affected_sites=23),
        # Chart window widened so a site's expected doses per window reach
        # min_events_in_window (4 patients x 3 weekly doses = 12 >= 10), the same
        # rule that gives 7 days at 20 patients and 14 days at 7.
        "pps_4": v(trial__patients_per_site=4, kri__chart_window_days=21),
        "pps_14": v(trial__patients_per_site=14),
        "mild": v(failures__adherence_decay__floor_rate=0.75,
                  failures__missing_attestation__degraded_rate=0.80,
                  failures__protocol_lag__extra_lag_days=100),
        "severe": v(failures__adherence_decay__floor_rate=0.40,
                    failures__missing_attestation__degraded_rate=0.40,
                    failures__protocol_lag__extra_lag_days=300),
    }


def run_variant(name, cfg, n, seed0):
    ref = estimate_reference(cfg, n_trials=10)
    fail_rows, run_rows = [], []
    for i in range(n):
        fr, rr = run_seed(cfg, ref, seed0 + i, name)
        fail_rows += fr
        run_rows += rr
        if (i + 1) % 10 == 0:
            print(f"  {name}: {i + 1}/{n}", flush=True)
    failures, runs = pd.DataFrame(fail_rows), pd.DataFrame(run_rows)
    keys = ["scenario", "family", "setting"]
    crit = failures[failures.failure_type.isin(CRITERION)]
    pts = crit.groupby(keys).agg(detection_rate=("detected", "mean"))
    lat = failures.groupby(keys).latency_from_effective_onset
    pts["median_latency_eff_onset"] = lat.median()
    pts["latency_p25"] = lat.quantile(0.25)
    pts["latency_p75"] = lat.quantile(0.75)
    pts = pts.join(runs.groupby(keys).agg(fp_per_site_year=("fp_per_site_year", "mean"))).reset_index()
    pts.to_csv(RES / f"sens_{name}_points.csv", index=False)
    failures.to_csv(RES / f"sens_{name}_failures.csv", index=False)


def summarize(names, n_boot=1000):
    rng = np.random.default_rng(0)
    rows = []
    for name in names:
        pf, ff = RES / f"sens_{name}_points.csv", RES / f"sens_{name}_failures.csv"
        if not pf.exists():
            continue
        m = matched(pd.read_csv(pf))
        m = m[m.fp_budget == BUDGET].set_index("family")
        fails = pd.read_csv(ff)
        seeds = fails.seed.unique()
        for ftype in sorted(fails.failure_type.unique()):
            per = {}
            for a in ARMS:
                if a not in m.index or pd.isna(m.loc[a, "setting"]):
                    continue
                d = fails[(fails.family == a) & (fails.setting == m.loc[a, "setting"])
                          & (fails.failure_type == ftype)]
                per[a] = (d, {s: g.latency_from_effective_onset.values for s, g in d.groupby("seed")})
            draws = {a: [] for a in per}
            for _ in range(n_boot):
                ss = rng.choice(seeds, len(seeds))
                for a, (_, by_seed) in per.items():
                    draws[a].append(np.nanmedian(np.concatenate([by_seed.get(s, []) for s in ss])))
            for a, (d, _) in per.items():
                row = {"variant": name, "failure_type": ftype, "family": a,
                       "setting": m.loc[a, "setting"],
                       "median_latency": d.latency_from_effective_onset.median(),
                       "detection_rate": d.detected.mean()}
                if a != "audit_28d" and "audit_28d" in per:
                    gap = np.array(draws["audit_28d"]) - np.array(draws[a])
                    row["days_faster_than_monthly_audit"] = (
                        per["audit_28d"][0].latency_from_effective_onset.median() - row["median_latency"])
                    row["gap_ci_low"], row["gap_ci_high"] = np.nanpercentile(gap, [2.5, 97.5])
                rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(RES / "sensitivity_summary.csv", index=False)
    pd.set_option("display.width", 220)
    best = (out[out.family.isin(["cusum", "ewma", "threshold"])]
            .sort_values("median_latency").groupby(["variant", "failure_type"]).head(1))
    print(best[["variant", "failure_type", "family", "median_latency", "detection_rate",
                "days_faster_than_monthly_audit", "gap_ci_low", "gap_ci_high"]]
          .sort_values(["failure_type", "variant"]).round(1).to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replications", type=int, default=50)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--variants", nargs="+", default=None)
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args()
    base = load_config(ALL_SCENARIOS["calibrated"])
    vs = variants(base)
    names = args.variants or [k for k in vs if k != "calibrated"]
    if args.summarize:
        summarize(names)
        return
    RES.mkdir(exist_ok=True)
    for name in names:
        print(f"{name}", flush=True)
        run_variant(name, vs[name], args.replications, args.seed)


if __name__ == "__main__":
    main()
