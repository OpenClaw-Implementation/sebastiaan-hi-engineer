"""AI Ark company enrichment — developer-portal/v1/companies endpoint.

Response is Spring-paginated: ``{content: [...], pageable, totalElements, ...}``.
Each result is a rich company record with sub-blocks: ``summary`` (name,
description, industry, staff, logo), ``link`` (website, LinkedIn), ``contact``
(phone, email), ``location``, ``industries``, ``technologies``, ``keywords``.

AI Ark's people-search returns loose matches (a query for "4FOOD Software"
returned Tata Group as first result). We enforce a name-match guard so wrong
companies don't overwrite the row.
"""

from __future__ import annotations

import re

import requests

from .base import DEFAULT_TIMEOUT, envelope, env

API_URL = env("AI_ARK_COMPANIES_URL",
              "https://api.ai-ark.com/api/developer-portal/v1/companies")


def _norm(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _name_matches(candidate: str | None, requested: str) -> bool:
    a, b = _norm(candidate), _norm(requested)
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    # Compare first two words normalised
    aw = _norm(" ".join(candidate.split()[:2])) if candidate else ""
    bw = _norm(" ".join(requested.split()[:2])) if requested else ""
    return bool(aw) and aw == bw


def _fields_from_hit(hit: dict) -> dict:
    summary = hit.get("summary") or {}
    link = hit.get("link") or {}
    contact = hit.get("contact") or {}
    location = hit.get("location") or {}
    industries = hit.get("industries") or []
    keywords = hit.get("keywords") or []

    loc = None
    if isinstance(location, dict):
        parts = [location.get(k) for k in ("city", "region", "country") if location.get(k)]
        loc = ", ".join(str(p) for p in parts) or None
    elif isinstance(location, str):
        loc = location

    industry = summary.get("industry")
    if not industry and industries:
        industry = industries[0] if isinstance(industries[0], str) else (
            industries[0].get("name") if isinstance(industries[0], dict) else None
        )

    specs = None
    if keywords:
        specs = ", ".join(str(k) for k in keywords[:20] if k) or None

    return {
        "website": link.get("website") or link.get("url"),
        "linkedin_url": link.get("linkedin") or link.get("linkedin_url"),
        "linkedin_industry": industry,
        "summary": summary.get("description"),
        "specialities": specs,
        "location": loc,
        "tel": (contact.get("phone") or contact.get("telephone")) if isinstance(contact, dict) else None,
        "email": contact.get("email") if isinstance(contact, dict) else None,
    }


def enrich_company(name: str, hints: dict | None = None) -> dict:
    api_key = env("AI_ARK_API_KEY")
    if not api_key:
        return envelope("ai_ark", error="AI_ARK_API_KEY not set")

    body = {"names": [name], "keywords": [name], "size": 5}
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

    hits = data.get("content") or []
    if not hits:
        return envelope("ai_ark", error="not_found", raw=data)

    # Name-match guard: find the first hit whose summary.name is close to `name`.
    winner = None
    for h in hits:
        cand = (h.get("summary") or {}).get("name")
        if _name_matches(cand, name):
            winner = h
            break
    if winner is None:
        return envelope(
            "ai_ark",
            error=f"no name match (top result: {(hits[0].get('summary') or {}).get('name','?')!r})",
            raw={"totalElements": data.get("totalElements"), "first_name": (hits[0].get("summary") or {}).get("name")},
        )

    fields = _fields_from_hit(winner)
    return envelope("ai_ark", ok=bool(fields), fields=fields, raw=data)
