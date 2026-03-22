"""Async SQLite persistence layer."""
import aiosqlite
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import settings

DB_PATH = settings.db_path

CREATE_MARKETS = """
CREATE TABLE IF NOT EXISTS markets (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    description TEXT,
    category TEXT,
    end_date TEXT,
    location TEXT,
    weather_type TEXT,
    raw_json TEXT,
    updated_at TEXT NOT NULL
)
"""

CREATE_PRICES = """
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    yes_price REAL,
    no_price REAL,
    fetched_at TEXT NOT NULL,
    FOREIGN KEY (market_id) REFERENCES markets(id)
)
"""

CREATE_NOAA_FORECASTS = """
CREATE TABLE IF NOT EXISTS noaa_forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    implied_probability REAL,
    forecast_text TEXT,
    fetched_at TEXT NOT NULL,
    FOREIGN KEY (market_id) REFERENCES markets(id)
)
"""

CREATE_ALERTS = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    divergence REAL NOT NULL,
    polymarket_prob REAL NOT NULL,
    noaa_prob REAL NOT NULL,
    fired_at TEXT NOT NULL,
    notified INTEGER DEFAULT 0,
    FOREIGN KEY (market_id) REFERENCES markets(id)
)
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_MARKETS)
        await db.execute(CREATE_PRICES)
        await db.execute(CREATE_NOAA_FORECASTS)
        await db.execute(CREATE_ALERTS)
        await db.commit()


async def upsert_market(market: dict) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO markets (id, question, description, category, end_date,
                                 location, weather_type, raw_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                question=excluded.question,
                description=excluded.description,
                category=excluded.category,
                end_date=excluded.end_date,
                location=excluded.location,
                weather_type=excluded.weather_type,
                raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            """,
            (
                market["id"],
                market.get("question", ""),
                market.get("description", ""),
                market.get("category", ""),
                market.get("endDate", ""),
                market.get("location", ""),
                market.get("weather_type", ""),
                json.dumps(market),
                now,
            ),
        )
        await db.commit()


async def insert_price(market_id: str, yes_price: Optional[float], no_price: Optional[float]) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO prices (market_id, yes_price, no_price, fetched_at) VALUES (?, ?, ?, ?)",
            (market_id, yes_price, no_price, now),
        )
        await db.commit()


async def insert_noaa_forecast(market_id: str, implied_prob: float, forecast_text: str) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO noaa_forecasts (market_id, implied_probability, forecast_text, fetched_at) VALUES (?, ?, ?, ?)",
            (market_id, implied_prob, forecast_text, now),
        )
        await db.commit()


async def get_latest_price(market_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT yes_price, no_price, fetched_at FROM prices WHERE market_id=? ORDER BY fetched_at DESC LIMIT 1",
            (market_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_latest_noaa(market_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT implied_probability, forecast_text, fetched_at FROM noaa_forecasts WHERE market_id=? ORDER BY fetched_at DESC LIMIT 1",
            (market_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_all_markets() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM markets") as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def insert_alert(market_id: str, divergence: float, polymarket_prob: float, noaa_prob: float) -> int:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO alerts (market_id, divergence, polymarket_prob, noaa_prob, fired_at) VALUES (?, ?, ?, ?, ?)",
            (market_id, divergence, polymarket_prob, noaa_prob, now),
        )
        await db.commit()
        return cur.lastrowid


async def mark_alert_notified(alert_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE alerts SET notified=1 WHERE id=?", (alert_id,))
        await db.commit()


async def get_last_alert_time(market_id: str) -> Optional[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT fired_at FROM alerts WHERE market_id=? ORDER BY fired_at DESC LIMIT 1",
            (market_id,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None
