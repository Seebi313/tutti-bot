#!/usr/bin/env python3
"""Tutti.ch Gratis-Bot — durchläuft alle konfigurierten Suchen und benachrichtigt per Email."""

import argparse
import logging
import sys
from datetime import datetime

import yaml

from config import build_search_config, load_config
from filter import filter_relevant
from notifier import send_notification, send_ntfy_alert
from scraper import fetch_free_listings
from state import SeenListings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("tutti-bot.log"),
    ],
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Tutti.ch Gratis-Bot")
    parser.add_argument("--config", default="config.yml", help="Pfad zur config.yml")
    parser.add_argument("--search", help="Nur die Suche mit diesem 'name' ausführen (Default: alle)")
    parser.add_argument("--dry-run", action="store_true", help="Kein Email senden, nur anzeigen")
    parser.add_argument("--reset", action="store_true", help="Gesehene Inserate zurücksetzen")
    parser.add_argument("--debug", action="store_true", help="Debug-Logging aktivieren")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        logger.error("Konfigurationsfehler: %s", e)
        try:
            with open(args.config, encoding="utf-8") as f:
                raw_config = yaml.safe_load(f) or {}
            send_ntfy_alert(raw_config, "Tutti-Bot Konfigurationsfehler", str(e))
        except Exception:
            pass
        sys.exit(1)

    searches = config["searches"]
    if args.search:
        searches = [s for s in searches if s["name"] == args.search]
        if not searches:
            logger.error("Suche '%s' nicht in config.yml gefunden", args.search)
            sys.exit(1)

    had_error = False
    for search in searches:
        try:
            _run_search(search, config, args)
        except Exception as e:
            had_error = True
            logger.error("[%s] Suche abgebrochen: %s", search["name"], e, exc_info=True)
            ts = datetime.now().strftime("%d.%m.%Y %H:%M")
            send_ntfy_alert(config, f"Tutti-Bot Fehler ({search['name']})", f"{ts}\n{e}")

    if had_error:
        sys.exit(1)


def _run_search(search: dict, global_config: dict, args) -> None:
    name = search["name"]
    cfg = build_search_config(global_config, search)

    state_path = cfg.get("state_file", f"seen_{name}.json")
    seen = SeenListings(path=state_path)
    seen.cleanup_old(days=30)

    if args.reset:
        seen.clear()
        logger.info("[%s] Datenbank zurückgesetzt.", name)

    # 1. Inserate holen
    free_url = cfg["free_url"]
    pages = cfg.get("pages", 3)
    logger.info("[%s] Suche Gratis-Inserate (%d Seiten)…", name, pages)
    listings = fetch_free_listings(free_url=free_url, pages=pages)
    logger.info("[%s] %d Gratis-Inserate gefunden", name, len(listings))

    if not listings:
        logger.warning("[%s] Keine Inserate gefunden. Evtl. free_url prüfen.", name)
        return

    # 2. Bereits gesehene herausfiltern
    new = [l for l in listings if not seen.has(l["id"])]
    logger.info("[%s] %d davon neu (noch nicht gesehen)", name, len(new))

    if not new:
        logger.info("[%s] Nichts Neues. Fertig.", name)
        return

    # 3. LLM-Filter
    logger.info("[%s] Bewerte mit Groq…", name)
    relevant = filter_relevant(new, cfg)
    logger.info("[%s] %d Inserate als relevant eingestuft", name, len(relevant))

    # 4. Alle neuen als gesehen markieren (auch nicht-relevante)
    seen.add_many([l["id"] for l in new])

    if not relevant:
        logger.info("[%s] Nichts Relevantes. Fertig.", name)
        return

    # 5. Email senden
    if args.dry_run:
        logger.info("[%s] [DRY RUN] Würde Email senden mit %d Inseraten:", name, len(relevant))
        for r in sorted(relevant, key=lambda x: x.get("score", 0), reverse=True):
            logger.info("  [%d/10] %s — %s (%s)", r.get("score", 0), r["title"], r["location"], r["postcode"])
    else:
        send_notification(sorted(relevant, key=lambda x: x.get("score", 0), reverse=True), cfg)
        logger.info("[%s] Fertig!", name)


if __name__ == "__main__":
    main()
