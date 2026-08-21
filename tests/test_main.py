import sys

import pytest

import main


def test_config_error_triggers_ntfy_alert(tmp_path, monkeypatch):
    """Regression test: a broken config.yml must still raise a ntfy alert,
    not just be logged silently (bug fixed 2026-08-21)."""
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "ntfy:\n  url: http://localhost:8081\n  topic: tutti-bot\n",
        encoding="utf-8",
    )

    def fake_load_config(path):
        raise ValueError("email.smtp_password fehlt in config.yml")

    alert_calls = []

    def fake_send_ntfy_alert(config, title, body):
        alert_calls.append((config, title, body))

    monkeypatch.setattr(main, "load_config", fake_load_config)
    monkeypatch.setattr(main, "send_ntfy_alert", fake_send_ntfy_alert)
    monkeypatch.setattr(sys, "argv", ["main.py", "--config", str(config_path)])

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 1
    assert len(alert_calls) == 1
    config, title, body = alert_calls[0]
    assert config["ntfy"]["topic"] == "tutti-bot"
    assert "Konfigurationsfehler" in title
    assert "smtp_password" in body


def test_config_error_with_unreadable_config_does_not_crash(monkeypatch):
    """If the config file itself is missing, the fallback read for the ntfy
    alert must fail silently instead of raising a second exception."""

    def fake_load_config(path):
        raise FileNotFoundError(f"Config nicht gefunden: {path}")

    alert_calls = []

    def fake_send_ntfy_alert(config, title, body):
        alert_calls.append((config, title, body))

    monkeypatch.setattr(main, "load_config", fake_load_config)
    monkeypatch.setattr(main, "send_ntfy_alert", fake_send_ntfy_alert)
    monkeypatch.setattr(sys, "argv", ["main.py", "--config", "/nonexistent/config.yml"])

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 1
    assert alert_calls == []  # no config to read ntfy settings from — must not crash


def _config_with_searches(*names):
    return {
        "email": {"smtp_password": "x", "smtp_user": "a@b.com", "to": "a@b.com"},
        "ntfy": {"url": "http://localhost:8081", "topic": "tutti-bot"},
        "searches": [{"name": n, "free_url": f"https://example.com/{n}"} for n in names],
    }


def test_runs_every_search_by_default(monkeypatch):
    config = _config_with_searches("haupt", "defekte")
    called_with = []

    monkeypatch.setattr(main, "load_config", lambda path: config)
    monkeypatch.setattr(main, "_run_search", lambda search, cfg, args: called_with.append(search["name"]))
    monkeypatch.setattr(sys, "argv", ["main.py"])

    main.main()

    assert called_with == ["haupt", "defekte"]


def test_search_flag_runs_only_that_search(monkeypatch):
    config = _config_with_searches("haupt", "defekte")
    called_with = []

    monkeypatch.setattr(main, "load_config", lambda path: config)
    monkeypatch.setattr(main, "_run_search", lambda search, cfg, args: called_with.append(search["name"]))
    monkeypatch.setattr(sys, "argv", ["main.py", "--search", "defekte"])

    main.main()

    assert called_with == ["defekte"]


def test_search_flag_with_unknown_name_exits_without_running_anything(monkeypatch):
    config = _config_with_searches("haupt")
    called_with = []

    monkeypatch.setattr(main, "load_config", lambda path: config)
    monkeypatch.setattr(main, "_run_search", lambda search, cfg, args: called_with.append(search["name"]))
    monkeypatch.setattr(sys, "argv", ["main.py", "--search", "nicht-vorhanden"])

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert exc_info.value.code == 1
    assert called_with == []


def test_one_search_failing_does_not_block_the_others(monkeypatch):
    """A broken search (e.g. dead free_url) must not prevent the remaining
    searches in the same run from executing."""
    config = _config_with_searches("haupt", "defekte")
    called_with = []
    alert_calls = []

    def fake_run_search(search, cfg, args):
        called_with.append(search["name"])
        if search["name"] == "haupt":
            raise RuntimeError("Groq API error")

    monkeypatch.setattr(main, "load_config", lambda path: config)
    monkeypatch.setattr(main, "_run_search", fake_run_search)
    monkeypatch.setattr(main, "send_ntfy_alert", lambda cfg, title, body: alert_calls.append((title, body)))
    monkeypatch.setattr(sys, "argv", ["main.py"])

    with pytest.raises(SystemExit) as exc_info:
        main.main()

    assert called_with == ["haupt", "defekte"]  # defekte still ran despite haupt failing
    assert exc_info.value.code == 1  # but the overall run is still reported as failed
    assert len(alert_calls) == 1
    assert "haupt" in alert_calls[0][0]
    assert "Groq API error" in alert_calls[0][1]


def test_all_searches_succeeding_exits_zero(monkeypatch):
    config = _config_with_searches("haupt")

    monkeypatch.setattr(main, "load_config", lambda path: config)
    monkeypatch.setattr(main, "_run_search", lambda search, cfg, args: None)
    monkeypatch.setattr(sys, "argv", ["main.py"])

    main.main()  # must not raise SystemExit at all


class FakeArgs:
    def __init__(self, dry_run=False, reset=False):
        self.dry_run = dry_run
        self.reset = reset


class FakeSeenListings:
    instances = []

    def __init__(self, path):
        self.path = path
        self.cleared = False
        self._seen = set()
        FakeSeenListings.instances.append(self)

    def cleanup_old(self, days):
        pass

    def clear(self):
        self.cleared = True
        self._seen = set()

    def has(self, listing_id):
        return listing_id in self._seen

    def add_many(self, listing_ids):
        self._seen.update(listing_ids)


def make_listing(lid):
    return {"id": lid, "title": f"Item {lid}", "location": "Bern", "postcode": "3000"}


def test_run_search_derives_state_file_from_name(monkeypatch):
    FakeSeenListings.instances = []
    monkeypatch.setattr(main, "SeenListings", FakeSeenListings)
    monkeypatch.setattr(main, "fetch_free_listings", lambda free_url, pages: [])

    search = {"name": "defekte", "free_url": "https://example.com"}
    main._run_search(search, _config_with_searches("defekte"), FakeArgs())

    assert FakeSeenListings.instances[0].path == "seen_defekte.json"


def test_run_search_respects_explicit_state_file_override(monkeypatch):
    FakeSeenListings.instances = []
    monkeypatch.setattr(main, "SeenListings", FakeSeenListings)
    monkeypatch.setattr(main, "fetch_free_listings", lambda free_url, pages: [])

    search = {"name": "haupt", "free_url": "https://example.com", "state_file": "seen_listings.json"}
    main._run_search(search, _config_with_searches("haupt"), FakeArgs())

    assert FakeSeenListings.instances[0].path == "seen_listings.json"


def test_run_search_dry_run_does_not_call_send_notification(monkeypatch):
    FakeSeenListings.instances = []
    monkeypatch.setattr(main, "SeenListings", FakeSeenListings)
    monkeypatch.setattr(main, "fetch_free_listings", lambda free_url, pages: [make_listing("1")])
    monkeypatch.setattr(main, "filter_relevant", lambda listings, cfg: [dict(l, score=9, reason="ok") for l in listings])

    sent = []
    monkeypatch.setattr(main, "send_notification", lambda listings, cfg: sent.append(listings))

    search = {"name": "haupt", "free_url": "https://example.com"}
    main._run_search(search, _config_with_searches("haupt"), FakeArgs(dry_run=True))

    assert sent == []


def test_run_search_marks_non_relevant_listings_as_seen(monkeypatch):
    """Non-relevant listings must still be recorded as seen, so the bot
    doesn't re-evaluate (and re-spend Groq quota on) the same ad forever."""
    FakeSeenListings.instances = []
    monkeypatch.setattr(main, "SeenListings", FakeSeenListings)
    monkeypatch.setattr(main, "fetch_free_listings", lambda free_url, pages: [make_listing("1")])
    monkeypatch.setattr(main, "filter_relevant", lambda listings, cfg: [])  # nothing relevant

    search = {"name": "haupt", "free_url": "https://example.com"}
    main._run_search(search, _config_with_searches("haupt"), FakeArgs())

    assert FakeSeenListings.instances[0].has("1") is True


def test_run_search_reset_clears_state_before_fetching(monkeypatch):
    FakeSeenListings.instances = []
    monkeypatch.setattr(main, "SeenListings", FakeSeenListings)
    monkeypatch.setattr(main, "fetch_free_listings", lambda free_url, pages: [])

    search = {"name": "haupt", "free_url": "https://example.com"}
    main._run_search(search, _config_with_searches("haupt"), FakeArgs(reset=True))

    assert FakeSeenListings.instances[0].cleared is True
