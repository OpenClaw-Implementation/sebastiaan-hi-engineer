"""RunLogger -- records each scrape step as a scrape_events row.

Each step is committed immediately (db autocommit), so the Logs+Costs tab can
read a run's progress live while the scrape is still executing. Event ordering
and the polling cursor use the DB-assigned ``id`` (monotonic), which keeps steps
correctly ordered even when several requests append to the same run.
"""

from __future__ import annotations

import db
from costs import cost_for


class RunLogger:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.credits = 0.0
        self.usd = 0.0

    def event(self, action: str, detail: str = "", status: str = "ok",
              duration_ms: float | None = None, **cost_kw) -> tuple[float, float]:
        credits, usd = cost_for(action, **cost_kw)
        self.credits += credits
        self.usd += usd
        db.log_event(
            self.run_id, action, detail, status,
            int(duration_ms) if duration_ms is not None else None,
            credits, usd, cost_kw or None,
        )
        return credits, usd


class NullLogger:
    """No-op logger so scrapers can run uninstrumented (tests, fallbacks)."""
    run_id = None

    def event(self, *args, **kwargs) -> tuple[float, float]:
        return 0.0, 0.0


NULL = NullLogger()
