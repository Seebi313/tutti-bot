import json
from datetime import datetime, timedelta

from state import SeenListings


def test_new_id_not_seen(tmp_path):
    seen = SeenListings(path=str(tmp_path / "seen.json"))
    assert seen.has("123") is False


def test_add_marks_as_seen_and_persists(tmp_path):
    path = tmp_path / "seen.json"
    seen = SeenListings(path=str(path))
    seen.add("123")
    assert seen.has("123") is True

    reloaded = SeenListings(path=str(path))
    assert reloaded.has("123") is True


def test_add_many(tmp_path):
    seen = SeenListings(path=str(tmp_path / "seen.json"))
    seen.add_many(["1", "2", "3"])
    assert seen.has("1") and seen.has("2") and seen.has("3")
    assert seen.has("4") is False


def test_clear(tmp_path):
    seen = SeenListings(path=str(tmp_path / "seen.json"))
    seen.add("123")
    seen.clear()
    assert seen.has("123") is False


def test_cleanup_old_removes_stale_entries(tmp_path):
    path = tmp_path / "seen.json"
    old_ts = (datetime.now() - timedelta(days=40)).isoformat()
    recent_ts = datetime.now().isoformat()
    path.write_text(json.dumps({"old": old_ts, "recent": recent_ts}), encoding="utf-8")

    seen = SeenListings(path=str(path))
    seen.cleanup_old(days=30)

    assert seen.has("old") is False
    assert seen.has("recent") is True


def test_cleanup_old_keeps_recent_within_window(tmp_path):
    path = tmp_path / "seen.json"
    recent_ts = (datetime.now() - timedelta(days=5)).isoformat()
    path.write_text(json.dumps({"recent": recent_ts}), encoding="utf-8")

    seen = SeenListings(path=str(path))
    seen.cleanup_old(days=30)

    assert seen.has("recent") is True


def test_corrupt_state_file_starts_empty(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text("not valid json{{{", encoding="utf-8")

    seen = SeenListings(path=str(path))
    assert seen.has("anything") is False


def test_missing_state_file_starts_empty(tmp_path):
    seen = SeenListings(path=str(tmp_path / "does_not_exist.json"))
    assert seen.has("anything") is False
