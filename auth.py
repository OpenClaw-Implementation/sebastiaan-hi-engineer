"""Authentication — Werkzeug-hashed passwords + Flask session cookie.

Every route except the small allowlist below is gated. HTML requests get a
302 to ``/login?next=<path>``; the JSON polling endpoints get a 401 payload
so the client's fetch loops don't accidentally render the login page.
"""

from __future__ import annotations

from functools import wraps

from flask import g, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db

# Endpoints (function names) that are reachable without a session.
ALLOWLIST = {"login", "logout", "healthz", "static"}

# Path prefixes that should return JSON 401 on auth failure instead of HTML redirect
# (so /logs/events + /stats/data polling loops handle it cleanly).
JSON_PATH_PREFIXES = ("/logs/events", "/stats/data")


def hash_password(plain: str) -> str:
    return generate_password_hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return check_password_hash(hashed, plain)
    except Exception:  # noqa: BLE001 -- malformed hash → treat as no match
        return False


def current_user() -> dict | None:
    email = session.get("user_email")
    if not email:
        return None
    if getattr(g, "_current_user_email", None) != email:
        g._current_user_email = email
        g._current_user = db.get_user(email)
    return g._current_user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def before_request_guard():
    """Register with ``app.before_request(auth.before_request_guard)``."""
    endpoint = (request.endpoint or "").split(".")[0]
    if endpoint in ALLOWLIST:
        return None
    if current_user():
        return None
    # JSON endpoints (polling) → 401 payload; everything else → redirect
    for prefix in JSON_PATH_PREFIXES:
        if request.path.startswith(prefix):
            return jsonify({"error": "unauthenticated"}), 401
    return redirect(url_for("login", next=request.path))
