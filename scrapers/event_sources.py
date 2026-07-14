"""Event-source dispatch — one entry-point per URL, parser chosen from the row.

Three parsers today:

  - **foodtech**     : the ``data-component="card-introduce"`` layout used by
                       food-tech-event + mtconference. Reuses the existing
                       exhibitor parser.
  - **safetyevent**  : WordPress Logo Slider (partners listed as
                       ``<img class="custom-logo lazyload" alt="Name">``).
  - **algolia**      : Easyfairs exhibitor pages (empack, rotterdampw, etc.).
                       Sniffs Algolia appId / apiKey / indexName out of the
                       static HTML, then paginates the public search API for
                       the complete list. Falls back to anchor scraping if
                       config can't be found.

Sites tagged ``unsupported`` (LinkedIn / Provada / vakbeursenergie) return an
empty list with an explanatory error rather than throwing.

Every parser returns a list of dicts shaped for
``db.upsert_company_from_exhibitor``:

    {name, tagline, stand, categories, logo_url, description, source_url}
"""

from __future__ import annotations

import json
import re
from time import perf_counter
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from runlog import NULL

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
        elif parser == "safetyevent":
            result["exhibitors"] = _safetyevent(url, logger)
        elif parser == "algolia":
            exhibitors, meta = _algolia(url, source.get("meta") or {}, logger)
            result["exhibitors"] = exhibitors
            result["meta_update"] = meta or None
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
# Parser 3: algolia (Easyfairs)
# --------------------------------------------------------------------------- #
_APP_ID_RE = re.compile(r'"(?:applicationI|appI|app_i)[Dd]"\s*:\s*"([A-Z0-9]{6,})"')
_API_KEY_RE = re.compile(r'"(?:apiKey|search[Kk]ey)"\s*:\s*"([a-f0-9]{20,})"')
_INDEX_RE = re.compile(r'"indexName"\s*:\s*"([A-Za-z0-9_-]+)"')
_ALGOLIA_HOST_RE = re.compile(r'([A-Z0-9]{6,})-dsn\.algolia(?:net|\.net)')


def _extract_algolia_config(html: str) -> tuple[str | None, str | None, str | None]:
    """Best-effort extraction of (appId, apiKey, indexName)."""
    appid = None
    apikey = None
    index = None
    m = _APP_ID_RE.search(html)
    if m:
        appid = m.group(1)
    if not appid:
        h = _ALGOLIA_HOST_RE.search(html)
        if h:
            appid = h.group(1)
    m = _API_KEY_RE.search(html)
    if m:
        apikey = m.group(1)
    # Prefer index names containing 'exhibit' / 'stand'
    indexes = _INDEX_RE.findall(html)
    if indexes:
        preferred = [i for i in indexes
                     if any(kw in i.lower() for kw in ("exhibit", "stand", "expos"))]
        index = preferred[0] if preferred else indexes[0]
    return appid, apikey, index


def _extract_event_name(url: str) -> str | None:
    """Extract the ?stands[refinementList][eventName][0]=... event filter."""
    from urllib.parse import parse_qs
    q = parse_qs(urlparse(url).query)
    for key, vals in q.items():
        if "eventName" in key and vals:
            return vals[0]
    return None


def _algolia_hit_to_exhibitor(hit: dict, source_url: str) -> dict:
    """Map an Algolia hit to our exhibitor shape."""
    name = hit.get("name") or hit.get("companyName") or hit.get("title") or ""
    stand = hit.get("stand") or hit.get("boothNumber") or hit.get("standNumber") or ""
    if isinstance(stand, list):
        stand = ", ".join(str(s) for s in stand if s)
    tagline = hit.get("shortDescription") or hit.get("subtitle") or ""
    description = hit.get("description") or hit.get("longDescription") or ""
    cats = hit.get("categories") or hit.get("themes") or hit.get("tags") or []
    if isinstance(cats, str):
        cats = [cats]
    elif isinstance(cats, list):
        cats = [str(c) for c in cats if c]
    else:
        cats = []
    logo = hit.get("logo") or hit.get("logoUrl") or hit.get("logoImage") or ""
    if isinstance(logo, dict):
        logo = logo.get("url") or logo.get("src") or ""
    return {
        "name": _clean(str(name)),
        "tagline": _clean(str(tagline)),
        "stand": _clean(str(stand)),
        "categories": cats,
        "logo_url": logo,
        "description": _clean(str(description)),
        "source_url": source_url,
    }


def _algolia_paginate(appid: str, apikey: str, index: str,
                      event_filter: str | None, source_url: str,
                      logger) -> list[dict]:
    endpoint = f"https://{appid}-dsn.algolia.net/1/indexes/{index}/query"
    headers = {
        "X-Algolia-Application-Id": appid,
        "X-Algolia-API-Key": apikey,
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    params_parts = ["hitsPerPage=100"]
    if event_filter:
        # Algolia refinement list -> `facetFilters=eventName:<name>`
        # URL-encoded via facetFilters, but simpler:
        from urllib.parse import quote
        params_parts.append(f"facetFilters=%5B%5B%22eventName%3A{quote(event_filter, safe='')}%22%5D%5D")
    exhibitors: list[dict] = []
    seen: set[str] = set()
    for page in range(0, 20):  # hard cap 2000 items
        body = {"params": "&".join(params_parts + [f"page={page}"])}
        try:
            r = requests.post(endpoint, headers=headers,
                              data=json.dumps(body), timeout=DEFAULT_TIMEOUT)
        except requests.exceptions.RequestException as exc:
            logger.event("algolia_query", f"page {page} network error: {exc}",
                         status="error")
            break
        if r.status_code >= 400:
            logger.event("algolia_query",
                         f"page {page} http {r.status_code}: {r.text[:200]}",
                         status="error")
            break
        try:
            data = r.json()
        except ValueError:
            logger.event("algolia_query", f"page {page} non-JSON response",
                         status="error"); break
        hits = data.get("hits") or []
        nb_pages = int(data.get("nbPages") or 1)
        for h in hits:
            ex = _algolia_hit_to_exhibitor(h, source_url)
            if ex["name"] and ex["name"].lower() not in seen:
                seen.add(ex["name"].lower())
                exhibitors.append(ex)
        logger.event("algolia_query",
                     f"page {page + 1}/{nb_pages}  hits={len(hits)}  total_so_far={len(exhibitors)}")
        if page + 1 >= nb_pages:
            break
    return exhibitors


def _algolia_anchor_fallback(html: str, source_url: str, logger) -> list[dict]:
    """When we can't find Algolia config, at least grab the visible anchor
    text so we get the first-page exhibitors."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "header", "footer", "nav"]):
        tag.decompose()
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/exhibitor" not in href.lower():
            continue
        text = _clean(a.get_text())
        if not text or len(text) < 3 or len(text) > 200:
            continue
        if text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append({
            "name": text, "tagline": "", "stand": "",
            "categories": [], "logo_url": "", "description": "",
            "source_url": urljoin(source_url, href),
        })
    logger.event("parse", f"anchor fallback: {len(out)} exhibitor hrefs")
    return out


def _algolia(url: str, meta: dict, logger) -> tuple[list[dict], dict | None]:
    """Returns (exhibitors, meta_update). Uses cached Algolia config from `meta`
    when present; otherwise sniffs it from the page HTML and returns the found
    values so the caller can persist them."""
    appid = meta.get("appId")
    apikey = meta.get("apiKey")
    index = meta.get("indexName")
    meta_update: dict | None = None

    if not (appid and apikey and index):
        html = fetch_html(url, timeout=DEFAULT_TIMEOUT)
        appid, apikey, index = _extract_algolia_config(html)
        logger.event("algolia_config",
                     f"appId={appid or '-'}  apiKey={'set' if apikey else '-'}  "
                     f"index={index or '-'}",
                     status="ok" if (appid and apikey and index) else "error")
        if appid and apikey and index:
            meta_update = {"appId": appid, "apiKey": apikey, "indexName": index}
        else:
            # Fall back to anchor scraping — best-effort partial list
            return _algolia_anchor_fallback(html, url, logger), None

    event_filter = _extract_event_name(url)
    exhibitors = _algolia_paginate(appid, apikey, index, event_filter, url, logger)
    return exhibitors, meta_update
