"""Audit-interval and KRI-window sweep.

Answers the objection that the continuous-vs-audit gap is an artifact of a
quarterly (90-day) audit cadence. Published protocols and site SOPs cluster at
4-12 weeks, so the audit arm is swept across 28/42/56/84 days (plus the
original 90 for reference). The audit lookback is tied to the interval: a
monitor reviews the period since the last visit.

It also sweeps the KRI rolling window (14 vs 28 days). The window imposes a
smoothing lag on both arms, so this separates detector cadence from indicator
smoothing.

The simulated trial (generate, inject, KRIs) is built once per seed and window
and shared across every audit interval, so every arm in a given seed is scored
against the same injected failures.

Usage:
    python src/sweep.py --replications 100
Outputs:
    results/sweep_failures.csv  one row per injected failure per arm
    results/sweep_runs.csv      one row per seed per arm (FP counts)
    results/sweep_summary.csv   aggregated by scenario, window, arm
"""

import argparse
import copy
from pathlib import Path

import numpy as np
import pandas as pd

import detect_audit
import detect_continuous
from generate import generate, _amendment_days
from inject import inject
from kri import compute_kris
from evaluate import count_false_positives
from run import load_config

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = {
    "base": ROOT / "config" / "scenario_base.yaml",
    "high_amendment": ROOT / "config" / "scenario_high_amendment.yaml",
}
INTERVALS = [28, 42, 56, 84, 90]
WINDOWS = [14, 28]


def effective_onset(row, cfg):
    """Day the failure can first show up in the data.

    Adherence decay and missing attestation act from start_day. A protocol-lag
    failure only becomes visible once an amendment is issued after it starts,
    because there is nothing to fail to acknowledge before then.
    """
    if row.failure_type != "protocol_lag":
        return row.start_day
    later = [d for d in _amendment_days(cfg) if d >= row.start_day]
    return later[0] if later else np.nan


def score(alerts, truth, cfg, arm_label, meta):
    """Match each injected failure to the first qualifying alert (same rule as evaluate.py)."""
    fail_rows = []
    matched = set()
    for f in truth.itertuples():
        cand = alerts[
            (alerts.site_id == f.site_id)
            & (alerts.failure_type == f.failure_type)
            & (alerts.detected_day >= f.start_day)
        ].sort_values("detected_day")
        onset_eff = effective_onset(f, cfg)
        if len(cand):
            first = cand.iloc[0]
            matched.add(first.name)
            lat = int(first.detected_day - f.start_day)
            lat_eff = first.detected_day - onset_eff if not np.isnan(onset_eff) else np.nan
        else:
            lat, lat_eff = np.nan, np.nan
        fail_rows.append(
            {**meta, "arm": arm_label, "failure_type": f.failure_type,
             "detected": len(cand) > 0, "latency_days": lat,
             "latency_from_effective_onset": lat_eff}
        )
    n_fp = count_false_positives(alerts, truth)
    site_years = cfg["trial"]["n_sites"] * cfg["trial"]["duration_days"] / 365.0
    run_row = {**meta, "arm": arm_label, "n_false_positives": n_fp,
               "fp_per_site_year": n_fp / site_years}
    return fail_rows, run_row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replications", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    fail_rows, run_rows = [], []
    for scen, path in SCENARIOS.items():
        base_cfg = load_config(path)
        for window in WINDOWS:
            cfg = copy.deepcopy(base_cfg)
            cfg["kri"]["window_days"] = window
            for i in range(args.replications):
                seed = args.seed + i
                rng = np.random.default_rng(seed)
                observed, truth = inject(generate(cfg, rng), cfg, rng)
                kris = compute_kris(observed, cfg)
                meta = {"scenario": scen, "window_days": window, "seed": seed}

                fr, rr = score(detect_continuous.detect(kris, cfg), truth, cfg, "continuous", meta)
                fail_rows += fr
                run_rows.append(rr)

                for interval in INTERVALS:
                    acfg = copy.deepcopy(cfg)
                    acfg["detection"]["audit"]["interval_days"] = interval
                    acfg["detection"]["audit"]["lookback_days"] = interval
                    fr, rr = score(detect_audit.detect(kris, acfg), truth, acfg,
                                   f"audit_{interval}d", meta)
                    fail_rows += fr
                    run_rows.append(rr)
            print(f"done: {scen}, window {window}d")

    failures = pd.DataFrame(fail_rows)
    runs = pd.DataFrame(run_rows)

    keys = ["scenario", "window_days", "arm"]
    det = failures.groupby(keys).agg(
        detection_rate=("detected", "mean"),
        median_latency=("latency_days", "median"),
        latency_p25=("latency_days", lambda s: s.quantile(0.25)),
        latency_p75=("latency_days", lambda s: s.quantile(0.75)),
        median_latency_eff_onset=("latency_from_effective_onset", "median"),
    )
    fp = runs.groupby(keys).agg(fp_per_site_year=("fp_per_site_year", "mean"))
    summary = det.join(fp).reset_index()

    by_type = failures.groupby(keys + ["failure_type"]).agg(
        detection_rate=("detected", "mean"),
        median_latency=("latency_days", "median"),
        median_latency_eff_onset=("latency_from_effective_onset", "median"),
    ).reset_index()

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    failures.to_csv(out / "sweep_failures.csv", index=False)
    runs.to_csv(out / "sweep_runs.csv", index=False)
    summary.to_csv(out / "sweep_summary.csv", index=False)
    by_type.to_csv(out / "sweep_by_type.csv", index=False)

    pd.set_option("display.width", 160)
    print(summary.round(2).to_string(index=False))
    print()
    print(by_type.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
