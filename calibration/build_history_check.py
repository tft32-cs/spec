import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment
from openpyxl.worksheet.datavalidation import DataValidation

d = pd.read_csv("calibration/ctgov_phase3_sample.csv")
for c in ["start_date", "primary_completion_date"]:
    d[c] = pd.to_datetime(d[c], format="mixed")
d = d[(d.n_sites >= 2) & ((d.primary_completion_date - d.start_date).dt.days >= 180)]
s = d.sample(30, random_state=5920).sort_values("start_date").reset_index(drop=True)

F = "Arial"
H = Font(name=F, bold=True, color="FFFFFF"); HF = PatternFill("solid", fgColor="1F3864")
B = Font(name=F); INP = Font(name=F, color="0000FF"); INF = PatternFill("solid", fgColor="FFF2CC")
LINK = Font(name=F, color="0563C1", underline="single"); GREY = Font(name=F, italic=True, color="7F7F7F")
thin = Side(style="thin", color="D9D9D9"); BOX = Border(top=thin, bottom=thin, left=thin, right=thin)
wrap = Alignment(wrap_text=True, vertical="top")

wb = Workbook()
# ---------------- Instructions ----------------
ins = wb.active; ins.title = "Instructions"
lines = [
    ("Registry check of protocol changes (validation for the Tufts CSDD amendment inputs)", Font(name=F, bold=True, size=13)),
    ("", B),
    ("What to do for each trial on the Trials tab:", Font(name=F, bold=True)),
    ("1. Click the History link. It opens the trial's 'History of Changes' tab on ClinicalTrials.gov.", B),
    ("2. Note the total number of versions listed and enter it in 'Total versions'.", B),
    ("3. Look only at versions dated on or after the Start date and on or before the Primary completion date (both shown on the row).", B),
    ("4. Of those, count the versions whose list of changed sections includes ANY of: Eligibility, Outcome Measures, Arms and Interventions, Study Design.", B),
    ("   Ignore versions that only change status, dates, contacts/locations, sponsor, references, or results.", GREY),
    ("5. Enter that count in 'Protocol-change versions', and their dates (YYYY-MM-DD, separated by semicolons) in 'Dates of those versions'.", B),
    ("6. Optional: note anything odd in Notes (e.g. 'many changes on one day', 'history tab would not load').", B),
    ("", B),
    ("Legend", Font(name=F, bold=True)),
    ("Blue text on a yellow cell = you fill it in. Black text = pre-filled from the ClinicalTrials.gov sample or calculated.", B),
    ("Row 2 of the Trials tab is a made-up EXAMPLE showing the format; it is excluded from the Summary.", B),
    ("", B),
    ("Why: a registry version that changes these sections is the closest public proxy for a substantial protocol amendment.", B),
    ("Registry updates are not the same as amendments, so this checks the Tufts CSDD figures rather than replacing them.", B),
    ("", B),
    ("Source of trials: random 30 (seed 5920) of the multi-site trials (>= 2 sites, >= 180 days) in the 300-trial sample of", GREY),
    ("completed industry-sponsored Phase 3 trials started 2015-2019, pulled from the ClinicalTrials.gov API v2 on 2026-11-16.", GREY),
]
for i, (t, f) in enumerate(lines, 1):
    c = ins.cell(row=i, column=1, value=t); c.font = f
ins.column_dimensions["A"].width = 130
ins.cell(row=13, column=1).fill = INF

# ---------------- Trials ----------------
ws = wb.create_sheet("Trials")
hdr = ["NCT ID", "History link", "Sponsor", "Condition", "Start date", "Primary completion",
       "Duration (years)", "Sites", "Total versions", "Protocol-change versions",
       "Dates of those versions", "Changes per trial-year", "Notes"]
widths = [14, 11, 28, 30, 12, 13, 10, 7, 10, 12, 34, 12, 30]
for j, (h, w) in enumerate(zip(hdr, widths), 1):
    c = ws.cell(row=1, column=j, value=h); c.font = H; c.fill = HF; c.alignment = Alignment(wrap_text=True, vertical="center")
    ws.column_dimensions[c.column_letter].width = w
ws.row_dimensions[1].height = 32

def row(r, nct, sponsor, cond, start, pc, sites, example=False):
    ws.cell(row=r, column=1, value=nct).font = GREY if example else B
    if example:
        ws.cell(row=r, column=2, value="(example)").font = GREY
    else:
        c = ws.cell(row=r, column=2, value="History")
        c.hyperlink = f"https://clinicaltrials.gov/study/{nct}?tab=history"; c.font = LINK
    ws.cell(row=r, column=3, value=sponsor).font = GREY if example else B
    ws.cell(row=r, column=4, value=cond).font = GREY if example else B
    for col, v in ((5, start), (6, pc)):
        c = ws.cell(row=r, column=col, value=v.to_pydatetime() if hasattr(v, "to_pydatetime") else v)
        c.number_format = "yyyy-mm-dd"; c.font = GREY if example else B
    c = ws.cell(row=r, column=7, value=f"=(F{r}-E{r})/365.25"); c.number_format = "0.0"; c.font = GREY if example else B
    ws.cell(row=r, column=8, value=sites).font = GREY if example else B
    for col in (9, 10, 11, 13):
        c = ws.cell(row=r, column=col); c.font = GREY if example else INP; c.fill = INF
    c = ws.cell(row=r, column=12, value=f'=IF(J{r}="","",J{r}/G{r})'); c.number_format = "0.00"; c.font = GREY if example else B
    for col in range(1, 14):
        ws.cell(row=r, column=col).border = BOX
        ws.cell(row=r, column=col).alignment = wrap

ex_start, ex_pc = pd.Timestamp("2016-03-01"), pd.Timestamp("2018-09-01")
row(2, "EXAMPLE", "(made-up example)", "(not a real trial)", ex_start, ex_pc, 40, example=True)
ws["I2"], ws["J2"], ws["K2"], ws["M2"] = 14, 3, "2016-11-14; 2017-06-02; 2018-01-20", "Example only"
for col in ("I2", "J2", "K2", "M2"):
    ws[col].font = GREY

for k, t in s.iterrows():
    r = k + 3
    cond = str(t.conditions).split("|")[0]
    row(r, t.nct_id, t.sponsor, cond, t.start_date, t.primary_completion_date, int(t.n_sites))
last = 2 + len(s)
dv = DataValidation(type="whole", operator="greaterThanOrEqual", formula1="0", allow_blank=True,
                    error="Enter a whole number (0 or more).")
ws.add_data_validation(dv); dv.add(f"I3:J{last}")
ws.freeze_panes = "C2"
ws["J1"].comment = Comment("Versions dated between Start and Primary completion whose changed sections include "
                           "Eligibility, Outcome Measures, Arms and Interventions, or Study Design.", "Teddy")

# ---------------- Summary ----------------
sm = wb.create_sheet("Summary")
sm.column_dimensions["A"].width = 52; sm.column_dimensions["B"].width = 14; sm.column_dimensions["C"].width = 60
rng_j, rng_g = f"Trials!J3:J{last}", f"Trials!G3:G{last}"
rows_ = [
    ("Measure", "Value", "Note"),
    ("Trials checked so far", f"=COUNT({rng_j})", "Counts filled-in rows (example row excluded)"),
    ("Mean protocol-change versions per trial", f'=IFERROR(AVERAGE({rng_j}),"")', ""),
    ("Median protocol-change versions per trial", f'=IFERROR(MEDIAN({rng_j}),"")', ""),
    ("Share of trials with at least one", f'=IFERROR(COUNTIF({rng_j},">0")/B2,"")', ""),
    ("Mean changes per trial-year", f'=IFERROR(SUMPRODUCT(({rng_j}<>"")*1,{rng_j})/SUMPRODUCT(({rng_j}<>"")*1,{rng_g}),"")',
     "Total changes / total years, over checked trials only"),
    ("", None, ""),
    ("Comparison inputs", None, ""),
    ("Tufts CSDD: substantial amendments per Phase III protocol", 3.4,
     "Tufts CSDD Impact Report 27(6), Nov/Dec 2025 (primary completion 2023-2025)"),
    ("Tufts CSDD: share of protocols with >= 1 amendment (all phases)", 0.76,
     "Getz et al., Ther Innov Regul Sci 58:539-548 (2024), 2022 cohort"),
    ("Calibrated scenario: amendments per trial", 3, "config/scenario_calibrated.yaml"),
    ("Calibrated scenario: amendments per trial-year", "=B11/(716/365.25)", "3 amendments over the 716-day median duration"),
    ("", None, ""),
    ("Registry mean as a share of Tufts (per trial)", '=IFERROR(B3/B9,"")', "Below 1 = registry under-records amendments"),
]
for i, (a, b, c) in enumerate(rows_, 1):
    sm.cell(row=i, column=1, value=a).font = Font(name=F, bold=(i in (1, 8)))
    cb = sm.cell(row=i, column=2, value=b); cb.font = B
    sm.cell(row=i, column=3, value=c).font = GREY if i > 1 else Font(name=F, bold=True)
for r_ in (3, 4, 6, 12): sm.cell(row=r_, column=2).number_format = "0.00"
for r_ in (5, 10, 14): sm.cell(row=r_, column=2).number_format = "0%"
sm["B9"].font = INP; sm["B10"].font = INP; sm["B11"].font = INP
wb.move_sheet("Summary", offset=-1)
wb.save("calibration/ctgov_history_check.xlsx")
print("rows", len(s), "last row", last)
