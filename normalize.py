"""Normalize raw scrape output into the ``companies`` directory table.

Called after every exhibitor scrape (Module 01 step 02 in the proposal): reads
the JSONB blob from ``app_cache['exhibitors']`` and upserts each entry into
``companies``. Idempotent — safe to re-run; existing enrichment fields are
preserved because ``upsert_company_from_exhibitor`` only touches the columns
the exhibitor scrape provides.
"""

from __future__ import annotations

import db


def normalize_exhibitors(exhibitors_blob: dict | None = None) -> dict:
    """Upsert every exhibitor from the given (or cached) scrape blob.

    Returns {"inserted_or_updated": N, "skipped": M}.
    """
    if exhibitors_blob is None:
        exhibitors_blob = db.cache_get("exhibitors", default={})
    exhibitors = (exhibitors_blob or {}).get("exhibitors", [])
    ok = skipped = 0
    for ex in exhibitors:
        if not ex.get("name"):
            skipped += 1
            continue
        cid = db.upsert_company_from_exhibitor(ex)
        if cid is None:
            skipped += 1
        else:
            ok += 1
    return {"inserted_or_updated": ok, "skipped": skipped, "total": len(exhibitors)}
