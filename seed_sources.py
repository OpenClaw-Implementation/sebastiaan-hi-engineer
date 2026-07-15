"""One-off: seed the 11 event source URLs. Idempotent — reruns just refresh
labels/parsers without touching last_scraped_at.

    heroku run python seed_sources.py -a hi-engineer-app
"""

from __future__ import annotations

import sys

import db

DEFAULT_SOURCES = [
    # url, label, parser
    ("https://food-tech-event.nl/nl/exposantenlijst/",
     "Food Tech Event", "foodtech"),
    ("https://mtconference.nl/nl/exposantenlijst/",
     "MT Conference", "foodtech"),
    # Safety Event partners are JS-loaded by a Logo Showcase WP plugin that
    # exposes no REST endpoint — needs a headless browser to enumerate.
    # Marked unsupported for now (flip to Firecrawl parser once wired).
    ("https://www.safetyevent.nl/partners/",
     "Safety Event (partners)", "unsupported"),
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
    # Firecrawl-rendered: SPA whose exhibitor list only appears after JS.
    # Verified working during Firecrawl probe (Nuxt DOM with <a class="exhibitor">).
    ("https://www.provada.nl/bezoekers/standhouders",
     "Provada", "firecrawl"),
    # Known unsupported (JS-only + no accessible DOM even after render, OR auth-gated).
    # Kept in the table so the UI shows them with an explanatory error.
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
