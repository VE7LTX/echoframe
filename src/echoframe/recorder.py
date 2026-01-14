"""Audio recording utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class RecordingResult:
    audio_path: str
    duration_seconds: int


def list_input_devices(loopback: bool = False) -> List[Dict[str, Any]]:
    try:
        import sounddevice as sd
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError("sounddevice is required for device detection.") from exc

    devices = sd.query_devices()
    if loopback:
        return [d for d in devices if d.get("max_output_channels", 0) > 0]
    return [d for d in devices if d.get("max_input_channels", 0) > 0]


def find_input_device(prefer_name: Optional[str] = None, loopback: bool = False) -> dict:
    candidates = list_input_devices(loopback=loopback)
    if not candidates:
        raise RuntimeError("No input devices found.")

    if prefer_name:
        preferred = [
            d for d in candidates if prefer_name.lower() in d.get("name", "").lower()
        ]
        if preferred:
            return preferred[0]

    zoom_hits = [
        d
        for d in candidates
        if "zoom h2" in d.get("name", "").lower()
        or "zoom h4" in d.get("name", "").lower()
    ]
    if zoom_hits:
        return zoom_hits[0]

    return candidates[0]


def record_audio(
    output_path: str,
    duration_seconds: int,
    sample_rate_hz: int = 44100,
    channels: int = 1,
    device_name: Optional[str] = None,
    loopback: bool = False,
) -> RecordingResult:
    try:
        import sounddevice as sd
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError("sounddevice is required for recording.") from exc

    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError("numpy is required for recording.") from exc

    device = find_input_device(device_name, loopback=loopback)
    device_index = device.get("index")
    frames = int(duration_seconds * sample_rate_hz)
    if frames <= 0:
        raise ValueError("duration_seconds must be > 0.")

    extra_settings = None
    if loopback and hasattr(sd, "WasapiSettings"):
        extra_settings = sd.WasapiSettings(loopback=True)

    recording = sd.rec(
        frames,
        samplerate=sample_rate_hz,
        channels=channels,
        dtype="int16",
        device=device_index,
        extra_settings=extra_settings,
    )
    sd.wait()

    if recording.dtype != np.int16:
        recording = recording.astype(np.int16)

    import wave

    with wave.open(output_path, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate_hz)
        handle.writeframes(recording.tobytes())

    return RecordingResult(audio_path=output_path, duration_seconds=duration_seconds)


def record_audio_stream(
    output_path: str,
    sample_rate_hz: int = 44100,
    channels: int = 1,
    device_name: Optional[str] = None,
    stop_event=None,
    loopback: bool = False,
) -> RecordingResult:
    try:
        import sounddevice as sd
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError("sounddevice is required for recording.") from exc

    device = find_input_device(device_name, loopback=loopback)
    device_index = device.get("index")

    import wave

    frames_written = 0
    with wave.open(output_path, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate_hz)

        def _callback(indata, _frames, _time, status):
            nonlocal frames_written
            if status:
                return
            handle.writeframes(indata.tobytes())
            frames_written += _frames

        extra_settings = None
        if loopback and hasattr(sd, "WasapiSettings"):
            extra_settings = sd.WasapiSettings(loopback=True)
        try:
            with sd.InputStream(
                samplerate=sample_rate_hz,
                channels=channels,
                dtype="int16",
                device=device_index,
                callback=_callback,
                extra_settings=extra_settings,
            ):
                while True:
                    if stop_event is not None and stop_event.is_set():
                        break
                    sd.sleep(100)
        except KeyboardInterrupt:
            pass

    duration_seconds = int(frames_written / sample_rate_hz)
    return RecordingResult(audio_path=output_path, duration_seconds=duration_seconds)


def record_audio_stream_dual(
    output_path: str,
    sample_rate_hz: int = 44100,
    mic_channels: int = 1,
    system_channels: int = 2,
    mic_device_name: Optional[str] = None,
    system_device_name: Optional[str] = None,
    stop_event=None,
    duration_seconds: Optional[int] = None,
) -> RecordingResult:
    try:
        import sounddevice as sd
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError("sounddevice is required for recording.") from exc

    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError("numpy is required for recording.") from exc

    mic_device = find_input_device(mic_device_name, loopback=False)
    system_device = find_input_device(system_device_name, loopback=True)
    mic_index = mic_device.get("index")
    system_index = system_device.get("index")

    import wave

    frames_written = 0
    target_frames = None
    if duration_seconds:
        target_frames = int(duration_seconds * sample_rate_hz)

    blocksize = 1024
    extra_settings = None
    if hasattr(sd, "WasapiSettings"):
        extra_settings = sd.WasapiSettings(loopback=True)

    with wave.open(output_path, "wb") as handle:
        handle.setnchannels(mic_channels + system_channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate_hz)

        with sd.InputStream(
            samplerate=sample_rate_hz,
            channels=mic_channels,
            dtype="int16",
            device=mic_index,
            blocksize=blocksize,
        ) as mic_stream, sd.InputStream(
            samplerate=sample_rate_hz,
            channels=system_channels,
            dtype="int16",
            device=system_index,
            blocksize=blocksize,
            extra_settings=extra_settings,
        ) as sys_stream:
            while True:
                if stop_event is not None and stop_event.is_set():
                    break
                mic_data, _ = mic_stream.read(blocksize)
                sys_data, _ = sys_stream.read(blocksize)

                if mic_data.shape[0] != sys_data.shape[0]:
                    frames = min(mic_data.shape[0], sys_data.shape[0])
                    mic_data = mic_data[:frames]
                    sys_data = sys_data[:frames]

                if mic_data.dtype != np.int16:
                    mic_data = mic_data.astype(np.int16)
                if sys_data.dtype != np.int16:
                    sys_data = sys_data.astype(np.int16)

                combined = np.concatenate([mic_data, sys_data], axis=1)
                handle.writeframes(combined.tobytes())
                frames_written += combined.shape[0]

                if target_frames and frames_written >= target_frames:
                    break

    actual_duration = int(frames_written / sample_rate_hz)
    return RecordingResult(audio_path=output_path, duration_seconds=actual_duration)
