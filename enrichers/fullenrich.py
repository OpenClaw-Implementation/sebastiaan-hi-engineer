"""FullEnrich company enrichment — companies/search endpoint."""

from __future__ import annotations

import requests

from .base import DEFAULT_TIMEOUT, envelope, env

API_URL = env("FULLENRICH_COMPANIES_URL", "https://app.fullenrich.com/api/v2/companies/search")


def _pick(d: dict, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _fields(c: dict) -> dict:
    if not isinstance(c, dict):
        return {}
    hq = c.get("headquarters") or c.get("hq") or {}
    if isinstance(hq, dict):
        loc = ", ".join([hq[k] for k in ("city", "region", "country") if hq.get(k)]) or None
    else:
        loc = hq or None
    specs = c.get("specialities") or c.get("specialties") or []
    if isinstance(specs, list):
        specs = ", ".join(str(s) for s in specs if s) or None
    return {
        "website": _pick(c, "website", "domain"),
        "linkedin_url": _pick(c, "linkedin_url", "linkedinUrl", "linkedin"),
        "linkedin_industry": _pick(c, "industry", "linkedin_industry"),
        "summary": _pick(c, "description", "about", "summary"),
        "specialities": specs,
        "location": loc,
        "tel": _pick(c, "phone", "telephone"),
    }


def enrich_company(name: str, hints: dict | None = None) -> dict:
    api_key = env("FULLENRICH_API_KEY")
    if not api_key:
        return envelope("fullenrich", error="FULLENRICH_API_KEY not set")

    body = {"limit": 3, "company_names": [{"value": name}]}
    domain = (hints or {}).get("website") or (hints or {}).get("domain")
    if domain:
        body["company_domains"] = [{"value": domain}]

    try:
        resp = requests.post(
            API_URL,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {api_key}"},
            json=body,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        return envelope("fullenrich", error=f"network: {e}")

    if resp.status_code >= 400:
        return envelope("fullenrich", error=f"http {resp.status_code}: {resp.text[:200]}",
                        raw=resp.text[:400])

    try:
        data = resp.json()
    except ValueError:
        return envelope("fullenrich", error="non-JSON response", raw=resp.text[:400])

    items = data.get("data") or data.get("results") or data.get("companies") or []
    credits = float((data.get("metadata") or {}).get("credits", 0) or 0)
    if not items:
        return envelope("fullenrich", error="not_found", credits=credits, raw=data)

    fields = _fields(items[0])
    return envelope("fullenrich", ok=bool(fields), fields=fields,
                    credits=credits, raw=data)
