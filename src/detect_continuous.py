"""Stage 4a: continuous central statistical monitoring.

Evaluates every KRI at every computed timepoint and raises an alert once a
threshold has been breached on N consecutive timepoints. The persistence
requirement is what separates a signal from single-window noise; raising it
trades detection speed for a lower false positive rate, which is the central
trade-off this project measures.
"""

import pandas as pd

from schema import ALERT_COLUMNS, KRI_TO_FAILURE

ARM = "continuous"


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
    params = cfg["detection"]["continuous"]
    min_events = cfg["kri"]["min_events_in_window"]
    persistence = params["persistence_days"]

    alerts = []
    for (site, kri_name), g in kris.groupby(["site_id", "kri_name"]):
        g = g.sort_values("day")
        run = 0
        fired = False
        for r in g.itertuples():
            if r.n_events < min_events and kri_name != "version_lag_days":
                run = 0
                continue
            if _breached(kri_name, r.value, params):
                run += 1
            else:
                # Breach cleared: re-arm, so a later episode at the same site
                # raises a new alert. Firing once per site-KRI for the whole
                # trial let a single early noise alert mask a real failure.
                run = 0
                fired = False
            if run >= persistence and not fired:
                alerts.append(
                    {
                        "arm": ARM,
                        "site_id": site,
                        "detected_day": int(r.day),
                        "failure_type": KRI_TO_FAILURE[kri_name],
                        "kri_triggered": kri_name,
                        "observed_value": float(r.value),
                    }
                )
                fired = True

    return pd.DataFrame(alerts, columns=ALERT_COLUMNS)
