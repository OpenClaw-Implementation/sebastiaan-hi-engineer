"""Scraping Engine -- parse Food Tech Event exhibitor cards into structured data.

Adapted from the reference parse_exhibitors.py: instead of reading a saved HTML
file it fetches the live "EVENT SOURCE" URL(s) with a direct cURL-style request
and parses every ``data-component="card-introduce"`` block with BeautifulSoup.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .fetcher import fetch_html
from .sources import EVENT_SOURCES, dedupe_keep_order


def clean_text(text: str | None) -> str:
    """Collapse whitespace, strip edges."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def parse_stand(raw: str) -> str:
    """Extract stand number from 'Stand: 151' format."""
    m = re.search(r"Stand:\s*(.+)", raw)
    return m.group(1).strip() if m else raw.strip()


def _abs_url(base: str, src: str | None) -> str:
    """Resolve a possibly-relative asset URL against the page URL."""
    if not src:
        return ""
    return urljoin(base, src)


def parse_exhibitors_html(html: str, base_url: str) -> list[dict]:
    """Parse exhibitor cards out of a page's HTML."""
    soup = BeautifulSoup(html, "html.parser")
    exhibitors: list[dict] = []

    cards = soup.find_all("div", attrs={"data-component": "card-introduce"})
    for card in cards:
        entry: dict = {}

        name_el = card.find("p", class_="card-introduce__name")
        entry["name"] = clean_text(name_el.get_text()) if name_el else ""

        desc_el = card.find("div", class_="card-introduce__description")
        entry["tagline"] = clean_text(desc_el.get_text()) if desc_el else ""

        stand_el = card.find("p", class_="card-introduce__stand")
        entry["stand"] = parse_stand(clean_text(stand_el.get_text())) if stand_el else ""

        raw_cats = card.get("data-categories", "")
        entry["categories"] = (
            [c.strip() for c in raw_cats.split(";") if c.strip()] if raw_cats else []
        )

        img_el = card.select_one(".card-introduce__image img")
        logo = ""
        if img_el:
            logo = img_el.get("src") or img_el.get("data-src") or ""
        entry["logo_url"] = _abs_url(base_url, logo)

        modal = card.find("div", class_="modal--exposant")
        if modal:
            full_el = modal.find("div", class_="modal__full-content")
            entry["description"] = clean_text(full_el.get_text()) if full_el else ""
            modal_img = modal.select_one(".modal__image")
            modal_src = ""
            if modal_img:
                modal_src = modal_img.get("src") or modal_img.get("data-src") or ""
            entry["image_url"] = _abs_url(base_url, modal_src)
        else:
            entry["description"] = ""
            entry["image_url"] = ""

        entry["source_url"] = base_url
        if entry["name"]:
            exhibitors.append(entry)

    return exhibitors


def scrape_event_sources(urls: list[str] | None = None) -> dict:
    """Fetch and parse the configured EVENT SOURCE URLs (first 50 unique).

    Returns a dict with the parsed exhibitors and a per-source report so the UI
    can show what happened with each URL.
    """
    urls = dedupe_keep_order(urls or EVENT_SOURCES, cap=50)

    all_exhibitors: list[dict] = []
    seen_names: set[str] = set()
    reports: list[dict] = []

    for url in urls:
        try:
            html = fetch_html(url)
            parsed = parse_exhibitors_html(html, url)
            new = 0
            for ex in parsed:
                key = ex["name"].lower()
                if key not in seen_names:
                    seen_names.add(key)
                    all_exhibitors.append(ex)
                    new += 1
            reports.append({"url": url, "status": "ok", "found": len(parsed), "added": new})
        except Exception as exc:  # noqa: BLE001 -- surface any failure to the UI
            reports.append({"url": url, "status": "error", "error": str(exc)})

    # Category breakdown (mirrors the reference script's summary).
    cats: dict[str, int] = {}
    for ex in all_exhibitors:
        for c in ex["categories"]:
            cats[c] = cats.get(c, 0) + 1

    return {
        "exhibitors": all_exhibitors,
        "count": len(all_exhibitors),
        "sources": reports,
        "categories": dict(sorted(cats.items(), key=lambda kv: -kv[1])),
    }
