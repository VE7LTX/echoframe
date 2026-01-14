"""CLI entry point."""

from __future__ import annotations

import argparse
from datetime import datetime
import os

import json

from .recorder import (
    find_device_info_by_name,
    find_zoom_name_from_candidates,
    list_input_devices,
    record_audio,
    record_audio_stream,
    record_audio_stream_dual,
)
from .transcriber import transcribe_audio
from .renderer import render_note
from .storage import build_session_basename, ensure_dir, get_output_dirs
from .config import load_config
from .session_io import load_session, load_segments, save_segments, save_session
from .models import Session
from .audio_utils import extract_channels


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
    devices_cmd.add_argument(
        "--detail",
        action="store_true",
        help="Show detailed device channel info.",
    )

    record_cmd = sub.add_parser("record")
    record_cmd.add_argument("--title", default="Session", help="Session title.")
    record_cmd.add_argument("--config", default="echoframe_config.yml", help="Config.")
    record_cmd.add_argument("--base-dir", help="Base output directory.")
    record_cmd.add_argument("--context-type", help="Context type for subfolders.")
    record_cmd.add_argument(
        "--use-type-folders",
        action="store_true",
        help="Store recordings/notes under context type subfolders.",
    )
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

    h2_cmd = sub.add_parser("h2")
    h2_cmd.add_argument("--title", default="Session", help="Session title.")
    h2_cmd.add_argument("--config", default="echoframe_config.yml", help="Config.")
    h2_cmd.add_argument("--base-dir", help="Base output directory.")
    h2_cmd.add_argument("--context-type", default="Interview", help="Context type.")
    h2_cmd.add_argument(
        "--use-type-folders",
        action="store_true",
        help="Store recordings/notes under context type subfolders.",
    )
    h2_cmd.add_argument(
        "--duration", type=int, help="Seconds. Omit for manual stop."
    )
    h2_cmd.add_argument("--rate", type=int, default=44100, help="Sample rate.")
    h2_cmd.add_argument(
        "--channels", type=int, default=4, help="Mic channels (4 for H2)."
    )
    h2_cmd.add_argument("--device", help="Override device name substring.")
    h2_cmd.add_argument("--transcribe", action="store_true", help="Transcribe + note.")
    h2_cmd.add_argument("--model", default="small", help="Whisper model.")
    h2_cmd.add_argument("--language", help="Language code.")

    transcribe_cmd = sub.add_parser("transcribe")
    transcribe_cmd.add_argument("audio_path", help="Path to audio file.")
    transcribe_cmd.add_argument("--model", default="small", help="Whisper model.")
    transcribe_cmd.add_argument("--language", help="Language code.")
    transcribe_cmd.add_argument("--out", help="Write segments to JSON.")
    sub.add_parser("diarize")
    sub.add_parser("note")
    sub.add_parser("process")
    sub.add_parser("config")
    show_cmd = sub.add_parser("show")
    show_cmd.add_argument("path", help="Path to .session.json or .segments.json")
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
                line = f"[{index}] {name} (outputs: {channels})"
            else:
                channels = device.get("max_input_channels", 0)
                line = f"[{index}] {name} (inputs: {channels})"
            if args.detail:
                extra = []
                if "default_samplerate" in device:
                    extra.append(f"rate={device.get('default_samplerate')}")
                if "hostapi" in device:
                    extra.append(f"hostapi={device.get('hostapi')}")
                if extra:
                    line = f"{line} [{', '.join(extra)}]"
            print(line)
        return 0

    if args.command == "record":
        base_dir = args.base_dir
        if not base_dir and os.path.exists(args.config):
            cfg = load_config(args.config)
            base_dir = cfg.base_dir
        paths = get_output_dirs(
            base_dir or os.getcwd(),
            context_type=args.context_type,
            use_type_folders=bool(args.use_type_folders),
        )
        basename = build_session_basename(args.title, datetime.now())
        output_path = os.path.join(paths["recordings"], f"{basename}.wav")
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

    if args.command == "h2":
        base_dir = args.base_dir
        if not base_dir and os.path.exists(args.config):
            cfg = load_config(args.config)
            base_dir = cfg.base_dir
        paths = get_output_dirs(
            base_dir or os.getcwd(),
            context_type=args.context_type,
            use_type_folders=bool(args.use_type_folders),
        )
        basename = build_session_basename(args.title, datetime.now())
        output_path = os.path.join(paths["recordings"], f"{basename}.wav")
        devices = list_input_devices(loopback=False)
        device_name = None
        if args.device:
            info = find_device_info_by_name(args.device, loopback=False)
            device_name = info.get("name") if info else None
        if not device_name:
            device_name = find_zoom_name_from_candidates(devices)
        if not device_name:
            print("Zoom H2/H4 device not found.")
            return 1
        info = find_device_info_by_name(device_name, loopback=False)
        max_in = info.get("max_input_channels", 0) if info else 0
        channels = min(args.channels, max_in) if max_in else args.channels
        if channels != args.channels:
            print(f"Adjusting mic channels to {channels} (max {max_in})")
        if args.duration:
            record_result = record_audio(
                output_path=output_path,
                duration_seconds=args.duration,
                sample_rate_hz=args.rate,
                channels=channels,
                device_name=device_name,
                loopback=False,
            )
        else:
            record_result = record_audio_stream(
                output_path=output_path,
                sample_rate_hz=args.rate,
                channels=channels,
                device_name=device_name,
                loopback=False,
            )
        print(f"Wrote {output_path}")
        if not args.transcribe:
            return 0

        transcribe_path = output_path
        if channels > 2:
            segments_dir = paths["segments"]
            ensure_dir(segments_dir)
            front_path = os.path.join(segments_dir, f"{basename}.front.wav")
            extract_channels(output_path, front_path, [0, 1])
            transcribe_path = front_path

        segments = transcribe_audio(
            transcribe_path, model_name=args.model, language=args.language
        )
        note_text = render_note(
            title=args.title,
            date=datetime.now().strftime("%Y-%m-%d"),
            audio_filename=os.path.basename(output_path),
            segments=segments,
            participants=None,
            tags=[args.context_type] if args.context_type else None,
            duration_seconds=record_result.duration_seconds,
            device=device_name,
            sample_rate_hz=args.rate,
            bit_depth=16,
            channels=channels,
            capture_mode="mic",
            mic_device=device_name,
            system_device=None,
            system_channels=0,
            channel_map=["front_left", "front_right", "rear_left", "rear_right"][
                : channels
            ],
            context_type=args.context_type,
            contact_name=None,
            contact_id=None,
            organization=None,
            project=None,
            location=None,
            channel=None,
            context_notes=None,
            timestamped_notes=None,
            debug_log=None,
        )
        note_path = os.path.join(paths["notes"], f"{basename}.md")
        with open(note_path, "w", encoding="utf-8") as handle:
            handle.write(note_text)
        segments_path = os.path.join(paths["segments"], f"{basename}.segments.json")
        save_segments(segments_path, segments)
        session_path = os.path.join(paths["sessions"], f"{basename}.session.json")
        session = Session(
            session_id=basename,
            title=args.title,
            started_at=datetime.now().strftime("%Y-%m-%d"),
            duration_seconds=record_result.duration_seconds,
            audio_path=output_path,
            segments=segments,
            note_path=note_path,
            ai_summary=None,
            ai_sentiment=None,
            context_type=args.context_type,
            contact_name=None,
            contact_id=None,
            organization=None,
            project=None,
            location=None,
            channel=None,
            context_notes=None,
        )
        save_session(session_path, session)
        print(f"Note saved: {note_path}")
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

    if args.command == "show":
        if args.path.endswith(".session.json"):
            session = load_session(args.path)
            print(f"Session: {session.title}")
            print(f"Started: {session.started_at}")
            print(f"Audio: {session.audio_path}")
            print(f"Note: {session.note_path}")
            print(f"Segments: {len(session.segments)}")
        elif args.path.endswith(".segments.json"):
            segments = load_segments(args.path)
            print(f"Segments: {len(segments)}")
        else:
            print("Unsupported file. Use .session.json or .segments.json")
        return 0

    if args.command == "gui":
        from .gui import launch_gui

        launch_gui()
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
