"""One-off cleanup — delete jobs + articles rows whose title or url fails the
current filters (``is_noise_title`` / ``is_noise_url``). Safe to re-run; only
touches rows that match.

    heroku run python clean_noise.py --dry-run  -a hi-engineer-app   # preview
    heroku run python clean_noise.py            -a hi-engineer-app   # actually delete
"""

from __future__ import annotations

import argparse
import sys

import db
from scrapers.listing_extractor import is_noise_title, is_noise_url


def scan_table(table: str) -> list[tuple[int, str, str, str]]:
    """Return the list of (id, title, url, reason) rows that would be deleted."""
    if not db.using_db():
        print("no DATABASE_URL; skipped"); return []

    def q(cur):
        cur.execute(f"select id, title, coalesce(url,''), coalesce(source_page,'') "
                    f"from {table}")
        return cur.fetchall()

    rows = db._run(q)
    hits: list[tuple[int, str, str, str]] = []
    for rid, title, url, source_page in rows:
        if is_noise_title(title):
            hits.append((rid, title, url, "title"))
        elif is_noise_url(url, source_page):
            hits.append((rid, title, url, "url"))
    return hits


def delete_rows(table: str, ids: list[int]) -> None:
    def q(cur):
        cur.execute(f"delete from {table} where id = any(%s::bigint[])", (ids,))
    db._run(q)


def process(table: str, dry_run: bool) -> int:
    hits = scan_table(table)
    print(f"\n=== {table}: {len(hits)} row(s) would be removed ===")
    for rid, title, url, reason in hits[:200]:
        print(f"  [{reason}] id={rid:>4}  title={title[:50]!r:52}  url={url[:80]}")
    if hits and not dry_run:
        delete_rows(table, [h[0] for h in hits])
        print(f"{table}: deleted {len(hits)} rows")
    elif hits:
        print(f"{table}: DRY RUN — nothing deleted")
    return len(hits)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                   help="list rows that would be deleted, don't touch the DB")
    args = p.parse_args()

    total = 0
    for tbl in ("jobs", "articles"):
        total += process(tbl, dry_run=args.dry_run)
    print(f"\nTotal noise rows {'previewed' if args.dry_run else 'removed'}: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
