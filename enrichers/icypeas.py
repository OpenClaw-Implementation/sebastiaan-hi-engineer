"""IcyPeas company enrichment — find-companies endpoint."""

from __future__ import annotations

import requests

from .base import DEFAULT_TIMEOUT, envelope, env

API_URL = env("ICYPEAS_COMPANIES_URL", "https://app.icypeas.com/api/find-companies")


def _pick(d: dict, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _fields_from_company(c: dict) -> dict:
    """Map IcyPeas company record → the enrichable-fields dict."""
    if not isinstance(c, dict):
        return {}
    location = _pick(c, "address", "location", "headquarters", "hq")
    if isinstance(location, dict):
        parts = [location.get(k) for k in ("city", "region", "country") if location.get(k)]
        location = ", ".join(parts) if parts else None

    return {
        "website": _pick(c, "website", "domain", "companyDomain", "companyWebsite"),
        "linkedin_url": _pick(c, "linkedinUrl", "linkedin_url", "linkedinCompanyUrl", "url"),
        "linkedin_industry": _pick(c, "industry", "linkedinIndustry"),
        "summary": _pick(c, "description", "about", "summary"),
        "specialities": ", ".join(c["specialities"]) if isinstance(c.get("specialities"), list) else _pick(c, "specialities", "specialty"),
        "location": location if isinstance(location, str) else None,
        "tel": _pick(c, "phone", "telephone", "tel"),
    }


def enrich_company(name: str, hints: dict | None = None) -> dict:
    api_key = env("ICYPEAS_API_KEY")
    if not api_key:
        return envelope("icypeas", error="ICYPEAS_API_KEY not set")

    body = {
        "query": {"companyName": {"include": [name]}},
        "pagination": {"size": 3},
    }
    try:
        resp = requests.post(
            API_URL,
            headers={"Content-Type": "application/json", "Authorization": api_key},
            json=body,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        return envelope("icypeas", error=f"network: {e}")

    if resp.status_code >= 400:
        return envelope("icypeas", error=f"http {resp.status_code}: {resp.text[:200]}",
                        raw=resp.text[:400])

    try:
        data = resp.json()
    except ValueError:
        return envelope("icypeas", error="non-JSON response", raw=resp.text[:400])

    if data.get("success") is False:
        return envelope("icypeas", error=data.get("message") or "api success=false", raw=data)

    # IcyPeas nests results under one of these keys depending on tier.
    items = data.get("companies") or data.get("items") or data.get("results") or []
    if not items:
        # Charged even on miss (per IcyPeas docs).
        return envelope("icypeas", error="not_found", credits=0.02, usd=0.02 * 0.019, raw=data)

    fields = _fields_from_company(items[0])
    credits = round(0.02 * len(items), 4)
    return envelope("icypeas", ok=bool(fields), fields=fields,
                    credits=credits, usd=round(credits * 0.019, 6), raw=data)
