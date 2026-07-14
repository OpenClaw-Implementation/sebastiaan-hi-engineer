"""One-off cleanup — delete jobs + articles rows whose title fails the
current ``is_noise_title`` filter. Safe to re-run; only touches rows that
match the filter.

    heroku run python clean_noise.py -a hi-engineer-app
"""

from __future__ import annotations

import sys

import db
from scrapers.listing_extractor import is_noise_title


def clean_table(table: str) -> int:
    if not db.using_db():
        print("no DATABASE_URL; skipped"); return 0

    def q_select(cur):
        cur.execute(f"select id, title from {table}")
        return cur.fetchall()

    def q_delete(cur, ids):
        cur.execute(f"delete from {table} where id = any(%s::bigint[])", (ids,))

    rows = db._run(q_select)
    noisy_ids = [rid for rid, title in rows if is_noise_title(title)]
    print(f"{table}: {len(rows)} rows examined, {len(noisy_ids)} match noise filter")
    if noisy_ids:
        db._run(lambda cur: q_delete(cur, noisy_ids))
        print(f"{table}: deleted {len(noisy_ids)} rows")
    return len(noisy_ids)


def main() -> int:
    total = 0
    for tbl in ("jobs", "articles"):
        total += clean_table(tbl)
    print(f"\nTotal noise rows removed: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
