"""Scraping Engine -- Icypeas people enrichment, keyed by company name.

Adapted from the reference Icypeas lead-gen script. The original searched by a
fixed job-title/location/company query; here the query is *adapted to the
company name* of each scraped exhibitor, so we look up the people working at
that specific supplier.

The API key is read from the ICYPEAS_API_KEY environment variable (Heroku config
var) and is never committed to the repo. Enrichment is on-demand only -- it runs
when the user clicks "Find people", so paid API credits are spent deliberately.
"""

from __future__ import annotations

import os

import requests

API_URL = "https://app.icypeas.com/api/find-people"
DEFAULT_PAGE_SIZE = 10
REQUEST_TIMEOUT = 25


def has_api_key() -> bool:
    return bool(os.environ.get("ICYPEAS_API_KEY"))


def _headers() -> dict:
    api_key = os.environ.get("ICYPEAS_API_KEY", "")
    return {"Content-Type": "application/json", "Authorization": api_key}


def build_query(company_name: str, size: int = DEFAULT_PAGE_SIZE) -> dict:
    """Adapted criteria: search people by the scraped company's name.

    We also bias toward decision-makers (the title list from the reference
    script) so the most useful contacts surface first.
    """
    return {
        "query": {
            "currentCompanyName": {"include": [company_name]},
            "currentJobTitle": {
                "include": [
                    "Owner",
                    "Founder",
                    "CEO",
                    "Managing Director",
                    "Director",
                    "Sales",
                    "Manager",
                ]
            },
        },
        "pagination": {"size": size},
    }


def find_people(company_name: str, size: int = DEFAULT_PAGE_SIZE) -> dict:
    """Run an Icypeas find-people search for a single company name.

    Returns a normalized dict the UI can render:
        {ok, company, count, leads, raw, error}
    On any failure ``ok`` is False and ``error`` carries the reason; ``raw``
    always holds whatever the API returned for debugging.
    """
    if not has_api_key():
        return {
            "ok": False,
            "company": company_name,
            "count": 0,
            "leads": [],
            "raw": None,
            "error": "ICYPEAS_API_KEY is not set on the server.",
        }

    try:
        resp = requests.post(
            API_URL,
            headers=_headers(),
            json=build_query(company_name, size),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        return {
            "ok": False,
            "company": company_name,
            "count": 0,
            "leads": [],
            "raw": None,
            "error": f"Request failed: {exc}",
        }

    try:
        data = resp.json()
    except ValueError:
        return {
            "ok": False,
            "company": company_name,
            "count": 0,
            "leads": [],
            "raw": resp.text[:2000],
            "error": f"Non-JSON response (HTTP {resp.status_code}).",
        }

    if resp.status_code >= 400 or data.get("success") is False:
        return {
            "ok": False,
            "company": company_name,
            "count": 0,
            "leads": [],
            "raw": data,
            "error": data.get("message") or f"API error (HTTP {resp.status_code}).",
        }

    # The reference script reads results from data["leads"]; some Icypeas
    # responses nest them under "items"/"results", so we look in each.
    leads = data.get("leads") or data.get("items") or data.get("results") or []
    return {
        "ok": True,
        "company": company_name,
        "count": len(leads),
        "leads": leads,
        "raw": data,
        "error": None,
    }
