"""Run the jobs or articles pipeline against every eligible company.

Usage:
    heroku run python bulk_pipeline.py jobs      -a hi-engineer-app
    heroku run python bulk_pipeline.py articles  -a hi-engineer-app
"""

from __future__ import annotations

import sys
import time

import db
from runlog import RunLogger
from scrapers import articles_pipeline, jobs_pipeline


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("jobs", "articles"):
        print("Usage: python bulk_pipeline.py [jobs|articles]"); return 2
    kind = sys.argv[1]
    scraper = (jobs_pipeline.scrape_jobs_for_company if kind == "jobs"
               else articles_pipeline.scrape_articles_for_company)

    pending = db.companies_for_pipeline(kind)
    n = len(pending)
    if n == 0:
        print(f"No companies pending for {kind}."); return 0

    run_id = db.create_run(f"{kind}_bulk", f"{kind.capitalize()} pipeline ({n} companies)")
    log = RunLogger(run_id)

    print(f"{kind} pipeline: {n} companies eligible", flush=True)
    print(f"Run id: {run_id}", flush=True)
    print(f"{'#':>4} | {'company':32} | {'items':>5} | {'new':>4} | {'time':>7} | note",
          flush=True)
    print("-" * 92, flush=True)

    totals = {"items_seen": 0, "items_new": 0, "errors": 0}
    start = time.time()
    for i, c in enumerate(pending, 1):
        t0 = time.time()
        try:
            r = scraper(c, logger=log)
        except Exception as exc:  # noqa: BLE001
            r = {"company_id": c["id"], "count": 0, "new": 0, "url": None,
                 "error": f"scraper crash: {exc}"}
        dt = time.time() - t0
        totals["items_seen"] += r["count"]
        totals["items_new"] += r["new"]
        if r.get("error"):
            totals["errors"] += 1
        note = r.get("error") or (r.get("url") or "-")
        print(f"{i:>4} | {c['name'][:32]:32} | {r['count']:>5} | {r['new']:>4} | "
              f"{dt:6.1f}s | {note[:60]}", flush=True)

    log.event(f"{kind}_summary",
              f"{n} companies · {totals['items_seen']} items seen · "
              f"{totals['items_new']} new · {totals['errors']} errors")
    db.finish_run(run_id)

    elapsed = time.time() - start
    print("-" * 92, flush=True)
    print(f"DONE in {elapsed:.1f}s ({elapsed/max(n,1):.1f}s/company avg)", flush=True)
    print(f"Items seen: {totals['items_seen']} · New: {totals['items_new']} · "
          f"Errors: {totals['errors']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
