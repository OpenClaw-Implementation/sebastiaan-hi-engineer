"""Content Engine -- scrape industrial / food media portals for viewing.

Each Media source is a supplier/company directory page. We fetch it with a
direct cURL-style request (no Firecrawl/Apify) and pull out:
  * page title + meta description
  * a list of company / listing entries
  * a cleaned plain-text rendering of the page (scripts/nav/styles stripped)

Where a portal's markup is known, a per-domain rule extracts clean company
names; otherwise a generic, noise-filtered fallback runs. Portals that build
their directory client-side (WordPress AJAX, JS frameworks) expose nothing in
the static HTML -- those are detected and flagged so the limitation is explicit.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .fetcher import fetch_html

MAX_TEXT_CHARS = 12000
MAX_LISTINGS = 400

# Per-domain extraction rules. "href" = anchors whose href contains the marker;
# "select" = CSS selector whose matched elements hold a company name.
DOMAIN_RULES: dict[str, dict] = {
    "installatieenbouw.nl": {"href": "/bedrijven/bedrijf/"},
    "industriebouw-online.nl": {"href": "/bedrijf/"},
    "vakbladvoedingsindustrie.nl": {"select": ".supplier-item h4"},
    "regiobedrijf.nl": {"select": ".companieslistcompany"},
    # Directory rendered client-side; static HTML is a news magazine shell only.
    "processcontrol.nl": {"dynamic": True},
}


def _rule_for(host: str) -> dict | None:
    host = host.replace("www.", "")
    return next((r for d, r in DOMAIN_RULES.items() if d in host), None)

_NAV_NOISE = re.compile(
    r"^(home|menu|login|inloggen|registreren|register|contact|cookie|privacy|"
    r"nieuws|news|over ons|about|zoeken|search|meer|meer info|read more|lees meer|"
    r"next|vorige|volgende|previous|nl|en|de|fr|»|←|→)$",
    re.IGNORECASE,
)
_PHONE = re.compile(r"^[\d\s()+\-./]{6,}$")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _slug_to_name(href: str) -> str:
    slug = [p for p in urlparse(href).path.split("/") if p]
    if not slug:
        return ""
    return slug[-1].replace("-", " ").replace("_", " ").strip().title()


def _is_company_name(name: str) -> bool:
    if not name or len(name) < 2 or len(name) > 120:
        return False
    if _NAV_NOISE.match(name):
        return False
    if _EMAIL.search(name) or _PHONE.match(name):
        return False
    if not re.search(r"[A-Za-zÀ-ſ]", name):  # needs at least one letter
        return False
    return True


def _add(listings: list[dict], seen: set[str], name: str, href: str = "") -> None:
    name = _clean(name)
    if not _is_company_name(name):
        return
    key = name.lower()
    if key in seen:
        return
    seen.add(key)
    listings.append({"name": name, "url": href})


def _extract_listings(soup: BeautifulSoup, base_url: str) -> list[dict]:
    listings: list[dict] = []
    seen: set[str] = set()

    rule = _rule_for(urlparse(base_url).netloc)
    if rule and rule.get("dynamic"):
        return []  # company list isn't in the static HTML

    if rule and "href" in rule:
        for a in soup.find_all("a", href=True):
            if rule["href"] in a["href"]:
                href = urljoin(base_url, a["href"])
                _add(listings, seen, a.get_text() or _slug_to_name(href), href)
    elif rule and "select" in rule:
        for el in soup.select(rule["select"]):
            a = el.find("a", href=True)
            href = urljoin(base_url, a["href"]) if a else ""
            _add(listings, seen, el.get_text(), href)

    # Generic fallback when no rule matched (or a rule found nothing).
    if not listings:
        candidates = soup.select(
            "article h2 a, article h3 a, .card h2 a, .card h3 a, li h2 a, li h3 a, "
            ".company a, .bedrijf a, .listing a, h2.entry-title a, h3.entry-title a"
        )
        if len(candidates) < 5:
            candidates += soup.select("article h2, article h3, .card h2, .card h3, .company, .bedrijf")
        for el in candidates:
            a = el if el.name == "a" else el.find("a", href=True)
            href = urljoin(base_url, a["href"]) if (a and a.get("href")) else ""
            _add(listings, seen, el.get_text(), href)

    return listings[:MAX_LISTINGS]


def _visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form", "header", "footer", "nav"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)[:MAX_TEXT_CHARS]


def scrape_media(url: str) -> dict:
    """Fetch one Media source URL and return structured, viewable content."""
    try:
        # Shorter timeout than the default so one slow portal can't blow the
        # request budget when scraping sources one after another.
        html = fetch_html(url, timeout=12)
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "ok": False, "error": str(exc)}

    soup = BeautifulSoup(html, "html.parser")
    title = _clean(soup.title.get_text()) if soup.title else ""
    desc_el = soup.find("meta", attrs={"name": "description"})
    description = _clean(desc_el.get("content")) if desc_el else ""

    listings = _extract_listings(soup, url)
    # Strip chrome for the text view (uses a fresh parse so listings keep markup).
    text = _visible_text(BeautifulSoup(html, "html.parser"))

    rule = _rule_for(urlparse(url).netloc)
    is_dynamic = bool(rule and rule.get("dynamic"))
    note = ""
    if not listings and (is_dynamic or (len(text) < 1500 and len(html) > 40000)):
        note = (
            "This portal builds its directory in the browser (JavaScript/AJAX); "
            "the static HTML returned by a direct request contains only the page "
            "shell, not the company listings."
        )

    return {
        "url": url,
        "ok": True,
        "title": title,
        "description": description,
        "listing_count": len(listings),
        "listings": listings,
        "text": text,
        "text_truncated": len(text) >= MAX_TEXT_CHARS,
        "note": note,
    }
