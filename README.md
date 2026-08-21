# tutti-bot

A Python bot that watches [tutti.ch](https://www.tutti.ch) — Switzerland's largest classifieds site — for listings matching your interests, uses an LLM to judge *actual* relevance instead of keyword matching, and emails you the ones worth seeing.

Runs unattended on a schedule (systemd timer / cron), scrapes without a browser, and fails loudly instead of silently sending you junk when something's misconfigured.

## Why

Free and cheap listings on tutti.ch move fast and get flooded with things you don't want. Manually re-checking a search every day doesn't scale, and a plain keyword filter can't tell "free firewood" from "free firewood-scented candle." This bot re-checks for you on a timer and uses an LLM to make the actual judgment call — "is this the kind of thing I described I'm looking for?" — instead of pattern matching.

## How it works

```
tutti.ch search URL
        │
        ▼
  scraper.py   ── HTTP GET, parses the __NEXT_DATA__ JSON tutti.ch's
        │           Next.js frontend embeds in the page — no browser,
        │           no Selenium/Playwright.
        ▼
  state.py     ── tracks already-seen listing IDs (JSON file) so you're
        │           only notified about genuinely new listings.
        ▼
  filter.py    ── batches new listings to Groq (fast LLM inference),
        │           asks it to score 1–10 against a free-text description
        │           of what you're looking for.
        ▼
  notifier.py  ── emails everything above your score threshold; pushes
                    a ntfy alert if the run failed instead.
```

## Design decisions worth mentioning

- **Multiple independent searches, one config, one process.** Add a `name` + a tutti.ch search URL under `searches:` in `config.yml` and you have a new, independently-filtered search — different region, different price range, different interests, whatever the URL supports. No code changes, no new file, one shared systemd timer runs all of them.
- **Fail loud, not silent.** A missing API key or a broken config aborts the run and fires a push alert — the bot never falls back to "just email everything, unfiltered" because the filter step is broken.
- **Fully mocked test suite.** All 62 tests run in well under a second with zero network access — no live site, no LLM API calls — so they run in CI on every push (see `.github/workflows/test.yml`) and locally without needing real credentials.
- **No browser automation.** tutti.ch's frontend is a Next.js app that ships its initial data as JSON embedded in the page (`<script id="__NEXT_DATA__">`). A plain HTTP GET plus a regex and `json.loads` gets structured data directly — far faster and more reliable than driving a headless browser.
- **The scraper isn't limited to free listings**, despite the name — any tutti.ch search URL works, price filter included. The LLM prompt considers price as a factor when scoring relevance.

## Quickstart

```bash
git clone <this-repo>
cd tutti-bot
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp config.yml.example config.yml
# edit config.yml: SMTP credentials, a Groq API key, at least one search
venv/bin/python main.py --dry-run
```

Get a free Groq API key at [console.groq.com/keys](https://console.groq.com/keys) — no billing required for the models this bot uses. For Gmail SMTP you'll need an [app password](https://myaccount.google.com/apppasswords) (requires 2FA).

To find a `free_url` for a search: open tutti.ch, set whatever filters you want (region, price, keyword), and copy the resulting URL.

## Configuration

See [`config.yml.example`](config.yml.example) for the full annotated schema. Briefly:

- Top-level `email`, `groq_api_key`, `groq_model`, `location`, and `ntfy` are shared across all searches.
- Each entry under `searches` needs at least `name` and `free_url`, and can override anything from the shared config (its own `interests`, `min_relevance_score`, `pages`, even a different `email.from`).
- Nothing here is Gratis-specific — the price range lives entirely in the URL you configure.

## Running the tests

```bash
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -v
```

Every external call (HTTP, Groq, SMTP, ntfy) is mocked, so the suite needs no credentials and no network access — it validates parsing logic, config merging, error handling, and the CLI wiring in isolation.

## Deployment

Built for a systemd timer:

```bash
bash install.sh   # creates the venv, config.yml, offers to install the timer
```

`tutti-bot.service` / `tutti-bot.timer` run `main.py` every 30 minutes. Any other scheduler (cron, a container with a sleep loop, etc.) works just as well — the bot itself is just `python main.py`, no daemon, no persistent process.

```bash
# manual dry-run, no email sent
venv/bin/python main.py --dry-run

# run one specific search
venv/bin/python main.py --search haupt

# forget everything a search has already reported, re-evaluate the current listings
venv/bin/python main.py --search haupt --reset
```

## Stack

Python 3.12 · [Groq API](https://groq.com) (Llama / open-weight models) · `requests` · `PyYAML` · `pytest` · systemd

## License

MIT — see [LICENSE](LICENSE).
