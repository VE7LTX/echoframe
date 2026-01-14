"""Transcription with Faster-Whisper."""

from __future__ import annotations

from typing import List, Optional, Callable
from .models import Segment


def transcribe_audio(
    audio_path: str,
    model_name: str = "small",
    language: str | None = None,
    device: str | None = None,
    compute_type: str | None = None,
    progress_cb: Optional[Callable[[float], None]] = None,
    total_duration_s: Optional[float] = None,
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
        if progress_cb and total_duration_s:
            progress = min(max(seg.end / total_duration_s, 0.0), 1.0)
            progress_cb(progress)
    return output
