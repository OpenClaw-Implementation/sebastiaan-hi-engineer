"""IcyPeas company enrichment.

IcyPeas exposes ``find-companies`` but its ``query`` object doesn't accept a
free-text company-name filter on our tier (rejects with a validation error).
Fortunately ``find-people`` filtered by ``currentCompanyName.include=[name]``
returns leads whose response already contains rich company-level fields
(``lastCompanyWebsite``, ``lastCompanyUrl``, ``lastCompanyIndustry``,
``lastCompanyAddress``, ``lastCompanyDescription``, ``lastCompanySize``) —
first lead → company snapshot. That's what we use here.

Cost: 0.02 credit per result returned (per ``lead``, not per company).
"""

from __future__ import annotations

import requests

from .base import DEFAULT_TIMEOUT, envelope, env

FIND_PEOPLE_URL = env("ICYPEAS_URL", "https://app.icypeas.com/api/find-people")


def _first(*vals):
    for v in vals:
        if v not in (None, "", 0, -1):
            return v
    return None


def _fields_from_lead(lead: dict) -> dict:
    """Extract company-level fields from a find-people lead's `lastCompany*`."""
    if not isinstance(lead, dict):
        return {}
    website = _first(lead.get("lastCompanyWebsite"))
    linkedin = _first(lead.get("lastCompanyUrl"))
    industry = _first(lead.get("lastCompanyIndustry"))
    location = _first(lead.get("lastCompanyAddress"), lead.get("address"))
    if location and isinstance(location, str):
        # Address strings like "Havenstraat 52, 1271AG, HUIZEN, NH, Netherlands"
        # → keep the city + country slice at most.
        parts = [p.strip() for p in location.split(",") if p.strip()]
        if len(parts) >= 2:
            location = ", ".join(parts[-3:] if len(parts) >= 3 else parts[-2:])
    summary = _first(lead.get("lastCompanyDescription"))
    return {
        "website": website,
        "linkedin_url": linkedin,
        "linkedin_industry": industry,
        "location": location,
        "summary": summary,
    }


def enrich_company(name: str, hints: dict | None = None) -> dict:
    api_key = env("ICYPEAS_API_KEY")
    if not api_key:
        return envelope("icypeas", error="ICYPEAS_API_KEY not set")

    # Two-pass strategy:
    #   1. NL-filtered  — bias multinationals to their Dutch presence.
    #   2. Global fallback — if NL returns 0 leads, retry unfiltered so we
    #      still get *some* data for global companies with no NL LinkedIn footprint.
    def _query(with_nl: bool) -> tuple[requests.Response | None, str | None]:
        q: dict = {"currentCompanyName": {"include": [name]}}
        if with_nl:
            q["location"] = {"include": ["Netherlands", "Nederland", "Holland"]}
        try:
            r = requests.post(
                FIND_PEOPLE_URL,
                headers={"Content-Type": "application/json", "Authorization": api_key},
                json={"query": q, "pagination": {"size": 3}},
                timeout=DEFAULT_TIMEOUT,
            )
            return r, None
        except requests.exceptions.RequestException as ex:
            return None, f"network: {ex}"

    resp, err = _query(with_nl=True)
    if err:
        return envelope("icypeas", error=err)
    if resp.status_code >= 400:
        return envelope("icypeas", error=f"http {resp.status_code}: {resp.text[:200]}",
                        raw=resp.text[:400])
    try:
        data = resp.json()
    except ValueError:
        return envelope("icypeas", error="non-JSON response", raw=resp.text[:400])
    if data.get("success") is False:
        return envelope("icypeas", error=data.get("message") or "api success=false", raw=data)

    leads = data.get("leads") or data.get("items") or data.get("results") or []
    # Fallback pass without NL filter (only if the filtered pass returned nothing).
    if not leads:
        resp2, err2 = _query(with_nl=False)
        if resp2 is not None and resp2.status_code < 400:
            try:
                data2 = resp2.json()
                if data2.get("success") is not False:
                    leads2 = data2.get("leads") or data2.get("items") or data2.get("results") or []
                    if leads2:
                        leads = leads2
                        data = data2
            except ValueError:
                pass
    n = len(leads)
    credits = round(0.02 * n, 4)
    usd = round(credits * 0.019, 6)
    if not leads:
        return envelope("icypeas", error="not_found", credits=credits, usd=usd, raw=data)

    # Merge fields from up to 3 leads (any non-empty wins) — different leads at
    # the same company sometimes carry different subsets of company-level data.
    merged: dict = {}
    for lead in leads[:3]:
        for k, v in _fields_from_lead(lead).items():
            if v and not merged.get(k):
                merged[k] = v
    return envelope("icypeas", ok=bool(merged), fields=merged,
                    credits=credits, usd=usd, raw=data)
