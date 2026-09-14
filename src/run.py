"""Orchestrates the pipeline end to end.

Single run:   python src/run.py --config config/scenario_base.yaml --seed 1 --save
Replications: python src/run.py --config config/scenario_base.yaml --replications 100

Reporting a distribution across replications rather than a point estimate from
one simulation is what makes the false positive rate and latency figures mean
anything. One run gives a false positive count; a hundred gives an interval.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

import detect_audit
import detect_continuous
from evaluate import evaluate
from generate import generate
from inject import inject
from kri import compute_kris

ROOT = Path(__file__).resolve().parent.parent


def load_config(path):
    with open(path) as fh:
        return yaml.safe_load(fh)


def write_table(df, directory, stem):
    """Prefer parquet, fall back to CSV when no parquet engine is installed.

    Parquet keeps dtypes and is much faster to re-read for ad hoc querying
    (DuckDB reads it directly), but the pipeline should not hard-fail on a
    machine without pyarrow.
    """
    try:
        df.to_parquet(directory / f"{stem}.parquet", index=False)
    except (ImportError, ValueError):
        df.to_csv(directory / f"{stem}.csv", index=False)


def run_once(cfg, seed, save=False):
    rng = np.random.default_rng(seed)

    clean = generate(cfg, rng)
    observed, truth = inject(clean, cfg, rng)
    kris = compute_kris(observed, cfg)

    alerts = pd.concat(
        [detect_continuous.detect(kris, cfg), detect_audit.detect(kris, cfg)],
        ignore_index=True,
    )
    summary = evaluate(alerts, truth, cfg, seed=seed)

    if save:
        d = ROOT / "data"
        d.mkdir(exist_ok=True)
        write_table(clean, d, "events_clean")
        write_table(observed, d, "events_observed")
        write_table(truth, d, "ground_truth")
        write_table(kris, d, "kris")
        write_table(alerts, d, "alerts")

    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config" / "scenario_base.yaml"))
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--replications", type=int, default=1)
    ap.add_argument("--save", action="store_true", help="write intermediate artifacts")
    args = ap.parse_args()

    cfg = load_config(args.config)
    base_seed = args.seed if args.seed is not None else cfg.get("seed", 1)

    frames = []
    for i in range(args.replications):
        frames.append(run_once(cfg, base_seed + i, save=args.save and i == 0))
    results = pd.concat(frames, ignore_index=True)

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    results.to_csv(out / "runs.csv", index=False)

    agg = (
        results.groupby("arm")
        .agg(
            detection_rate=("detection_rate", "mean"),
            median_latency=("median_latency_days", "median"),
            latency_p25=("median_latency_days", lambda s: s.quantile(0.25)),
            latency_p75=("median_latency_days", lambda s: s.quantile(0.75)),
            fp_per_site_year=("fp_per_site_year", "mean"),
        )
        .reset_index()
    )
    agg.to_csv(out / "summary.csv", index=False)

    print(f"\n{args.replications} replication(s), config: {Path(args.config).name}\n")
    print(agg.to_string(index=False))
    print(f"\nWrote {out / 'runs.csv'} and {out / 'summary.csv'}")


if __name__ == "__main__":
    main()
