"""Markdown note rendering."""

from __future__ import annotations

from typing import List, Optional
from .models import Segment


def render_note(
    title: str,
    date: str,
    audio_filename: str,
    segments: List[Segment],
    summary: Optional[str] = None,
    sentiment: Optional[str] = None,
    participants: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    duration_seconds: Optional[int] = None,
    device: Optional[str] = None,
    sample_rate_hz: Optional[int] = None,
    bit_depth: Optional[int] = None,
    channels: Optional[int] = None,
    capture_mode: Optional[str] = None,
    mic_device: Optional[str] = None,
    system_device: Optional[str] = None,
    system_channels: Optional[int] = None,
    channel_map: Optional[List[str]] = None,
    context_type: Optional[str] = None,
    contact_name: Optional[str] = None,
    contact_id: Optional[str] = None,
    organization: Optional[str] = None,
    project: Optional[str] = None,
    location: Optional[str] = None,
    channel: Optional[str] = None,
    context_notes: Optional[str] = None,
) -> str:
    lines: List[str] = []
    lines.append("---")
    lines.append("schema: 1")
    lines.append(f"title: {title}")
    lines.append(f"date: {date}")
    lines.append(f"audio: {audio_filename}")
    if duration_seconds is not None:
        lines.append(f"duration_seconds: {duration_seconds}")
    if participants:
        lines.append("participants:")
        for name in participants:
            lines.append(f"  - {name}")
    if tags:
        lines.append("tags:")
        for tag in tags:
            lines.append(f"  - {tag}")
    if device:
        lines.append(f"device: {device}")
    if sample_rate_hz:
        lines.append(f"sample_rate_hz: {sample_rate_hz}")
    if bit_depth:
        lines.append(f"bit_depth: {bit_depth}")
    if channels:
        lines.append(f"channels: {channels}")
    if capture_mode:
        lines.append(f"capture_mode: {capture_mode}")
    if mic_device:
        lines.append(f"mic_device: {mic_device}")
    if system_device:
        lines.append(f"system_device: {system_device}")
    if system_channels:
        lines.append(f"system_channels: {system_channels}")
    if channel_map:
        lines.append("channel_map:")
        for label in channel_map:
            lines.append(f"  - {label}")
    if context_type:
        lines.append(f"context_type: {context_type}")
    if contact_name:
        lines.append(f"contact_name: {contact_name}")
    if contact_id:
        lines.append(f"contact_id: {contact_id}")
    if organization:
        lines.append(f"organization: {organization}")
    if project:
        lines.append(f"project: {project}")
    if location:
        lines.append(f"location: {location}")
    if channel:
        lines.append(f"channel: {channel}")
    if summary:
        lines.append("summary: >")
        for line in summary.splitlines():
            lines.append(f"  {line}")
    if sentiment:
        lines.append(f"sentiment: {sentiment}")
    lines.append("---")
    lines.append("")
    if context_notes:
        lines.append("## Context")
        lines.append("")
        lines.append(context_notes)
        lines.append("")
    lines.append("## Transcript")
    lines.append("")
    for seg in segments:
        speaker = f" {seg.speaker}:" if seg.speaker else ""
        lines.append(f"[{seg.start:0>8.2f}]{speaker} {seg.text}")
    lines.append("")
    return "\n".join(lines)
