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
import uuid
from datetime import datetime, timezone
from decimal import Decimal
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
            );
            create table if not exists scrape_runs (
                run_id uuid primary key,
                kind text not null,
                label text,
                status text not null default 'running',
                started_at timestamptz not null default now(),
                finished_at timestamptz,
                total_credits numeric not null default 0,
                total_usd numeric not null default 0,
                meta jsonb
            );
            create table if not exists scrape_events (
                id bigserial primary key,
                run_id uuid not null references scrape_runs(run_id) on delete cascade,
                ts timestamptz not null default now(),
                action text not null,
                detail text,
                status text not null default 'ok',
                duration_ms integer,
                credits numeric not null default 0,
                usd numeric not null default 0,
                meta jsonb
            );
            create index if not exists scrape_events_run_id_idx on scrape_events(run_id, id);
            create index if not exists scrape_runs_started_idx on scrape_runs(started_at desc);
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


# --------------------------------------------------------------------------- #
# Run / event log (Logs+Costs tab)
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _dictify(cur) -> list[dict]:
    cols = [c[0] for c in cur.description]
    return [{c: _jsonable(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


_RUN_COLS = "run_id, kind, label, status, started_at, finished_at, total_credits, total_usd"


# --- file fallback helpers (no DATABASE_URL) ------------------------------- #
def _file_runs() -> list[dict]:
    path = DATA_DIR / "runs.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return []
    return []


def _file_save_runs(runs: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "runs.json").write_text(
        json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _strip_events(run: dict) -> dict:
    return {k: v for k, v in run.items() if k != "events"}


# --- public API ------------------------------------------------------------ #
def create_run(kind: str, label: str = "", meta=None) -> str:
    run_id = str(uuid.uuid4())
    if not using_db():
        runs = _file_runs()
        runs.insert(0, {
            "run_id": run_id, "kind": kind, "label": label, "status": "running",
            "started_at": _now_iso(), "finished_at": None,
            "total_credits": 0, "total_usd": 0, "events": [],
        })
        _file_save_runs(runs)
        return run_id

    from psycopg2.extras import Json

    _run(lambda cur: cur.execute(
        "insert into scrape_runs (run_id, kind, label, meta) values (%s, %s, %s, %s)",
        (run_id, kind, label, Json(meta) if meta else None),
    ))
    return run_id


def log_event(run_id, action, detail="", status="ok", duration_ms=None,
              credits=0.0, usd=0.0, meta=None) -> None:
    if not using_db():
        runs = _file_runs()
        for r in runs:
            if r["run_id"] == run_id:
                r["events"].append({
                    "id": len(r["events"]) + 1, "ts": _now_iso(),
                    "action": action, "detail": detail, "status": status,
                    "duration_ms": duration_ms, "credits": credits, "usd": usd,
                })
                break
        _file_save_runs(runs)
        return

    from psycopg2.extras import Json

    _run(lambda cur: cur.execute(
        """insert into scrape_events
               (run_id, action, detail, status, duration_ms, credits, usd, meta)
           values (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (run_id, action, detail, status, duration_ms, credits, usd,
         Json(meta) if meta else None),
    ))


def finish_run(run_id, status="finished") -> None:
    if not using_db():
        runs = _file_runs()
        for r in runs:
            if r["run_id"] == run_id:
                r["status"] = status
                r["finished_at"] = _now_iso()
                r["total_credits"] = round(sum(e["credits"] for e in r["events"]), 4)
                r["total_usd"] = round(sum(e["usd"] for e in r["events"]), 6)
                break
        _file_save_runs(runs)
        return

    _run(lambda cur: cur.execute(
        """update scrape_runs set
               status = %s, finished_at = now(),
               total_credits = coalesce((select sum(credits) from scrape_events where run_id = %s), 0),
               total_usd     = coalesce((select sum(usd)     from scrape_events where run_id = %s), 0)
           where run_id = %s""",
        (status, run_id, run_id, run_id),
    ))


def get_latest_run():
    if not using_db():
        runs = _file_runs()
        return _strip_events(runs[0]) if runs else None

    def q(cur):
        cur.execute(f"select {_RUN_COLS} from scrape_runs order by started_at desc limit 1")
        rows = _dictify(cur)
        return rows[0] if rows else None

    return _run(q)


def get_run(run_id):
    if not using_db():
        for r in _file_runs():
            if r["run_id"] == run_id:
                return _strip_events(r)
        return None

    def q(cur):
        cur.execute(f"select {_RUN_COLS} from scrape_runs where run_id = %s", (run_id,))
        rows = _dictify(cur)
        return rows[0] if rows else None

    return _run(q)


def get_events(run_id, after_id=0) -> list[dict]:
    if not using_db():
        for r in _file_runs():
            if r["run_id"] == run_id:
                return [e for e in r["events"] if e["id"] > after_id]
        return []

    def q(cur):
        cur.execute(
            """select id, ts, action, detail, status, duration_ms, credits, usd
               from scrape_events where run_id = %s and id > %s order by id""",
            (run_id, after_id),
        )
        return _dictify(cur)

    return _run(q)


def get_runs(limit=30) -> list[dict]:
    if not using_db():
        return [_strip_events(r) for r in _file_runs()[:limit]]

    def q(cur):
        cur.execute(f"select {_RUN_COLS} from scrape_runs order by started_at desc limit %s", (limit,))
        return _dictify(cur)

    return _run(q)


def cumulative_spend() -> dict:
    if not using_db():
        runs = _file_runs()
        return {
            "credits": round(sum(r.get("total_credits", 0) for r in runs), 4),
            "usd": round(sum(r.get("total_usd", 0) for r in runs), 6),
        }

    def q(cur):
        cur.execute("select coalesce(sum(total_credits),0) c, coalesce(sum(total_usd),0) u from scrape_runs")
        rows = _dictify(cur)
        return {"credits": rows[0]["c"], "usd": rows[0]["u"]}

    return _run(q)
