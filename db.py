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
import sys
import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL")
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))

_conn = None
_lock = threading.Lock()

# True until any DB call fails. Flipped back to True on the next successful call.
# Routes consult ``is_healthy()`` to render a "DB unavailable" banner so a paused/
# unreachable Supabase degrades the app gracefully instead of crashing it at boot.
_HEALTHY = True


def is_healthy() -> bool:
    return _HEALTHY


def _ok() -> None:
    global _HEALTHY
    if not _HEALTHY:
        _HEALTHY = True
        print("[db] recovered", file=sys.stderr)


def _fail(where: str, err: Exception) -> None:
    global _HEALTHY
    if _HEALTHY:
        _HEALTHY = False
        print(f"[db] DEGRADED ({where}): {err}", file=sys.stderr)


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
    try:
        # Advisory lock serialises concurrent workers so that only one runs the
        # DDL block at a time. Otherwise multiple `CREATE TABLE IF NOT EXISTS`
        # sessions race on pg_type and one worker fails with
        # `duplicate key value violates unique constraint pg_type_typname_nsp_index`,
        # potentially leaving later tables in the block un-created.
        _run(lambda cur: cur.execute("select pg_advisory_lock(1834521)"))
        try:
            _init_db_unsafe()
        finally:
            _run(lambda cur: cur.execute("select pg_advisory_unlock(1834521)"))
        _ok()
    except Exception as e:  # noqa: BLE001 -- boot must never crash on DB outage
        _fail("init_db", e)


def _init_db_unsafe() -> None:
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

            create table if not exists companies (
                id bigserial primary key,
                name text not null unique,
                category_1 text, category_2 text, category_3 text,
                location text, tel text, email text, website text,
                news_url text, jobs_url text,
                linkedin_url text, linkedin_industry text,
                summary text, specialities text,
                event_source text, event_pitch text, event_profile text,
                logo_url text, stand text,
                enrich_status text not null default 'pending',
                enrich_source text,
                enriched_at timestamptz,
                updated_at timestamptz not null default now()
            );
            create index if not exists companies_status_idx on companies(enrich_status);
            create index if not exists companies_name_lower_idx on companies(lower(name));

            create table if not exists company_enrichment_log (
                id bigserial primary key,
                company_id bigint not null references companies(id) on delete cascade,
                attempt_no int,
                source text,
                success boolean not null,
                duration_ms int,
                credits numeric not null default 0,
                usd numeric not null default 0,
                error_message text,
                details jsonb,
                searched_at timestamptz not null default now()
            );
            create index if not exists company_enrich_log_idx on company_enrichment_log(company_id, id);
            alter table company_enrichment_log
                add column if not exists run_id uuid references scrape_runs(run_id) on delete set null;
            create index if not exists company_enrich_log_run_idx on company_enrichment_log(run_id);
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

    try:
        result = _run(_q)
        _ok()
        return result
    except Exception as e:  # noqa: BLE001
        _fail("cache_get", e)
        return default


def cache_set(key: str, value) -> None:
    if not using_db():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / f"{key}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return

    from psycopg2.extras import Json

    try:
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
        _ok()
    except Exception as e:  # noqa: BLE001
        _fail("cache_set", e)


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

    try:
        _run(lambda cur: cur.execute(
            "insert into scrape_runs (run_id, kind, label, meta) values (%s, %s, %s, %s)",
            (run_id, kind, label, Json(meta) if meta else None),
        ))
        _ok()
    except Exception as e:  # noqa: BLE001
        _fail("create_run", e)
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

    try:
        _run(lambda cur: cur.execute(
            """insert into scrape_events
                   (run_id, action, detail, status, duration_ms, credits, usd, meta)
               values (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (run_id, action, detail, status, duration_ms, credits, usd,
             Json(meta) if meta else None),
        ))
        _ok()
    except Exception as e:  # noqa: BLE001
        _fail("log_event", e)


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

    try:
        _run(lambda cur: cur.execute(
            """update scrape_runs set
                   status = %s, finished_at = now(),
                   total_credits = coalesce((select sum(credits) from scrape_events where run_id = %s), 0),
                   total_usd     = coalesce((select sum(usd)     from scrape_events where run_id = %s), 0)
               where run_id = %s""",
            (status, run_id, run_id, run_id),
        ))
        _ok()
    except Exception as e:  # noqa: BLE001
        _fail("finish_run", e)


def get_latest_run():
    if not using_db():
        runs = _file_runs()
        return _strip_events(runs[0]) if runs else None

    def q(cur):
        cur.execute(f"select {_RUN_COLS} from scrape_runs order by started_at desc limit 1")
        rows = _dictify(cur)
        return rows[0] if rows else None

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("get_latest_run", e); return None


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

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("get_run", e); return None


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

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("get_events", e); return []


def get_runs(limit=30) -> list[dict]:
    if not using_db():
        return [_strip_events(r) for r in _file_runs()[:limit]]

    def q(cur):
        cur.execute(f"select {_RUN_COLS} from scrape_runs order by started_at desc limit %s", (limit,))
        return _dictify(cur)

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("get_runs", e); return []


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

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("cumulative_spend", e); return {"credits": 0, "usd": 0}


# --------------------------------------------------------------------------- #
# Companies + enrichment log (Module 01 normalized directory)
# --------------------------------------------------------------------------- #
COMPANY_COLS = (
    "id, name, category_1, category_2, category_3, location, tel, email, "
    "website, news_url, jobs_url, linkedin_url, linkedin_industry, summary, "
    "specialities, event_source, event_pitch, event_profile, logo_url, stand, "
    "enrich_status, enrich_source, enriched_at, updated_at"
)

# Fields the enrichment cascade may fill in. `event_*` are set at insert time.
ENRICHABLE_FIELDS = (
    "location", "tel", "email", "website", "news_url", "jobs_url",
    "linkedin_url", "linkedin_industry", "summary", "specialities",
)


def upsert_company_from_exhibitor(ex: dict) -> int | None:
    """Upsert one scraped exhibitor into `companies`. Returns the row id or None
    on DB failure. Only sets fields we scrape; enrichable fields stay NULL."""
    if not using_db():
        # File fallback: keep it simple -- return a synthetic id via hash of name
        return abs(hash(ex.get("name", "")))
    cats = ex.get("categories") or []
    cat1 = cats[0] if len(cats) > 0 else None
    cat2 = cats[1] if len(cats) > 1 else None
    cat3 = cats[2] if len(cats) > 2 else None

    def q(cur):
        cur.execute(
            """
            insert into companies
                (name, category_1, category_2, category_3,
                 event_source, event_pitch, event_profile, logo_url, stand)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (name) do update set
                category_1   = coalesce(excluded.category_1,   companies.category_1),
                category_2   = coalesce(excluded.category_2,   companies.category_2),
                category_3   = coalesce(excluded.category_3,   companies.category_3),
                event_source = coalesce(excluded.event_source, companies.event_source),
                event_pitch  = coalesce(excluded.event_pitch,  companies.event_pitch),
                event_profile= coalesce(excluded.event_profile,companies.event_profile),
                logo_url     = coalesce(excluded.logo_url,     companies.logo_url),
                stand        = coalesce(excluded.stand,        companies.stand),
                updated_at   = now()
            returning id
            """,
            (
                ex.get("name"), cat1, cat2, cat3,
                ex.get("source_url"), ex.get("tagline"), ex.get("description"),
                ex.get("logo_url"), ex.get("stand"),
            ),
        )
        return cur.fetchone()[0]

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("upsert_company_from_exhibitor", e); return None


def list_companies(status: str | None = None, limit: int | None = None) -> list[dict]:
    if not using_db():
        return []

    def q(cur):
        where = "where enrich_status = %s" if status else ""
        lim = "limit %s" if limit else ""
        params = tuple(x for x in (status, limit) if x is not None)
        cur.execute(f"select {COMPANY_COLS} from companies {where} order by name {lim}", params)
        return _dictify(cur)

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("list_companies", e); return []


def get_company(company_id: int) -> dict | None:
    if not using_db():
        return None

    def q(cur):
        cur.execute(f"select {COMPANY_COLS} from companies where id = %s", (company_id,))
        rows = _dictify(cur)
        return rows[0] if rows else None

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("get_company", e); return None


def count_companies_by_status() -> dict:
    if not using_db():
        return {"pending": 0, "enriched": 0, "terminal": 0, "total": 0}

    def q(cur):
        cur.execute(
            "select enrich_status, count(*) from companies group by enrich_status"
        )
        rows = cur.fetchall()
        d = {r[0]: r[1] for r in rows}
        d["total"] = sum(d.values())
        return d

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("count_companies_by_status", e); return {"pending": 0, "enriched": 0, "terminal": 0, "total": 0}


def update_company_fields(company_id: int, fields: dict, source: str | None = None,
                          status: str = "enriched") -> None:
    """SET only whitelisted fields; also stamp enrich_source/enriched_at/status."""
    if not using_db():
        return
    clean = {k: v for k, v in fields.items() if k in ENRICHABLE_FIELDS and v not in (None, "")}
    if not clean and source is None and status is None:
        return
    sets, params = [], []
    for k, v in clean.items():
        sets.append(f"{k} = coalesce(%s, {k})")
        params.append(v)
    if source is not None:
        sets.append("enrich_source = %s")
        params.append(source)
    if status is not None:
        sets.append("enrich_status = %s")
        params.append(status)
    sets.append("enriched_at = now()")
    sets.append("updated_at = now()")
    params.append(company_id)
    sql = f"update companies set {', '.join(sets)} where id = %s"

    try:
        _run(lambda cur: cur.execute(sql, tuple(params)))
        _ok()
    except Exception as e:  # noqa: BLE001
        _fail("update_company_fields", e)


def log_company_enrichment(company_id: int, attempt_no: int, source: str,
                           success: bool, duration_ms: int | None = None,
                           credits: float = 0.0, usd: float = 0.0,
                           error_message: str | None = None,
                           details: dict | None = None,
                           run_id: str | None = None) -> None:
    if not using_db():
        return
    from psycopg2.extras import Json
    try:
        _run(lambda cur: cur.execute(
            """insert into company_enrichment_log
                   (company_id, attempt_no, source, success, duration_ms,
                    credits, usd, error_message, details, run_id)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (company_id, attempt_no, source, success, duration_ms, credits, usd,
             error_message, Json(details) if details else None, run_id),
        ))
        _ok()
    except Exception as e:  # noqa: BLE001
        _fail("log_company_enrichment", e)


# --------------------------------------------------------------------------- #
# Stats aggregations (Analytics tab, /stats)
# --------------------------------------------------------------------------- #
_WINDOWS = {"24h": "1 day", "7d": "7 days", "30d": "30 days"}


def _window_where(window: str, col: str) -> str:
    """Build a WHERE clause fragment for a time window. Unknown → no filter."""
    interval = _WINDOWS.get(window)
    return f"where {col} > now() - interval '{interval}'" if interval else ""


def cascade_by_source_with_deltas(window: str = "7d") -> list[dict]:
    """Per-provider aggregates + delta % vs the previous same-length window.
    For ``window='all'`` deltas are undefined and returned as None."""
    if not using_db():
        return []
    if window not in _WINDOWS:
        # All-time: just return current-window rows with null deltas
        rows = cascade_by_source(window)
        for r in rows:
            r["delta_attempts_pct"] = None
            r["delta_usd_pct"] = None
        return rows

    interval = _WINDOWS[window]

    def q(cur):
        cur.execute(f"""
            with cur as (
              select source,
                     count(*)::int as attempts,
                     sum(success::int)::int as hits,
                     coalesce(sum(usd),0)::float as usd,
                     coalesce(sum(credits),0)::float as credits,
                     coalesce(avg(duration_ms),0)::int as avg_ms
                from company_enrichment_log
                where searched_at > now() - interval '{interval}'
                group by source
            ), prev as (
              select source,
                     count(*)::int as attempts,
                     coalesce(sum(usd),0)::float as usd
                from company_enrichment_log
                where searched_at between now() - (interval '{interval}') * 2
                                      and now() - interval '{interval}'
                group by source
            )
            select c.source, c.attempts, c.hits,
                   case when c.attempts > 0
                        then round((100.0 * c.hits / c.attempts)::numeric, 1)::float
                        else 0 end as hit_rate_pct,
                   c.avg_ms, c.credits, c.usd,
                   coalesce(p.attempts, 0)::int as prev_attempts,
                   coalesce(p.usd, 0)::float as prev_usd,
                   case when coalesce(p.attempts, 0) > 0
                        then round((100.0 * (c.attempts - p.attempts) / p.attempts)::numeric, 0)::int
                        else null end as delta_attempts_pct,
                   case when coalesce(p.usd, 0) > 0
                        then round((100.0 * (c.usd - p.usd) / p.usd)::numeric, 0)::int
                        else null end as delta_usd_pct
              from cur c
              left join prev p on p.source = c.source
              order by c.attempts desc
        """)
        return _dictify(cur)

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("cascade_by_source_with_deltas", e); return []


def cascade_by_source(window: str = "7d") -> list[dict]:
    """Per-provider aggregates from company_enrichment_log."""
    if not using_db():
        return []
    where = _window_where(window, "searched_at")

    def q(cur):
        cur.execute(f"""
            select source,
                   count(*)::int as attempts,
                   sum(success::int)::int as hits,
                   case when count(*) > 0
                        then round(100.0 * sum(success::int) / count(*), 1)::float
                        else 0 end as hit_rate_pct,
                   coalesce(avg(duration_ms), 0)::int as avg_ms,
                   round(sum(credits)::numeric, 4)::float as credits,
                   round(sum(usd)::numeric, 6)::float as usd
              from company_enrichment_log {where}
              group by source
              order by attempts desc
        """)
        return _dictify(cur)

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("cascade_by_source", e); return []


def field_fill_rates() -> dict:
    """Percentage of companies with each enrichable column populated."""
    if not using_db():
        return {"total": 0}

    def q(cur):
        cur.execute("""
            select
              count(*)::int as total,
              round(100.0 * sum((website          is not null)::int) / nullif(count(*),0), 1)::float as website,
              round(100.0 * sum((linkedin_url     is not null)::int) / nullif(count(*),0), 1)::float as linkedin_url,
              round(100.0 * sum((linkedin_industry is not null)::int) / nullif(count(*),0), 1)::float as linkedin_industry,
              round(100.0 * sum((location         is not null)::int) / nullif(count(*),0), 1)::float as location,
              round(100.0 * sum((summary          is not null)::int) / nullif(count(*),0), 1)::float as summary,
              round(100.0 * sum((specialities     is not null)::int) / nullif(count(*),0), 1)::float as specialities,
              round(100.0 * sum((tel              is not null)::int) / nullif(count(*),0), 1)::float as tel,
              round(100.0 * sum((email            is not null)::int) / nullif(count(*),0), 1)::float as email,
              round(100.0 * sum((news_url         is not null)::int) / nullif(count(*),0), 1)::float as news_url,
              round(100.0 * sum((jobs_url         is not null)::int) / nullif(count(*),0), 1)::float as jobs_url
            from companies
        """)
        rows = _dictify(cur)
        return rows[0] if rows else {"total": 0}

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("field_fill_rates", e); return {"total": 0}


def _top_of(sql: str, limit: int) -> list[dict]:
    def q(cur):
        cur.execute(sql, (limit,))
        return _dictify(cur)
    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("top_of", e); return []


def top_industries(limit: int = 15) -> list[dict]:
    if not using_db():
        return []
    return _top_of(
        """select linkedin_industry as name, count(*)::int as count
             from companies where linkedin_industry is not null
             group by 1 order by 2 desc limit %s""",
        limit,
    )


def top_locations(limit: int = 15) -> list[dict]:
    """City-level: first token before the comma."""
    if not using_db():
        return []
    return _top_of(
        """select trim(split_part(location, ',', 1)) as name, count(*)::int as count
             from companies where location is not null
             group by 1 order by 2 desc limit %s""",
        limit,
    )


def top_categories(limit: int = 15) -> list[dict]:
    """Union across category_1/2/3."""
    if not using_db():
        return []
    return _top_of(
        """with cats as (
              select category_1 as c from companies where category_1 is not null
              union all select category_2 from companies where category_2 is not null
              union all select category_3 from companies where category_3 is not null
           )
           select c as name, count(*)::int as count from cats
            group by 1 order by 2 desc limit %s""",
        limit,
    )


def source_distribution() -> list[dict]:
    if not using_db():
        return []

    def q(cur):
        cur.execute("""
            select coalesce(enrich_source, '(pending/terminal)') as source,
                   count(*)::int as count
              from companies
              group by 1 order by 2 desc
        """)
        return _dictify(cur)

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("source_distribution", e); return []


def daily_cost(days: int = 14) -> list[dict]:
    """Cost & run counts by day for the last N days."""
    if not using_db():
        return []
    days = max(1, int(days))

    def q(cur):
        cur.execute(f"""
            select to_char(date(started_at), 'YYYY-MM-DD') as day,
                   count(*)::int as runs,
                   round(coalesce(sum(total_usd), 0)::numeric, 4)::float as usd,
                   round(coalesce(sum(total_credits), 0)::numeric, 4)::float as credits
              from scrape_runs
              where started_at > now() - interval '{days} days'
              group by 1 order by 1
        """)
        return _dictify(cur)

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("daily_cost", e); return []


def run_detail(run_id: str) -> dict:
    """Full drill-down for /logs/<run_id>: header + events + touched companies."""
    empty = {"run": None, "events": [], "companies": []}
    if not using_db():
        return empty

    def q(cur):
        cur.execute(f"select {_RUN_COLS} from scrape_runs where run_id = %s", (run_id,))
        rows = _dictify(cur)
        if not rows:
            return empty
        run = rows[0]

        cur.execute(
            """select id, ts, action, detail, status, duration_ms, credits, usd
                 from scrape_events where run_id = %s order by id""",
            (run_id,),
        )
        events = _dictify(cur)

        companies: list[dict] = []
        if run["kind"] in ("enrich_company", "enrich_bulk_all", "enrich_batch"):
            # Prefer exact join on run_id (populated for new runs).
            cur.execute(
                """
                select c.id, c.name, c.enrich_status, c.enrich_source,
                       count(l.id)::int as attempts,
                       sum(l.success::int)::int as hits,
                       round(sum(l.credits)::numeric, 4)::float as credits,
                       round(sum(l.usd)::numeric, 6)::float as usd,
                       min(l.searched_at) as first_ts
                  from company_enrichment_log l
                  join companies c on c.id = l.company_id
                 where l.run_id = %s
                 group by c.id, c.name, c.enrich_status, c.enrich_source
                 order by first_ts
                """,
                (run_id,),
            )
            companies = _dictify(cur)

            # Fall back to time-window overlap for legacy rows (before the
            # run_id column existed on this table).
            if not companies:
                cur.execute(
                    """
                    select c.id, c.name, c.enrich_status, c.enrich_source,
                           count(l.id)::int as attempts,
                           sum(l.success::int)::int as hits,
                           round(sum(l.credits)::numeric, 4)::float as credits,
                           round(sum(l.usd)::numeric, 6)::float as usd,
                           min(l.searched_at) as first_ts
                      from company_enrichment_log l
                      join companies c on c.id = l.company_id
                     where l.run_id is null
                       and l.searched_at between (%s::timestamptz - interval '2 seconds')
                                             and (coalesce(%s::timestamptz, now())
                                                  + interval '2 seconds')
                     group by c.id, c.name, c.enrich_status, c.enrich_source
                     order by first_ts
                    """,
                    (run["started_at"], run["finished_at"]),
                )
                companies = _dictify(cur)

        return {"run": run, "events": events, "companies": companies}

    try:
        result = _run(q); _ok(); return result
    except Exception as e:  # noqa: BLE001
        _fail("run_detail", e); return empty
