"""Fetches markets from Polymarket Gamma API, prices from CLOB API, and NOAA forecasts."""
import logging
import re
from typing import Optional

import httpx

from .config import settings
from . import db

logger = logging.getLogger(__name__)

# Keywords that suggest a weather-related market
WEATHER_KEYWORDS = [
    "rain", "rainfall", "hurricane", "tornado", "storm", "flood",
    "temperature", "heat", "cold", "snow", "blizzard", "drought",
    "wildfire", "wind", "hail", "lightning", "frost", "freeze",
    "precipitation", "weather",
]

# Map common city/state names to NOAA grid points (office/gridX/gridY)
LOCATION_GRID_MAP: dict[str, tuple[str, int, int]] = {
    "new york": ("OKX", 33, 37),
    "nyc": ("OKX", 33, 37),
    "los angeles": ("LOX", 151, 49),
    "la": ("LOX", 151, 49),
    "chicago": ("LOT", 74, 73),
    "houston": ("HGX", 66, 97),
    "miami": ("MFL", 110, 37),
    "dallas": ("FWD", 95, 97),
    "phoenix": ("PSR", 158, 54),
    "seattle": ("SEW", 124, 67),
    "denver": ("BOU", 56, 63),
    "atlanta": ("FFC", 51, 85),
    "boston": ("BOX", 71, 90),
    "san francisco": ("MTR", 84, 105),
    "sf": ("MTR", 84, 105),
    "new orleans": ("LIX", 66, 76),
    "oklahoma city": ("OUN", 74, 84),
}


def _is_weather_market(market: dict) -> bool:
    text = " ".join([
        market.get("question", ""),
        market.get("description", ""),
        market.get("category", ""),
    ]).lower()
    return any(kw in text for kw in WEATHER_KEYWORDS)


def _extract_location(market: dict) -> Optional[str]:
    text = " ".join([market.get("question", ""), market.get("description", "")]).lower()
    for loc in LOCATION_GRID_MAP:
        if loc in text:
            return loc
    return None


def _extract_weather_type(market: dict) -> str:
    text = " ".join([market.get("question", ""), market.get("description", "")]).lower()
    for kw in ["rain", "hurricane", "tornado", "storm", "flood", "temperature",
                "heat", "cold", "snow", "blizzard", "drought", "wildfire",
                "wind", "hail", "frost", "freeze", "precipitation"]:
        if kw in text:
            return kw
    return "weather"


async def fetch_weather_markets(client: httpx.AsyncClient) -> list[dict]:
    """Fetch open markets from Gamma API and filter to weather-related ones."""
    markets = []
    offset = 0
    limit = 100

    while True:
        try:
            resp = await client.get(
                f"{settings.polymarket_gamma_url}/markets",
                params={"active": "true", "closed": "false", "limit": limit, "offset": offset},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Gamma API error: {e}")
            break

        if not data:
            break

        for m in data:
            if _is_weather_market(m):
                m["location"] = _extract_location(m) or ""
                m["weather_type"] = _extract_weather_type(m)
                markets.append(m)

        if len(data) < limit:
            break
        offset += limit

    logger.info(f"Found {len(markets)} weather-related markets")
    return markets


async def fetch_clob_price(client: httpx.AsyncClient, condition_id: str) -> tuple[Optional[float], Optional[float]]:
    """Return (yes_price, no_price) for a market condition from the CLOB API."""
    try:
        resp = await client.get(
            f"{settings.polymarket_clob_url}/midpoint",
            params={"token_id": condition_id},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        mid = float(data.get("mid", 0))
        return mid, 1.0 - mid
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.warning(f"CLOB price fetch failed for {condition_id}: {e}")
        return None, None


async def fetch_noaa_forecast(client: httpx.AsyncClient, location: str) -> Optional[dict]:
    """Fetch NOAA gridpoint forecast and return raw periods."""
    grid = LOCATION_GRID_MAP.get(location)
    if not grid:
        return None

    office, grid_x, grid_y = grid
    try:
        resp = await client.get(
            f"{settings.noaa_api_url}/gridpoints/{office}/{grid_x},{grid_y}/forecast",
            headers={"User-Agent": settings.noaa_user_agent, "Accept": "application/geo+json"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        periods = data.get("properties", {}).get("periods", [])
        return {"periods": periods}
    except httpx.HTTPError as e:
        logger.warning(f"NOAA forecast fetch failed for {location}: {e}")
        return None


def _noaa_implied_probability(forecast: dict, weather_type: str) -> float:
    """
    Derive a crude implied probability from NOAA forecast text for the given weather type.
    Returns a value in [0, 1].
    """
    periods = forecast.get("periods", [])
    if not periods:
        return 0.5  # unknown

    # Use the first two periods (day + night)
    texts = " ".join(p.get("detailedForecast", "") for p in periods[:2]).lower()

    # Precipitation probability is sometimes explicit
    pop_match = re.search(r"(\d+)\s*percent chance", texts)
    if pop_match:
        base_prob = int(pop_match.group(1)) / 100.0
    else:
        # Keyword heuristics
        if any(w in texts for w in ["likely", "probable"]):
            base_prob = 0.70
        elif any(w in texts for w in ["chance", "possible", "slight"]):
            base_prob = 0.35
        elif any(w in texts for w in ["none", "no rain", "sunny", "clear", "dry"]):
            base_prob = 0.05
        else:
            base_prob = 0.20

    # Adjust for specific weather types
    type_present = weather_type in texts or any(
        syn in texts
        for syn in {
            "hurricane": ["tropical storm", "hurricane"],
            "tornado": ["tornado", "severe thunderstorm"],
            "snow": ["snow", "blizzard", "flurries"],
            "frost": ["frost", "freeze"],
            "flood": ["flood", "flash flood"],
        }.get(weather_type, [weather_type])
    )

    if not type_present and weather_type not in ("rain", "precipitation", "weather"):
        base_prob *= 0.5  # dampen if specific hazard not mentioned

    return min(max(base_prob, 0.01), 0.99)


async def poll_once() -> None:
    """Main polling cycle: fetch markets, prices, forecasts and persist."""
    logger.info("Starting poll cycle")
    async with httpx.AsyncClient() as client:
        markets = await fetch_weather_markets(client)

        for market in markets:
            await db.upsert_market(market)

            # Fetch CLOB price — use conditionId or first token id
            condition_id = market.get("conditionId") or (
                market.get("tokens", [{}])[0].get("token_id") if market.get("tokens") else None
            )
            if condition_id:
                yes_price, no_price = await fetch_clob_price(client, condition_id)
                if yes_price is not None:
                    await db.insert_price(market["id"], yes_price, no_price)

            # Fetch NOAA forecast
            location = market.get("location", "")
            if location:
                forecast = await fetch_noaa_forecast(client, location)
                if forecast:
                    prob = _noaa_implied_probability(forecast, market.get("weather_type", "weather"))
                    text = "; ".join(
                        p.get("shortForecast", "") for p in forecast.get("periods", [])[:2]
                    )
                    await db.insert_noaa_forecast(market["id"], prob, text)

    logger.info("Poll cycle complete")
