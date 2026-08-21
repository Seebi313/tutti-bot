import notifier
from notifier import _build_html, _card, _fmt_time, send_ntfy_alert, send_notification


def make_listing(**overrides):
    base = {
        "id": "1",
        "title": "Bohrmaschine",
        "description": "Funktioniert noch gut",
        "location": "Thun",
        "postcode": "3600",
        "url": "https://www.tutti.ch/de/vi/x/1",
        "timestamp": "2026-08-20T10:00:00Z",
        "score": 8,
        "reason": "Passt zu Werkzeug-Interesse",
    }
    base.update(overrides)
    return base


def test_send_ntfy_alert_skips_without_url_or_topic(monkeypatch):
    calls = []
    monkeypatch.setattr(notifier.requests, "post", lambda *a, **k: calls.append((a, k)))

    send_ntfy_alert({}, "Titel", "Body")
    send_ntfy_alert({"ntfy": {"url": "http://x"}}, "Titel", "Body")
    send_ntfy_alert({"ntfy": {"topic": "t"}}, "Titel", "Body")

    assert calls == []


def test_send_ntfy_alert_posts_with_correct_url_and_headers(monkeypatch):
    captured = {}

    def fake_post(url, data, headers, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers

        class Resp:
            pass
        return Resp()

    monkeypatch.setattr(notifier.requests, "post", fake_post)

    cfg = {"ntfy": {"url": "http://localhost:8081/", "topic": "tutti-bot"}}
    send_ntfy_alert(cfg, "Fehler", "Es ist etwas kaputt")

    assert captured["url"] == "http://localhost:8081/tutti-bot"
    assert captured["headers"]["Title"] == "Fehler"
    assert captured["data"] == "Es ist etwas kaputt".encode("utf-8")


def test_send_ntfy_alert_swallows_request_errors(monkeypatch):
    def fake_post(*a, **k):
        raise ConnectionError("kein Netz")

    monkeypatch.setattr(notifier.requests, "post", fake_post)

    cfg = {"ntfy": {"url": "http://localhost:8081", "topic": "tutti-bot"}}
    send_ntfy_alert(cfg, "Fehler", "Body")  # must not raise


def test_send_notification_uses_smtp_correctly(monkeypatch):
    calls = {}

    class FakeSMTP:
        def __init__(self, host, port):
            calls["host"] = host
            calls["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo(self):
            calls["ehlo"] = True

        def starttls(self):
            calls["starttls"] = True

        def login(self, user, password):
            calls["login"] = (user, password)

        def sendmail(self, from_addr, to_addr, msg):
            calls["sendmail"] = (from_addr, to_addr)

    monkeypatch.setattr(notifier.smtplib, "SMTP", FakeSMTP)

    cfg = {
        "email": {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_user": "me@example.com",
            "smtp_password": "app-pw",
            "to": "me@example.com",
        }
    }
    send_notification([make_listing()], cfg)

    assert calls["host"] == "smtp.gmail.com"
    assert calls["port"] == 587
    assert calls["login"] == ("me@example.com", "app-pw")
    assert calls["sendmail"][0] == "me@example.com"
    assert calls["sendmail"][1] == "me@example.com"


def test_build_html_includes_listing_title_and_count():
    html = _build_html([make_listing(title="Alte Bohrmaschine")])
    assert "Alte Bohrmaschine" in html
    assert "1 relevante Inserate" in html


def test_fmt_time_formats_iso_timestamp():
    assert _fmt_time("2026-08-20T10:05:00Z") == "20.08. 10:05"


def test_fmt_time_returns_raw_on_invalid_input():
    assert _fmt_time("nicht-eine-zeit") == "nicht-eine-zeit"


def test_fmt_time_empty_string():
    assert _fmt_time("") == ""


def test_card_shows_actual_price_not_hardcoded_gratis():
    card = _card(make_listing(price="CHF 50.–"))
    assert "CHF 50.–" in card
    assert "GRATIS" not in card


def test_card_falls_back_to_placeholder_when_price_missing():
    card = _card(make_listing(price=""))
    assert "💰 ?" in card


def test_card_escapes_untrusted_listing_fields():
    """Title/description/location/reason come from other people's tutti.ch
    ads — must be HTML-escaped, not interpolated raw into the email."""
    card = _card(make_listing(
        title='<img src=x onerror=alert(1)>',
        description='<script>evil()</script>',
        location='<b>Bern</b>',
        reason='<script>alert(2)</script>',
    ))
    assert "<img" not in card
    assert "<script>" not in card
    assert "<b>Bern</b>" not in card
    assert "&lt;img src=x onerror=alert(1)&gt;" in card
    assert "&lt;script&gt;evil()&lt;/script&gt;" in card
