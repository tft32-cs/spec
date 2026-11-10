"""Stage 3: compute key risk indicators from the observed log.

Three KRIs, each mapped to one failure mode and each grounded in something a
real risk-based monitoring plan would track under ICH E6(R3):

  adherence_rate     observed doses over protocol-expected doses, rolling window
  attestation_rate   share of window events carrying an attestation
  version_lag_days   days a site has been operating without acknowledging the
                     current protocol version

Both detection arms consume this table. Neither recomputes indicators itself,
so a change to a KRI definition automatically applies to both arms and the
comparison stays fair.
"""

import pandas as pd

from generate import expected_doses_per_window, _amendment_days
from schema import KRI_COLUMNS


def compute_kris(observed, cfg, step_days=7):
    window = cfg["kri"]["window_days"]
    duration = cfg["trial"]["duration_days"]
    expected_doses = expected_doses_per_window(cfg, window)
    amendment_days = _amendment_days(cfg)

    site_events = observed[observed.site_id != "SPONSOR"]
    sites = sorted(site_events.site_id.unique())

    acks = site_events[site_events.event_type == "version_ack"]
    ack_lookup = {
        (r.site_id, r.protocol_version): r.day for r in acks.itertuples()
    }

    rows = []
    for day in range(window, duration + 1, step_days):
        lo = day - window
        win = site_events[(site_events.day > lo) & (site_events.day <= day)]
        by_site = {s: g for s, g in win.groupby("site_id")}

        # Current protocol version as of this day.
        current_version = 1 + sum(1 for d in amendment_days if d <= day)

        for site in sites:
            g = by_site.get(site, win.iloc[0:0])
            n_events = len(g)

            doses = int((g.event_type == "dose_administered").sum())
            rows.append(
                {
                    "site_id": site,
                    "day": day,
                    "kri_name": "adherence_rate",
                    "value": doses / expected_doses if expected_doses else float("nan"),
                    "n_events": n_events,
                }
            )

            if n_events:
                att = float((g.attestation_status == "attested").mean())
            else:
                att = float("nan")
            rows.append(
                {
                    "site_id": site,
                    "day": day,
                    "kri_name": "attestation_rate",
                    "value": att,
                    "n_events": n_events,
                }
            )

            # Days since the oldest issued version this site has still not
            # acknowledged. Measuring from the current version alone reset the
            # clock at every new amendment, so a site that never acknowledged
            # anything looked compliant right after each issue date, and an
            # audit cadence that happened to land there never saw it.
            lag = 0.0
            for v in range(2, current_version + 1):
                ack_day = ack_lookup.get((site, v))
                if ack_day is None or ack_day > day:
                    lag = float(day - amendment_days[v - 2])
                    break
            rows.append(
                {
                    "site_id": site,
                    "day": day,
                    "kri_name": "version_lag_days",
                    "value": lag,
                    "n_events": n_events,
                }
            )

    return pd.DataFrame(rows, columns=KRI_COLUMNS)
