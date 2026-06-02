import os
from pathlib import Path
from typing import TypedDict


class AppConfigItems(TypedDict):
  LOG_LEVEL: str
  DATABASE: Path
  CURRENCY: str
  REQUEST_EMAIL_HEADER: str | None
  TELEGRAM_BOT_TOKEN: str | None
  TELEGRAM_CHAT_ID: str | None


def load_env_config() -> AppConfigItems:
  """Load application config values from environment variables."""
  return {
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO").upper(),
    "DATABASE": Path(os.getenv("DATABASE", "iou.db")),
    "CURRENCY": os.getenv("CURRENCY", "USD"),
    "REQUEST_EMAIL_HEADER": os.getenv("REQUEST_EMAIL_HEADER"),
    "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
    "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID"),
  }
