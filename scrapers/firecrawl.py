"""Thin Firecrawl client — POST /v1/scrape returning rendered HTML.

Only used by the ``firecrawl`` parser in ``event_sources.py`` — the direct
cURL scrapers stay untouched. Free tier gives 500 credits; each scrape is
1 credit. We keep the request options conservative (waitFor + a couple of
scrolls) to reliably render lazy-loaded content without burning long dyno time.
"""

from __future__ import annotations

import os

import requests

API_URL = os.environ.get("FIRECRAWL_URL", "https://api.firecrawl.dev/v1/scrape")
DEFAULT_TIMEOUT = 90  # seconds — Firecrawl often takes 5-30 s per page

DEFAULT_ACTIONS = [
    {"type": "wait", "milliseconds": 1500},
    {"type": "scroll", "direction": "down"},
    {"type": "wait", "milliseconds": 2000},
    {"type": "scroll", "direction": "down"},
    {"type": "wait", "milliseconds": 1500},
]


def has_api_key() -> bool:
    return bool(os.environ.get("FIRECRAWL_API_KEY"))


def scrape(url: str, wait_ms: int = 5000, use_actions: bool = True,
           timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Return ``{ok, html, error, credits_charged, raw}`` — cascade-style envelope.

    ``credits_charged`` is hard-coded to 1 per successful call (Firecrawl's
    current pricing). Failure paths return 0.
    """
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        return {"ok": False, "html": "", "error": "FIRECRAWL_API_KEY not set",
                "credits_charged": 0, "raw": None}

    body: dict = {"url": url, "formats": ["html"], "waitFor": wait_ms}
    if use_actions:
        body["actions"] = DEFAULT_ACTIONS

    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json=body, timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "html": "", "error": f"network: {exc}",
                "credits_charged": 0, "raw": None}

    if resp.status_code >= 400:
        return {"ok": False, "html": "",
                "error": f"http {resp.status_code}: {resp.text[:200]}",
                "credits_charged": 0, "raw": resp.text[:400]}
    try:
        data = resp.json()
    except ValueError:
        return {"ok": False, "html": "", "error": "non-JSON response",
                "credits_charged": 0, "raw": resp.text[:400]}

    if not data.get("success"):
        return {"ok": False, "html": "", "error": data.get("error") or "not success",
                "credits_charged": 0, "raw": data}

    html = (data.get("data") or {}).get("html") or ""
    return {"ok": True, "html": html, "error": None,
            "credits_charged": 1, "raw": data}
