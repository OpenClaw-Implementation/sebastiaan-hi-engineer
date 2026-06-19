"""Supabase keep-alive ping.

Run by Heroku Scheduler once a day to reset the Supabase free-tier inactivity
timer (the project auto-pauses after ~1 week without activity, which crashes
the app at boot). Costs nothing; just opens a connection and runs ``select 1``.

Invocation (set in the Scheduler dashboard):

    python heartbeat.py
"""

from __future__ import annotations

import sys

import db


def main() -> int:
    if not db.using_db():
        print("heartbeat: skipped (no DATABASE_URL)")
        return 0
    try:
        result = db._run(lambda cur: (cur.execute("select 1, now()"), cur.fetchone())[1])
        print(f"heartbeat: OK {result}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"heartbeat: FAILED — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
