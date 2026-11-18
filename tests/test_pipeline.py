"""Invariant checks. Run with: python -m pytest tests/ -q

These guard the properties the evaluation depends on, not implementation
details. If injection stops being separable from generation, or a detector
stops emitting the shared alert schema, the comparison silently stops being
meaningful — these catch that.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import detect_audit  # noqa: E402
import detect_continuous  # noqa: E402
from evaluate import evaluate  # noqa: E402
from generate import generate  # noqa: E402
from inject import inject  # noqa: E402
from kri import compute_kris  # noqa: E402
from run import load_config  # noqa: E402
from schema import ALERT_COLUMNS, EVENT_COLUMNS  # noqa: E402


@pytest.fixture(scope="module")
def cfg():
    return load_config(ROOT / "config" / "scenario_base.yaml")


@pytest.fixture(scope="module")
def pipeline(cfg):
    rng = np.random.default_rng(42)
    clean = generate(cfg, rng)
    observed, truth = inject(clean, cfg, rng)
    kris = compute_kris(observed, cfg)
    return clean, observed, truth, kris


def test_generator_schema(pipeline):
    clean = pipeline[0]
    assert list(clean.columns) == EVENT_COLUMNS
    assert len(clean) > 0


def test_same_seed_is_reproducible(cfg):
    a = generate(cfg, np.random.default_rng(7))
    b = generate(cfg, np.random.default_rng(7))
    assert a.equals(b)


def test_injection_changes_the_log(pipeline):
    clean, observed = pipeline[0], pipeline[1]
    assert not clean.equals(observed)


def test_ground_truth_start_days_are_in_range(pipeline, cfg):
    truth = pipeline[2]
    assert len(truth) == cfg["failures"]["n_affected_sites"]
    assert (truth.start_day >= cfg["failures"]["earliest_start_day"]).all()
    assert (truth.start_day <= cfg["trial"]["duration_days"]).all()


def test_detectors_share_the_alert_schema(pipeline, cfg):
    kris = pipeline[3]
    for module in (detect_continuous, detect_audit):
        alerts = module.detect(kris, cfg)
        assert list(alerts.columns) == ALERT_COLUMNS


def test_audit_alerts_land_on_audit_days(pipeline, cfg):
    kris = pipeline[3]
    alerts = detect_audit.detect(kris, cfg)
    interval = cfg["detection"]["audit"]["interval_days"]
    assert (alerts.detected_day % interval == 0).all()


def test_no_alert_precedes_its_failure(pipeline, cfg):
    """Latency must never be negative — the core evaluation invariant."""
    import pandas as pd

    kris, truth = pipeline[3], pipeline[2]
    alerts = pd.concat(
        [detect_continuous.detect(kris, cfg), detect_audit.detect(kris, cfg)],
        ignore_index=True,
    )
    summary = evaluate(alerts, truth, cfg, seed=42)
    latencies = summary.median_latency_days.dropna()
    assert (latencies >= 0).all()


def test_version_lag_does_not_reset_at_new_amendment(cfg):
    """A site that never acknowledges keeps accruing lag across amendments."""
    import pandas as pd
    from generate import _amendment_days

    amend = _amendment_days(cfg)
    obs = pd.DataFrame(
        [{"site_id": "S01", "day": d, "event_type": "dose_administered",
          "attestation_status": "attested"} for d in range(1, cfg["trial"]["duration_days"] + 1, 7)]
    )
    lag = compute_kris(obs, cfg)
    lag = lag[lag.kri_name == "version_lag_days"].set_index("day").value
    day = max(d for d in lag.index if d > amend[1])
    assert lag[day] == day - amend[0]


def test_continuous_rearms_after_breach_clears(cfg):
    import pandas as pd

    values = [0.5] * 3 + [0.95] * 3 + [0.5] * 3
    kris = pd.DataFrame({"site_id": "S01", "day": range(28, 28 + 7 * len(values), 7),
                         "kri_name": "adherence_rate", "value": values, "n_events": 50})
    alerts = detect_continuous.detect(kris, cfg)
    assert len(alerts) == 2


def _flat_kris(values, kri="adherence_rate", site="S01", start=7, step=7):
    import pandas as pd
    return pd.DataFrame({"site_id": site, "day": range(start, start + step * len(values), step),
                         "kri_name": kri, "value": values, "n_events": 50})


def test_control_charts_quiet_in_control_and_fire_on_shift(cfg):
    from detect_control_chart import detect_cusum, detect_ewma

    ref = {"adherence_rate": (0.92, 0.03)}
    quiet = _flat_kris([0.92] * 40)
    assert detect_cusum(quiet, cfg, ref, k=0.5, h=4).empty
    assert detect_ewma(quiet, cfg, ref, lam=0.2, L=3).empty

    # A 2-sd drop accumulates (2 - 0.5) = 1.5 per week, so CUSUM crosses h=4 on week 3.
    shifted = _flat_kris([0.92] * 10 + [0.86] * 10)
    a = detect_cusum(shifted, cfg, ref, k=0.5, h=4)
    assert len(a) == 1 and a.detected_day.iloc[0] == 7 + 7 * 12
    assert len(detect_ewma(shifted, cfg, ref, lam=0.2, L=3)) == 1


def test_site_reference_uses_each_sites_own_run_in(cfg):
    import pandas as pd
    from detect_control_chart import site_reference

    kris = pd.concat([_flat_kris([0.85] * 20, site="S01"), _flat_kris([0.95] * 20, site="S02")])
    ref = {"adherence_rate": (0.90, 0.04), "within_sd": {"adherence_rate": 0.03}}
    sref = site_reference(kris, cfg, ref, runin_day=56)
    assert sref[("S01", "adherence_rate")] == (0.85, 0.03)
    assert sref[("S02", "adherence_rate")] == (0.95, 0.03)
