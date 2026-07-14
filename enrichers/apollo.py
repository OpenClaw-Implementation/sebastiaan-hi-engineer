"""Apollo.io company enrichment.

Two endpoints, tried in order:
  1. organizations/enrich?domain=<d>  — needs a domain hint from an earlier leg.
  2. mixed_companies/search           — name-only fallback.
Both bill per call on the paid tier, so this leg only fires last in the cascade.
"""

from __future__ import annotations

import requests

from .base import DEFAULT_TIMEOUT, envelope, env

ENRICH_URL = env("APOLLO_ORG_ENRICH_URL",
                 "https://api.apollo.io/api/v1/organizations/enrich")
SEARCH_URL = env("APOLLO_ORG_SEARCH_URL",
                 "https://api.apollo.io/api/v1/mixed_companies/search")


def _pick(d: dict, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _fields(org: dict) -> dict:
    if not isinstance(org, dict):
        return {}
    hq = ", ".join([org.get(k) for k in ("city", "state", "country") if org.get(k)]) or None
    if not hq:
        addr = org.get("primary_address") or org.get("headquarters_address")
        if isinstance(addr, str):
            hq = addr
    specs = org.get("keywords") or org.get("specialties") or []
    if isinstance(specs, list):
        specs = ", ".join(str(s) for s in specs[:20] if s) or None
    return {
        "website": _pick(org, "website_url", "primary_domain", "domain", "website"),
        "linkedin_url": _pick(org, "linkedin_url"),
        "linkedin_industry": _pick(org, "industry"),
        "summary": _pick(org, "short_description", "description"),
        "specialities": specs,
        "location": hq,
        "tel": _pick(org, "phone", "primary_phone", "sanitized_phone"),
    }


def _via_enrich(api_key: str, domain: str) -> dict:
    try:
        resp = requests.post(
            ENRICH_URL,
            headers={"Content-Type": "application/json",
                     "Cache-Control": "no-cache", "X-Api-Key": api_key},
            params={"domain": domain},
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        return envelope("apollo", error=f"enrich network: {e}")
    if resp.status_code >= 400:
        return envelope("apollo", error=f"enrich http {resp.status_code}: {resp.text[:200]}",
                        raw=resp.text[:400])
    try:
        data = resp.json()
    except ValueError:
        return envelope("apollo", error="enrich non-JSON", raw=resp.text[:400])
    org = data.get("organization") or {}
    if not org:
        return envelope("apollo", error="no organization in enrich response",
                        credits=1.0, usd=0.05, raw=data)
    return envelope("apollo", ok=True, fields=_fields(org),
                    credits=1.0, usd=0.05, raw=data)


def _via_search(api_key: str, name: str) -> dict:
    body = {"q_organization_name": name, "page": 1, "per_page": 3}
    try:
        resp = requests.post(
            SEARCH_URL,
            headers={"Content-Type": "application/json",
                     "Cache-Control": "no-cache", "X-Api-Key": api_key},
            json=body,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        return envelope("apollo", error=f"search network: {e}")
    if resp.status_code >= 400:
        return envelope("apollo", error=f"search http {resp.status_code}: {resp.text[:200]}",
                        raw=resp.text[:400])
    try:
        data = resp.json()
    except ValueError:
        return envelope("apollo", error="search non-JSON", raw=resp.text[:400])
    orgs = data.get("organizations") or data.get("accounts") or []
    if not orgs:
        return envelope("apollo", error="not_found", credits=1.0, usd=0.05, raw=data)
    return envelope("apollo", ok=True, fields=_fields(orgs[0]),
                    credits=1.0, usd=0.05, raw=data)


def enrich_company(name: str, hints: dict | None = None) -> dict:
    api_key = env("APOLLO_API_KEY")
    if not api_key:
        return envelope("apollo", error="APOLLO_API_KEY not set")

    domain = (hints or {}).get("website") or (hints or {}).get("domain")
    if domain:
        # Strip protocol/paths so `domain=` is just the host
        d = domain.replace("https://", "").replace("http://", "").split("/")[0]
        if d:
            r = _via_enrich(api_key, d)
            if r["ok"]:
                return r
    return _via_search(api_key, name)
