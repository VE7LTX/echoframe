"""Markdown note rendering."""

from __future__ import annotations

from typing import List, Optional
from .models import Segment


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f"\"{escaped}\""


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _build_timeline_lines(
    segments: List[Segment], timestamped_notes: Optional[List[dict]]
) -> List[str]:
    timeline = []
    for seg in segments:
        text = _clean_text(seg.text)
        speaker = _clean_text(seg.speaker) if seg.speaker else ""
        timeline.append(
            {
                "time": seg.start,
                "line": f"[{seg.start:0>8.2f}]"
                f"{' ' + speaker + ':' if speaker else ''} {text}",
            }
        )
    if timestamped_notes:
        for note in timestamped_notes:
            stamp = note.get("timestamp", "00:00")
            try:
                mins, secs = stamp.split(":", 1)
                seconds = float(mins) * 60 + float(secs)
            except ValueError:
                seconds = 0.0
            label = "NOTE"
            if note.get("contact"):
                label = f"NOTE ({_clean_text(str(note.get('contact')))})"
            note_text = _clean_text(str(note.get("text", "")))
            line = f"[{seconds:0>8.2f}] {label}: {note_text}"
            timeline.append({"time": seconds, "line": line})
    return [item["line"] for item in sorted(timeline, key=lambda x: x["time"])]


def render_contact_note_header(
    date: str,
    contact_name: str,
    contact_id: Optional[str] = None,
    organization: Optional[str] = None,
    project: Optional[str] = None,
    location: Optional[str] = None,
    channel: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> str:
    lines: List[str] = []
    lines.append("---")
    lines.append("schema: 1")
    lines.append(f"title: {_yaml_quote(f'{contact_name} {date}')}")
    lines.append(f"date: {_yaml_quote(date)}")
    lines.append(f"contact_name: {_yaml_quote(contact_name)}")
    if contact_id:
        lines.append(f"contact_id: {_yaml_quote(contact_id)}")
    if organization:
        lines.append(f"organization: {_yaml_quote(organization)}")
    if project:
        lines.append(f"project: {_yaml_quote(project)}")
    if location:
        lines.append(f"location: {_yaml_quote(location)}")
    if channel:
        lines.append(f"channel: {_yaml_quote(channel)}")
    if tags:
        lines.append("tags:")
        for tag in tags:
            lines.append(f"  - {_yaml_quote(tag)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Contact Log: {_clean_text(contact_name)}")
    lines.append("")
    return "\n".join(lines)


def render_recording_section(
    title: str,
    date: str,
    audio_filename: str,
    segments: List[Segment],
    participants: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    duration_seconds: Optional[int] = None,
    capture_mode: Optional[str] = None,
    mic_device: Optional[str] = None,
    system_device: Optional[str] = None,
    sample_rate_hz: Optional[int] = None,
    bit_depth: Optional[int] = None,
    channels: Optional[int] = None,
    system_channels: Optional[int] = None,
    channel_map: Optional[List[str]] = None,
    context_type: Optional[str] = None,
    context_notes: Optional[str] = None,
    timestamped_notes: Optional[List[dict]] = None,
    debug_log: Optional[str] = None,
    started_at: Optional[str] = None,
    ended_at: Optional[str] = None,
) -> str:
    lines: List[str] = []
    display_start = started_at.replace("T", " ") if started_at else date
    lines.append(f"## Recording {display_start}")
    lines.append("")
    lines.append(f"- Title: {_clean_text(title)}")
    lines.append(f"- Audio: {_clean_text(audio_filename)}")
    if started_at:
        lines.append(f"- Started: {_clean_text(started_at)}")
    if ended_at:
        lines.append(f"- Ended: {_clean_text(ended_at)}")
    if duration_seconds is not None:
        lines.append(f"- Duration (s): {duration_seconds}")
    if context_type:
        lines.append(f"- Context type: {_clean_text(context_type)}")
    if tags:
        lines.append(f"- Tags: {', '.join(_clean_text(t) for t in tags)}")
    if participants:
        lines.append(f"- Participants: {', '.join(_clean_text(p) for p in participants)}")
    if capture_mode:
        lines.append(f"- Capture mode: {_clean_text(capture_mode)}")
    if mic_device:
        lines.append(f"- Mic device: {_clean_text(mic_device)}")
    if capture_mode in ("system", "dual") and system_device:
        lines.append(f"- System device: {_clean_text(system_device)}")
    if sample_rate_hz:
        lines.append(f"- Sample rate (Hz): {sample_rate_hz}")
    if bit_depth:
        lines.append(f"- Bit depth: {bit_depth}")
    if channels:
        lines.append(f"- Channels: {channels}")
    if capture_mode in ("system", "dual") and system_channels:
        lines.append(f"- System channels: {system_channels}")
    if channel_map:
        lines.append(f"- Channel map: {', '.join(_clean_text(c) for c in channel_map)}")
    lines.append("")
    if context_notes:
        lines.append("### Context Notes")
        lines.append("")
        lines.append(context_notes)
        lines.append("")
    lines.append("### Transcript")
    lines.append("")
    lines.extend(_build_timeline_lines(segments, timestamped_notes))
    lines.append("")
    if debug_log:
        lines.append("### Debug Log")
        lines.append("")
        lines.append("```text")
        lines.extend(debug_log.splitlines())
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


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
    timestamped_notes: Optional[List[dict]] = None,
    debug_log: Optional[str] = None,
    started_at: Optional[str] = None,
    ended_at: Optional[str] = None,
) -> str:
    lines: List[str] = []
    lines.append("---")
    lines.append("schema: 1")
    lines.append(f"title: {_yaml_quote(title)}")
    lines.append(f"date: {_yaml_quote(date)}")
    lines.append(f"audio: {_yaml_quote(audio_filename)}")
    if started_at:
        lines.append(f"started_at: {_yaml_quote(started_at)}")
    if ended_at:
        lines.append(f"ended_at: {_yaml_quote(ended_at)}")
    if duration_seconds is not None:
        lines.append(f"duration_seconds: {duration_seconds}")
    if participants:
        lines.append("participants:")
        for name in participants:
            lines.append(f"  - {_yaml_quote(name)}")
    if tags:
        lines.append("tags:")
        for tag in tags:
            lines.append(f"  - {_yaml_quote(tag)}")
    if device:
        lines.append(f"device: {_yaml_quote(device)}")
    if sample_rate_hz:
        lines.append(f"sample_rate_hz: {sample_rate_hz}")
    if bit_depth:
        lines.append(f"bit_depth: {bit_depth}")
    if channels:
        lines.append(f"channels: {channels}")
    if capture_mode:
        lines.append(f"capture_mode: {_yaml_quote(capture_mode)}")
    if mic_device:
        lines.append(f"mic_device: {_yaml_quote(mic_device)}")
    if capture_mode in ("system", "dual") and system_device:
        lines.append(f"system_device: {_yaml_quote(system_device)}")
    if capture_mode in ("system", "dual") and system_channels:
        lines.append(f"system_channels: {system_channels}")
    if channel_map:
        lines.append("channel_map:")
        for label in channel_map:
            lines.append(f"  - {_yaml_quote(label)}")
    if context_type:
        lines.append(f"context_type: {_yaml_quote(context_type)}")
    if contact_name:
        lines.append(f"contact_name: {_yaml_quote(contact_name)}")
    if contact_id:
        lines.append(f"contact_id: {_yaml_quote(contact_id)}")
    if organization:
        lines.append(f"organization: {_yaml_quote(organization)}")
    if project:
        lines.append(f"project: {_yaml_quote(project)}")
    if location:
        lines.append(f"location: {_yaml_quote(location)}")
    if channel:
        lines.append(f"channel: {_yaml_quote(channel)}")
    if summary:
        lines.append("summary: >")
        for line in summary.splitlines():
            lines.append(f"  {line}")
    if sentiment:
        lines.append(f"sentiment: {_yaml_quote(sentiment)}")
    lines.append("---")
    lines.append("")
    lines.append("## Session Details")
    lines.append("")
    lines.append(f"- Title: {_clean_text(title)}")
    lines.append(f"- Date: {_clean_text(date)}")
    lines.append(f"- Audio: {_clean_text(audio_filename)}")
    if started_at:
        lines.append(f"- Started: {_clean_text(started_at)}")
    if ended_at:
        lines.append(f"- Ended: {_clean_text(ended_at)}")
    if duration_seconds is not None:
        lines.append(f"- Duration (s): {duration_seconds}")
    if participants:
        lines.append(f"- Participants: {', '.join(_clean_text(p) for p in participants)}")
    if contact_name:
        lines.append(f"- Contact: {_clean_text(contact_name)}")
    if contact_id:
        lines.append(f"- Contact ID: {_clean_text(contact_id)}")
    if organization:
        lines.append(f"- Organization: {_clean_text(organization)}")
    if project:
        lines.append(f"- Project: {_clean_text(project)}")
    if location:
        lines.append(f"- Location: {_clean_text(location)}")
    if channel:
        lines.append(f"- Channel: {_clean_text(channel)}")
    if context_type:
        lines.append(f"- Context type: {_clean_text(context_type)}")
    if tags:
        lines.append(f"- Tags: {', '.join(_clean_text(t) for t in tags)}")
    if capture_mode:
        lines.append(f"- Capture mode: {_clean_text(capture_mode)}")
    if mic_device:
        lines.append(f"- Mic device: {_clean_text(mic_device)}")
    if capture_mode in ("system", "dual") and system_device:
        lines.append(f"- System device: {_clean_text(system_device)}")
    if sample_rate_hz:
        lines.append(f"- Sample rate (Hz): {sample_rate_hz}")
    if bit_depth:
        lines.append(f"- Bit depth: {bit_depth}")
    if channels:
        lines.append(f"- Channels: {channels}")
    if capture_mode in ("system", "dual") and system_channels:
        lines.append(f"- System channels: {system_channels}")
    if channel_map:
        lines.append(f"- Channel map: {', '.join(_clean_text(c) for c in channel_map)}")
    lines.append("")

    if context_notes:
        lines.append("## Context Notes")
        lines.append("")
        lines.append(context_notes)
        lines.append("")
    lines.append("## Transcript")
    lines.append("")

    lines.extend(_build_timeline_lines(segments, timestamped_notes))
    lines.append("")
    if debug_log:
        lines.append("## Debug Log")
        lines.append("")
        lines.append("```text")
        lines.extend(debug_log.splitlines())
        lines.append("```")
        lines.append("")
    return "\n".join(lines)
