import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
  url_prefix: str
  api_only: bool
  log_level: str
  database_path: Path
  currency: str
  request_id_header: str | None
  trust_proxy: bool
  telegram_bot_token: str | None
  telegram_chat_id: str | None


def load_env_config() -> Config:
  """Load application config values from environment variables."""
  return Config(
    url_prefix=os.getenv("OWE_URL_PREFIX", ""),
    api_only=bool(os.getenv("OWE_API_ONLY")),
    log_level=os.getenv("OWE_LOG_LEVEL", "INFO").upper(),
    database_path=Path(os.getenv("OWE_DATABASE", "owe.db")),
    currency=os.getenv("OWE_CURRENCY", "USD"),
    request_id_header=os.getenv("OWE_REQUEST_ID_HEADER"),
    trust_proxy=bool(os.getenv("OWE_TRUST_PROXY")),
    telegram_bot_token=os.getenv("OWE_TELEGRAM_BOT_TOKEN"),
    telegram_chat_id=os.getenv("OWE_TELEGRAM_CHAT_ID"),
  )
