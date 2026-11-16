# Calibration

The calibrated scenario (`config/scenario_calibrated.yaml`) replaces the base
scenario's illustrative trial shape and amendment timing with values from real
trials and published benchmarks.

## Trial shape: ClinicalTrials.gov sample

`tools/fetch_ctgov.py` listed every completed, industry-sponsored,
interventional Phase 3 trial that started 2015-2019 (3,379 trials, public API
v2) and drew a random sample of 300 (seed 5920). The sample is in
`calibration/ctgov_phase3_sample.csv`; `calibration/summarize_ctgov.py`
reproduces the table below.

Multi-site trials only (241 of 300; 50 were single-site and 9 listed no sites).

| Quantile | Sites | Patients per site | Duration (start to primary completion, days) |
|---|---|---|---|
| 10% | 9 | 2.4 | 259 |
| 25% | 18 | 4.2 | 471 |
| **50%** | **41** | **6.9** | **716** |
| 75% | 93 | 13.5 | 1,106 |
| 90% | 159 | 38.5 | 1,699 |

Calibrated values: 41 sites, 7 patients per site, 716 days. Real trials are
wider and thinner than the base scenario (12 sites x 20 patients, 540 days),
which makes each site's rates noisier.

Limitations: patients are all enrolled at the start of the simulation, whereas
real trials enroll over time; site counts come from the record's current
location list.

## Amendment timing: Tufts CSDD benchmarks

The plan was to fit amendment frequency and timing to ClinicalTrials.gov record
version histories. The registry serves those only through an undocumented
internal endpoint, and it refused scripted requests (HTTP 403), so amendment
inputs come from the published Tufts CSDD benchmarks instead:

- **Number of amendments.** Tufts CSDD's 2022 cohort (950 protocols, published
  2024) found a mean of 3.3 amendments per amended protocol, and its 2025 report
  found 3.4 substantial amendments for a typical Phase III protocol. Calibrated:
  3 amendments, spread evenly across the 716-day trial (days 179, 358, 537).
- **Site adoption lag.** The same 2024 study found that investigative sites
  operate under different protocol versions for a mean of 215 days. Read as the
  spread of routine adoption across sites (roughly 0-215 days): mean 107 days,
  sd 62 (the sd of a uniform 0-215 spread). The base scenario assumed 21 +/- 7.

Sources:
- Getz KA et al. "New Benchmarks on Protocol Amendment Practices, Trends and
  their Impact on Clinical Trial Performance." Therapeutic Innovation &
  Regulatory Science 58, 539-548 (2024). doi:10.1007/s43441-024-00622-9
- Tufts CSDD Impact Report 27(6), November/December 2025 (Phase III: 3.4
  substantial amendments per protocol, primary completion 2023-2025).

## Consequences for the detectors

- **Version-lag thresholds scale with routine lag.** Threshold and audit arms
  sweep version lag from mean + 3 sd (lenient) to mean + 1 sd (tight) of routine
  adoption (293 to 169 days here), so routine adoption is never a breach. Base
  and high-amendment scenarios keep their original 60 to 28 day range.
- **Control charts use 14-day windows.** Seven patients give about six doses a
  week, under the 10-event minimum, so the charts read non-overlapping 14-day
  windows in this scenario (weekly elsewhere).
- **Protocol lag is reported separately.** With routine adoption spread over
  months, a lagging site is indistinguishable from a slow normal site until its
  lag passes ~170 days, and failures that start late can run out of trial before
  any arm sees them. Operating points are therefore selected on adherence decay
  and missing attestation (>= 95% detection), and protocol lag is reported with
  its own detection rate.

## Result under calibration (100 simulated trials, <= 0.05 false alarms per site-year)

Median days from onset to alert (`results/cc_by_type_calibrated.csv`; figure
`results/cc_by_type_calibrated_0.05.png`):

| Failure type | Best continuous | Audit every 4 wks | Audit every 8 wks | Audit every 12 wks |
|---|---|---|---|---|
| Missing attestation | 16 (CUSUM) | 35 | 54 | 80 |
| Adherence decay | 73 (threshold rule) | 86 | 102 | 130 |
| Protocol-version lag | 93 (CUSUM), 72% found | 107, 71% found | 90, 75% found | 135, 64% found |

Compared with the base scenario, continuous monitoring keeps its lead on
missing attestation (~19 days faster than a monthly audit, 95% CI 17-21) and
adherence decay (~13 days, CI 10-16), but the gaps shrink, and with ~7 patients
per site the control charts no longer beat the simple threshold rule on
adherence. Protocol-version lag is detected late and incompletely by every arm,
with no consistent winner.

To reproduce:

    python src/tradeoff_cc.py --replications 100 --scenarios calibrated --tag _calibrated \
        --criterion-types adherence_decay missing_attestation
    python src/report_cc.py _calibrated
    python src/plot_cc.py calibrated _calibrated 0.05
