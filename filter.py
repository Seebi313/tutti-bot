"""LLM-based relevance filtering using Groq (free tier, no billing required)."""

import json
import logging
import re
import time

from groq import Groq

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-20b"
MODEL = "llama-3.3-70b-versatile"
BATCH_SIZE = 12


def filter_relevant(listings: list[dict], config: dict) -> list[dict]:
    """Score listings with Groq/Llama, return only those above min_relevance_score."""
    if not listings:
        return []

    api_key = config.get("groq_api_key", "")
    if not api_key:
        raise RuntimeError("groq_api_key fehlt in config.yml — LLM-Filter nicht möglich")

    min_score = config.get("min_relevance_score", 6)
    client = Groq(api_key=api_key)

    results = []
    for i in range(0, len(listings), BATCH_SIZE):
        if i:
            time.sleep(25)
        batch = listings[i : i + BATCH_SIZE]
        scored = _score_batch(batch, config, client)
        results.extend(l for l in scored if l.get("score", 0) >= min_score)

    return results


def _score_batch(listings: list[dict], config: dict, client: Groq) -> list[dict]:
    listings_text = "\n---\n".join(
        f"ID: {l['id']}\nTitel: {l['title']}\nPreis: {l.get('price', '')}\nBeschreibung: {l['description'][:150]}\nOrt: {l['location']} (PLZ {l['postcode']})"
        for l in listings
    )

    home = config.get("location", {}).get("home", "3000 Bern")
    interests = config.get("interests", "")

    prompt = f"""Du bewertest Inserate auf tutti.ch (Schweizer Kleinanzeigen) für jemanden in {home}.

Interessen und Bedürfnisse:
{interests}

Bewerte folgende Inserate (Skala 1-10):
- 9-10: Sehr interessant, unbedingt anschauen
- 7-8: Wahrscheinlich brauchbar
- 5-6: Vielleicht interessant
- 1-4: Nicht relevant (falsche Kategorie, zu weit entfernt, nicht brauchbar, Preis unangemessen)

Berücksichtige Nützlichkeit, Relevanz zu den Interessen, Preis/Leistung und Entfernung von {home}.

Antworte AUSSCHLIESSLICH mit einem JSON-Array (kein anderer Text):
[{{"id": "LISTING_ID", "score": ZAHL, "reason": "Kurze Begründung auf Deutsch"}}]

Inserate:
{listings_text}"""

    try:
        max_out = min(3000, 110 * len(listings) + 1200)
        response = client.chat.completions.create(
            model=config.get("groq_model", DEFAULT_MODEL),
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=max_out,
            temperature=0.1,
            reasoning_effort="low",
        )
        choice = response.choices[0]
        logger.debug("finish_reason=%s, completion_tokens=%s",
                    choice.finish_reason, response.usage.completion_tokens)
        logger.debug("Antwort (erste 400 Zeichen): %s", (choice.message.content or "")[:400])
        scores = _parse_json(choice.message.content)
        logger.debug("%d Scores geparst, Beispiel: %s", len(scores), scores[:2])
        if not scores:
            raise RuntimeError("Groq lieferte kein verwertbares JSON")
        score_map = {s["id"]: s for s in scores}
        for listing in listings:
            info = score_map.get(listing["id"], {})
            listing["score"] = info.get("score", 0)
            listing["reason"] = info.get("reason", "")
        return listings

    except Exception as e:
        logger.error("Groq API error: %s", e)
        raise

def _parse_json(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        logger.warning("No JSON array in response: %s", text[:300])
        return []
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        logger.error("JSON parse error: %s", e)
        return []
