"""Speaker diarization and alignment."""

from __future__ import annotations

from typing import List, Dict, Optional
from .models import Segment


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def diarize_segments(
    audio_path: str,
    segments: List[Segment],
    speaker_map: Optional[Dict[str, str]] = None,
    hf_token: Optional[str] = None,
) -> List[Segment]:
    try:
        from pyannote.audio import Pipeline
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pyannote.audio is required for diarization.") from exc

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization", use_auth_token=hf_token
    )
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
