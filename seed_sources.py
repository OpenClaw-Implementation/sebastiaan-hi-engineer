"""One-off: seed the event source URLs. Idempotent — reruns just refresh
labels/parsers without touching last_scraped_at.

    heroku run python seed_sources.py -a hi-engineer-app

Ships 26 sources across 4 parsers:
  * foodtech    (3): food-tech-event, mtconference, automation-xperience
  * easyfairs   (11): 5 Easyfairs deep-industry (empack et al) + aqua/pork/bakkers/
                     groenesector (Easyfairs) + rematec/interclean (same shape)
  * firecrawl   (9):  provada + 8 JS-only Jaarbeurs/Ahoy events
  * unsupported (3): safetyevent, vakbeursenergie, LinkedIn
"""

from __future__ import annotations

import sys

import db

DEFAULT_SOURCES = [
    # url, label, parser
    #
    # --- foodtech parser (data-component="card-introduce") ---
    ("https://food-tech-event.nl/nl/exposantenlijst/",
     "Food Tech Event", "foodtech"),
    ("https://mtconference.nl/nl/exposantenlijst/",
     "MT Conference", "foodtech"),
    # 104 card-introduce cards verified on probe (2026-07-16).
    ("https://automation-xperience.nl/en/exhibitor-list/",
     "Automation Xperience (Apr 2027, Gorinchem)", "foodtech"),

    # --- easyfairs parser (SSR anchors, URL-slug names) ---
    ("https://www.empack.nl/exhibitors/",
     "Empack (Easyfairs)", "easyfairs"),
    ("https://www.rotterdamprocessingweek.nl/exhibitors/",
     "Rotterdam Processing Week (Easyfairs)", "easyfairs"),
    ("https://www.mrprocessing.nl/exhibitors/?stands%5BrefinementList%5D%5BeventName%5D%5B0%5D=M%2BR%20Rotterdam%202027",
     "M+R Rotterdam 2027 (Easyfairs)", "easyfairs"),
    ("https://www.pumpsvalves.nl/exhibitors/?stands%5BrefinementList%5D%5BeventName%5D%5B0%5D=Pumps%20%26%20Valves%20Rotterdam%202027",
     "Pumps & Valves Rotterdam 2027 (Easyfairs)", "easyfairs"),
    ("https://www.solidsrotterdam.nl/exhibitors/?stands%5BrefinementList%5D%5BeventName%5D%5B0%5D=Solids%20Rotterdam%202027",
     "Solids Rotterdam 2027 (Easyfairs)", "easyfairs"),
    # New Easyfairs adds (SSR anchor pattern verified).
    ("https://www.aquanederland.nl/en/exhibitors/",
     "Aqua Nederland (Easyfairs)", "easyfairs"),
    ("https://www.porkpoultryexpo.nl/en/exhibitors/",
     "Dutch Pork & Poultry Expo (Easyfairs)", "easyfairs"),
    ("https://www.bakkersvak.nl/exhibitors/",
     "Bakkersvak & IJs-Vak (Easyfairs)", "easyfairs"),
    ("https://www.groenesector.nl/exhibitor/",
     "De Groene Sector Vakbeurs (Easyfairs)", "easyfairs"),
    # Same static /path/company-slug shape as Easyfairs (parser handles them
    # via the same URL-slug extraction — the "/exhibitor" filter matches both).
    ("https://www.rematec.com/amsterdam/exhibitors",
     "ReMaTec Amsterdam (Apr 2027) — remanufacturing", "easyfairs"),
    ("https://www.intercleanshow.com/amsterdam/exhibitor-list",
     "Interclean Amsterdam — cleaning industry", "easyfairs"),

    # --- firecrawl parser (JS-rendered, auto-detects extractor) ---
    # Provada: verified rendering, ~12 exhibitors extracted via Nuxt DOM.
    ("https://www.provada.nl/bezoekers/standhouders",
     "Provada", "firecrawl"),
    # The 8 Jaarbeurs/Ahoy/FHI events — JS-loaded shells; Firecrawl attempts to
    # render + one of the extractors (foodtech / provida / generic anchor) picks up
    # whatever's in the DOM after JS. Yield is uncertain until first run.
    ("https://event.technishow.nl/en/bezoeken/exposantenlijst-2026",
     "TechniShow 2026 (Jaarbeurs) — industrial production tech", "firecrawl"),
    ("https://www.maakindustrie.nl/en/esef/bezoeken",
     "ESEF Maakindustrie 2026 (Jaarbeurs) — manufacturing supply", "firecrawl"),
    ("https://www.vsk.nl/en/bezoeken/expbez",
     "VSK+E 2026 (Jaarbeurs) — installation industry", "firecrawl"),
    ("https://www.bouwbeurs.nl/bezoeken/exposantenlijst",
     "BouwBeurs 2027 (Jaarbeurs) — construction", "firecrawl"),
    ("https://www.vakbeursfoodspecialiteiten.nl/bezoekers/exposantenlijst",
     "Vakbeurs Foodspecialiteiten 2026 — food specialties", "firecrawl"),
    ("https://fhi.nl/wots/exposanten/",
     "WoTS 2026 (Jaarbeurs, via FHI) — World of Technology & Science", "firecrawl"),
    ("https://www.infratech.nl/exposanten/exposantenlijst",
     "InfraTech 2027 (Ahoy) — infrastructure", "firecrawl"),
    ("https://www.maintenancenext.nl/en/exhibitors",
     "Maintenance NEXT 2027 (Ahoy) — asset management", "firecrawl"),

    # --- known unsupported (kept in table so the UI shows the reason) ---
    ("https://www.safetyevent.nl/partners/",
     "Safety Event (partners)", "unsupported"),
    ("https://www.vakbeursenergie.nl/nl/exposantenlijst/",
     "Vakbeurs Energie", "unsupported"),
    ("https://www.linkedin.com/school/mikrocentrum/people/",
     "Mikrocentrum (LinkedIn)", "unsupported"),
]


def main() -> int:
    if not db.using_db():
        print("ERROR: DATABASE_URL not set"); return 2
    db.init_db()
    created = updated = 0
    for url, label, parser in DEFAULT_SOURCES:
        existing = None
        for s in db.list_event_sources():
            if s["url"] == url:
                existing = s; break
        rid = db.upsert_event_source(url=url, label=label, parser=parser, active=True)
        if existing:
            updated += 1
            print(f"  updated  #{rid:<3} [{parser:12}] {label}")
        else:
            created += 1
            print(f"  created  #{rid:<3} [{parser:12}] {label}")
    print(f"\n{created} created, {updated} updated. Total in table: "
          f"{len(db.list_event_sources())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
