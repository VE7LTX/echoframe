"""Transcription with Faster-Whisper."""

from __future__ import annotations

from typing import List
from .models import Segment


def transcribe_audio(
    audio_path: str,
    model_name: str = "small",
    language: str | None = None,
    device: str | None = None,
    compute_type: str | None = None,
) -> List[Segment]:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "faster-whisper is required for transcription."
        ) from exc

    kwargs = {}
    if device:
        kwargs["device"] = device
    if compute_type:
        kwargs["compute_type"] = compute_type
    model = WhisperModel(model_name, **kwargs)
    segments, _info = model.transcribe(audio_path, language=language)

    output: List[Segment] = []
    for seg in segments:
        output.append(Segment(start=seg.start, end=seg.end, text=seg.text.strip()))
    return output
