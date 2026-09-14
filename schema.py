"""Canonical schemas for every artifact the pipeline passes between stages.

Keeping these in one place is what lets the evaluator stay arm-agnostic: both
detectors emit ALERT_COLUMNS, so evaluate.py never needs to know which one
produced a given row.
"""

EVENT_COLUMNS = [
    "event_id",
    "trial_id",
    "site_id",
    "stakeholder_type",
    "event_type",
    "protocol_version",
    "day",
    "attestation_status",
]

# One row per injected failure. This is the ground truth the detectors never see.
GROUND_TRUTH_COLUMNS = [
    "failure_id",
    "site_id",
    "failure_type",
    "start_day",
    "end_day",
]

# The interface both detection arms implement.
ALERT_COLUMNS = [
    "arm",
    "site_id",
    "detected_day",
    "failure_type",
    "kri_triggered",
    "observed_value",
]

KRI_COLUMNS = [
    "site_id",
    "day",
    "kri_name",
    "value",
    "n_events",
]

EVENT_TYPES = [
    "amendment_issued",
    "version_ack",
    "dose_administered",
    "consent_recorded",
]

STAKEHOLDERS = ["sponsor", "cro", "site"]

# Maps each KRI to the failure type it is designed to catch.
KRI_TO_FAILURE = {
    "version_lag_days": "protocol_lag",
    "adherence_rate": "adherence_decay",
    "attestation_rate": "missing_attestation",
}
