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

from flask import Flask, flash, redirect, render_template, request, url_for

import db
from scrapers import icypeas
from scrapers.exhibitors import scrape_event_sources
from scrapers.media import scrape_media
from scrapers.sources import EVENT_SOURCES, MEDIA_SOURCES, dedupe_keep_order

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hi-engineer-dev-secret")

db.init_db()

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
    result = scrape_event_sources()
    result["scraped_at"] = _now()
    _save(KEY_EXHIBITORS, result)
    ok = sum(1 for s in result["sources"] if s["status"] == "ok")
    flash(
        f"Scraped {result['count']} unique exhibitors from {ok}/{len(result['sources'])} "
        f"source(s).",
        "success" if result["count"] else "error",
    )
    return redirect(url_for("scraping_engine"))


@app.route("/scraping-engine/enrich", methods=["POST"])
def scraping_engine_enrich():
    company = (request.form.get("company") or "").strip()
    if not company:
        flash("No company name supplied.", "error")
        return redirect(url_for("scraping_engine"))

    result = icypeas.find_people(company)
    result["enriched_at"] = _now()
    store = _load(KEY_ENRICHMENT, {})
    store[company] = result
    _save(KEY_ENRICHMENT, store)

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

    store = _load(KEY_MEDIA, {})
    to_scrape = [url] if url else targets  # blank = scrape all (no-JS fallback)
    for target in to_scrape:
        result = scrape_media(target)
        result["scraped_at"] = _now()
        store[target] = result
        _save(KEY_MEDIA, store)  # incremental: survives a router timeout

    # JSON mode (used by the client-side "Scrape all" loop) -- no flash/redirect.
    if request.args.get("format") == "json":
        r = store.get(url, {}) if url else {}
        return {
            "ok": r.get("ok", True),
            "url": url,
            "title": r.get("title", ""),
            "listing_count": r.get("listing_count", 0),
            "error": r.get("error"),
        }

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


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
