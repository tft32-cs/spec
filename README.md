# Continuous statistical monitoring of clinical trial workflow integrity

INFO 5920 specialization project — Theodore Taylor, Cornell Tech

## Research question

Can continuous statistical monitoring of trial workflow event logs detect
protocol-conformance and adherence-integrity failures substantially earlier than
scheduled audit, and what is that earlier detection worth in regulatory terms?

Tufts CSDD reports that three of four protocols undergo at least one amendment,
with sites operating an average of 215 days under outdated versions before
synchronization. Current practice catches the resulting deviations through
periodic manual audit, months after the data is generated. ICH E6(R3) and the
risk-based monitoring literature argue instead for continuous statistical
surveillance of incoming data. This project quantifies what that shift buys.

## Design

The pipeline separates the data a detector sees from the record of what was
actually injected. That separation is what makes detection latency measurable:
without a recorded true start day, "detected 59 days earlier" has no referent.

```
config ──> generate ──> inject ──┬──> observed log ──> KRIs ──┬──> continuous arm ──┐
                                 │                            │                     ├──> evaluator
                                 └──> ground truth ───────────┴──> audit arm ───────┘
```

Both detection arms emit the same alert schema (`src/schema.py`), so the
evaluator never needs to know which arm produced a row. Adding a third
comparison arm costs one module and no changes elsewhere.

### Failure modes

| Type | Mechanism | KRI that should catch it |
|---|---|---|
| `protocol_lag` | Site stops acknowledging amendments; operates on an obsolete version | `version_lag_days` |
| `adherence_decay` | Dosing compliance decays linearly toward a floor | `adherence_rate` |
| `missing_attestation` | Events still occur but stop being attested | `attestation_rate` |

### Metrics

- **Detection latency** — days from true failure start to first alert
- **Detection rate** — share of injected failures ever alerted on
- **False positives per site-year** — alerts matching no injected failure

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
# One run, saving every intermediate artifact for inspection
python src/run.py --config config/scenario_base.yaml --seed 1 --save

# Replications — report distributions, not point estimates
python src/run.py --config config/scenario_base.yaml --replications 100

# Tests
python -m pytest tests/ -q
```

Results land in `results/runs.csv` (one row per arm per seed) and
`results/summary.csv` (aggregated). Intermediate artifacts go to `data/`,
which is gitignored because everything in it is regenerable from a seed.

## Current state

The skeleton runs end to end and all seven invariant tests pass. A 30-seed
run of the base scenario currently produces:

| Arm | Detection rate | Median latency | Interquartile range |
|---|---|---|---|
| Continuous | 1.00 | 81.5 days | 68–87 |
| Scheduled audit | 1.00 | 135.5 days | 116–145 |

These are placeholder numbers from untuned thresholds, not findings.

## Open work

1. **Thresholds are untuned.** Both arms currently detect everything with
   almost no false positives, which means the thresholds are too lenient to
   sit anywhere interesting on the ROC curve. Sweep them and report the
   latency/false-positive trade-off rather than a single operating point.
2. **Detection rules are fixed thresholds.** Replace with control-chart rules
   (CUSUM or EWMA) and compare against site-level empirical baselines rather
   than global constants.
3. **Calibration against real data.** Amendment frequency and inter-amendment
   timing should be fit to protocol version histories from ClinicalTrials.gov,
   which publishes full archived record versions per trial. Injected deviation
   types should map to categories cited in FDA inspection findings.
4. **Power impact.** Translate adherence decay into effective sample size and
   preserved statistical power. Scoped as optional — if it stalls, latency and
   false positive rate stand as the primary results.

## Layout

```
config/     scenario parameters, one YAML per scenario
src/        pipeline modules, one per stage
data/       generated artifacts (gitignored)
results/    evaluation output
tests/      invariant checks
```
