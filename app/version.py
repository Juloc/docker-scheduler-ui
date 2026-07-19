from __future__ import annotations

import os
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent
_VERSION_FILE = _ROOT / "VERSION"


def _read_version() -> str:
    override = os.getenv("APP_VERSION", "").strip()
    if override:
        return override
    try:
        value = _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0-dev"
    return value or "0.0.0-dev"


APP_VERSION = _read_version()
BUILD_COMMIT = os.getenv("APP_COMMIT", "unknown").strip() or "unknown"
ASSET_VERSION = f"{APP_VERSION}-{BUILD_COMMIT[:8]}"
