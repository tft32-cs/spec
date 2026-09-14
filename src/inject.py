"""Stage 2: corrupt the clean log and record exactly what was done.

This is the most important module in the project. It returns two things:
the observed log (all any detector ever sees) and a ground truth table
recording which site failed, in what way, starting on which day. Detection
latency is only measurable because start_day is recorded here rather than
being implicit in the generation process.
"""

import numpy as np
import pandas as pd

from schema import GROUND_TRUTH_COLUMNS


def _pick_targets(cfg, sites, rng):
    f = cfg["failures"]
    n = min(f["n_affected_sites"], len(sites))
    chosen = rng.choice(sites, size=n, replace=False)
    assignments = []
    for i, site in enumerate(chosen):
        ftype = f["types"][i % len(f["types"])]
        start = int(rng.integers(f["earliest_start_day"], f["latest_start_day"]))
        assignments.append((site, ftype, start))
    return assignments


def inject(events, cfg, rng):
    trial = cfg["trial"]
    f = cfg["failures"]
    end_day = trial["duration_days"]

    sites = sorted(events.loc[events.site_id != "SPONSOR", "site_id"].unique())
    assignments = _pick_targets(cfg, sites, rng)

    df = events.copy()
    truth = []

    for i, (site, ftype, start) in enumerate(assignments, start=1):
        truth.append(
            {
                "failure_id": f"F{i:03d}",
                "site_id": site,
                "failure_type": ftype,
                "start_day": start,
                "end_day": end_day,
            }
        )

        if ftype == "protocol_lag":
            # The site stops acknowledging amendments promptly: any ack that
            # would have landed after the failure start is pushed far out,
            # simulating the site operating on an obsolete protocol version.
            extra = f["protocol_lag"]["extra_lag_days"]
            mask = (df.site_id == site) & (df.event_type == "version_ack") & (df.day >= start)
            df.loc[mask, "day"] = df.loc[mask, "day"] + extra
            # Acks pushed past the end of the trial never happen at all.
            df = df[~((df.site_id == site) & (df.event_type == "version_ack") & (df.day > end_day))]

        elif ftype == "adherence_decay":
            # Dosing compliance decays linearly from baseline toward a floor.
            floor = f["adherence_decay"]["floor_rate"]
            decay_days = f["adherence_decay"]["decay_days"]
            mask = (df.site_id == site) & (df.event_type == "dose_administered") & (df.day >= start)
            idx = df.index[mask]
            days = df.loc[idx, "day"].to_numpy()
            progress = np.clip((days - start) / decay_days, 0, 1)
            keep_prob = 1.0 - progress * (1.0 - floor)
            keep = rng.random(len(idx)) < keep_prob
            df = df.drop(index=idx[~keep])

        elif ftype == "missing_attestation":
            # Events still occur but stop being attested reliably.
            degraded = f["missing_attestation"]["degraded_rate"]
            mask = (df.site_id == site) & (df.day >= start)
            idx = df.index[mask]
            attested = rng.random(len(idx)) < degraded
            df.loc[idx, "attestation_status"] = np.where(attested, "attested", "missing")

        else:
            raise ValueError(f"unknown failure type: {ftype}")

    observed = df.sort_values(["day", "site_id"]).reset_index(drop=True)
    ground_truth = pd.DataFrame(truth, columns=GROUND_TRUTH_COLUMNS)
    return observed, ground_truth
