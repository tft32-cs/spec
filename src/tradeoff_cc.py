"""Control charts vs threshold rule vs scheduled audit, at matched false-alarm rates.

The headline question: does a continuous detector that accumulates evidence
(CUSUM / EWMA) beat a monthly audit at the same false-alarm rate, or only tie
it? Every arm is swept across its own sensitivity setting, which traces out a
latency vs false-alarm curve. Arms are then compared at fixed false-alarm
budgets: for each budget, the fastest operating point of each arm whose false
alarm rate is within the budget and which still detects at least
MIN_DETECTION of injected failures (so a detector cannot look fast by missing
the hard cases, which have no latency).

Arms and their sweeps:
  threshold   threshold tightness (tradeoff.py) x persistence 1-3
  cusum       slack k in {0.5, 1.0} x decision limit h (weekly KRIs, site baselines)
  ewma        smoothing lam in {0.1, 0.2, 0.3} x limit width L (same inputs)
  audit_Nd    threshold tightness, audits every 28 / 56 / 84 days

All arms in one seed are scored against the same simulated trial.

Usage:
    python src/tradeoff_cc.py --replications 100
Outputs:
    results/cc_points.csv     one row per scenario x arm x setting
    results/cc_matched.csv    best latency per arm at each false-alarm budget
"""

import argparse
import copy
from pathlib import Path

import numpy as np
import pandas as pd

import detect_audit
import detect_continuous
from detect_control_chart import chart_kris, detect_cusum, detect_ewma, estimate_reference, site_reference
from generate import generate
from inject import inject
from kri import compute_kris
from run import load_config
from sweep import SCENARIOS, score
from tradeoff import AUDIT_INTERVALS, PERSISTENCE, TIGHTNESS, thresholds

ROOT = Path(__file__).resolve().parent.parent

CUSUM_K = [0.5, 1.0]
CUSUM_H = [1, 2, 3, 4, 5, 6, 8, 10, 13, 16, 20, 25, 30]
EWMA_LAM = [0.1, 0.2, 0.3]
EWMA_L = [1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8, 10]
BUDGETS = [0.02, 0.05, 0.10, 0.20]  # false alarms per site-year
MIN_DETECTION = 0.95


def run_seed(cfg, ref, seed, scen):
    rng = np.random.default_rng(seed)
    observed, truth = inject(generate(cfg, rng), cfg, rng)
    kris = compute_kris(observed, cfg)
    ckris = chart_kris(observed, cfg)
    sref = site_reference(ckris, cfg, ref)
    fail_rows, run_rows = [], []

    def add(alerts, c, family, setting):
        meta = {"scenario": scen, "seed": seed, "family": family, "setting": setting}
        fr, rr = score(alerts, truth, c, family, meta)
        fail_rows.extend(fr)
        run_rows.append(rr)

    for t in TIGHTNESS:
        th = thresholds(t)
        for p in PERSISTENCE:
            c = copy.deepcopy(cfg)
            c["detection"]["continuous"].update(th, persistence_days=p)
            add(detect_continuous.detect(kris, c), c, "threshold", f"t={t} p={p}")
        for interval in AUDIT_INTERVALS:
            c = copy.deepcopy(cfg)
            c["detection"]["audit"].update(th, interval_days=interval, lookback_days=interval)
            add(detect_audit.detect(kris, c), c, f"audit_{interval}d", f"t={t}")

    for k in CUSUM_K:
        for h in CUSUM_H:
            add(detect_cusum(ckris, cfg, sref, k=k, h=h), cfg, "cusum", f"k={k} h={h}")
    for lam in EWMA_LAM:
        for L in EWMA_L:
            add(detect_ewma(ckris, cfg, sref, lam=lam, L=L), cfg, "ewma", f"lam={lam} L={L}")
    return fail_rows, run_rows


def matched(points):
    rows = []
    for (scen, family), g in points.groupby(["scenario", "family"]):
        ok = g[g.detection_rate >= MIN_DETECTION]
        for b in BUDGETS:
            cand = ok[ok.fp_per_site_year <= b]
            if cand.empty:
                rows.append({"scenario": scen, "family": family, "fp_budget": b})
                continue
            best = cand.sort_values(["median_latency_eff_onset", "fp_per_site_year"]).iloc[0]
            rows.append({
                "scenario": scen, "family": family, "fp_budget": b,
                "median_latency_eff_onset": best.median_latency_eff_onset,
                "latency_p25": best.latency_p25, "latency_p75": best.latency_p75,
                "detection_rate": best.detection_rate,
                "fp_per_site_year": best.fp_per_site_year, "setting": best.setting,
            })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replications", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    fail_rows, run_rows = [], []
    for scen, path in SCENARIOS.items():
        cfg = load_config(path)
        ref = estimate_reference(cfg)
        print(f"{scen}: in-control reference {ref}", flush=True)  # noqa
        for i in range(args.replications):
            fr, rr = run_seed(cfg, ref, args.seed + i, scen)
            fail_rows += fr
            run_rows += rr
            if (i + 1) % 10 == 0:
                print(f"  {scen}: {i + 1}/{args.replications} seeds", flush=True)

    failures = pd.DataFrame(fail_rows)
    runs = pd.DataFrame(run_rows)
    keys = ["scenario", "family", "setting"]
    lat = failures.groupby(keys).latency_from_effective_onset
    det = failures.groupby(keys).agg(detection_rate=("detected", "mean"))
    det["median_latency_eff_onset"] = lat.median()
    det["latency_p25"] = lat.quantile(0.25)
    det["latency_p75"] = lat.quantile(0.75)
    fp = runs.groupby(keys).agg(fp_per_site_year=("fp_per_site_year", "mean"))
    points = det.join(fp).reset_index()

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    points.to_csv(out / "cc_points.csv", index=False)
    failures.to_csv(out / "cc_failures.csv", index=False)
    m = matched(points)
    m.to_csv(out / "cc_matched.csv", index=False)

    pd.set_option("display.width", 200)
    for scen, g in m.groupby("scenario"):
        print(f"\n== {scen}: median days from onset to alert, at each false-alarm budget")
        print(g.pivot(index="family", columns="fp_budget", values="median_latency_eff_onset").round(1).to_string())


if __name__ == "__main__":
    main()
