"""Data models for EchoFrame."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: Optional[str] = None


@dataclass
class Session:
    session_id: str
    title: str
    started_at: str
    duration_seconds: Optional[int]
    audio_path: str
    segments: List[Segment]
    note_path: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_sentiment: Optional[str] = None
    context_type: Optional[str] = None
    contact_name: Optional[str] = None
    contact_id: Optional[str] = None
    organization: Optional[str] = None
    project: Optional[str] = None
    location: Optional[str] = None
    channel: Optional[str] = None
    context_notes: Optional[str] = None
