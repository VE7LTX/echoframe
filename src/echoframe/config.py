"""Configuration handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import yaml


@dataclass
class AudioConfig:
    sample_rate_hz: int = 44100
    bit_depth: int = 16
    channels: int = 1


@dataclass
class NotesConfig:
    add_summary_section: bool = True
    add_action_items_section: bool = False
    embed_audio: bool = True


@dataclass
class PersonalAIConfig:
    enabled: bool = False
    api_key: Optional[str] = None
    domain_name: Optional[str] = None
    summary_prompt: str = "Summarize the key points in 3-5 bullets."
    sentiment_prompt: str = "Describe the overall sentiment in one sentence."
    context_check_prompt: str = (
        "Check the context fields against the transcript and flag discrepancies."
    )


@dataclass
class Config:
    base_dir: str
    device_name: Optional[str] = None
    whisper_model: str = "small"
    language: Optional[str] = None
    diarization: bool = False
    save_audio: bool = True
    audio: AudioConfig = field(default_factory=AudioConfig)
    notes: NotesConfig = field(default_factory=NotesConfig)
    personal_ai: PersonalAIConfig = field(default_factory=PersonalAIConfig)
    context: dict = field(default_factory=dict)


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    audio = AudioConfig(**data.get("audio", {}))
    notes = NotesConfig(**data.get("notes", {}))
    personal_ai = PersonalAIConfig(**data.get("personal_ai", {}))

    return Config(
        base_dir=data.get("base_dir", ""),
        device_name=data.get("device_name"),
        whisper_model=data.get("whisper_model", "small"),
        language=data.get("language"),
        diarization=bool(data.get("diarization", False)),
        save_audio=bool(data.get("save_audio", True)),
        audio=audio,
        notes=notes,
        personal_ai=personal_ai,
        context=data.get("context", {}),
    )


def save_config(path: str, config: Config) -> None:
    data = {
        "base_dir": config.base_dir,
        "device_name": config.device_name,
        "whisper_model": config.whisper_model,
        "language": config.language,
        "diarization": config.diarization,
        "save_audio": config.save_audio,
        "audio": {
            "sample_rate_hz": config.audio.sample_rate_hz,
            "bit_depth": config.audio.bit_depth,
            "channels": config.audio.channels,
        },
        "notes": {
            "add_summary_section": config.notes.add_summary_section,
            "add_action_items_section": config.notes.add_action_items_section,
            "embed_audio": config.notes.embed_audio,
        },
        "personal_ai": {
            "enabled": config.personal_ai.enabled,
            "api_key": config.personal_ai.api_key,
            "domain_name": config.personal_ai.domain_name,
            "summary_prompt": config.personal_ai.summary_prompt,
            "sentiment_prompt": config.personal_ai.sentiment_prompt,
            "context_check_prompt": config.personal_ai.context_check_prompt,
        },
        "context": config.context,
    }
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False)
