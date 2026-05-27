"""Persistence layer -- Supabase Postgres, with a local file fallback.

The app caches three JSON blobs (exhibitors / enrichment / media). When
``DATABASE_URL`` is set (the Supabase pooler connection string on Heroku) they
are stored in the ``app_cache`` table so they survive dyno restarts. With no
``DATABASE_URL`` (local dev) the blobs fall back to JSON files under DATA_DIR.

    app_cache(key text primary key, value jsonb, updated_at timestamptz)
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL")
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))

_conn = None
_lock = threading.Lock()


def using_db() -> bool:
    return bool(DATABASE_URL)


# --------------------------------------------------------------------------- #
# Postgres connection (lazy, with reconnect-on-failure)
# --------------------------------------------------------------------------- #
def _connect():
    import psycopg2

    conn = psycopg2.connect(DATABASE_URL, connect_timeout=15, sslmode="require")
    conn.autocommit = True
    return conn


def _get_conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = _connect()
    return _conn


def _reset_conn() -> None:
    global _conn
    try:
        if _conn is not None:
            _conn.close()
    except Exception:  # noqa: BLE001
        pass
    _conn = None


def _run(fn):
    """Run ``fn(cursor)`` with one reconnect retry on a dropped connection."""
    import psycopg2

    with _lock:
        for attempt in (1, 2):
            try:
                with _get_conn().cursor() as cur:
                    return fn(cur)
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                _reset_conn()
                if attempt == 2:
                    raise


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def init_db() -> None:
    if not using_db():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return
    _run(
        lambda cur: cur.execute(
            """
            create table if not exists app_cache (
                key text primary key,
                value jsonb not null,
                updated_at timestamptz not null default now()
            )
            """
        )
    )


def cache_get(key: str, default=None):
    if not using_db():
        path = DATA_DIR / f"{key}.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                return default
        return default

    def _q(cur):
        cur.execute("select value from app_cache where key = %s", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    return _run(_q)


def cache_set(key: str, value) -> None:
    if not using_db():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / f"{key}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return

    from psycopg2.extras import Json

    _run(
        lambda cur: cur.execute(
            """
            insert into app_cache (key, value, updated_at)
            values (%s, %s, now())
            on conflict (key) do update
                set value = excluded.value, updated_at = now()
            """,
            (key, Json(value)),
        )
    )
