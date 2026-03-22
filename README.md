# Polymarket Weather Monitor

A Python bot that monitors [Polymarket](https://polymarket.com) weather-related prediction markets, compares them against [NOAA](https://www.weather.gov) forecast data, and fires alerts when the divergence exceeds a configurable threshold.

## Architecture

```
polymarket_monitor/
├── config.py      # Pydantic-settings config from .env
├── db.py          # Async SQLite layer (aiosqlite)
├── poller.py      # Fetches markets (Gamma API), prices (CLOB API), NOAA forecasts
├── analyser.py    # Computes divergence scores
├── alerts.py      # Alert engine with deduplication & cooldown
└── notifier.py    # Telegram + Discord notification senders
main.py            # Entry point with APScheduler
```

### Flow

```
Poller ──► SQLite ──► Analyser ──► Alert engine ──► Notifier
              ▲                                       (Telegram / Discord)
       NOAA + CLOB
```

## Quickstart

### 1. Install dependencies

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — at minimum set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
# or DISCORD_WEBHOOK_URL
```

### 3. Run

```bash
# Continuous mode (polls every 15 min by default)
python main.py

# Override interval
python main.py --interval 5

# Single cycle, no notifications — useful for testing
python main.py --run-once --dry-run
```

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `POLYMARKET_GAMMA_URL` | `https://gamma-api.polymarket.com` | Gamma REST API base |
| `POLYMARKET_CLOB_URL` | `https://clob.polymarket.com` | CLOB API base |
| `NOAA_API_URL` | `https://api.weather.gov` | NOAA API base |
| `DB_PATH` | `polymarket_monitor.db` | SQLite file path |
| `POLL_INTERVAL_MINUTES` | `15` | Minutes between polls |
| `DIVERGENCE_THRESHOLD` | `20.0` | Alert threshold (percentage points) |
| `ALERT_COOLDOWN_HOURS` | `4` | Min hours between repeat alerts per market |
| `TELEGRAM_BOT_TOKEN` | _(empty)_ | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | _(empty)_ | Target chat/channel ID |
| `DISCORD_WEBHOOK_URL` | _(empty)_ | Discord channel webhook URL |
| `DRY_RUN` | `false` | Print alerts instead of sending |
| `LOG_LEVEL` | `INFO` | Python logging level |

## Notification setup

### Telegram
1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token
2. Invite the bot to a group or start a DM
3. Get your `chat_id` from `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`

### Discord
1. Server Settings → Integrations → Webhooks → New Webhook
2. Copy the webhook URL into `DISCORD_WEBHOOK_URL`

## Running tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

## How divergence is calculated

```
divergence = |polymarket_yes_price × 100  −  noaa_implied_probability × 100|
```

NOAA implied probability is derived from the gridpoint forecast text using:
- Explicit percentage-chance phrases (`"40 percent chance"`)
- Keyword heuristics (`"likely"` → 70%, `"chance"` → 35%, `"sunny"` → 5%)
- Hazard-specific dampening when the specific weather type isn't mentioned

An alert fires when `divergence ≥ DIVERGENCE_THRESHOLD` and the market is not in the cooldown window.

## Supported locations

The NOAA integration ships with grid-point mappings for: New York, Los Angeles, Chicago, Houston, Miami, Dallas, Phoenix, Seattle, Denver, Atlanta, Boston, San Francisco, New Orleans, Oklahoma City.

To add more, extend `LOCATION_GRID_MAP` in `polymarket_monitor/poller.py` using coordinates from `https://api.weather.gov/points/{lat},{lon}`.
