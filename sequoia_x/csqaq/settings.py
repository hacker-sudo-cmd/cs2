"""Settings for the CSQAQ selector."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class CSQAQSettings(BaseSettings):
    csqaq_api_token: str
    csqaq_feishu_webhook_url: Optional[str] = None
    csqaq_request_timeout: float = 15.0
    csqaq_auto_bind_ip: bool = True
    csqaq_min_interval_seconds: float = 1.1
    csqaq_retry_count: int = 3

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
