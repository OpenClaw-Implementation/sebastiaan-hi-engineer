"""One-off: re-scrape just the ``parser='firecrawl'`` sources.

Used after adding a new extractor strategy to validate the yield jump before
running a full pipeline. Stage 1 only — no enrichment, no jobs/articles.

    heroku run python rescrape_firecrawl.py -a hi-engineer-app
"""

from __future__ import annotations

import sys
import time

import db
from runlog import RunLogger
from scrapers import event_sources


def main() -> int:
    if not db.using_db():
        print("no DATABASE_URL, aborting"); return 2

    sources = [s for s in db.list_event_sources(only_active=True)
               if s["parser"] == "firecrawl"]
    print(f"Re-scraping {len(sources)} firecrawl sources", flush=True)

    run_id = db.create_run("rescrape_firecrawl",
                           f"Re-scrape {len(sources)} firecrawl sources")
    log = RunLogger(run_id)
    started = time.time()

    total_scraped = total_new = 0
    per_source: list[tuple[str, int, int]] = []
    for s in sources:
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
        per_source.append((s.get("label") or s["url"], result["count"], added))
        print(f"  {s.get('label') or s['url']:60s}  scraped={result['count']:>4}  upserted={added:>4}",
              flush=True)

    db.finish_run(run_id, status="ok")
    print(f"\nDone in {time.time() - started:.0f}s. "
          f"Scraped {total_scraped}, upserted {total_new}. "
          f"Firecrawl spend: ${log.usd:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
