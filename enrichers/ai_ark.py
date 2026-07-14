"""AI Ark company enrichment — developer-portal/v1/companies endpoint."""

from __future__ import annotations

import requests

from .base import DEFAULT_TIMEOUT, envelope, env

API_URL = env("AI_ARK_COMPANIES_URL",
              "https://api.ai-ark.com/api/developer-portal/v1/companies")


def _pick(d: dict, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _fields(c: dict) -> dict:
    if not isinstance(c, dict):
        return {}
    loc = _pick(c, "location", "headquarters", "hq", "address", "city")
    if isinstance(loc, dict):
        loc = ", ".join([loc[k] for k in ("city", "region", "country") if loc.get(k)]) or None
    specs = c.get("specialities") or c.get("specialties") or []
    if isinstance(specs, list):
        specs = ", ".join(str(s) for s in specs if s) or None
    return {
        "website": _pick(c, "website", "domain", "url"),
        "linkedin_url": _pick(c, "linkedin_url", "linkedin", "linkedinUrl"),
        "linkedin_industry": _pick(c, "industry"),
        "summary": _pick(c, "description", "about", "summary", "bio"),
        "specialities": specs,
        "location": loc if isinstance(loc, str) else None,
        "tel": _pick(c, "phone", "telephone"),
    }


def enrich_company(name: str, hints: dict | None = None) -> dict:
    api_key = env("AI_ARK_API_KEY")
    if not api_key:
        return envelope("ai_ark", error="AI_ARK_API_KEY not set")

    # AI Ark people-search uses filter arrays; the companies endpoint mirrors this.
    body = {"names": [name], "keywords": [name], "size": 3}
    try:
        resp = requests.post(
            API_URL,
            headers={"Content-Type": "application/json", "X-TOKEN": api_key},
            json=body,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        return envelope("ai_ark", error=f"network: {e}")

    if resp.status_code >= 400:
        return envelope("ai_ark", error=f"http {resp.status_code}: {resp.text[:200]}",
                        raw=resp.text[:400])

    try:
        data = resp.json()
    except ValueError:
        return envelope("ai_ark", error="non-JSON response", raw=resp.text[:400])

    items = (data.get("companies") or data.get("results") or data.get("data")
             or data.get("items") or [])
    if not items:
        return envelope("ai_ark", error="not_found", raw=data)

    fields = _fields(items[0])
    return envelope("ai_ark", ok=bool(fields), fields=fields, raw=data)
