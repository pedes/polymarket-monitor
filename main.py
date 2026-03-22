#!/usr/bin/env python3
"""Entry point for the Polymarket weather monitor."""
import argparse
import asyncio
import logging
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from polymarket_monitor.config import settings
from polymarket_monitor import db
from polymarket_monitor.poller import poll_once
from polymarket_monitor.alerts import evaluate_and_alert
from polymarket_monitor.notifier import MultiNotifier

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Polymarket weather market monitor")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print alerts to stdout instead of sending notifications",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run a single poll+analyse cycle then exit",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=settings.poll_interval_minutes,
        help="Poll interval in minutes (default: %(default)s)",
    )
    return parser.parse_args()


async def run_cycle(notifier: MultiNotifier) -> None:
    await poll_once()
    alerted = await evaluate_and_alert(notifier)
    if alerted:
        logger.info(f"Fired {len(alerted)} alert(s) this cycle")
    else:
        logger.info("No alerts this cycle")


async def main() -> None:
    args = parse_args()

    # Allow --dry-run flag to override .env setting
    if args.dry_run:
        import polymarket_monitor.config as cfg_module
        cfg_module.settings.dry_run = True

    logger.info(
        f"Starting Polymarket monitor | dry_run={settings.dry_run} | "
        f"interval={args.interval}m | threshold={settings.divergence_threshold}pp"
    )

    await db.init_db()
    notifier = MultiNotifier.from_settings()

    if args.run_once:
        await run_cycle(notifier)
        return

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_cycle,
        "interval",
        minutes=args.interval,
        args=[notifier],
        id="poll_and_alert",
        next_run_time=__import__("datetime").datetime.now(),  # run immediately on start
    )
    scheduler.start()
    logger.info(f"Scheduler started. Next poll in {args.interval} minutes.")

    try:
        # Keep the event loop alive
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler…")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
