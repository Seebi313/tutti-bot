import json

import pytest
import requests

import scraper
from scraper import _normalize, _parse_next_data, fetch_free_listings


def _html_with_listings(nodes):
    payload = {
        "props": {
            "pageProps": {
                "dehydratedState": {
                    "queries": [
                        {
                            "state": {
                                "data": {
                                    "listings": {
                                        "edges": [{"node": n} for n in nodes]
                                    }
                                }
                            }
                        }
                    ]
                }
            }
        }
    }
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script></html>'


SAMPLE_NODE = {
    "listingID": "42",
    "title": "Alte Bohrmaschine",
    "body": "Funktioniert noch, Kabel leicht defekt.",
    "formattedPrice": "Gratis",
    "postcodeInformation": {
        "postcode": "3600",
        "locationName": "Thun",
        "canton": {"shortName": "BE"},
    },
    "timestamp": "2026-08-20T10:00:00Z",
    "seoInformation": {"deSlug": "alte-bohrmaschine"},
    "thumbnail": {"normalRendition": {"src": "https://img.example.com/1.jpg"}},
}


def test_parse_next_data_extracts_listings():
    html = _html_with_listings([SAMPLE_NODE])
    result = _parse_next_data(html)
    assert len(result) == 1
    assert result[0]["id"] == "42"
    assert result[0]["title"] == "Alte Bohrmaschine"


def test_parse_next_data_missing_script_returns_empty():
    assert _parse_next_data("<html><body>nichts hier</body></html>") == []


def test_parse_next_data_malformed_json_returns_empty():
    html = '<html><script id="__NEXT_DATA__" type="application/json">{not valid json</script></html>'
    assert _parse_next_data(html) == []


def test_normalize_builds_seo_url():
    result = _normalize(SAMPLE_NODE)
    assert result["url"] == "https://www.tutti.ch/de/vi/alte-bohrmaschine/42"
    assert result["postcode"] == "3600"
    assert result["location"] == "Thun"
    assert result["canton"] == "BE"
    assert result["image_url"] == "https://img.example.com/1.jpg"


def test_normalize_falls_back_to_id_only_url_without_slug():
    node = dict(SAMPLE_NODE)
    node["seoInformation"] = {}
    result = _normalize(node)
    assert result["url"] == "https://www.tutti.ch/de/vi/42"


def test_normalize_handles_missing_thumbnail():
    node = dict(SAMPLE_NODE)
    node["thumbnail"] = None
    result = _normalize(node)
    assert result["image_url"] == ""


def test_fetch_free_listings_deduplicates_and_stops_on_short_page(monkeypatch):
    call_count = {"n": 0}

    def fake_get(url, headers, params, timeout):
        call_count["n"] += 1
        nodes = [dict(SAMPLE_NODE, listingID=str(call_count["n"]))]
        resp = requests.Response()
        resp.status_code = 200
        resp._content = _html_with_listings(nodes).encode("utf-8")
        return resp

    monkeypatch.setattr(scraper.requests, "get", fake_get)
    results = fetch_free_listings(free_url="https://example.com", pages=5)

    assert call_count["n"] == 1
    assert len(results) == 1


def test_fetch_free_listings_handles_request_error(monkeypatch):
    def fake_get(url, headers, params, timeout):
        raise requests.RequestException("boom")

    monkeypatch.setattr(scraper.requests, "get", fake_get)
    results = fetch_free_listings(free_url="https://example.com", pages=3)

    assert results == []
