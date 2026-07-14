"""Company-enrichment cascade orchestrator.

For each pending company:
  1. Walk providers in order (IcyPeas → FullEnrich → AI Ark → Apollo).
  2. Merge fields from every hit — first-hit-wins per field, but later legs can
     fill in blanks the earlier legs missed (this is more useful than pure
     first-hit-wins because no single provider covers all 10 fields).
  3. After the API cascade, if we now know a website, probe common subpaths
     for News/Jobs.
  4. Log every leg to company_enrichment_log AND stream it via RunLogger so the
     Logs+Costs tab shows steps + costs live.
  5. Update the companies row atomically.
"""

from __future__ import annotations

from time import perf_counter

import db

from . import ai_ark, apollo, fullenrich, icypeas, site_probe

# Cheapest → most expensive. Each is (name, module, cost_action).
PROVIDERS = [
    ("icypeas", icypeas, "icypeas_find_companies"),
    ("fullenrich", fullenrich, "fullenrich_company"),
    ("ai_ark", ai_ark, "ai_ark_company"),
    ("apollo", apollo, "apollo_organization"),
]


def _merge_missing(current: dict, new: dict) -> dict:
    """Return the subset of `new` whose keys aren't already set in `current`."""
    return {k: v for k, v in new.items() if v and not current.get(k)}


def enrich_one(company: dict, logger=None) -> dict:
    """Run the cascade for a single companies row (dict from db.get_company).

    Returns a small report: {source, attempts, hit_sources, final_fields, credits, usd}.
    """
    company_id = company["id"]
    name = company["name"]

    # Seed with whatever the row already has, so we don't re-request known fields.
    known = {
        "website": company.get("website"),
        "linkedin_url": company.get("linkedin_url"),
        "linkedin_industry": company.get("linkedin_industry"),
        "summary": company.get("summary"),
        "specialities": company.get("specialities"),
        "location": company.get("location"),
        "tel": company.get("tel"),
        "email": company.get("email"),
        "news_url": company.get("news_url"),
        "jobs_url": company.get("jobs_url"),
    }
    collected: dict = {k: v for k, v in known.items() if v}
    first_hit_source: str | None = None
    hit_sources: list[str] = []
    total_credits = 0.0
    total_usd = 0.0

    for attempt_no, (src, module, action) in enumerate(PROVIDERS, start=1):
        t = perf_counter()
        env = module.enrich_company(name, hints=collected)
        duration_ms = int((perf_counter() - t) * 1000)

        # Log to DB audit table (per-attempt row).
        db.log_company_enrichment(
            company_id=company_id, attempt_no=attempt_no, source=src,
            success=bool(env["ok"]), duration_ms=duration_ms,
            credits=env["credits"], usd=env["usd"],
            error_message=env["error"], details={"fields": env["fields"], "raw": env["raw"]},
        )
        # Stream to Logs+Costs tab.
        if logger is not None:
            detail = f"{name}: " + (
                "no fields" if not env["ok"]
                else ", ".join(env["fields"].keys())
            )
            if env["error"]:
                detail = f"{name}: {env['error']}"
            logger.event(
                action, detail,
                status="ok" if env["ok"] else "error",
                duration_ms=duration_ms,
                credits=env["credits"],  # explicit override -- provider-specific
            )
        total_credits += env["credits"]
        total_usd += env["usd"]

        if env["ok"]:
            hit_sources.append(src)
            if first_hit_source is None:
                first_hit_source = src
            newly = _merge_missing(collected, env["fields"])
            collected.update(newly)
            # Early-exit: once we have the two anchor fields (website +
            # linkedin_url), skip the remaining paid legs. Apollo in particular
            # bills 1 credit per call regardless of outcome, so short-circuiting
            # after a good IcyPeas hit saves ~$0.05 per company.
            if collected.get("website") and collected.get("linkedin_url"):
                break
            # Also stop if every enrichable field is now filled.
            if all(collected.get(k) for k in db.ENRICHABLE_FIELDS):
                break

    # Post-API website subpath probe for News/Jobs.
    if collected.get("website") and (not collected.get("news_url") or not collected.get("jobs_url")):
        t = perf_counter()
        probed = site_probe.probe_site(collected["website"])
        duration_ms = int((perf_counter() - t) * 1000)
        newly = _merge_missing(collected, probed)
        collected.update(newly)
        db.log_company_enrichment(
            company_id=company_id, attempt_no=len(PROVIDERS) + 1, source="site_probe",
            success=bool(newly), duration_ms=duration_ms,
            credits=0.0, usd=0.0,
            error_message=None if newly else "no news/jobs paths responded",
            details={"fields": newly},
        )
        if logger is not None:
            logger.event("site_probe",
                         f"{name}: " + (", ".join(newly.keys()) if newly else "no news/jobs"),
                         status="ok" if newly else "error",
                         duration_ms=duration_ms)

    # Persist to the companies row.
    only_new = {k: v for k, v in collected.items() if v and not known.get(k)}
    if only_new:
        db.update_company_fields(
            company_id, only_new,
            source=(first_hit_source + "_auto") if first_hit_source else "cascade_auto",
            status="enriched",
        )
    else:
        # Nothing new — mark terminal so we don't retry this row on future bulk runs.
        db.update_company_fields(company_id, {}, source=None, status="terminal")

    return {
        "name": name,
        "hit_sources": hit_sources,
        "filled_fields": list(only_new.keys()),
        "credits": round(total_credits, 4),
        "usd": round(total_usd, 6),
        "status": "enriched" if only_new else "terminal",
    }
