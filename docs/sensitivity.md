# Sensitivity

One-at-a-time variations around the calibrated scenario (`src/sensitivity.py`,
50 simulated trials each). Trial-shape variants use the interquartile range of
the ClinicalTrials.gov sample; severity variants change all three failure types
together (adherence floor 0.75 / 0.40, attestation rate 0.80 / 0.40, extra
protocol lag 100 / 300 days; calibrated 0.55 / 0.60 / 200).

Figure: `results/sensitivity_gap.png`. Table: `results/sensitivity_summary.csv`.

Days sooner than a monthly audit for the best continuous arm, at <= 0.05 false
alarms per site-year (95% bootstrap CI):

| Variant | Missing attestation | Adherence decay |
|---|---|---|
| Calibrated (41 sites, 7 per site) | +19 (17 to 21) | +13 (10 to 16) |
| 18 sites | +18 (14 to 21) | +8 (0 to 14) |
| 93 sites | +20 (18 to 22) | +10 (9 to 13) |
| 4 patients per site | +13 (10 to 15) | -2 (-7 to 2) |
| 14 patients per site | +22 (19 to 24) | +19 (17 to 23) |
| Milder failures | +29 (24 to 41) | +6 (0 to 14) |
| More severe failures | +16 (14 to 19) | +8 (5 to 11) |

Reading:
- Missing attestation: continuous monitoring is faster than a monthly audit in
  every variant, by about 2 to 4 weeks.
- Adherence decay: faster in every variant except the smallest sites (4
  patients each), where it ties a monthly audit; the advantage grows with
  patients per site, because per-site rates get less noisy.
- Site count barely matters; patients per site is what drives the result.
- At 4 patients per site the threshold rule cannot stay under 0.05 false alarms
  per site-year, and the control charts need 21-day windows to have enough
  events to compute attestation at all.
- Protocol-version lag stays slow and incompletely detected by every arm in
  every variant (see `results/sensitivity_summary.csv`).

Reproduce:

    python src/sensitivity.py --replications 50
    python src/sensitivity.py --summarize --variants calibrated sites_18 sites_93 pps_4 pps_14 mild severe
    python src/plot_sensitivity.py
