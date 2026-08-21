"""JSON-file-based tracking of seen listing IDs."""

import json
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen_listings.json")


class SeenListings:
    def __init__(self, path: str = STATE_PATH):
        self.path = path
        self._data: dict[str, str] = {}  # id -> iso timestamp
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Could not load state file: %s", e)
                self._data = {}

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f)

    def has(self, listing_id: str) -> bool:
        return listing_id in self._data

    def add(self, listing_id: str):
        self._data[listing_id] = datetime.now().isoformat()
        self._save()

    def add_many(self, listing_ids: list[str]):
        now = datetime.now().isoformat()
        for lid in listing_ids:
            self._data[lid] = now
        self._save()

    def clear(self):
        self._data = {}
        self._save()
        logger.info("Cleared seen listings")

    def cleanup_old(self, days: int = 30):
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        before = len(self._data)
        self._data = {k: v for k, v in self._data.items() if v >= cutoff}
        removed = before - len(self._data)
        if removed:
            self._save()
            logger.info("Removed %d stale entries (older than %d days)", removed, days)
