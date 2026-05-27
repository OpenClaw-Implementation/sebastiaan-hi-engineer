"""Per-action cost model -- the single source of truth for the Logs+Costs tab.

Today the only paid dependency is Icypeas, and we use its cheap operations:
  * find-people *count*  -> free
  * find-people *results* -> 0.02 credit each
Direct-HTTP scraping and Supabase writes are free. Email search/verification and
Claude AI summarization (Content Engine Module 02) slot in here when built.

Credit -> USD rate is configurable: ICYPEAS_USD_PER_CREDIT (default 0.019, the
Icypeas Basic-plan rate; lower on higher tiers).
Sources: https://api-doc.icypeas.com/how-works/credit-cost/ , icypeas.com/pricing
"""

from __future__ import annotations

import os

USD_PER_CREDIT = float(os.environ.get("ICYPEAS_USD_PER_CREDIT", "0.019"))

# action -> (kwarg holding the unit count, credits charged per unit)
_CREDIT_RULES: dict[str, tuple[str, float]] = {
    "icypeas_find_people": ("results", 0.02),
    "icypeas_find_companies": ("results", 0.02),
    "icypeas_email_search": ("emails", 1.0),
    "icypeas_email_verify": ("emails", 0.1),
    "icypeas_reverse_lookup": ("profiles", 10.0),
}


def cost_for(action: str, **kw) -> tuple[float, float]:
    """Return (credits, usd) for an action. Free/unknown actions cost nothing.

    Pass the unit count for paid actions (e.g. results=10), or an explicit
    ``credits=`` override (e.g. for token-based AI costs computed by the caller).
    """
    credits = 0.0
    rule = _CREDIT_RULES.get(action)
    if rule:
        unit_key, per_unit = rule
        credits = per_unit * float(kw.get(unit_key, 0) or 0)
    if "credits" in kw and kw["credits"] is not None:
        credits = float(kw["credits"])
    return round(credits, 4), round(credits * USD_PER_CREDIT, 6)
