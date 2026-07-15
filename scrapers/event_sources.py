"""Event-source dispatch — one entry-point per URL, parser chosen from the row.

Two parsers plus a graceful unsupported branch:

  - **foodtech**     : the ``data-component="card-introduce"`` layout used by
                       food-tech-event + mtconference. Reuses the existing
                       exhibitor parser.
  - **easyfairs**    : Easyfairs exhibitor pages (empack, rotterdampw, etc.).
                       Extracts SSR-rendered anchors that point at individual
                       exhibitor pages, derives clean company names from the
                       URL slugs, and dedupes by URL. Only the first-page set
                       is exposed by the SSR (rest is JS-loaded from Easyfairs'
                       auth-gated backend), so this recovers roughly the first
                       25–30 exhibitors per event. Fetching the full list would
                       need a headless browser (T4 Firecrawl path).
  - **unsupported**  : LinkedIn / Provada / Vakbeurs Energie / Safety Event —
                       all load their entries via JS or behind auth. Kept in
                       the table so they show up with a clear ``last_error``.
                       Fixable later by adding Firecrawl to the cascade.

Every parser returns a list of dicts shaped for
``db.upsert_company_from_exhibitor``:

    {name, tagline, stand, categories, logo_url, description, source_url}
"""

from __future__ import annotations

import re
from time import perf_counter
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from runlog import NULL

from . import firecrawl as firecrawl_client
from .exhibitors import parse_exhibitors_html
from .fetcher import DEFAULT_TIMEOUT, USER_AGENT, fetch_html


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #
def scrape_source(source: dict, logger=NULL) -> dict:
    """Run the parser configured on this event_source row.

    Returns ``{parser, url, count, exhibitors, error, meta_update}`` — the
    caller (route or bulk runner) upserts each exhibitor to ``companies``,
    then calls ``db.mark_source_scraped`` with count + error + meta_update.
    """
    url = source["url"]
    parser = (source.get("parser") or "unsupported").lower()
    label = source.get("label") or url

    logger.event("source_start", f"{label}  [{parser}]  {url}")
    t = perf_counter()
    result: dict = {"parser": parser, "url": url, "count": 0, "exhibitors": [],
                    "error": None, "meta_update": None}
    try:
        if parser == "foodtech":
            result["exhibitors"] = _foodtech(url, logger)
        elif parser in ("easyfairs", "algolia"):  # keep old name for back-compat
            result["exhibitors"] = _easyfairs(url, logger)
        elif parser == "firecrawl":
            exhibitors, credits = _firecrawl(url, source.get("meta") or {}, logger)
            result["exhibitors"] = exhibitors
            if credits:
                result["meta_update"] = {"last_credits_charged": credits}
        elif parser == "safetyevent":  # kept for future re-enablement; today: unsupported
            result["exhibitors"] = _safetyevent(url, logger)
        elif parser == "unsupported":
            result["error"] = "unsupported (JS-only or auth-gated)"
        else:
            result["error"] = f"unknown parser: {parser}"
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    result["count"] = len(result["exhibitors"])
    logger.event(
        "source_done",
        f"{label}: {result['count']} exhibitors" +
        (f" (error: {result['error']})" if result["error"] else ""),
        duration_ms=(perf_counter() - t) * 1000,
        status="ok" if not result["error"] else "error",
    )
    return result


# --------------------------------------------------------------------------- #
# Parser 1: foodtech  (card-introduce layout)
# --------------------------------------------------------------------------- #
def _foodtech(url: str, logger) -> list[dict]:
    html = fetch_html(url, timeout=DEFAULT_TIMEOUT)
    exhibitors = parse_exhibitors_html(html, url)
    logger.event("parse", f"card-introduce cards: {len(exhibitors)}")
    return exhibitors


# --------------------------------------------------------------------------- #
# Parser 2: safetyevent partners  (WordPress Logo Slider imgs)
# --------------------------------------------------------------------------- #
def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _safetyevent(url: str, logger) -> list[dict]:
    html = fetch_html(url, timeout=DEFAULT_TIMEOUT)
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for img in soup.find_all("img"):
        classes = " ".join(img.get("class") or [])
        alt = _clean(img.get("alt"))
        if "custom-logo" not in classes:
            continue
        if not alt or len(alt) < 3 or alt.lower() in ("logo", "custom logo"):
            continue
        key = alt.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "name": alt,
            "tagline": "",
            "stand": "",
            "categories": [],
            "logo_url": img.get("data-src") or img.get("src") or "",
            "description": "",
            "source_url": url,
        })
    logger.event("parse", f"safetyevent partners: {len(out)}")
    return out


# --------------------------------------------------------------------------- #
# Parser: easyfairs  (SSR-anchor extraction with URL-slug company names)
# --------------------------------------------------------------------------- #
# Easyfairs sites (empack, rotterdampw, mrprocessing, pumpsvalves,
# solidsrotterdam) SSR-render only the first ~25 exhibitors as static
# ``<a href="/exhibitors/<slug>-<id>/">`` links; the rest of the list is
# JS-loaded from ``my.easyfairs.com/backend`` behind session auth. Without a
# headless browser we can only recover the SSR set — but the URL slug gives us
# a clean company name (much better than the polluted anchor text).
#
# For full lists you'd need Firecrawl / Playwright (T4 tier).

_EASYFAIRS_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,}$")
_TRAILING_ID_RE = re.compile(r"-\d{4,}$")
_LANG_URL_PARTS = ("/en/", "/de/", "/fr/", "/nl/", "?lang=", "/page/")

# Post-title-case fix-ups for common abbreviations mangled by ``.title()``
_ABBREV_FIXUPS = (
    (re.compile(r"\bBv\b"), "BV"),
    (re.compile(r"\bNv\b"), "NV"),
    (re.compile(r"\bGmbh\b"), "GmbH"),
    (re.compile(r"\bLlc\b"), "LLC"),
    (re.compile(r"\bAg\b"), "AG"),
    (re.compile(r"\bBvba\b"), "BVBA"),
    (re.compile(r"\bSa\b"), "SA"),
    (re.compile(r"\bSl\b"), "SL"),
    (re.compile(r"\bSpa\b"), "SpA"),
)


def _slug_to_name(slug: str) -> str:
    """Turn ``altrimex-packaging-solutions-249562`` into ``Altrimex Packaging
    Solutions`` (strip trailing numeric id, hyphens → spaces, title-case,
    then fix common corp-suffix casing)."""
    clean = _TRAILING_ID_RE.sub("", slug)
    name = clean.replace("-", " ").title()
    for rx, sub in _ABBREV_FIXUPS:
        name = rx.sub(sub, name)
    return _clean(name)


def _easyfairs(url: str, logger) -> list[dict]:
    """Extract exhibitor cards from the SSR HTML: anchors matching
    ``/exhibitors/<slug>/`` become companies, with the name derived from the
    slug (clean + canonical) and dedupe done by URL."""
    html = fetch_html(url, timeout=DEFAULT_TIMEOUT)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "header", "footer", "nav"]):
        tag.decompose()

    out: list[dict] = []
    seen: set[str] = set()
    skipped_lang = 0

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/exhibitor" not in href.lower():
            continue
        # skip language switchers / pagination / trailing-index links
        low = href.lower()
        if any(part in low for part in _LANG_URL_PARTS):
            skipped_lang += 1
            continue

        abs_url = urljoin(url, href)
        slug = urlparse(abs_url).path.rstrip("/").split("/")[-1]
        # slug must look like a real company slug (not generic "exhibitors")
        if not _EASYFAIRS_SLUG_RE.match(slug):
            continue
        if abs_url in seen:
            continue
        seen.add(abs_url)

        name = _slug_to_name(slug)
        if not name or len(name) < 2:
            continue
        out.append({
            "name": name,
            "tagline": "",
            "stand": "",
            "categories": [],
            "logo_url": "",
            "description": "",
            "source_url": abs_url,
        })

    logger.event("parse",
                 f"easyfairs SSR anchors: {len(out)} exhibitors "
                 f"(skipped {skipped_lang} language-switcher hrefs)")
    return out


# --------------------------------------------------------------------------- #
# Parser: firecrawl  (JS-rendered pages via Firecrawl API)
# --------------------------------------------------------------------------- #
# For sites whose exhibitor list is only visible after JS runs. Fetches the
# rendered HTML via Firecrawl, then tries a battery of extractors (Provada
# `<a class="exhibitor">`, foodtech card-introduce, easyfairs URL-slug,
# safety-event custom-logo, generic anchor) and returns whichever yields the
# most results. `meta.strategy` can pin a specific extractor to skip auto-detect.

def _provada_extractor(html: str, source_url: str) -> list[dict]:
    """Provada: `<a class="exhibitor">` with nested `.premium` div + name + `.stand`."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for a in soup.find_all("a", class_="exhibitor"):
        text = _clean(a.get_text(" "))
        stand = ""
        stand_el = a.find(class_="stand")
        if stand_el:
            stand = _clean(stand_el.get_text()).replace("Stand ", "")
        # Company name = link text minus 'premium' prefix minus 'Stand N.NN' suffix
        name = re.sub(r"^premium\s*", "", text, flags=re.I)
        name = re.sub(r"\s*Stand\s+[\d.]+\s*$", "", name).strip()
        if not name or len(name) < 2:
            continue
        href = a.get("href") or ""
        out.append({
            "name": name, "tagline": "", "stand": stand,
            "categories": [], "logo_url": "", "description": "",
            "source_url": urljoin(source_url, href) if href else source_url,
        })
    return out


def _safetyevent_after_render_extractor(html: str, source_url: str) -> list[dict]:
    """Safety Event: after JS render, partner logos become `<img class="custom-logo">`
    but skip the site's own header logo (alt text contains 'SafetyEvent')."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for img in soup.find_all("img"):
        classes = " ".join(img.get("class") or [])
        alt = _clean(img.get("alt", ""))
        if "custom-logo" not in classes:
            continue
        if not alt or len(alt) < 3:
            continue
        if "safetyevent" in alt.lower() or alt.lower().startswith("logo van"):
            continue
        key = alt.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "name": alt, "tagline": "", "stand": "",
            "categories": [], "logo_url": img.get("src") or img.get("data-src") or "",
            "description": "", "source_url": source_url,
        })
    return out


def _generic_anchor_extractor(html: str, source_url: str) -> list[dict]:
    """Very generic: any anchor whose href contains /exposant|/exhibitor|/standhouder|/partner/."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "header", "footer", "nav"]):
        tag.decompose()
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        low = a["href"].lower()
        if not any(k in low for k in ("/exposant", "/exhibitor", "/standhouder", "/partner", "/deelnemer")):
            continue
        text = _clean(a.get_text())
        if not text or len(text) < 3 or len(text) > 200:
            continue
        if any(x in low for x in ("/en/", "/de/", "/fr/", "/page/", "?lang=")):
            continue
        abs_url = urljoin(source_url, a["href"])
        if abs_url in seen:
            continue
        seen.add(abs_url)
        out.append({
            "name": text, "tagline": "", "stand": "",
            "categories": [], "logo_url": "", "description": "",
            "source_url": abs_url,
        })
    return out


_EXTRACTORS = [
    ("provada", _provada_extractor),
    ("foodtech", lambda html, url: parse_exhibitors_html(html, url)),
    ("safetyevent", _safetyevent_after_render_extractor),
    ("generic_anchor", _generic_anchor_extractor),
]


def _firecrawl(url: str, meta: dict, logger) -> tuple[list[dict], int]:
    """Fetch via Firecrawl, then try extractors; return (exhibitors, credits_charged).
    ``meta.strategy`` pins a specific extractor name if set."""
    from .listing_extractor import extract_listings  # local import to avoid circular

    if not firecrawl_client.has_api_key():
        logger.event("firecrawl", "FIRECRAWL_API_KEY not set — skipped",
                     status="error")
        return [], 0

    t = perf_counter()
    result = firecrawl_client.scrape(url, wait_ms=5000, use_actions=True)
    logger.event("firecrawl_fetch",
                 f"rendered: {'ok' if result['ok'] else result.get('error')}  "
                 f"({len(result['html']):,} bytes, {result['credits_charged']} cr)",
                 duration_ms=(perf_counter() - t) * 1000,
                 status="ok" if result["ok"] else "error",
                 credits=float(result["credits_charged"]))
    if not result["ok"]:
        return [], result["credits_charged"]

    html = result["html"]
    strategy_hint = (meta.get("strategy") or "").lower()

    # If a strategy is pinned, use only that extractor
    if strategy_hint:
        for name, fn in _EXTRACTORS:
            if name == strategy_hint:
                out = fn(html, url)
                logger.event("firecrawl_extract",
                             f"strategy={name}: {len(out)} exhibitors")
                return out, result["credits_charged"]

    # Otherwise auto-detect: run every extractor, take the one with the most
    best_name = ""
    best_out: list[dict] = []
    for name, fn in _EXTRACTORS:
        try:
            out = fn(html, url)
        except Exception:  # noqa: BLE001 -- extractor bugs shouldn't kill the whole scrape
            out = []
        if len(out) > len(best_out):
            best_out = out
            best_name = name
    logger.event("firecrawl_extract",
                 f"best strategy={best_name or 'none'}: {len(best_out)} exhibitors")
    return best_out, result["credits_charged"]

