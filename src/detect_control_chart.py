"""Stage 4c: continuous monitoring with statistical process control charts.

The threshold rule in detect_continuous.py looks at one window at a time, so it
has to choose between reacting to noise and waiting for several breaches in a
row. Control charts instead accumulate evidence across windows: a small,
persistent shift adds up, while one noisy window does not. That is the
standard tool for time-to-signal after a shift (average run length), which is
the metric this project measures.

Both charts work on a standardized KRI, oriented so that "worse" is positive:

  adherence_rate, attestation_rate   z = (mu - x) / sd   (a drop is bad)
  version_lag_days                   z = (x - mu) / sd   (a rise is bad)

For the two rates, mu and sd are the in-control (no failure) level, estimated
from clean simulated trials that the evaluation never sees (Phase I
estimation). A sponsor would set these from historical trials or the trial's
own run-in.

Version lag is different: when in control it sits at zero and then spikes at
every site after each amendment, while the site works through its routine
acknowledgment. Standardizing against its overall mean would make every
amendment look like a failure. Instead lag is measured against the expected
acknowledgment window (normal_ack_lag_days +/- ack_lag_sd), so only lag beyond
what a site normally takes accumulates evidence.

CUSUM (one-sided, upper):  S_t = max(0, S_{t-1} + z_t - k), signal when S_t > h
EWMA:                      E_t = lam * z_t + (1 - lam) * E_{t-1},
                           signal when E_t > L * sqrt(lam / (2 - lam))

Two design choices matter, and both came out of testing:

  * Charts read non-overlapping weekly KRIs (CHART_WINDOW_DAYS), not the 28-day
    rolling KRI sampled weekly that the threshold and audit arms use. Rolling
    windows overlap by three weeks, so one noisy stretch was counted about four
    times, which inflated false alarms. Charting each period once is the
    textbook setup; the chart does the accumulating.
  * Rates are standardized against each site's own run-in level
    (site_reference), not the trial-wide mean. With a pooled mean, a site whose
    normal adherence is slightly low drifts into alarm without any failure.
    Assumes a failure-free run-in (RUNIN_DAY), which holds in this simulation
    because failures start no earlier than day 120; a real run-in can be
    contaminated, which is a limitation.

Alerting matches the other arms: one alert when the chart first crosses its
limit, and it re-arms once the statistic falls back below the limit. Windows
with too few events to compute a stable rate leave the statistic unchanged.
"""

import numpy as np
import pandas as pd

from generate import generate
from kri import compute_kris
from schema import ALERT_COLUMNS, KRI_TO_FAILURE

LOWER_IS_WORSE = {"adherence_rate", "attestation_rate"}
CHART_WINDOW_DAYS = 7
RUNIN_DAY = 112


def chart_cfg(cfg):
    """Config for the charts' non-overlapping weekly KRIs."""
    c = {**cfg, "kri": {**cfg["kri"], "window_days": CHART_WINDOW_DAYS}}
    return c


def chart_kris(observed, cfg):
    return compute_kris(observed, chart_cfg(cfg), step_days=CHART_WINDOW_DAYS)


def estimate_reference(cfg, n_trials=20, seed=100_000):
    """In-control mean and sd of each KRI, from clean trials with no injected failures.

    Seeds start far from the evaluation seeds so no evaluated trial is used here.
    """
    min_events = cfg["kri"]["min_events_in_window"]
    frames = []
    for i in range(n_trials):
        rng = np.random.default_rng(seed + i)
        kris = chart_kris(generate(cfg, rng), cfg)
        ok = (kris.kri_name == "version_lag_days") | (kris.n_events >= min_events)
        frames.append(kris[ok & kris.value.notna()].assign(trial=i))
    clean = pd.concat(frames)
    rates = clean[clean.kri_name.isin(LOWER_IS_WORSE)]
    ref = rates.groupby("kri_name").value.agg(["mean", "std"])
    out = {k: (float(r["mean"]), max(float(r["std"]), 1e-6)) for k, r in ref.iterrows()}
    # Within-site sd: spread of each site around its own mean, for site baselines.
    dev = rates.value - rates.groupby(["trial", "site_id", "kri_name"]).value.transform("mean")
    out["within_sd"] = {k: max(float(v), 1e-6) for k, v in dev.groupby(rates.kri_name).std().items()}
    am = cfg["amendments"]
    out["version_lag_days"] = (float(am["normal_ack_lag_days"]), float(am["ack_lag_sd"]))
    return out


def site_reference(kris, cfg, ref, runin_day=RUNIN_DAY):
    """Per-site baseline: each site's own mean over the run-in, with the pooled
    within-site sd. Removes stable between-site differences (a site whose normal
    adherence is 0.88 is not failing) so only change from a site's own level
    accumulates. Version lag keeps the acknowledgment-window reference.
    """
    min_events = cfg["kri"]["min_events_in_window"]
    run = kris[(kris.day <= runin_day) & kris.kri_name.isin(LOWER_IS_WORSE)
               & (kris.n_events >= min_events) & kris.value.notna()]
    means = run.groupby(["site_id", "kri_name"]).value.mean()
    out = {}
    for (site, k), mu in means.items():
        out[(site, k)] = (float(mu), ref["within_sd"][k])
    return {**ref, **out}


def _standardize(kri_name, value, ref, site=None):
    mu, sd = ref.get((site, kri_name)) or ref[kri_name]
    z = (value - mu) / sd
    return -z if kri_name in LOWER_IS_WORSE else z


def _run_chart(kris, cfg, ref, update, limit, arm):
    min_events = cfg["kri"]["min_events_in_window"]
    alerts = []
    for (site, kri_name), g in kris.groupby(["site_id", "kri_name"]):
        stat = 0.0
        in_alarm = False
        for r in g.sort_values("day").itertuples():
            if pd.isna(r.value):
                continue
            if r.n_events < min_events and kri_name != "version_lag_days":
                continue
            stat = update(stat, _standardize(kri_name, r.value, ref, site))
            if stat > limit and not in_alarm:
                alerts.append(
                    {
                        "arm": arm,
                        "site_id": site,
                        "detected_day": int(r.day),
                        "failure_type": KRI_TO_FAILURE[kri_name],
                        "kri_triggered": kri_name,
                        "observed_value": float(r.value),
                    }
                )
                in_alarm = True
            elif stat <= limit:
                in_alarm = False
    return pd.DataFrame(alerts, columns=ALERT_COLUMNS)


def detect_cusum(kris, cfg, ref, k=0.5, h=5.0):
    return _run_chart(kris, cfg, ref, lambda s, z: max(0.0, s + z - k), h, "cusum")


def detect_ewma(kris, cfg, ref, lam=0.2, L=3.0):
    limit = L * np.sqrt(lam / (2 - lam))
    return _run_chart(kris, cfg, ref, lambda e, z: lam * z + (1 - lam) * e, limit, "ewma")
