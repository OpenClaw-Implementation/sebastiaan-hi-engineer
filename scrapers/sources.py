"""Source URLs, derived from EPCM Guide_Netherlands.xlsx.

EVENT_SOURCES -- the unique URLs from the Companies sheet, column "EVENT SOURCE".
                 In the workbook all 112 rows point at the same exhibitor list,
                 so there is exactly one unique URL. Kept as a list (deduped,
                 capped at 50) so additional event sources can be added later.

MEDIA_SOURCES -- the "Media" block (rows 2-12) from the Sources sheet. These are
                 the industrial / food portals scraped by the Content Engine.
                 Duplicates from the sheet are removed, order preserved.
"""

from __future__ import annotations

# --- Scraping Engine: Companies sheet -> "EVENT SOURCE" (first 50 unique) ---
EVENT_SOURCES: list[str] = [
    "https://food-tech-event.nl/nl/exposantenlijst/",
]

# --- Content Engine: Sources sheet -> "Media" block ---
MEDIA_SOURCES: list[str] = [
    "https://installatieenbouw.nl/bedrijven/",
    "https://vakbladvoedingsindustrie.nl/en/leveranciers",
    "https://industriebouw-online.nl/bedrijvenindex/",
    "https://www.processcontrol.nl/bedrijvenwijzer/",
    "https://solidsprocessing.nl/companyprofile/?expertise=&search=&paging=",
    "https://fluidsprocessing.nl/leverancier/?expertise=&search=&paging=",
    "https://www.industrielinqs.nl/partners-leden/",
    "https://regiobedrijf.nl/industrie/",
    "https://tim.pmg.nl/nl/leveranciers/?ct=&pd=&lc=&kw=&lt=",
]


def dedupe_keep_order(urls: list[str], cap: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        u = u.strip()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
            if cap and len(out) >= cap:
                break
    return out
