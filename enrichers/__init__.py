"""Company-enrichment cascade.

Given a company name, walks a chain of third-party providers (IcyPeas →
FullEnrich → AI Ark → Apollo, cheapest first) and returns the first hit's
normalised field map. Each attempt writes one row to ``company_enrichment_log``
and one live event to the Logs+Costs stream via ``RunLogger``.

Envelope every provider returns:

    {
        "ok":       bool,           # True if any field was recovered
        "source":   "icypeas" | "fullenrich" | "ai_ark" | "apollo",
        "fields":   {name: value},  # subset of ENRICHABLE_FIELDS (db.py)
        "credits":  float,          # provider units burned
        "usd":      float,
        "error":    str | None,     # populated on failure / miss
        "raw":      any,            # raw response (bounded slice)
    }
"""
