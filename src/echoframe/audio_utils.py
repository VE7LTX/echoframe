"""Audio helpers."""

from __future__ import annotations

import wave
from typing import List

import numpy as np


def extract_channels(
    input_path: str,
    output_path: str,
    channels_to_keep: List[int],
) -> None:
    with wave.open(input_path, "rb") as handle:
        channels = handle.getnchannels()
        sampwidth = handle.getsampwidth()
        framerate = handle.getframerate()
        frames = handle.getnframes()

        if sampwidth != 2:
            raise ValueError("Only 16-bit PCM is supported for channel extraction.")

        raw = handle.readframes(frames)

    data = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        data = data.reshape(-1, channels)
    else:
        data = data.reshape(-1, 1)

    keep = [idx for idx in channels_to_keep if 0 <= idx < channels]
    if not keep:
        raise ValueError("No valid channels selected.")

    sliced = data[:, keep]

    with wave.open(output_path, "wb") as out:
        out.setnchannels(len(keep))
        out.setsampwidth(2)
        out.setframerate(framerate)
        out.writeframes(sliced.tobytes())
