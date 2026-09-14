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
