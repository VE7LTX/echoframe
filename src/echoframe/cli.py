"""CLI entry point."""

from __future__ import annotations

import argparse
from datetime import datetime
import os

import json

from .recorder import (
    list_input_devices,
    record_audio,
    record_audio_stream,
    record_audio_stream_dual,
)
from .transcriber import transcribe_audio
from .storage import build_session_basename, ensure_dir


def main() -> int:
    parser = argparse.ArgumentParser(prog="echoframe")
    sub = parser.add_subparsers(dest="command")

    devices_cmd = sub.add_parser("devices")
    devices_cmd.add_argument("--match", help="Filter device names by substring.")
    devices_cmd.add_argument(
        "--loopback",
        action="store_true",
        help="List output devices for system audio capture (WASAPI).",
    )

    record_cmd = sub.add_parser("record")
    record_cmd.add_argument("--title", default="Session", help="Session title.")
    record_cmd.add_argument("--out-dir", default="Recordings", help="Output folder.")
    record_cmd.add_argument(
        "--duration", type=int, help="Seconds. Omit for manual stop."
    )
    record_cmd.add_argument("--device", help="Preferred device name substring.")
    record_cmd.add_argument("--rate", type=int, default=44100, help="Sample rate.")
    record_cmd.add_argument("--channels", type=int, default=1, help="Mic channels.")
    record_cmd.add_argument(
        "--loopback",
        action="store_true",
        help="Capture system audio via WASAPI loopback.",
    )
    record_cmd.add_argument(
        "--mode",
        choices=["mic", "system", "dual"],
        default="mic",
        help="Capture mode.",
    )
    record_cmd.add_argument("--mic-device", help="Mic device substring.")
    record_cmd.add_argument("--system-device", help="System device substring.")
    record_cmd.add_argument(
        "--system-channels", type=int, default=2, help="System channels."
    )

    transcribe_cmd = sub.add_parser("transcribe")
    transcribe_cmd.add_argument("audio_path", help="Path to audio file.")
    transcribe_cmd.add_argument("--model", default="small", help="Whisper model.")
    transcribe_cmd.add_argument("--language", help="Language code.")
    transcribe_cmd.add_argument("--out", help="Write segments to JSON.")
    sub.add_parser("diarize")
    sub.add_parser("note")
    sub.add_parser("process")
    sub.add_parser("config")
    sub.add_parser("gui")

    args = parser.parse_args()
    if args.command == "devices":
        devices = list_input_devices(loopback=bool(args.loopback))
        if args.match:
            devices = [
                d for d in devices if args.match.lower() in d.get("name", "").lower()
            ]
        for device in devices:
            name = device.get("name", "Unknown")
            index = device.get("index", "?")
            if args.loopback:
                channels = device.get("max_output_channels", 0)
                print(f"[{index}] {name} (outputs: {channels})")
            else:
                channels = device.get("max_input_channels", 0)
                print(f"[{index}] {name} (inputs: {channels})")
        return 0

    if args.command == "record":
        ensure_dir(args.out_dir)
        basename = build_session_basename(args.title, datetime.now())
        output_path = os.path.join(args.out_dir, f"{basename}.wav")
        mode = args.mode
        mic_device = args.mic_device or args.device
        system_device = args.system_device or args.device
        if mode == "dual":
            record_audio_stream_dual(
                output_path=output_path,
                sample_rate_hz=args.rate,
                mic_channels=args.channels,
                system_channels=args.system_channels,
                mic_device_name=mic_device,
                system_device_name=system_device,
                duration_seconds=args.duration,
            )
        elif args.duration:
            record_audio(
                output_path=output_path,
                duration_seconds=args.duration,
                sample_rate_hz=args.rate,
                channels=args.channels,
                device_name=system_device if mode == "system" else mic_device,
                loopback=mode == "system" or args.loopback,
            )
        else:
            record_audio_stream(
                output_path=output_path,
                sample_rate_hz=args.rate,
                channels=args.channels,
                device_name=system_device if mode == "system" else mic_device,
                loopback=mode == "system" or args.loopback,
            )
        print(f"Wrote {output_path}")
        return 0

    if args.command == "transcribe":
        segments = transcribe_audio(
            args.audio_path, model_name=args.model, language=args.language
        )
        if args.out:
            payload = [
                {"start": s.start, "end": s.end, "text": s.text, "speaker": s.speaker}
                for s in segments
            ]
            with open(args.out, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        print(f"Segments: {len(segments)}")
        return 0

    if args.command == "gui":
        from .gui import launch_gui

        launch_gui()
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
