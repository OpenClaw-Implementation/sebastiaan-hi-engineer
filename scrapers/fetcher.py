"""Thin HTTP fetch helper -- direct cURL-style requests, no Firecrawl/Apify.

A single browser-like User-Agent and sane timeouts are shared by every scraper
so the behaviour against source sites is consistent.
"""

from __future__ import annotations

import requests

# A real browser UA -- several of the source portals 403 a bare python-requests UA.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 25  # seconds -- stay well under Heroku's 30s router timeout


def fetch_html(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """GET a URL and return decoded HTML text. Raises on HTTP error."""
    resp = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "nl,en;q=0.8",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    # Let requests guess the encoding from headers/content when not declared.
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text
