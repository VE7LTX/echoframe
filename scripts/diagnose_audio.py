import argparse
import os
import sys
import threading
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import sounddevice as sd


def _find_device(match: str | None, loopback: bool) -> dict | None:
    devices = sd.query_devices()
    if not match:
        return None
    match_lower = match.lower()
    for info in devices:
        name = info.get("name", "").lower()
        if match_lower in name:
            if loopback and info.get("max_output_channels", 0) > 0:
                return info
            if not loopback and info.get("max_input_channels", 0) > 0:
                return info
    return None


def _describe_device(info: dict, label: str) -> None:
    print(f"{label}: {info.get('name', '')}")
    print(f"Index: {info.get('index', '')}")
    print(f"Host API: {info.get('hostapi', '')}")
    print(f"Max input channels: {info.get('max_input_channels', 0)}")
    print(f"Max output channels: {info.get('max_output_channels', 0)}")
    print(f"Default sample rate: {info.get('default_samplerate', '')}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", help="Device name substring.")
    parser.add_argument(
        "--loopback", action="store_true", help="Capture system audio via loopback."
    )
    parser.add_argument("--seconds", type=float, default=6.0, help="Test duration.")
    parser.add_argument("--rate", type=int, default=44100, help="Sample rate.")
    parser.add_argument("--channels", type=int, default=2, help="Channels.")
    args = parser.parse_args()

    info = _find_device(args.device, args.loopback)
    if info is None:
        info = sd.query_devices(None, "output" if args.loopback else "input")
    _describe_device(info, "Loopback device" if args.loopback else "Input device")

    max_channels = (
        info.get("max_output_channels", 0)
        if args.loopback
        else info.get("max_input_channels", 0)
    )
    channels = min(args.channels, max_channels or args.channels)
    if channels != args.channels:
        print(f"Adjusting channels to {channels} (max {max_channels})")

    levels = {"rms": [], "peaks": []}
    lock = threading.Lock()

    def _callback(indata, _frames, _time, status):
        if status:
            return
        data = indata.astype("float32")
        if data.ndim == 1:
            rms = np.sqrt(np.mean(data**2))
            peak = np.max(np.abs(data))
            rms_vals = [float(rms)]
            peak_vals = [float(peak)]
        else:
            rms_vals = np.sqrt(np.mean(data**2, axis=0)).tolist()
            peak_vals = np.max(np.abs(data), axis=0).tolist()
        with lock:
            levels["rms"] = rms_vals
            levels["peaks"] = peak_vals

    extra_settings = None
    if args.loopback and hasattr(sd, "WasapiSettings"):
        try:
            extra_settings = sd.WasapiSettings(loopback=True)
        except TypeError:
            extra_settings = None

    stream = sd.InputStream(
        samplerate=args.rate,
        channels=channels,
        dtype="int16",
        device=info.get("index"),
        callback=_callback,
        extra_settings=extra_settings,
    )
    stream.start()
    print("Streaming... press Ctrl+C to stop early.")

    end = time.time() + args.seconds
    try:
        while time.time() < end:
            with lock:
                rms_vals = list(levels["rms"])
                peak_vals = list(levels["peaks"])
            if rms_vals:
                rms_str = " ".join(f"{v:.3f}" for v in rms_vals)
                peak_str = " ".join(f"{v:.3f}" for v in peak_vals)
                print(f"RMS [{rms_str}] | Peaks [{peak_str}]")
            else:
                print("No samples yet...")
            time.sleep(0.5)
    finally:
        stream.stop()
        stream.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
