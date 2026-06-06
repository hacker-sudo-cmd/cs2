"""Configuration helpers for Sequoia-X."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    db_path: str = "data/sequoia_v2.db"
    start_date: str = "2024-01-01"
    feishu_webhook_url: str
    strategy_webhooks: dict[str, str] = {}

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def model_post_init(self, __context: object) -> None:
        webhooks = dict(self.strategy_webhooks)
        prefix = "STRATEGY_WEBHOOK_"
        for key, value in os.environ.items():
            if key.upper().startswith(prefix):
                strategy_key = key[len(prefix):].lower()
                webhooks[strategy_key] = value

        object.__setattr__(self, "strategy_webhooks", webhooks)

        db_path = Path(self.db_path).expanduser()
        if not db_path.is_absolute():
            db_path = PROJECT_ROOT / db_path
        object.__setattr__(self, "db_path", str(db_path.resolve()))

    def get_webhook_url(self, webhook_key: str) -> str:
        return self.strategy_webhooks.get(webhook_key.lower(), self.feishu_webhook_url)


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
