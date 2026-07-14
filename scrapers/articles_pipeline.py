"""Articles pipeline — per-company probe + listing extraction + upsert.

Mirrors ``jobs_pipeline`` but for news/blog pages. Uses ``companies.news_url``
when set; otherwise probes common NL/EN news/blog paths and back-fills.
"""

from __future__ import annotations

from time import perf_counter
from urllib.parse import urljoin, urlparse

import requests

import db
from runlog import NULL

from .fetcher import fetch_html, USER_AGENT
from .listing_extractor import extract_listings

ARTICLES_LANDING_PATHS = (
    "news", "nieuws", "blog", "articles", "actueel", "pers", "press",
    "media", "updates", "insights",
    "en/news", "en/blog", "nl/nieuws", "nl/blog",
)

# Href substrings that suggest an anchor points at a specific article.
# Includes YYYY/MM date patterns commonly used in blog permalinks.
ARTICLES_LINK_HINTS = [
    "/news/", "/nieuws/", "/blog/", "/article", "/post/", "/actueel/",
    "/pers/", "/press/", "/media/", "/insight",
    "/2024/", "/2025/", "/2026/",
]

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


def scrape_articles_for_company(company: dict, logger=NULL) -> dict:
    cid = company["id"]
    name = company["name"]

    canonical = (company.get("news_url") or "").strip() or None
    website = company.get("website")
    base = _absolute(website)

    if not canonical:
        if not base:
            logger.event("articles_probe", f"{name}: no website — skipped",
                         status="error")
            db.mark_company_scraped(cid, "articles")
            return {"company_id": cid, "count": 0, "new": 0, "url": None,
                    "error": "no_website"}
        t = perf_counter()
        canonical = _probe(base, ARTICLES_LANDING_PATHS)
        logger.event(
            "articles_probe",
            f"{name}: " + (f"found {canonical}" if canonical else "no news/blog page"),
            status="ok" if canonical else "error",
            duration_ms=(perf_counter() - t) * 1000,
        )
        if canonical:
            db.update_company_fields(cid, {"news_url": canonical},
                                     source=None, status=None)
        else:
            db.mark_company_scraped(cid, "articles")
            return {"company_id": cid, "count": 0, "new": 0, "url": None,
                    "error": "no_page"}

    try:
        t = perf_counter()
        html = fetch_html(canonical, timeout=10)
        logger.event("articles_fetch",
                     f"{name}: GET {canonical} ({len(html):,} bytes)",
                     duration_ms=(perf_counter() - t) * 1000)
    except Exception as exc:  # noqa: BLE001
        logger.event("articles_fetch", f"{name}: {canonical} failed: {exc}", status="error")
        db.mark_company_scraped(cid, "articles")
        return {"company_id": cid, "count": 0, "new": 0, "url": canonical,
                "error": str(exc)}

    t = perf_counter()
    items = extract_listings(html, canonical, ARTICLES_LINK_HINTS)
    ex_ms = (perf_counter() - t) * 1000

    new_count = 0
    for it in items:
        inserted = db.upsert_article(
            company_id=cid, title=it["title"], url=it["url"],
            source_page=canonical, summary=it.get("snippet"),
        )
        if inserted:
            new_count += 1

    logger.event("articles_extract",
                 f"{name}: {len(items)} articles on page ({new_count} new)",
                 duration_ms=ex_ms)
    db.mark_company_scraped(cid, "articles")
    return {"company_id": cid, "count": len(items), "new": new_count,
            "url": canonical, "error": None}
