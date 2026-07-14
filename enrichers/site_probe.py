"""Probe a company website for News + Jobs subpages.

Once the API cascade has resolved ``website``, this pings a handful of common
NL/EN paths (``/nieuws``, ``/vacatures``, ``/news``, ``/careers`` …). First
2xx response for each category wins. Purely HTTP GETs — no cost, no third-party.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests

from .base import user_agent

NEWS_PATHS = ("nieuws", "news", "media", "blog", "pers", "press", "actueel")
JOBS_PATHS = ("vacatures", "werken-bij", "careers", "jobs", "carriere", "career")

TIMEOUT = 6


def _absolute(website: str) -> str | None:
    if not website:
        return None
    website = website.strip()
    if not website.startswith(("http://", "https://")):
        website = "https://" + website
    p = urlparse(website)
    if not p.netloc:
        return None
    return f"{p.scheme}://{p.netloc}"


def _try(base: str, paths: tuple[str, ...]) -> str | None:
    for p in paths:
        url = urljoin(base + "/", p)
        try:
            r = requests.get(url, headers={"User-Agent": user_agent()},
                             timeout=TIMEOUT, allow_redirects=True)
            if 200 <= r.status_code < 300 and len(r.content) > 500:
                return r.url  # follow-through URL after redirects
        except requests.exceptions.RequestException:
            continue
    return None


def probe_site(website: str) -> dict:
    """Return {'news_url': ..., 'jobs_url': ...} — either key may be missing."""
    base = _absolute(website)
    if not base:
        return {}
    fields: dict = {}
    news = _try(base, NEWS_PATHS)
    if news:
        fields["news_url"] = news
    jobs = _try(base, JOBS_PATHS)
    if jobs:
        fields["jobs_url"] = jobs
    return fields
