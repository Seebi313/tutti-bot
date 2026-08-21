import pytest

from config import build_search_config, load_config

VALID = {
    "email": {
        "smtp_password": "secret",
        "smtp_user": "me@example.com",
        "to": "me@example.com",
    },
    "searches": [
        {"name": "haupt", "free_url": "https://example.com/haupt"},
    ],
}


def write_yaml(path, data):
    import yaml
    path.write_text(yaml.dump(data), encoding="utf-8")


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(str(tmp_path / "nope.yml"))


def test_missing_smtp_password_raises(tmp_path):
    cfg = dict(VALID)
    cfg["email"] = {"smtp_user": "a@b.com", "to": "a@b.com"}
    p = tmp_path / "config.yml"
    write_yaml(p, cfg)
    with pytest.raises(ValueError, match="smtp_password"):
        load_config(str(p))


def test_missing_smtp_user_raises(tmp_path):
    cfg = dict(VALID)
    cfg["email"] = {"smtp_password": "x", "to": "a@b.com"}
    p = tmp_path / "config.yml"
    write_yaml(p, cfg)
    with pytest.raises(ValueError, match="smtp_user"):
        load_config(str(p))


def test_missing_to_raises(tmp_path):
    cfg = dict(VALID)
    cfg["email"] = {"smtp_password": "x", "smtp_user": "a@b.com"}
    p = tmp_path / "config.yml"
    write_yaml(p, cfg)
    with pytest.raises(ValueError, match="email.to"):
        load_config(str(p))


def test_missing_searches_raises(tmp_path):
    cfg = {"email": VALID["email"]}
    p = tmp_path / "config.yml"
    write_yaml(p, cfg)
    with pytest.raises(ValueError, match="searches"):
        load_config(str(p))


def test_empty_searches_list_raises(tmp_path):
    cfg = dict(VALID)
    cfg["searches"] = []
    p = tmp_path / "config.yml"
    write_yaml(p, cfg)
    with pytest.raises(ValueError, match="searches"):
        load_config(str(p))


def test_search_without_name_raises(tmp_path):
    cfg = dict(VALID)
    cfg["searches"] = [{"free_url": "https://example.com"}]
    p = tmp_path / "config.yml"
    write_yaml(p, cfg)
    with pytest.raises(ValueError, match="name"):
        load_config(str(p))


def test_search_without_free_url_raises(tmp_path):
    cfg = dict(VALID)
    cfg["searches"] = [{"name": "haupt"}]
    p = tmp_path / "config.yml"
    write_yaml(p, cfg)
    with pytest.raises(ValueError, match="free_url"):
        load_config(str(p))


def test_duplicate_search_names_raise(tmp_path):
    cfg = dict(VALID)
    cfg["searches"] = [
        {"name": "haupt", "free_url": "https://a.example.com"},
        {"name": "haupt", "free_url": "https://b.example.com"},
    ]
    p = tmp_path / "config.yml"
    write_yaml(p, cfg)
    with pytest.raises(ValueError, match="mehrfach vergeben"):
        load_config(str(p))


def test_valid_minimal_config_loads_with_defaults(tmp_path):
    p = tmp_path / "config.yml"
    write_yaml(p, VALID)
    cfg = load_config(str(p))
    assert cfg["email"]["smtp_password"] == "secret"
    assert cfg["location"]["home"] == "3000 Bern"
    assert cfg["min_relevance_score"] == 6
    assert len(cfg["searches"]) == 1


def test_missing_groq_api_key_does_not_raise(tmp_path, caplog):
    p = tmp_path / "config.yml"
    write_yaml(p, VALID)
    cfg = load_config(str(p))
    assert not cfg.get("groq_api_key")
    assert "groq_api_key" in caplog.text


def test_two_searches_supported(tmp_path):
    cfg = dict(VALID)
    cfg["searches"] = [
        {"name": "haupt", "free_url": "https://a.example.com", "min_relevance_score": 6},
        {"name": "defekte", "free_url": "https://b.example.com", "min_relevance_score": 5},
    ]
    p = tmp_path / "config.yml"
    write_yaml(p, cfg)
    cfg = load_config(str(p))
    assert [s["name"] for s in cfg["searches"]] == ["haupt", "defekte"]


def test_empty_config_file_raises_on_missing_email(tmp_path):
    p = tmp_path / "config.yml"
    p.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(str(p))


def test_build_search_config_inherits_global_and_applies_override():
    global_config = {
        "email": {"smtp_user": "a@b.com", "from": "Global <a@b.com>"},
        "groq_api_key": "gsk_global",
        "min_relevance_score": 6,
        "searches": [],
    }
    search = {
        "name": "defekte",
        "free_url": "https://example.com",
        "min_relevance_score": 5,
        "email": {"from": "Defekte <a@b.com>"},
    }
    cfg = build_search_config(global_config, search)

    assert cfg["groq_api_key"] == "gsk_global"  # inherited
    assert cfg["min_relevance_score"] == 5  # overridden
    assert cfg["email"]["smtp_user"] == "a@b.com"  # inherited nested key
    assert cfg["email"]["from"] == "Defekte <a@b.com>"  # overridden nested key
    assert "searches" not in cfg  # the list itself isn't leaked into a search's own config


def test_build_search_config_does_not_mutate_global_config():
    global_config = {"email": {"from": "Global"}, "searches": []}
    search = {"name": "x", "free_url": "https://example.com", "email": {"from": "Override"}}
    build_search_config(global_config, search)
    assert global_config["email"]["from"] == "Global"


def test_build_search_config_second_call_unaffected_by_first():
    """Regression: build_search_config used to deep-mutate nested dicts
    (like 'email') on the shared global config via a shallow copy, so a
    search with an override could silently leak into a later search's
    config within the same main.py loop iteration."""
    global_config = {"email": {"from": "Global"}, "searches": []}
    defekte = {"name": "defekte", "free_url": "https://b.example.com", "email": {"from": "Defekte"}}
    haupt = {"name": "haupt", "free_url": "https://a.example.com"}

    build_search_config(global_config, defekte)  # runs first, as it might in main.py's loop
    haupt_cfg = build_search_config(global_config, haupt)

    assert haupt_cfg["email"]["from"] == "Global"
