# pogan deploy-gate proof 1782244830
"""Hi-Engineer -- Heroku web app.

Two tabs:
  * Scraping Engine  -- scrapes the Food Tech Event exhibitor list (the
                        "EVENT SOURCE" URL from the workbook), structures the
                        exhibitors, and enriches each with Icypeas people search
                        keyed by company name.
  * Content Engine   -- scrapes the industrial/food "Media" portals and shows
                        the content for viewing.

All scraping uses direct cURL-style requests (no Firecrawl/Apify). Results are
persisted via ``db`` -- Supabase Postgres when DATABASE_URL is set (durable
across dyno restarts), falling back to local JSON files otherwise.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from time import perf_counter

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

import auth
import costs
import db
import normalize
from enrichers import cascade as enrichment_cascade
from runlog import RunLogger
from scrapers import articles_pipeline, event_sources as event_sources_module, icypeas, jobs_pipeline
from scrapers.exhibitors import scrape_event_sources
from scrapers.media import scrape_media
from scrapers.sources import EVENT_SOURCES, MEDIA_SOURCES, dedupe_keep_order

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hi-engineer-dev-secret")

# Trust Heroku's X-Forwarded-* headers so url_for() etc. see https.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Session cookie: 12 h idle, HttpOnly always, Secure only on Heroku (local dev
# runs on http). SameSite Lax so forms from the same origin keep working.
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("DYNO"))

db.init_db()

# Global auth guard — redirects unauth HTML requests to /login, returns 401
# JSON for the polling endpoints.
app.before_request(auth.before_request_guard)


@app.context_processor
def _inject_db_health():
    """Expose the DB health flag and current user to every template."""
    return {"db_healthy": db.is_healthy(), "current_user": auth.current_user()}


# --------------------------------------------------------------------------- #
# Login / logout
# --------------------------------------------------------------------------- #
def _safe_next(target: str | None) -> str:
    """Only allow same-origin relative next targets."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("scraping_engine")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    next_url = request.values.get("next") or ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = db.get_user(email)
        if user and auth.verify_password(password, user["password_hash"]):
            session.clear()
            session["user_email"] = email
            session.permanent = True
            db.record_login(email)
            return redirect(_safe_next(next_url))
        error = "Invalid email or password."
    return render_template("login.html", error=error, next=next_url)


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

# Cache keys in the app_cache table (or <key>.json in the file fallback).
KEY_EXHIBITORS = "exhibitors"
KEY_ENRICHMENT = "enrichment"
KEY_MEDIA = "media"

# Optional fixed label shown for the "scraped" date instead of the live scrape
# time (e.g. the canonical data date). Set the SCRAPED_AT_DISPLAY config var to
# override; leave it unset to show the actual scrape timestamp.
SCRAPED_AT_DISPLAY = os.environ.get("SCRAPED_AT_DISPLAY")


# --------------------------------------------------------------------------- #
# Store helpers (delegate to db: Supabase Postgres or file fallback)
# --------------------------------------------------------------------------- #
def _load(key: str, default):
    value = db.cache_get(key)
    return value if value is not None else default


def _save(key: str, data) -> None:
    db.cache_set(key, data)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return redirect(url_for("scraping_engine"))


@app.route("/scraping-engine")
def scraping_engine():
    data = _load(KEY_EXHIBITORS, None)
    if data and SCRAPED_AT_DISPLAY:
        data["scraped_at"] = SCRAPED_AT_DISPLAY
    enrichment = _load(KEY_ENRICHMENT, {})
    sources = db.list_event_sources()
    return render_template(
        "scraping_engine.html",
        active="scraping",
        data=data,
        enrichment=enrichment,
        event_sources=dedupe_keep_order(EVENT_SOURCES, cap=50),
        icypeas_ready=icypeas.has_api_key(),
        sources=sources,
        source_counts=db.count_event_sources(),
        directory_counts=db.count_companies_by_status(),
    )


@app.route("/scraping-engine/scrape", methods=["POST"])
def scraping_engine_scrape():
    run_id = db.create_run("exhibitors", "Scrape exhibitors")
    log = RunLogger(run_id)
    try:
        result = scrape_event_sources(logger=log)
        result["scraped_at"] = _now()
        t = perf_counter()
        _save(KEY_EXHIBITORS, result)
        log.event("supabase_write", "saved exhibitors → app_cache",
                  duration_ms=(perf_counter() - t) * 1000)

        t = perf_counter()
        norm = normalize.normalize_exhibitors(result)
        log.event("normalize",
                  f"upserted {norm['inserted_or_updated']}/{norm['total']} into companies "
                  f"(skipped {norm['skipped']})",
                  duration_ms=(perf_counter() - t) * 1000)
        db.finish_run(run_id)
        ok = sum(1 for s in result["sources"] if s["status"] == "ok")
        flash(
            f"Scraped {result['count']} unique exhibitors from {ok}/{len(result['sources'])} "
            f"source(s).",
            "success" if result["count"] else "error",
        )
    except Exception as exc:  # noqa: BLE001
        log.event("error", str(exc), status="error")
        db.finish_run(run_id, "error")
        flash(f"Scrape failed: {exc}", "error")
    return redirect(url_for("scraping_engine"))


@app.route("/scraping-engine/enrich", methods=["POST"])
def scraping_engine_enrich():
    company = (request.form.get("company") or "").strip()
    if not company:
        flash("No company name supplied.", "error")
        return redirect(url_for("scraping_engine"))

    # A missing key is a server-config issue, not a per-company result -- flash it
    # and bail so it never gets persisted into the enrichment cache.
    if not icypeas.has_api_key():
        flash("Icypeas enrichment is disabled — ICYPEAS_API_KEY is not set on the server.", "error")
        return redirect(url_for("scraping_engine"))

    run_id = db.create_run("enrich", f"Find people · {company}")
    log = RunLogger(run_id)
    result = icypeas.find_people(company, logger=log)
    result["enriched_at"] = _now()
    store = _load(KEY_ENRICHMENT, {})
    store[company] = result
    t = perf_counter()
    _save(KEY_ENRICHMENT, store)
    log.event("supabase_write", "saved enrichment → app_cache",
              duration_ms=(perf_counter() - t) * 1000)
    db.finish_run(run_id, "finished" if result["ok"] else "error")

    if result["ok"]:
        flash(f"Icypeas: found {result['count']} contact(s) for '{company}'.", "success")
    else:
        flash(f"Icypeas error for '{company}': {result['error']}", "error")
    return redirect(url_for("scraping_engine") + f"#company-{company.replace(' ', '-')}")


@app.route("/content-engine")
def content_engine():
    media = _load(KEY_MEDIA, {})
    sources = dedupe_keep_order(MEDIA_SOURCES)
    return render_template(
        "content_engine.html",
        active="content",
        sources=sources,
        media=media,
    )


@app.route("/content-engine/scrape", methods=["POST"])
def content_engine_scrape():
    url = (request.form.get("url") or "").strip()
    targets = dedupe_keep_order(MEDIA_SOURCES)
    if url and url not in targets:
        flash("Unknown source URL.", "error")
        return redirect(url_for("content_engine"))

    to_scrape = [url] if url else targets  # blank = scrape all
    label = f"Scrape {url}" if url else f"Scrape all media ({len(targets)} sources)"
    run_id = db.create_run("media", label)
    log = RunLogger(run_id)

    store = _load(KEY_MEDIA, {})
    for target in to_scrape:
        result = scrape_media(target, logger=log)
        result["scraped_at"] = _now()
        store[target] = result
        t = perf_counter()
        _save(KEY_MEDIA, store)  # incremental: each source persists as it completes
        log.event("supabase_write", f"saved {target}", duration_ms=(perf_counter() - t) * 1000)
    db.finish_run(run_id)

    # Kicked off via keepalive fetch (the "Scrape all" button) -- no page is
    # waiting on the response, so just acknowledge.
    if request.args.get("format") == "json":
        ok = sum(1 for t in to_scrape if store.get(t, {}).get("ok"))
        return jsonify({"run_id": run_id, "scraped": ok, "total": len(to_scrape)})

    if url:
        r = store[url]
        if r.get("ok"):
            flash(f"Scraped '{r.get('title') or url}' ({r.get('listing_count', 0)} listings).", "success")
        else:
            flash(f"Failed to scrape {url}: {r.get('error')}", "error")
    else:
        ok = sum(1 for t in targets if store.get(t, {}).get("ok"))
        flash(f"Scraped {ok}/{len(targets)} media sources.", "success" if ok else "error")
    return redirect(url_for("content_engine"))


@app.route("/logs")
def logs():
    return render_template(
        "logs.html",
        active="logs",
        runs=db.get_runs(limit=30),
        latest=db.get_latest_run(),
        cumulative=db.cumulative_spend(),
        usd_per_credit=costs.USD_PER_CREDIT,
    )


@app.route("/logs/events")
def logs_events():
    """Polled by the Logs+Costs tab. Returns the latest (or a given) run plus its
    events after ``after`` (event id cursor), and cumulative spend."""
    after = request.args.get("after", default=0, type=int)
    run_id = request.args.get("run_id")
    run = db.get_run(run_id) if run_id else db.get_latest_run()
    events = db.get_events(run["run_id"], after) if run else []
    return jsonify({"run": run, "events": events, "cumulative": db.cumulative_spend()})


@app.route("/scraping-engine/sources", methods=["POST"])
def scraping_engine_sources_add():
    url = (request.form.get("url") or "").strip()
    label = (request.form.get("label") or "").strip()
    parser = (request.form.get("parser") or "unsupported").strip()
    if not url:
        flash("URL required.", "error")
        return redirect(url_for("scraping_engine"))
    if parser not in {"foodtech", "easyfairs", "algolia", "safetyevent", "unsupported"}:
        parser = "unsupported"
    sid = db.upsert_event_source(url=url, label=label, parser=parser)
    flash(f"Saved source #{sid}: {label or url}", "success")
    return redirect(url_for("scraping_engine"))


@app.route("/scraping-engine/sources/<int:sid>/delete", methods=["POST"])
def scraping_engine_sources_delete(sid):
    db.delete_event_source(sid)
    flash(f"Deleted source #{sid}.", "success")
    return redirect(url_for("scraping_engine"))


@app.route("/scraping-engine/sources/<int:sid>/scrape", methods=["POST"])
def scraping_engine_sources_scrape(sid):
    """Server-side: scrape one source, upsert each exhibitor into companies,
    mark the source as scraped. Returns JSON with count for the JS orchestrator."""
    source = db.get_event_source(sid)
    if not source:
        return jsonify({"error": "not_found"}), 404

    run_id = db.create_run("source_scrape",
                           f"Scrape source: {source.get('label') or source['url']}")
    log = RunLogger(run_id)
    try:
        result = event_sources_module.scrape_source(source, logger=log)
        added = updated = 0
        for ex in result["exhibitors"]:
            cid = db.upsert_company_from_exhibitor(ex)
            if cid:
                added += 1
        t = perf_counter()
        # Persist bookkeeping on the source row
        db.mark_source_scraped(sid, result["count"], error=result.get("error"),
                               meta_update=result.get("meta_update"))
        log.event("source_persist",
                  f"upserted {added} into companies · "
                  f"marked source scraped at now()",
                  duration_ms=(perf_counter() - t) * 1000)
        db.finish_run(run_id, "finished" if not result["error"] else "error")
    except Exception as exc:  # noqa: BLE001
        log.event("error", str(exc), status="error")
        db.finish_run(run_id, "error")
        return jsonify({"error": str(exc), "run_id": run_id}), 500

    if request.args.get("format") == "json":
        return jsonify({
            "run_id": run_id,
            "source_id": sid,
            "count": result["count"],
            "upserted": added,
            "error": result.get("error"),
        })
    flash(f"Scraped {source.get('label') or source['url']}: "
          f"{result['count']} exhibitors → upserted {added} companies.",
          "success" if result["count"] and not result["error"] else "error")
    return redirect(url_for("scraping_engine"))


@app.route("/companies")
def companies():
    status = request.args.get("status")  # 'pending' | 'enriched' | 'terminal' | None
    return render_template(
        "companies.html",
        active="companies",
        rows=db.list_companies(status=status),
        counts=db.count_companies_by_status(),
        filter_status=status,
    )


@app.route("/companies/normalize", methods=["POST"])
def companies_normalize():
    run_id = db.create_run("normalize", "Normalize exhibitors → companies")
    log = RunLogger(run_id)
    t = perf_counter()
    result = normalize.normalize_exhibitors()
    log.event("normalize",
              f"upserted {result['inserted_or_updated']}/{result['total']} "
              f"(skipped {result['skipped']})",
              duration_ms=(perf_counter() - t) * 1000)
    db.finish_run(run_id)
    flash(f"Normalized {result['inserted_or_updated']} companies "
          f"(skipped {result['skipped']}).",
          "success" if result["inserted_or_updated"] else "error")
    return redirect(url_for("companies"))


@app.route("/companies/enrich", methods=["POST"])
def companies_enrich():
    """Enrich a single company (per-row button)."""
    cid = int(request.form["id"])
    company = db.get_company(cid)
    if not company:
        flash("Company not found.", "error")
        return redirect(url_for("companies"))

    run_id = db.create_run("enrich_company", f"Enrich · {company['name']}")
    log = RunLogger(run_id)
    report = enrichment_cascade.enrich_one(company, logger=log)
    db.finish_run(run_id)

    if report["filled_fields"]:
        flash(f"Filled {len(report['filled_fields'])} field(s) for "
              f"{company['name']} via {'+'.join(report['hit_sources']) or '(none)'} "
              f"(cost ${report['usd']:.4f}).",
              "success")
    else:
        flash(f"No new data for {company['name']} — marked terminal.", "error")
    return redirect(url_for("companies"))


@app.route("/companies/enrich-all", methods=["POST"])
def companies_enrich_all():
    """Bulk-enrich pending companies in a chunk. The client's JS loop calls this
    repeatedly with a small ``?limit`` until ``remaining_pending`` reaches 0 --
    each request stays well under Heroku's 30s router timeout even at ~10s per
    company."""
    limit = max(1, min(int(request.args.get("limit", 10)), 50))
    pending = db.list_companies(status="pending", limit=limit)

    run_id = db.create_run("enrich_batch",
                           f"Enrich batch ({len(pending)} of pending)")
    log = RunLogger(run_id)
    totals = {"filled": 0, "terminal": 0, "usd": 0.0, "credits": 0.0}
    for c in pending:
        report = enrichment_cascade.enrich_one(c, logger=log)
        totals["usd"] += report["usd"]
        totals["credits"] += report["credits"]
        if report["filled_fields"]:
            totals["filled"] += 1
        else:
            totals["terminal"] += 1
    log.event("batch_summary",
              f"{totals['filled']} enriched, {totals['terminal']} terminal, "
              f"${totals['usd']:.4f} in this batch",
              credits=totals["credits"])
    db.finish_run(run_id)

    remaining = db.count_companies_by_status().get("pending", 0)

    if request.args.get("format") == "json":
        return jsonify({
            "run_id": run_id,
            "processed": len(pending),
            "remaining_pending": remaining,
            **totals,
        })
    flash(f"Batch: enriched {totals['filled']}, terminal {totals['terminal']} "
          f"(${totals['usd']:.4f}). Remaining pending: {remaining}.",
          "success" if totals["filled"] else "error")
    return redirect(url_for("companies"))


def _gather_stats(window: str) -> dict:
    counts = db.count_companies_by_status()
    return {
        "window": window,
        "directory": {
            "total": counts.get("total", 0),
            "pending": counts.get("pending", 0),
            "enriched": counts.get("enriched", 0),
            "terminal": counts.get("terminal", 0),
            "cumulative": db.cumulative_spend(),
        },
        "cascade": db.cascade_by_source_with_deltas(window),
        "fill_rates": db.field_fill_rates(),
        "sources": db.source_distribution(),
        "top_industries": db.top_industries(15),
        "top_locations": db.top_locations(15),
        "top_categories": db.top_categories(15),
        "runs": db.get_runs(limit=20),
        "daily_cost": db.daily_cost(14),
        "pipelines": {
            "jobs": {
                "summary": db.pipeline_summary("jobs"),
                "top": db.top_pipeline_sources("jobs", 10),
            },
            "articles": {
                "summary": db.pipeline_summary("articles"),
                "top": db.top_pipeline_sources("articles", 10),
            },
        },
    }


@app.route("/stats")
def stats():
    window = request.args.get("window", "7d")
    if window not in ("24h", "7d", "30d", "all"):
        window = "7d"
    return render_template(
        "stats.html",
        active="stats",
        stats=_gather_stats(window),
    )


@app.route("/stats/data")
def stats_data():
    window = request.args.get("window", "7d")
    if window not in ("24h", "7d", "30d", "all"):
        window = "7d"
    return jsonify(_gather_stats(window))


@app.route("/logs/<run_id>")
def run_detail_view(run_id):
    data = db.run_detail(run_id)
    return render_template("run_detail.html", active="logs", **data)


def _pipeline_view(kind: str, template: str):
    """Shared render for /jobs and /articles: list items + filters + summary."""
    since_map = {"24h": "1 day", "7d": "7 days", "all": None}
    since_key = request.args.get("since", "all")
    since = since_map.get(since_key)
    company_q = (request.args.get("company") or "").strip() or None
    company_id = None
    if company_q:
        for c in db.list_companies():
            if company_q.lower() in c["name"].lower():
                company_id = c["id"]; break
    items = (db.list_jobs(company_id=company_id, since=since, limit=500)
             if kind == "jobs"
             else db.list_articles(company_id=company_id, since=since, limit=500))
    return render_template(
        template, active=kind,
        summary=db.pipeline_summary(kind),
        items=items,
        since=since_key,
        company_q=company_q or "",
    )


@app.route("/jobs")
def jobs():
    return _pipeline_view("jobs", "jobs.html")


@app.route("/articles")
def articles():
    return _pipeline_view("articles", "articles.html")


def _run_pipeline_batch(kind: str):
    """Chunked batch endpoint (used by the JS loop on each tab)."""
    limit = max(1, min(int(request.args.get("limit", 8)), 30))
    companies = db.companies_for_pipeline(kind, limit=limit)
    scraper = (jobs_pipeline.scrape_jobs_for_company if kind == "jobs"
               else articles_pipeline.scrape_articles_for_company)

    run_kind = f"{kind}_pipeline"
    run_id = db.create_run(run_kind, f"{kind.capitalize()} batch ({len(companies)})")
    log = RunLogger(run_id)
    totals = {"processed": 0, "items_new": 0, "items_seen": 0, "errors": 0}
    for c in companies:
        r = scraper(c, logger=log)
        totals["processed"] += 1
        totals["items_new"] += r["new"]
        totals["items_seen"] += r["count"]
        if r.get("error"):
            totals["errors"] += 1
    log.event("batch_summary",
              f"{totals['processed']} companies · {totals['items_seen']} items seen "
              f"({totals['items_new']} new) · {totals['errors']} errors")
    db.finish_run(run_id)
    remaining = db.count_companies_for_pipeline(kind)

    if request.args.get("format") == "json":
        return jsonify({"run_id": run_id, **totals, "remaining": remaining})
    flash(f"{kind.capitalize()} batch: {totals['items_new']} new items across "
          f"{totals['processed']} companies. {remaining} remaining.",
          "success" if totals["items_seen"] else "error")
    return redirect(url_for("jobs" if kind == "jobs" else "articles"))


@app.route("/jobs/run", methods=["POST"])
def jobs_run():
    return _run_pipeline_batch("jobs")


@app.route("/articles/run", methods=["POST"])
def articles_run():
    return _run_pipeline_batch("articles")


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
