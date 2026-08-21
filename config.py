"""Load and validate configuration from config.yml."""

import copy
import logging
import os

import yaml

logger = logging.getLogger(__name__)

DEFAULTS = {
    "location": {"home": "3000 Bern"},
    "interests": "Ich interessiere mich für nützliche Haushaltsgegenstände, Werkzeug, Möbel, Elektronik, Fahrräder und Bücher.",
    "min_relevance_score": 6,
    "pages": 3,
}


def load_config(path: str = "config.yml") -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Config nicht gefunden: {path}\n"
            "Bitte 'cp config.yml.example config.yml' ausführen und ausfüllen."
        )
    with open(path, encoding="utf-8") as f:
        user = yaml.safe_load(f) or {}

    cfg = _merge(copy.deepcopy(DEFAULTS), user)
    _validate(cfg)
    return cfg


def build_search_config(global_config: dict, search: dict) -> dict:
    """Merge one entry from `searches` onto the shared/global config.

    Lets a search override anything from the global config (interests,
    min_relevance_score, even nested dicts like email.from) while
    inheriting everything it doesn't set (groq_api_key, smtp settings, ntfy).
    """
    base = copy.deepcopy({k: v for k, v in global_config.items() if k != "searches"})
    return _merge(base, search)


def _merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            base[k] = _merge(base[k], v)
        else:
            base[k] = v
    return base


def _validate(cfg: dict):
    email = cfg.get("email", {})
    if not email.get("smtp_password"):
        raise ValueError("email.smtp_password fehlt in config.yml")
    if not email.get("to"):
        raise ValueError("email.to fehlt in config.yml")
    if not email.get("smtp_user"):
        raise ValueError("email.smtp_user fehlt in config.yml")
    if not cfg.get("groq_api_key"):
        logger.warning("groq_api_key nicht gesetzt — Bot bricht beim LLM-Filter ab")

    searches = cfg.get("searches")
    if not searches or not isinstance(searches, list):
        raise ValueError("searches fehlt oder ist leer in config.yml — mindestens eine Suche nötig")

    names = set()
    for search in searches:
        if not isinstance(search, dict) or not search.get("name"):
            raise ValueError("Jede Suche unter 'searches' braucht ein 'name'-Feld")
        if not search.get("free_url"):
            raise ValueError(f"Suche '{search['name']}' hat keine free_url")
        if search["name"] in names:
            raise ValueError(f"Such-Name '{search['name']}' ist mehrfach vergeben — Namen müssen eindeutig sein")
        names.add(search["name"])
