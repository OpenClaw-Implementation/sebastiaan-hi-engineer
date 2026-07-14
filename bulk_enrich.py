"""One-off bulk enrichment of every pending company.

Run on a Heroku one-off dyno so we're not bound by the 30s router timeout:

    heroku run python bulk_enrich.py -a hi-engineer-app

Every leg attempt is written to ``company_enrichment_log`` (audit) AND streamed
via ``RunLogger`` so the Logs+Costs tab shows the run live while it executes.
"""

from __future__ import annotations

import sys
import time

import db
from enrichers import cascade
from runlog import RunLogger


def main() -> int:
    pending = db.list_companies(status="pending")
    n = len(pending)
    if n == 0:
        print("No pending companies. Nothing to do.")
        return 0

    run_id = db.create_run("enrich_bulk_all", f"Enrich all pending ({n} companies)")
    log = RunLogger(run_id)

    print(f"Starting bulk enrichment: {n} companies", flush=True)
    print(f"Run id: {run_id}", flush=True)
    print(f"{'#':>4} | {'company':32} | {'status':9} | {'src':16} | {'usd':>7} | {'time':>7}",
          flush=True)
    print("-" * 92, flush=True)

    totals = {"filled": 0, "terminal": 0, "credits": 0.0, "usd": 0.0}
    start = time.time()
    for i, c in enumerate(pending, 1):
        t0 = time.time()
        try:
            r = cascade.enrich_one(c, logger=log)
        except Exception as exc:  # noqa: BLE001 -- keep going even if one row explodes
            r = {"name": c["name"], "status": "terminal", "usd": 0.0, "credits": 0.0,
                 "hit_sources": [], "filled_fields": []}
            print(f"  ERROR on {c['name']}: {exc}", flush=True)
        dt = time.time() - t0
        totals["credits"] += r["credits"]
        totals["usd"] += r["usd"]
        if r["status"] == "enriched":
            totals["filled"] += 1
        else:
            totals["terminal"] += 1
        src = "+".join(r.get("hit_sources", [])) or "-"
        print(f"{i:>4} | {c['name'][:32]:32} | {r['status']:9} | {src[:16]:16} | "
              f"{r['usd']:7.4f} | {dt:6.1f}s", flush=True)

    log.event("bulk_summary",
              f"{totals['filled']} enriched, {totals['terminal']} terminal, "
              f"${totals['usd']:.4f} total",
              credits=totals["credits"])
    db.finish_run(run_id)

    elapsed = time.time() - start
    print("-" * 92, flush=True)
    print(f"DONE in {elapsed:.1f}s "
          f"({elapsed / max(n,1):.1f}s/company avg)", flush=True)
    print(f"Filled: {totals['filled']} · Terminal: {totals['terminal']} · "
          f"Credits: {totals['credits']:.4f} · Total: ${totals['usd']:.4f}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
