"""Latency vs false-positive trade-off.

With the default thresholds neither arm produces a single false positive, so
the persistence rule is pure cost and the arms cannot be compared on the
question that matters: how fast is each one at a given false alarm rate?

This sweeps threshold tightness (one scalar that moves all three KRI
thresholds together, from lenient to tight) and, for the continuous arm,
persistence (1-3 consecutive weekly breaches). Audit arms are run at 28, 56
and 84 days with lookback tied to interval. Each (arm, tightness) pair is one
point on that arm's latency/false-positive curve.

Tightness maps linearly between the lenient and tight ends below. Tight ends
sit just outside normal site variation (adherence baseline 0.92 +/- 0.03,
attestation 0.97, routine ack lag 21 +/- 7 days), which is where false alarms
start.

Usage:
    python src/tradeoff.py --replications 100
Outputs:
    results/tradeoff_points.csv   one row per scenario x arm x tightness
"""

import argparse
import copy
from pathlib import Path

import numpy as np
import pandas as pd

import detect_audit
import detect_continuous
from generate import generate
from inject import inject
from kri import compute_kris
from run import load_config
from sweep import SCENARIOS, score

ROOT = Path(__file__).resolve().parent.parent

LENIENT = {"adherence_threshold": 0.70, "attestation_threshold": 0.75, "version_lag_threshold_days": 60}
TIGHT = {"adherence_threshold": 0.88, "attestation_threshold": 0.94, "version_lag_threshold_days": 28}
TIGHTNESS = np.round(np.linspace(0, 1, 9), 3)
PERSISTENCE = [1, 2, 3]
AUDIT_INTERVALS = [28, 56, 84]


def thresholds(t):
    out = {}
    for k in LENIENT:
        v = LENIENT[k] + t * (TIGHT[k] - LENIENT[k])
        out[k] = int(round(v)) if k.endswith("_days") else float(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replications", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    fail_rows, run_rows = [], []
    for scen, path in SCENARIOS.items():
        cfg = load_config(path)
        for i in range(args.replications):
            seed = args.seed + i
            rng = np.random.default_rng(seed)
            observed, truth = inject(generate(cfg, rng), cfg, rng)
            kris = compute_kris(observed, cfg)

            for t in TIGHTNESS:
                th = thresholds(t)
                meta = {"scenario": scen, "seed": seed, "tightness": t, **th}

                for p in PERSISTENCE:
                    c = copy.deepcopy(cfg)
                    c["detection"]["continuous"].update(th, persistence_days=p)
                    fr, rr = score(detect_continuous.detect(kris, c), truth, c,
                                   f"continuous_p{p}", meta)
                    fail_rows += fr
                    run_rows.append(rr)

                for interval in AUDIT_INTERVALS:
                    c = copy.deepcopy(cfg)
                    c["detection"]["audit"].update(th, interval_days=interval,
                                                   lookback_days=interval)
                    fr, rr = score(detect_audit.detect(kris, c), truth, c,
                                   f"audit_{interval}d", meta)
                    fail_rows += fr
                    run_rows.append(rr)
        print(f"done: {scen}")

    failures = pd.DataFrame(fail_rows)
    runs = pd.DataFrame(run_rows)
    keys = ["scenario", "arm", "tightness"]
    det = failures.groupby(keys).agg(
        detection_rate=("detected", "mean"),
        median_latency_eff_onset=("latency_from_effective_onset", "median"),
        median_latency=("latency_days", "median"),
    )
    fp = runs.groupby(keys).agg(fp_per_site_year=("fp_per_site_year", "mean"))
    points = det.join(fp).reset_index()
    th_cols = pd.DataFrame([{"tightness": t, **thresholds(t)} for t in TIGHTNESS])
    points = points.merge(th_cols, on="tightness")

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    points.to_csv(out / "tradeoff_points.csv", index=False)
    failures.to_csv(out / "tradeoff_failures.csv", index=False)

    pd.set_option("display.width", 200)
    print(points.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
