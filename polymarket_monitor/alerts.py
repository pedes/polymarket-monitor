"""Alert engine: evaluates divergence results and fires alerts with deduplication."""
import logging
from datetime import datetime, timedelta

from .analyser import DivergenceResult, compute_divergence, exceeds_threshold, format_divergence
from .config import settings
from . import db

logger = logging.getLogger(__name__)


async def _is_in_cooldown(market_id: str) -> bool:
    last = await db.get_last_alert_time(market_id)
    if last is None:
        return False
    last_dt = datetime.fromisoformat(last)
    cooldown = timedelta(hours=settings.alert_cooldown_hours)
    return datetime.utcnow() - last_dt < cooldown


async def evaluate_and_alert(notifier) -> list[DivergenceResult]:
    """
    Pull latest prices + NOAA data for every known market, compute divergence,
    and fire alerts for those that exceed the threshold and are not in cooldown.

    Returns list of DivergenceResult objects that were alerted.
    """
    markets = await db.get_all_markets()
    alerted: list[DivergenceResult] = []

    for market in markets:
        market_id = market["id"]
        question = market.get("question", market_id)

        price_row = await db.get_latest_price(market_id)
        noaa_row = await db.get_latest_noaa(market_id)

        if price_row is None or noaa_row is None:
            continue

        yes_price = price_row.get("yes_price")
        noaa_prob = noaa_row.get("implied_probability")

        if yes_price is None or noaa_prob is None:
            continue

        result = compute_divergence(market_id, question, yes_price, noaa_prob)

        if not exceeds_threshold(result, settings.divergence_threshold):
            continue

        if await _is_in_cooldown(market_id):
            logger.debug(f"Market {market_id} in cooldown, skipping alert")
            continue

        alert_id = await db.insert_alert(market_id, result.divergence, result.polymarket_prob, result.noaa_prob)

        if settings.dry_run:
            print(f"[DRY RUN] Alert #{alert_id}:\n{format_divergence(result)}\n")
        else:
            try:
                await notifier.send(result)
                await db.mark_alert_notified(alert_id)
            except Exception as e:
                logger.error(f"Failed to send alert #{alert_id}: {e}")

        alerted.append(result)

    return alerted
