"""Generic listing-page extractor for jobs / articles / etc.

Given a page's HTML + a list of href-path substring hints (e.g. ``['/job',
'/vacature']`` for a careers page, ``['/blog', '/news']`` for an articles feed),
returns a deduped list of ``{title, url, snippet}`` entries pulled from
anchor tags whose href matches one of the hints.

Strips typical chrome (header/nav/footer/script/style/noscript) first so nav
links don't leak into the results, and filters out short/nav-noise anchor text.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

MIN_TITLE = 5
MAX_TITLE = 200
MAX_ITEMS = 200

_WS = re.compile(r"\s+")
_NAV_NOISE = re.compile(
    r"^(home|menu|login|inloggen|registreren|register|contact|cookie|privacy|"
    r"nieuws|news|over ons|about|zoeken|search|meer|meer info|read more|"
    r"lees meer|next|vorige|volgende|previous|nl|en|de|fr|»|←|→|share|delen)$",
    re.IGNORECASE,
)


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return _WS.sub(" ", text).strip()


def _href_matches(href: str, hints: list[str]) -> bool:
    href_l = href.lower()
    return any(h in href_l for h in hints)


def _grab_snippet(anchor) -> str | None:
    """Return a lede paragraph near the anchor (best-effort, bounded to 400c)."""
    for candidate in (
        anchor.find_next("p"),
        anchor.parent.find("p") if anchor.parent else None,
    ):
        if candidate is not None and hasattr(candidate, "get_text"):
            text = _clean(candidate.get_text())
            if text and len(text) > 20:
                return text[:400]
    return None


def extract_listings(html: str, base_url: str, link_hints: list[str]) -> list[dict]:
    """Extract ``[{title, url, snippet}]`` from a listing page.

    ``link_hints`` are lowercase substrings — a matching href on any ``<a>``
    element makes it a candidate. First-hit-wins by URL (dedupe).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Strip obvious chrome so nav anchors don't leak in.
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav", "form"]):
        tag.decompose()

    hints = [h.lower() for h in link_hints]
    seen: set[str] = set()
    out: list[dict] = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not _href_matches(href, hints):
            continue
        # A hash-only link or the same-page slug isn't a listing item.
        if href.startswith("#") or href.strip() in ("/", ""):
            continue
        title = _clean(a.get_text())
        if not title or len(title) < MIN_TITLE or len(title) > MAX_TITLE:
            continue
        if _NAV_NOISE.match(title):
            continue

        abs_url = urljoin(base_url, href)
        if abs_url in seen:
            continue
        seen.add(abs_url)
        out.append({"title": title, "url": abs_url, "snippet": _grab_snippet(a)})
        if len(out) >= MAX_ITEMS:
            break

    return out
