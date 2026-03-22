from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Polymarket
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    polymarket_clob_url: str = "https://clob.polymarket.com"

    # NOAA
    noaa_api_url: str = "https://api.weather.gov"
    noaa_user_agent: str = "polymarket-monitor/1.0"

    # Database
    db_path: str = "polymarket_monitor.db"

    # Scheduling
    poll_interval_minutes: int = 15

    # Alert thresholds
    divergence_threshold: float = 20.0   # percentage points
    alert_cooldown_hours: int = 4        # hours between repeat alerts per market

    # Telegram
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # Discord
    discord_webhook_url: Optional[str] = None

    # Misc
    dry_run: bool = False
    log_level: str = "INFO"

    @field_validator("divergence_threshold")
    @classmethod
    def threshold_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("divergence_threshold must be positive")
        return v


settings = Settings()
