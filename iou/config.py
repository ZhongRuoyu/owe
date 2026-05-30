import os
from pathlib import Path

DATABASE = Path(os.getenv("DATABASE", "iou.db"))
BILLING_REPO = (
  Path(os.getenv("BILLING_REPO", "")) if os.getenv("BILLING_REPO") else None
)
GIT = os.getenv("GIT", "git")
CURRENCY = os.getenv("CURRENCY", "USD")
