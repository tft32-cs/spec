"""Summarize trial shape from the ClinicalTrials.gov sample (calibration/ctgov_phase3_sample.csv).

Sample: 300 trials drawn at random (seed 5920) from the 3,379 completed,
industry-sponsored, interventional Phase 3 trials that started 2015-2019,
pulled with tools/fetch_ctgov.py via the public API v2.

Multi-site trials only (n_sites >= 2) for site counts and patients per site:
n_sites == 0 means no locations were listed, and single-site trials have no
cross-site monitoring problem. Duration is start -> primary completion.
"""
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
d = pd.read_csv(HERE / "ctgov_phase3_sample.csv")
for c in ["start_date", "primary_completion_date"]:
    d[c] = pd.to_datetime(d[c], format="mixed")
d["duration_days"] = (d.primary_completion_date - d.start_date).dt.days
m = d[d.n_sites >= 2].copy()
m["patients_per_site"] = m.enrollment / m.n_sites
q = [0.10, 0.25, 0.50, 0.75, 0.90]
out = pd.DataFrame({
    "n_sites": m.n_sites.quantile(q),
    "patients_per_site": m.patients_per_site.quantile(q),
    "duration_days": m.duration_days.quantile(q),
    "enrollment": m.enrollment.quantile(q),
}).round(1)
out.index.name = "quantile"
print(f"{len(d)} trials; {len(m)} multi-site; {int((d.n_sites == 0).sum())} with no sites listed; "
      f"{int((d.n_sites == 1).sum())} single-site")
print(out.to_string())
out.to_csv(HERE / "ctgov_summary.csv")
