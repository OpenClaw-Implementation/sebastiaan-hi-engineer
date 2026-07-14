"""Jobs pipeline — per-company probe + listing extraction + upsert.

Uses the company's ``jobs_url`` when we already know it (from an earlier site
probe); otherwise probes a handful of common NL/EN paths and back-fills the
first that responds 2xx. Then fetches, extracts anchor-based listings whose
href looks like a job posting URL, and upserts into ``jobs``.
"""

from __future__ import annotations

from time import perf_counter
from urllib.parse import urljoin, urlparse

import requests

import db
from runlog import NULL

from .fetcher import fetch_html, USER_AGENT
from .listing_extractor import extract_listings

# Landing pages to try in order (case-insensitive substring, but we build the
# actual URL with normal casing).
JOBS_LANDING_PATHS = (
    "jobs", "careers", "vacatures", "werken-bij", "carriere",
    "vacancies", "join-us", "join",
    "en/jobs", "en/careers", "nl/vacatures", "over-ons/vacatures",
)

# Href substrings that suggest an anchor is a specific job posting (not a
# category link, not the "back to careers" nav item).
JOBS_LINK_HINTS = ["/job", "/career", "/vacature", "/vacancy",
                   "/position", "/opening", "boards.greenhouse.io", "lever.co",
                   "workable.com", "workday", "smartrecruiters"]

PROBE_TIMEOUT = 5


def _absolute(website: str | None) -> str | None:
    if not website:
        return None
    website = website.strip()
    if not website.startswith(("http://", "https://")):
        website = "https://" + website
    p = urlparse(website)
    if not p.netloc:
        return None
    return f"{p.scheme}://{p.netloc}"


def _probe(base: str, paths: tuple[str, ...]) -> str | None:
    """Return the first path that returns 2xx (URL after redirects), else None."""
    for path in paths:
        url = urljoin(base + "/", path)
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT},
                             timeout=PROBE_TIMEOUT, allow_redirects=True)
            if 200 <= r.status_code < 300 and len(r.content) > 500:
                return r.url
        except requests.exceptions.RequestException:
            continue
    return None


def scrape_jobs_for_company(company: dict, logger=NULL) -> dict:
    """Run the jobs pipeline for one company. Returns a per-company report dict."""
    cid = company["id"]
    name = company["name"]

    canonical = (company.get("jobs_url") or "").strip() or None
    website = company.get("website")
    base = _absolute(website)

    # If we don't have a canonical page yet, probe.
    if not canonical:
        if not base:
            logger.event("jobs_probe", f"{name}: no website — skipped",
                         status="error")
            db.mark_company_scraped(cid, "jobs")
            return {"company_id": cid, "count": 0, "new": 0, "url": None,
                    "error": "no_website"}
        t = perf_counter()
        canonical = _probe(base, JOBS_LANDING_PATHS)
        logger.event(
            "jobs_probe",
            f"{name}: " + (f"found {canonical}" if canonical else "no jobs page"),
            status="ok" if canonical else "error",
            duration_ms=(perf_counter() - t) * 1000,
        )
        if canonical:
            # Back-fill the discovered URL so future runs skip the probe.
            db.update_company_fields(cid, {"jobs_url": canonical},
                                     source=None, status=None)
        else:
            db.mark_company_scraped(cid, "jobs")
            return {"company_id": cid, "count": 0, "new": 0, "url": None,
                    "error": "no_page"}

    # Fetch the landing page.
    try:
        t = perf_counter()
        html = fetch_html(canonical, timeout=10)
        logger.event("jobs_fetch",
                     f"{name}: GET {canonical} ({len(html):,} bytes)",
                     duration_ms=(perf_counter() - t) * 1000)
    except Exception as exc:  # noqa: BLE001
        logger.event("jobs_fetch", f"{name}: {canonical} failed: {exc}", status="error")
        db.mark_company_scraped(cid, "jobs")
        return {"company_id": cid, "count": 0, "new": 0, "url": canonical,
                "error": str(exc)}

    # Extract job listings by href hint.
    t = perf_counter()
    items = extract_listings(html, canonical, JOBS_LINK_HINTS)
    ex_ms = (perf_counter() - t) * 1000

    new_count = 0
    for it in items:
        inserted = db.upsert_job(
            company_id=cid, title=it["title"], url=it["url"],
            source_page=canonical,
        )
        if inserted:
            new_count += 1

    logger.event("jobs_extract",
                 f"{name}: {len(items)} jobs on page ({new_count} new)",
                 duration_ms=ex_ms)
    db.mark_company_scraped(cid, "jobs")
    return {"company_id": cid, "count": len(items), "new": new_count,
            "url": canonical, "error": None}
