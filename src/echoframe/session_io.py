"""Session and segment persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import List

from .models import Segment, Session


def save_segments(path: str, segments: List[Segment]) -> None:
    payload = [asdict(seg) for seg in segments]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def save_session(path: str, session: Session) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(asdict(session), handle, indent=2)
