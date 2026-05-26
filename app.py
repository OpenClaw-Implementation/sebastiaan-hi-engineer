"""Hi-Engineer -- Heroku web app.

Two tabs:
  * Scraping Engine  -- scrapes the Food Tech Event exhibitor list (the
                        "EVENT SOURCE" URL from the workbook), structures the
                        exhibitors, and enriches each with Icypeas people search
                        keyed by company name.
  * Content Engine   -- scrapes the industrial/food "Media" portals and shows
                        the content for viewing.

All scraping uses direct cURL-style requests (no Firecrawl/Apify). Results are
cached as JSON in DATA_DIR so a tab renders instantly after a scrape (Heroku's
filesystem is ephemeral, so this cache resets when the dyno restarts).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

from scrapers import icypeas
from scrapers.exhibitors import scrape_event_sources
from scrapers.media import scrape_media
from scrapers.sources import EVENT_SOURCES, MEDIA_SOURCES, dedupe_keep_order

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hi-engineer-dev-secret")

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

EXHIBITORS_FILE = DATA_DIR / "exhibitors.json"
ENRICHMENT_FILE = DATA_DIR / "enrichment.json"
MEDIA_FILE = DATA_DIR / "media.json"


# --------------------------------------------------------------------------- #
# Tiny JSON store helpers
# --------------------------------------------------------------------------- #
def _load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return default
    return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
    data = _load(EXHIBITORS_FILE, None)
    enrichment = _load(ENRICHMENT_FILE, {})
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
    _save(EXHIBITORS_FILE, result)
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
    store = _load(ENRICHMENT_FILE, {})
    store[company] = result
    _save(ENRICHMENT_FILE, store)

    if result["ok"]:
        flash(f"Icypeas: found {result['count']} contact(s) for '{company}'.", "success")
    else:
        flash(f"Icypeas error for '{company}': {result['error']}", "error")
    return redirect(url_for("scraping_engine") + f"#company-{company.replace(' ', '-')}")


@app.route("/content-engine")
def content_engine():
    media = _load(MEDIA_FILE, {})
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

    store = _load(MEDIA_FILE, {})
    to_scrape = [url] if url else targets  # blank = scrape all
    for target in to_scrape:
        result = scrape_media(target)
        result["scraped_at"] = _now()
        store[target] = result
    _save(MEDIA_FILE, store)

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
