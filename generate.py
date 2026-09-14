"""Stage 1: generate a clean multi-site trial event log.

Clean means every site behaves within normal operating tolerance: amendments are
acknowledged after a typical administrative lag, dosing adherence sits near the
protocol-expected rate, and events are attested at the usual rate. No failures
are present. Corruption happens in inject.py so ground truth stays separable.
"""

import numpy as np
import pandas as pd

from schema import EVENT_COLUMNS


def _amendment_days(cfg):
    a = cfg["amendments"]
    return [
        a["first_amendment_day"] + i * a["spacing_days"]
        for i in range(a["n_amendments"])
    ]


def generate(cfg, rng):
    trial = cfg["trial"]
    amd = cfg["amendments"]
    adh = cfg["adherence"]

    sites = [f"SITE-{i:02d}" for i in range(1, trial["n_sites"] + 1)]
    amendment_days = _amendment_days(cfg)
    rows = []
    eid = 0

    def add(site, stakeholder, etype, version, day, attested=True):
        nonlocal eid
        eid += 1
        rows.append(
            {
                "event_id": f"E{eid:07d}",
                "trial_id": trial["trial_id"],
                "site_id": site,
                "stakeholder_type": stakeholder,
                "event_type": etype,
                "protocol_version": version,
                "day": int(day),
                "attestation_status": "attested" if attested else "missing",
            }
        )

    # Sponsor issues each amendment once, trial-wide.
    for v, day in enumerate(amendment_days, start=2):
        add("SPONSOR", "sponsor", "amendment_issued", v, day)

    # Each site has its own steady-state adherence propensity.
    site_adherence = {
        s: float(np.clip(rng.normal(adh["baseline_rate"], adh["site_variation_sd"]), 0.5, 1.0))
        for s in sites
    }

    att_rate = cfg["attestation"]["baseline_rate"]

    for site in sites:
        # Consent events at enrollment.
        for p in range(trial["patients_per_site"]):
            add(site, "site", "consent_recorded", 1, rng.integers(0, 30),
                attested=rng.random() < att_rate)

        # Version acknowledgements, one per amendment, after a normal lag.
        for v, day in enumerate(amendment_days, start=2):
            lag = max(1, rng.normal(amd["normal_ack_lag_days"], amd["ack_lag_sd"]))
            add(site, "site", "version_ack", v, day + lag,
                attested=rng.random() < att_rate)

        # Scheduled dosing. A dose that does not happen produces no event,
        # which is exactly how adherence gaps appear in real trial data.
        for day in range(0, trial["duration_days"], trial["dosing_interval_days"]):
            version = 1 + sum(1 for d in amendment_days if d <= day)
            n_expected = trial["patients_per_site"]
            n_taken = rng.binomial(n_expected, site_adherence[site])
            for _ in range(n_taken):
                add(site, "site", "dose_administered", version, day,
                    attested=rng.random() < att_rate)

    df = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    return df.sort_values(["day", "site_id"]).reset_index(drop=True)


def expected_doses_per_window(cfg, window_days):
    """How many doses a fully adherent site should record in a window.

    The KRI layer needs this denominator; it is a property of the protocol,
    not of the observed data, so it lives here with the generator.
    """
    trial = cfg["trial"]
    n_dosing_days = window_days / trial["dosing_interval_days"]
    return n_dosing_days * trial["patients_per_site"]
