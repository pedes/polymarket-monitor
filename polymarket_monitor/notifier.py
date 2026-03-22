"""Send alert notifications via Telegram and/or Discord."""
import logging
from typing import Optional

import httpx

from .analyser import DivergenceResult, format_divergence
from .config import settings

logger = logging.getLogger(__name__)


def _build_message(result: DivergenceResult) -> str:
    return (
        f"🌦 *Polymarket Weather Alert*\n\n"
        f"{format_divergence(result)}\n\n"
        f"Market: {result.market_id}"
    )


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token
        self._chat_id = chat_id
        self._base = f"https://api.telegram.org/bot{token}"

    async def send(self, result: DivergenceResult) -> None:
        message = _build_message(result)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base}/sendMessage",
                json={"chat_id": self._chat_id, "text": message, "parse_mode": "Markdown"},
                timeout=15,
            )
            resp.raise_for_status()
        logger.info(f"Telegram alert sent for market {result.market_id}")


class DiscordNotifier:
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    async def send(self, result: DivergenceResult) -> None:
        message = _build_message(result)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._webhook_url,
                json={"content": message},
                timeout=15,
            )
            resp.raise_for_status()
        logger.info(f"Discord alert sent for market {result.market_id}")


class MultiNotifier:
    """Fans out to all configured notifiers."""

    def __init__(self, notifiers: list) -> None:
        self._notifiers = notifiers

    async def send(self, result: DivergenceResult) -> None:
        for notifier in self._notifiers:
            try:
                await notifier.send(result)
            except Exception as e:
                logger.error(f"{type(notifier).__name__} failed: {e}")

    @classmethod
    def from_settings(cls) -> "MultiNotifier":
        notifiers = []
        if settings.telegram_bot_token and settings.telegram_chat_id:
            notifiers.append(TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id))
        if settings.discord_webhook_url:
            notifiers.append(DiscordNotifier(settings.discord_webhook_url))
        if not notifiers:
            logger.warning("No notifiers configured. Alerts will only be logged.")
        return cls(notifiers)
