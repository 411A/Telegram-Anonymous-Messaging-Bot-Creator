"""Pytest configuration: make the app importable without a production .env."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# configs.settings validates these at import time. Tests never call Telegram.
os.environ.setdefault("MAIN_BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("WEBHOOK_BASE_URL", "https://example.test")
os.environ.setdefault("TG_SECRET_TOKEN", "test-secret")
os.environ.setdefault("FASTAPI_PORT", "13360")
os.environ.setdefault("GIT_COMMIT", "")
