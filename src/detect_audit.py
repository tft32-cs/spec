"""Stage 4b: scheduled periodic audit — the baseline arm.

Represents current practice: a monitor visits on a fixed cadence and reviews
the preceding lookback period in aggregate. Two things make this slower than
continuous monitoring, and both are structural rather than stipulated. First,
nothing can be detected between visits, so detection is quantized to the audit
calendar. Second, aggregating the whole lookback window dilutes a problem that
began partway through it.

It uses the same thresholds as the continuous arm by default, so any measured
difference comes from timing and aggregation rather than from a stricter rule.
"""

import pandas as pd

from schema import ALERT_COLUMNS, KRI_TO_FAILURE

ARM = "audit"


def _breached(kri_name, value, params):
    if pd.isna(value):
        return False
    if kri_name == "adherence_rate":
        return value < params["adherence_threshold"]
    if kri_name == "attestation_rate":
        return value < params["attestation_threshold"]
    if kri_name == "version_lag_days":
        return value > params["version_lag_threshold_days"]
    return False


def detect(kris, cfg):
    params = cfg["detection"]["audit"]
    interval = params["interval_days"]
    lookback = params["lookback_days"]
    duration = cfg["trial"]["duration_days"]

    audit_days = list(range(interval, duration + 1, interval))
    alerts = []
    # Alert at the first audit of each breach episode. A key that was already
    # in breach at the previous audit is an open finding, not a new alert.
    in_breach = set()

    for audit_day in audit_days:
        lo = audit_day - lookback
        win = kris[(kris.day > lo) & (kris.day <= audit_day)]
        if win.empty:
            continue
        # Rates are reviewed in aggregate over the lookback period. Version
        # lag is a status check, not a rate: a monitor sees which protocol
        # version the site is operating under on the visit day, so the audit
        # reads the latest value. Averaging it let the amendment sawtooth
        # dilute a lagging site below threshold.
        win = win.sort_values("day")
        rates = win[win.kri_name != "version_lag_days"]
        status = win[win.kri_name == "version_lag_days"]
        agg = pd.concat(
            [
                rates.groupby(["site_id", "kri_name"])["value"].mean(),
                status.groupby(["site_id", "kri_name"])["value"].last(),
            ]
        ).reset_index()
        now_breached = set()
        for r in agg.itertuples():
            key = (r.site_id, r.kri_name)
            if not _breached(r.kri_name, r.value, params):
                continue
            now_breached.add(key)
            if key not in in_breach:
                alerts.append(
                    {
                        "arm": ARM,
                        "site_id": r.site_id,
                        "detected_day": int(audit_day),
                        "failure_type": KRI_TO_FAILURE[r.kri_name],
                        "kri_triggered": r.kri_name,
                        "observed_value": float(r.value),
                    }
                )
        in_breach = now_breached

    return pd.DataFrame(alerts, columns=ALERT_COLUMNS)
