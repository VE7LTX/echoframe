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


def sanitize_folder(name: str) -> str:
    value = (name or "").strip()
    if not value:
        return "General"
    return value.replace(" ", "-")


def ensure_structure(base_dir: str) -> dict:
    root = base_dir or os.getcwd()
    paths = {
        "root": root,
        "recordings": os.path.join(root, "Recordings"),
        "notes": os.path.join(root, "Notes"),
        "segments": os.path.join(root, "Segments"),
        "sessions": os.path.join(root, "Sessions"),
        "logs": os.path.join(root, "Logs"),
    }
    for path in paths.values():
        ensure_dir(path)
    return paths


def get_output_dirs(
    base_dir: str,
    context_type: str | None = None,
    use_type_folders: bool = False,
) -> dict:
    paths = ensure_structure(base_dir)
    if use_type_folders and context_type:
        folder = sanitize_folder(context_type)
        paths["recordings"] = os.path.join(paths["recordings"], folder)
        paths["notes"] = os.path.join(paths["notes"], folder)
        ensure_dir(paths["recordings"])
        ensure_dir(paths["notes"])
    return paths
