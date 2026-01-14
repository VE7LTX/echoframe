"""Speaker diarization and alignment."""

from __future__ import annotations

import logging
from typing import List, Dict, Optional

from .models import Segment

logger = logging.getLogger("echoframe")


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def diarize_segments(
    audio_path: str,
    segments: List[Segment],
    speaker_map: Optional[Dict[str, str]] = None,
    hf_token: Optional[str] = None,
) -> List[Segment]:
    def _fallback_channel_labels() -> List[Segment]:
        try:
            import soundfile as sf
            import numpy as np
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.warning("Fallback diarization unavailable: %s", exc)
            return segments

        waveform, sample_rate = sf.read(audio_path, always_2d=True)
        channel_count = waveform.shape[1]
        labels = (
            ["left", "right", "rear_left", "rear_right"][:channel_count]
            if channel_count > 1
            else ["speaker_0"]
        )
        output: List[Segment] = []
        for seg in segments:
            start = max(0, int(seg.start * sample_rate))
            end = max(start + 1, int(seg.end * sample_rate))
            window = waveform[start:end]
            if window.size == 0:
                best_idx = 0
            else:
                energy = np.mean(window**2, axis=0)
                best_idx = int(np.argmax(energy))
            speaker = labels[best_idx] if best_idx < len(labels) else f"speaker_{best_idx}"
            if speaker_map:
                speaker = speaker_map.get(speaker, speaker)
            output.append(
                Segment(start=seg.start, end=seg.end, text=seg.text, speaker=speaker)
            )
        logger.info("Fallback diarization used (channel energy labels).")
        return output

    if not hf_token:
        return _fallback_channel_labels()

    try:
        from pyannote.audio import Pipeline
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pyannote.audio is required for diarization.") from exc

    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization", token=hf_token
        )
    except TypeError:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization", use_auth_token=hf_token
        )

    diarization = None
    try:
        import soundfile as sf
        import torch

        waveform, sample_rate = sf.read(audio_path, always_2d=True)
        waveform = torch.from_numpy(waveform.T).float()
        diarization = pipeline(
            {"waveform": waveform, "sample_rate": int(sample_rate)}
        )
    except Exception:
        diarization = pipeline(audio_path)

    speaker_turns = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        speaker_turns.append((turn.start, turn.end, speaker))

    output: List[Segment] = []
    for seg in segments:
        best_speaker = None
        best_overlap = 0.0
        for start, end, speaker in speaker_turns:
            ov = _overlap(seg.start, seg.end, start, end)
            if ov > best_overlap:
                best_overlap = ov
                best_speaker = speaker
        if best_speaker and speaker_map:
            best_speaker = speaker_map.get(best_speaker, best_speaker)
        output.append(
            Segment(start=seg.start, end=seg.end, text=seg.text, speaker=best_speaker)
        )

    return output
