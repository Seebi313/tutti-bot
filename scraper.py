"""Fetch and parse free listings from tutti.ch."""

import json
import logging
import re

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tutti.ch"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
}

# Default URL slug for "Gratis" filter + Bern location.
# To find your own: go to tutti.ch, set "Gratis" filter + your city, copy the URL path.
DEFAULT_FREE_URL = "https://www.tutti.ch/de/q/bern/Ak8DAlMDAkZSlcHJpY2XDwMCRk6hsb2NhdGlvbq1nZW8tY2l0eS1iZXJuBQ"


def fetch_free_listings(free_url: str = DEFAULT_FREE_URL, pages: int = 3) -> list[dict]:
    """Fetch free listings from tutti.ch, up to `pages` pages."""
    seen_ids: set[str] = set()
    results = []

    for page in range(pages):
        batch = _fetch_page(free_url, page)
        if not batch:
            break
        for listing in batch:
            if listing["id"] not in seen_ids:
                seen_ids.add(listing["id"])
                results.append(listing)
        logger.debug("Page %d: %d items, %d unique so far", page + 1, len(batch), len(results))
        if len(batch) < 20:
            break

    return results


def _fetch_page(free_url: str, page: int) -> list[dict]:
    params = {"sortby": "newest", "o": page * 20} if page > 0 else {"sortby": "newest"}
    try:
        resp = requests.get(free_url, headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        return _parse_next_data(resp.text)
    except requests.RequestException as e:
        logger.error("HTTP error on page %d: %s", page, e)
        return []


def _parse_next_data(html: str) -> list[dict]:
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        logger.warning("__NEXT_DATA__ not found in HTML response")
        return []
    try:
        data = json.loads(m.group(1))
        queries = data["props"]["pageProps"]["dehydratedState"]["queries"]
        for query in queries:
            state_data = query.get("state", {}).get("data", {})
            if "listings" in state_data:
                edges = state_data["listings"].get("edges", [])
                return [_normalize(e["node"]) for e in edges if "node" in e]
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        logger.error("Failed to parse __NEXT_DATA__: %s", e)
    return []


def _normalize(node: dict) -> dict:
    postcode_info = node.get("postcodeInformation", {})
    canton_info = postcode_info.get("canton", {})
    listing_id = node.get("listingID", "")
    seo = node.get("seoInformation", {})

    # Use SEO slug for a proper URL if available
    de_slug = seo.get("deSlug", "")
    url = (
        f"{BASE_URL}/de/vi/{de_slug}/{listing_id}"
        if de_slug
        else f"{BASE_URL}/de/vi/{listing_id}"
    )

    thumbnail = node.get("thumbnail", {}) or {}
    image_url = thumbnail.get("normalRendition", {}).get("src", "") if thumbnail else ""

    return {
        "id": listing_id,
        "title": node.get("title", ""),
        "description": node.get("body", ""),
        "price": node.get("formattedPrice", ""),
        "postcode": postcode_info.get("postcode", ""),
        "location": postcode_info.get("locationName", ""),
        "canton": canton_info.get("shortName", ""),
        "timestamp": node.get("timestamp", ""),
        "url": url,
        "image_url": image_url,
    }
