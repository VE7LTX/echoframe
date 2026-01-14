"""Storage and naming utilities."""

from __future__ import annotations

import os
from datetime import datetime


def timestamp_slug(dt: datetime | None = None) -> str:
    now = dt or datetime.now()
    return now.strftime("%Y-%m-%d")


def build_session_basename(title: str, dt: datetime | None = None) -> str:
    slug = title.strip().replace(" ", "-") if title else "Session"
    return f"{timestamp_slug(dt)}--{slug}"


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)