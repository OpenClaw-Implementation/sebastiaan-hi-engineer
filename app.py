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
from datetime import datetime, timezone
from time import perf_counter

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

import costs
import db
import normalize
from enrichers import cascade as enrichment_cascade
from runlog import RunLogger
from scrapers import icypeas
from scrapers.exhibitors import scrape_event_sources
from scrapers.media import scrape_media
from scrapers.sources import EVENT_SOURCES, MEDIA_SOURCES, dedupe_keep_order

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hi-engineer-dev-secret")

db.init_db()


@app.context_processor
def _inject_db_health():
    """Expose the DB health flag to every template (drives the unavailable banner)."""
    return {"db_healthy": db.is_healthy()}

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
    return render_template(
        "scraping_engine.html",
        active="scraping",
        data=data,
        enrichment=enrichment,
        event_sources=dedupe_keep_order(EVENT_SOURCES, cap=50),
        icypeas_ready=icypeas.has_api_key(),
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
    """Bulk-enrich all pending companies server-side; JSON kicks it off and
    the browser is expected to navigate to /logs to watch it stream."""
    pending = db.list_companies(status="pending")
    run_id = db.create_run("enrich_batch",
                           f"Enrich all pending ({len(pending)} companies)")
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
    log.event("run_summary",
              f"{totals['filled']} enriched, {totals['terminal']} terminal, "
              f"${totals['usd']:.4f} total",
              credits=totals["credits"])
    db.finish_run(run_id)

    if request.args.get("format") == "json":
        return jsonify({"run_id": run_id, **totals, "processed": len(pending)})
    flash(f"Enriched {totals['filled']}, terminal {totals['terminal']} "
          f"(${totals['usd']:.4f}).",
          "success" if totals["filled"] else "error")
    return redirect(url_for("companies"))


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
