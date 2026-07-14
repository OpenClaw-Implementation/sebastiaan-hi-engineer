"""Shared envelope + helpers for company-enrichment providers."""

from __future__ import annotations

import os
from typing import Any

DEFAULT_TIMEOUT = 12  # seconds -- each provider should stay well under Heroku's 30s

_UA = (
    "Mozilla/5.0 (compatible; hi-engineer-enrichment/1.0; "
    "+https://hi-engineer-app-42963ff5fb67.herokuapp.com/)"
)


def envelope(source: str, ok: bool = False, fields: dict | None = None,
             credits: float = 0.0, usd: float = 0.0,
             error: str | None = None, raw: Any = None) -> dict:
    """Build the standard cascade envelope. `raw` is truncated to keep logs sane."""
    return {
        "ok": ok,
        "source": source,
        "fields": {k: v for k, v in (fields or {}).items() if v not in (None, "")},
        "credits": round(credits, 4),
        "usd": round(usd, 6),
        "error": error,
        "raw": _trim(raw),
    }


def _trim(raw: Any, limit: int = 2000) -> Any:
    if isinstance(raw, (dict, list)):
        s = str(raw)
        return s[:limit] + " …" if len(s) > limit else s
    if isinstance(raw, str):
        return raw[:limit]
    return raw


def env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v else default


def user_agent() -> str:
    return _UA
