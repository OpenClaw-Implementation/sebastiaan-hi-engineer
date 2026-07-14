"""One-off runner: scrape all active event sources, then normalize, enrich,
and run the jobs + articles pipelines against every new pending company.

Usage:
    heroku run python bulk_full_pipeline.py -a hi-engineer-app

Stages, in order, streaming to Logs+Costs via one shared RunLogger:
    1. Scrape every active event source (parser dispatched from the row).
    2. Upsert every returned exhibitor into `companies`.
    3. Cascade-enrich every pending company.
    4. Jobs pipeline over every companies-with-website eligible row.
    5. Articles pipeline over every companies-with-website eligible row.
"""

from __future__ import annotations

import sys
import time

import db
from enrichers import cascade as enrich_cascade
from runlog import RunLogger
from scrapers import articles_pipeline, event_sources, jobs_pipeline


def main() -> int:
    if not db.using_db():
        print("no DATABASE_URL, aborting"); return 2
    started = time.time()

    sources = db.list_event_sources(only_active=True)
    active = [s for s in sources if s["parser"] != "unsupported"]
    print(f"Full pipeline starting: {len(active)} active sources", flush=True)

    run_id = db.create_run("full_pipeline", f"Full run across {len(active)} sources")
    log = RunLogger(run_id)

    # ---- Stage 1: scrape sources + upsert exhibitors ----
    total_scraped = total_new = 0
    for s in active:
        result = event_sources.scrape_source(s, logger=log)
        added = 0
        for ex in result["exhibitors"]:
            cid = db.upsert_company_from_exhibitor(ex)
            if cid:
                added += 1
        db.mark_source_scraped(s["id"], result["count"],
                               error=result.get("error"),
                               meta_update=result.get("meta_update"))
        log.event("source_persist",
                  f"{s.get('label') or s['url']}: upserted {added} companies")
        total_scraped += result["count"]; total_new += added
        print(f"  {s.get('label') or s['url']}: {result['count']} exhibitors "
              f"→ upserted {added}", flush=True)

    print(f"\nStage 1 done: {total_scraped} exhibitors scraped, "
          f"{total_new} upserted into companies\n", flush=True)

    # ---- Stage 2: enrich all pending ----
    stage_start = time.time()
    pending = db.list_companies(status="pending")
    print(f"Stage 2: enriching {len(pending)} pending companies", flush=True)
    enriched = terminal = 0
    total_usd = 0.0
    for i, c in enumerate(pending, 1):
        try:
            r = enrich_cascade.enrich_one(c, logger=log)
        except Exception as exc:  # noqa: BLE001
            r = {"name": c["name"], "status": "terminal", "usd": 0.0,
                 "credits": 0.0, "filled_fields": [], "hit_sources": []}
            print(f"  ERR {c['name']}: {exc}", flush=True)
        total_usd += r["usd"]
        if r["status"] == "enriched":
            enriched += 1
        else:
            terminal += 1
        if i % 25 == 0:
            print(f"  ... {i}/{len(pending)} · ${total_usd:.3f} so far",
                  flush=True)
    print(f"Stage 2 done in {time.time() - stage_start:.0f}s: "
          f"{enriched} enriched, {terminal} terminal, ${total_usd:.4f}\n",
          flush=True)

    # ---- Stage 3: jobs pipeline ----
    stage_start = time.time()
    to_scan = db.companies_for_pipeline("jobs")
    print(f"Stage 3: jobs pipeline for {len(to_scan)} companies", flush=True)
    jobs_new = jobs_errors = 0
    for i, c in enumerate(to_scan, 1):
        try:
            r = jobs_pipeline.scrape_jobs_for_company(c, logger=log)
        except Exception:  # noqa: BLE001
            r = {"count": 0, "new": 0, "error": "crash"}
        jobs_new += r["new"]
        if r.get("error"):
            jobs_errors += 1
        if i % 25 == 0:
            print(f"  ... {i}/{len(to_scan)}", flush=True)
    print(f"Stage 3 done in {time.time() - stage_start:.0f}s: "
          f"+{jobs_new} new jobs, {jobs_errors} errors\n", flush=True)

    # ---- Stage 4: articles pipeline ----
    stage_start = time.time()
    to_scan = db.companies_for_pipeline("articles")
    print(f"Stage 4: articles pipeline for {len(to_scan)} companies",
          flush=True)
    art_new = art_errors = 0
    for i, c in enumerate(to_scan, 1):
        try:
            r = articles_pipeline.scrape_articles_for_company(c, logger=log)
        except Exception:  # noqa: BLE001
            r = {"count": 0, "new": 0, "error": "crash"}
        art_new += r["new"]
        if r.get("error"):
            art_errors += 1
        if i % 25 == 0:
            print(f"  ... {i}/{len(to_scan)}", flush=True)
    print(f"Stage 4 done in {time.time() - stage_start:.0f}s: "
          f"+{art_new} new articles, {art_errors} errors\n", flush=True)

    log.event("full_summary",
              f"sources: {len(active)} · scraped {total_scraped} exhibitors "
              f"({total_new} new) · enriched {enriched} · +{jobs_new} jobs · "
              f"+{art_new} articles · ${total_usd:.4f}")
    db.finish_run(run_id)

    total = time.time() - started
    print("=" * 72, flush=True)
    print(f"FULL PIPELINE DONE in {total:.0f}s (~{total/60:.1f} min)", flush=True)
    print(f"  sources:    {len(active)}", flush=True)
    print(f"  scraped:    {total_scraped}", flush=True)
    print(f"  new upsert: {total_new}", flush=True)
    print(f"  enriched:   {enriched}", flush=True)
    print(f"  jobs new:   +{jobs_new}", flush=True)
    print(f"  articles+:  +{art_new}", flush=True)
    print(f"  spend:      ${total_usd:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
