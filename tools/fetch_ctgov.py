"""Pull ClinicalTrials.gov record version histories for amendment calibration.

Run this on your own computer (Python 3.8+, standard library only):

    python fetch_ctgov.py

It writes ctgov_pull.zip next to this script. Send that file back.

What it does
  1. Lists completed, industry-sponsored, interventional Phase 3 trials that
     started 2015-2019, via the public API v2 (one page of 1,000 at a time).
  2. Picks a random sample (default 300; fixed seed so it is reproducible).
  3. For each sampled trial, saves its version history from the endpoint the
     cthist research package uses: /api/int/studies/{NCT}?history=true. That
     endpoint is undocumented, so the raw JSON is saved as-is and parsed later.
  4. Waits between requests to be polite to the server. Expect ~10 minutes.

It can be stopped and re-run: trials already saved are skipped.

Options:
    python fetch_ctgov.py --n 300 --phase PHASE3 --start 2015-01-01 --end 2019-12-31
"""

import argparse
import csv
import json
import random
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

API = "https://clinicaltrials.gov/api/v2/studies"
HISTORY = "https://clinicaltrials.gov/api/int/studies/{nct}?history=true"
HEADERS = {"User-Agent": "Cornell Tech INFO 5920 student project (amendment calibration)",
           "Accept": "application/json"}
OUT = Path(__file__).resolve().parent / "ctgov_pull"


def get_json(url, tries=4):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # network blip or rate limit: back off and retry
            if attempt == tries - 1:
                raise
            wait = 5 * (attempt + 1)
            print(f"    retry in {wait}s ({e})")
            time.sleep(wait)


def list_trials(phase, start, end):
    expr = (f"AREA[StudyType]INTERVENTIONAL AND AREA[Phase]{phase} "
            f"AND AREA[LeadSponsorClass]INDUSTRY AND AREA[OverallStatus]COMPLETED "
            f"AND AREA[StartDate]RANGE[{start},{end}]")
    fields = ",".join([
        "NCTId", "Phase", "StartDate", "PrimaryCompletionDate", "CompletionDate",
        "EnrollmentCount", "LeadSponsorName", "Condition", "LocationFacility",
    ])
    rows, token = [], None
    while True:
        params = {"filter.advanced": expr, "fields": fields, "pageSize": 1000, "countTotal": "true"}
        if token:
            params["pageToken"] = token
        page = get_json(API + "?" + urllib.parse.urlencode(params))
        if token is None:
            print(f"  {page.get('totalCount', '?')} trials match")
        for s in page.get("studies", []):
            ps = s.get("protocolSection", {})
            ident = ps.get("identificationModule", {})
            status = ps.get("statusModule", {})
            design = ps.get("designModule", {})
            locs = ps.get("contactsLocationsModule", {}).get("locations", [])
            rows.append({
                "nct_id": ident.get("nctId"),
                "phase": "|".join(design.get("phases", [])),
                "start_date": status.get("startDateStruct", {}).get("date"),
                "primary_completion_date": status.get("primaryCompletionDateStruct", {}).get("date"),
                "completion_date": status.get("completionDateStruct", {}).get("date"),
                "enrollment": design.get("enrollmentInfo", {}).get("count"),
                "n_sites": len(locs),
                "sponsor": ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name"),
                "conditions": "|".join(ps.get("conditionsModule", {}).get("conditions", [])),
            })
        token = page.get("nextPageToken")
        if not token:
            return rows
        time.sleep(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--phase", default="PHASE3")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2019-12-31")
    ap.add_argument("--seed", type=int, default=5920)
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between history requests")
    args = ap.parse_args()

    (OUT / "history").mkdir(parents=True, exist_ok=True)
    print("1/3 Listing trials...")
    trials = list_trials(args.phase, args.start, args.end)
    random.Random(args.seed).shuffle(trials)
    sample = trials[: args.n]
    with open(OUT / "trials.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(sample[0].keys()))
        w.writeheader()
        w.writerows(sample)
    (OUT / "query.json").write_text(json.dumps({**vars(args), "n_matching": len(trials)}, indent=2))

    print(f"2/3 Downloading version histories for {len(sample)} trials...")
    failed = []
    for i, t in enumerate(sample, 1):
        dest = OUT / "history" / f"{t['nct_id']}.json"
        if dest.exists():
            continue
        try:
            dest.write_text(json.dumps(get_json(HISTORY.format(nct=t["nct_id"]))), encoding="utf-8")
        except Exception as e:
            failed.append(t["nct_id"])
            print(f"    {t['nct_id']} failed: {e}")
        if i % 25 == 0:
            print(f"  {i}/{len(sample)}")
        time.sleep(args.delay)
    if failed:
        (OUT / "failed.txt").write_text("\n".join(failed))

    print("3/3 Zipping...")
    zpath = OUT.with_suffix(".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in OUT.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(OUT.parent))
    print(f"Done: {zpath}  ({len(sample) - len(failed)} histories, {len(failed)} failed)")


if __name__ == "__main__":
    main()
