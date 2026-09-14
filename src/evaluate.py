"""Stage 5: score alerts against ground truth.

Arm-agnostic by construction. It reads the alert schema, not the detector, so
adding a third comparison arm later requires no change here.

An alert is a true positive when it names a site and failure type that were
actually injected and fires on or after the failure start day. Latency is
measured from the true start day, which is why inject.py has to record it.
A failure that is never alerted on is a miss; an alert that matches no failure
is a false positive.
"""

import numpy as np
import pandas as pd


def evaluate(alerts, ground_truth, cfg, seed=None):
    duration = cfg["trial"]["duration_days"]
    rows = []

    for arm, arm_alerts in alerts.groupby("arm"):
        matched_alert_idx = set()
        per_failure = []

        for f in ground_truth.itertuples():
            cand = arm_alerts[
                (arm_alerts.site_id == f.site_id)
                & (arm_alerts.failure_type == f.failure_type)
                & (arm_alerts.detected_day >= f.start_day)
            ].sort_values("detected_day")

            if len(cand):
                first = cand.iloc[0]
                matched_alert_idx.add(first.name)
                per_failure.append(
                    {
                        "failure_id": f.failure_id,
                        "failure_type": f.failure_type,
                        "detected": True,
                        "latency_days": int(first.detected_day - f.start_day),
                    }
                )
            else:
                per_failure.append(
                    {
                        "failure_id": f.failure_id,
                        "failure_type": f.failure_type,
                        "detected": False,
                        "latency_days": np.nan,
                    }
                )

        pf = pd.DataFrame(per_failure)
        n_fp = len(arm_alerts) - len(matched_alert_idx)
        detected = pf[pf.detected]

        rows.append(
            {
                "seed": seed,
                "arm": arm,
                "n_failures": len(ground_truth),
                "n_detected": int(pf.detected.sum()),
                "detection_rate": float(pf.detected.mean()) if len(pf) else np.nan,
                "median_latency_days": float(detected.latency_days.median()) if len(detected) else np.nan,
                "mean_latency_days": float(detected.latency_days.mean()) if len(detected) else np.nan,
                "n_false_positives": int(n_fp),
                "fp_per_site_year": float(
                    n_fp / (cfg["trial"]["n_sites"] * duration / 365.0)
                ),
            }
        )

    summary = pd.DataFrame(rows)
    return summary
