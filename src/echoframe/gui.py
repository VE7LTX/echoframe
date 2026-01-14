"""Tkinter GUI for a compact recording bar."""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from collections import deque
from datetime import datetime

from .config import Config, load_config, save_config
from .diarizer import diarize_segments
from .recorder import (
    find_zoom_name_from_candidates,
    list_input_devices,
    record_audio_stream,
    record_audio_stream_dual,
)
from .renderer import render_contact_note_header, render_recording_section
from .storage import (
    build_session_basename,
    ensure_dir,
    ensure_structure,
    get_output_dirs,
    sanitize_folder,
)
from .transcriber import transcribe_audio
from .logging_utils import setup_logging
from .audio_utils import extract_channels
from .models import Session
from .session_io import save_segments, save_session


def launch_gui() -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("EchoFrame")
    root.resizable(False, False)
    root.configure(bg="#0b0f14")

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TFrame", background="#0b0f14")
    style.configure("TLabel", background="#0b0f14", foreground="#d8e1ff")
    style.configure(
        "TLabelFrame",
        background="#0b0f14",
        foreground="#8bd3ff",
    )
    style.configure(
        "TLabelFrame.Label",
        background="#0b0f14",
        foreground="#8bd3ff",
    )
    style.configure(
        "Neo.TLabelframe",
        background="#0b0f14",
        foreground="#8bd3ff",
        bordercolor="#0f1a2a",
        lightcolor="#0f1a2a",
        darkcolor="#0f1a2a",
    )
    style.configure(
        "Neo.TLabelframe.Label",
        background="#0b0f14",
        foreground="#8bd3ff",
    )
    style.configure(
        "TButton",
        background="#132033",
        foreground="#e6f1ff",
        borderwidth=1,
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("active", "#1b2a44")],
        foreground=[("active", "#ffffff")],
    )
    style.configure(
        "TEntry",
        fieldbackground="#111827",
        foreground="#e6f1ff",
        background="#111827",
        bordercolor="#1b2a44",
        lightcolor="#1b2a44",
        darkcolor="#1b2a44",
        relief="flat",
    )
    style.configure(
        "TCombobox",
        fieldbackground="#111827",
        foreground="#e6f1ff",
        background="#111827",
        bordercolor="#1b2a44",
        lightcolor="#1b2a44",
        darkcolor="#1b2a44",
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", "#111827")],
        foreground=[("readonly", "#e6f1ff")],
        selectbackground=[("readonly", "#132033")],
        selectforeground=[("readonly", "#e6f1ff")],
    )
    style.configure(
        "TCheckbutton",
        background="#0b0f14",
        foreground="#9ad1ff",
    )
    style.configure(
        "Neo.Horizontal.TProgressbar",
        troughcolor="#0f1a2a",
        background="#00e0ff",
        bordercolor="#0f1a2a",
        lightcolor="#00e0ff",
        darkcolor="#00b3cc",
    )

    config_path = "echoframe_config.yml"
    if os.path.exists(config_path):
        try:
            config = load_config(config_path)
        except Exception:
            config = Config(base_dir="")
    else:
        config = Config(base_dir="")

    base_paths = ensure_structure(config.base_dir)
    debug_enabled = bool(config.context.get("debug_logging", True))
    logger, log_path = setup_logging(
        log_dir=base_paths["logs"],
        level=logging.DEBUG if debug_enabled else logging.INFO,
    )

    def _thread_excepthook(args) -> None:
        logger.exception(
            "Thread exception",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_excepthook

    presets = {
        "context_types": config.context.get(
            "context_types",
            ["Interview", "Client Call", "Internal", "Fieldwork", "Webchat"],
        ),
        "channels": config.context.get(
            "channels", ["in_person", "phone", "webchat", "other"]
        ),
        "projects": config.context.get("projects", []),
        "organizations": config.context.get("organizations", []),
        "tags": config.context.get("tags", []),
        "profiles": config.context.get(
            "profiles",
            [
                {
                    "name": "Interview",
                    "context_type": "Interview",
                    "channel": "in_person",
                    "tags": ["interview"],
                },
                {
                    "name": "Client Call",
                    "context_type": "Client Call",
                    "channel": "phone",
                    "tags": ["client_call"],
                },
                {
                    "name": "Internal",
                    "context_type": "Internal",
                    "channel": "in_person",
                    "tags": ["internal"],
                },
                {
                    "name": "Webchat",
                    "context_type": "Webchat",
                    "channel": "webchat",
                    "tags": ["webchat"],
                },
            ],
        ),
    }
    last_used = config.context.get("last_used", {})
    my_profile = config.context.get("my_profile", {})

    def _last_used_value(key: str, fallback: str = "") -> str:
        value = last_used.get(key)
        if value is None or value == "":
            return fallback
        return value

    waveform_max = 2048
    waveform_render_max = 1024
    meter_refresh_ms = 300
    waveform_refresh_ms = 200
    meter_log_seconds = 5.0

    state = {
        "recording": False,
        "start_time": None,
        "stop_event": threading.Event(),
        "thread": None,
        "timestamped_notes": [],
        "active_contact": "",
        "active_contact_id": "",
        "pending_contact": "",
        "suppress_contact_prompt": False,
    }
    monitor = {
        "streams": [],
        "level": 0.0,
        "peak": 0.0,
        "lock": threading.Lock(),
        "channels": [],
        "peaks": [],
        "labels": [],
        "hud": None,
        "hud_canvas": None,
        "config": None,
        "waveform": deque(maxlen=waveform_max),
        "last_update": 0.0,
        "update_count": 0,
        "last_log": 0.0,
    }
    live = {
        "audio_queue": None,
        "text_queue": None,
        "stop_event": threading.Event(),
        "thread": None,
    }
    feed = {
        "queue": queue.Queue(),
        "max_lines": 200,
    }
    live["text_queue"] = feed["queue"]
    transcribe = {
        "progress_queue": queue.Queue(),
        "stage": "idle",
        "ratio": 0.0,
    }

    class _ToolTip:
        def __init__(self, widget, text: str) -> None:
            self.widget = widget
            self.text = text
            self.tip = None
            self._bootstrap_tip = None
            try:
                from ttkbootstrap.tooltip import ToolTip as BsToolTip

                self._bootstrap_tip = BsToolTip(widget, text=text)
                return
            except Exception:
                pass
            widget.bind("<Enter>", self._show)
            widget.bind("<Leave>", self._hide)

        def _show(self, _event=None) -> None:
            if self.tip or not self.text or self._bootstrap_tip is not None:
                return
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + 20
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry(f"+{x}+{y}")
            label = tk.Label(
                self.tip,
                text=self.text,
                background="#0f1a2a",
                foreground="#d8e1ff",
                relief="solid",
                borderwidth=1,
                font=("Segoe UI", 9),
                justify="left",
            )
            label.pack(ipadx=6, ipady=4)

        def _hide(self, _event=None) -> None:
            if self.tip:
                self.tip.destroy()
                self.tip = None

    def _set_status(text: str) -> None:
        if threading.current_thread() is threading.main_thread():
            status_var.set(text)
        else:
            root.after(0, lambda: status_var.set(text))
        timestamp = datetime.now().strftime("%H:%M:%S")
        feed["queue"].put(f"[{timestamp}] {text}")
        logger.info(text)

    def _log_fields(context: str) -> None:
        payload = {
            "title": title_var.get().strip(),
            "user_name": user_name_var.get().strip(),
            "attendees": attendees_var.get().strip(),
            "contact": contact_var.get().strip(),
            "contact_id": contact_id_var.get().strip(),
            "org": org_var.get().strip(),
            "project": project_var.get().strip(),
            "location": location_var.get().strip(),
            "channel": channel_var.get().strip(),
            "tags": tags_var.get().strip(),
            "context_type": context_type_var.get().strip(),
            "profile": profile_var.get().strip(),
            "capture_mode": capture_mode_var.get().strip(),
            "mic_device": mic_device_var.get().strip(),
            "system_device": system_device_var.get().strip(),
            "rate": rate_var.get().strip(),
            "mic_channels": mic_channels_var.get().strip(),
            "system_channels": system_channels_var.get().strip(),
            "model": model_var.get().strip(),
            "language": language_var.get().strip(),
            "device_pref": device_pref_var.get().strip(),
            "compute_type": compute_type_var.get().strip(),
            "live_model": live_model_var.get().strip(),
            "diarize": diarize_var.get(),
            "auto_tags": auto_tags_var.get(),
            "live_transcribe": live_transcribe_var.get(),
        }
        logger.debug("UI fields (%s): %s", context, payload)

    def _log_field_change(field_name: str) -> None:
        logger.debug("Field updated: %s", field_name)
        _log_fields(f"field:{field_name}")

    def _format_timestamp(seconds: float | int) -> str:
        total = int(max(0, seconds))
        mins, secs = divmod(total, 60)
        return f"{mins:02d}:{secs:02d}"

    def _collect_debug_log(start_ts: datetime, end_ts: datetime) -> str:
        if not debug_enabled_var.get():
            return ""
        if not os.path.exists(log_path):
            return ""
        lines = []
        try:
            with open(log_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    if len(line) < 20:
                        continue
                    try:
                        stamp = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue
                    if start_ts <= stamp <= end_ts:
                        lines.append(line.rstrip())
        except Exception as exc:
            logger.debug("Debug log read failed: %s", exc)
        return "\n".join(lines)

    def _describe_device(name: str, kind: str) -> str | None:
        if not name:
            return None
        try:
            import sounddevice as sd
        except Exception:
            return name
        try:
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
        except Exception:
            return name
        exact = next((d for d in devices if d.get("name") == name), None)
        info = exact
        if not info:
            name_lower = name.lower()
            info = next(
                (d for d in devices if name_lower in d.get("name", "").lower()), None
            )
        if not info:
            return name
        hostapi_name = ""
        host_idx = info.get("hostapi")
        if host_idx is not None and host_idx < len(hostapis):
            hostapi_name = hostapis[host_idx].get("name", "")
        detail = f"{info.get('name', name)}"
        if info.get("index") is not None:
            detail += f" (index {info.get('index')})"
        if hostapi_name:
            detail += f" [{hostapi_name}]"
        return detail

    def _cleanup_recordings(recordings_root: str, hours: int = 48) -> None:
        if not recordings_root or not os.path.exists(recordings_root):
            return
        cutoff = time.time() - hours * 3600
        removed = 0
        for root_dir, _, files in os.walk(recordings_root):
            for filename in files:
                if not filename.lower().endswith(".wav"):
                    continue
                path = os.path.join(root_dir, filename)
                try:
                    if os.path.getmtime(path) < cutoff:
                        os.remove(path)
                        removed += 1
                except Exception as exc:
                    logger.debug("Cleanup failed for %s: %s", path, exc)
        if removed:
            logger.info("Removed %s recordings older than %s hours", removed, hours)

    def _contact_daily_note_path(note_root: str, contact_name: str, date_str: str) -> str:
        slug = sanitize_folder(contact_name or "Unknown")
        contact_dir = os.path.join(note_root, "Contacts", slug)
        ensure_dir(contact_dir)
        return os.path.join(contact_dir, f"{date_str}.md")

    def _refresh_timestamped_notes() -> None:
        notes_list.delete(0, "end")
        for note in state["timestamped_notes"]:
            stamp = note.get("timestamp", "00:00")
            text = note.get("text", "")
            notes_list.insert("end", f"[{stamp}] {text}")

    def _update_note_controls() -> None:
        has_contact = bool(contact_var.get().strip())
        state_label = "normal" if has_contact else "disabled"
        if notes_entry is not None:
            notes_entry.configure(state=state_label)
        if add_note_btn is not None:
            add_note_btn.configure(state=state_label)

    def _remember_preset(key: str, value: str) -> None:
        value = value.strip()
        if not value:
            return
        if value not in presets[key]:
            presets[key].append(value)

    def _save_defaults() -> None:
        config.context["context_types"] = presets["context_types"]
        config.context["channels"] = presets["channels"]
        config.context["projects"] = presets["projects"]
        config.context["organizations"] = presets["organizations"]
        config.context["tags"] = presets["tags"]
        config.context["profiles"] = presets["profiles"]
        config.context["user_name"] = user_name_var.get().strip()
        config.context["default_context_type"] = context_type_var.get().strip()
        config.context["default_channel"] = channel_var.get().strip()
        config.context["use_type_folders"] = use_type_folders_var.get()
        config.context["debug_logging"] = debug_enabled_var.get()
        save_config(config_path, config)
        _log_fields("save_defaults")
        _set_status("Defaults saved")

    def _collect_last_used() -> dict:
        return {
            "title": title_var.get().strip(),
            "user_name": user_name_var.get().strip(),
            "attendees": attendees_var.get().strip(),
            "contact": contact_var.get().strip(),
            "contact_id": contact_id_var.get().strip(),
            "org": org_var.get().strip(),
            "project": project_var.get().strip(),
            "location": location_var.get().strip(),
            "channel": channel_var.get().strip(),
            "notes": notes_box.get("1.0", "end").strip(),
            "tags": tags_var.get().strip(),
            "context_type": context_type_var.get().strip(),
            "profile": profile_var.get().strip(),
            "capture_mode": capture_mode_var.get().strip(),
            "mic_device": mic_device_var.get().strip(),
            "system_device": system_device_var.get().strip(),
            "rate": rate_var.get().strip(),
            "mic_channels": mic_channels_var.get().strip(),
            "system_channels": system_channels_var.get().strip(),
            "model": model_var.get().strip(),
            "language": language_var.get().strip(),
            "device_pref": device_pref_var.get().strip(),
            "compute_type": compute_type_var.get().strip(),
            "live_model": live_model_var.get().strip(),
            "diarize": diarize_var.get(),
            "hf_token": hf_token_var.get().strip(),
            "speaker_map": speaker_map_var.get().strip(),
            "auto_tags": auto_tags_var.get(),
            "use_type_folders": use_type_folders_var.get(),
            "live_transcribe": live_transcribe_var.get(),
        }

    def _save_last_used() -> None:
        config.context["last_used"] = _collect_last_used()
        config.context["user_name"] = user_name_var.get().strip()
        config.device_name = mic_device_var.get().strip() or None
        config.whisper_model = model_var.get().strip() or "small"
        config.language = language_var.get().strip() or None
        try:
            config.audio.sample_rate_hz = int(rate_var.get())
        except ValueError:
            pass
        try:
            config.audio.channels = int(mic_channels_var.get())
        except ValueError:
            pass
        config.diarization = diarize_var.get()
        save_config(config_path, config)
        _log_fields("save_last_used")

    def _apply_my_profile(values: dict) -> None:
        if not values:
            return
        if values.get("user_name"):
            user_name_var.set(values.get("user_name", ""))
        if values.get("org"):
            org_var.set(values.get("org", ""))
        if values.get("project"):
            project_var.set(values.get("project", ""))
        if values.get("channel"):
            channel_var.set(values.get("channel", channel_var.get()))
        if values.get("tags"):
            tags_var.set(values.get("tags", ""))
        if values.get("location"):
            location_var.set(values.get("location", ""))
        if values.get("language"):
            language_var.set(values.get("language", ""))
        if values.get("default_context_type"):
            context_type_var.set(values.get("default_context_type", ""))

    def _update_timer() -> None:
        if state["recording"] and state["start_time"]:
            elapsed = int(time.time() - state["start_time"])
            mins, secs = divmod(elapsed, 60)
            timer_var.set(f"{mins:02d}:{secs:02d}")
        root.after(500, _update_timer)

    def _update_meter() -> None:
        with monitor["lock"]:
            level = monitor["level"]
            peak = monitor["peak"]
            channels = list(monitor["channels"])
            peaks = list(monitor["peaks"])
            labels = list(monitor["labels"])
            last_update = monitor["last_update"]
            update_count = monitor["update_count"]
            last_log = monitor["last_log"]
        if not channels and level > 0:
            channels = [level]
            peaks = [peak]
            labels = ["level"]
        _render_meters(channels, peaks, labels)
        if monitor["hud_canvas"] is not None:
            _update_hud(channels, peaks, labels)
        if debug_enabled_var.get():
            now = time.time()
            if now - last_log >= meter_log_seconds:
                logger.debug(
                    "Meter updates=%s last_update=%.2f level=%.2f peak=%.2f channels=%s",
                    update_count,
                    now - last_update if last_update else -1,
                    level,
                    peak,
                    len(channels),
                )
                with monitor["lock"]:
                    monitor["last_log"] = now
        root.after(meter_refresh_ms, _update_meter)

    monitor_refresh_job = None

    def _monitor_config() -> tuple:
        try:
            rate = int(rate_var.get())
        except ValueError:
            rate = 44100
        try:
            mic_channels = int(mic_channels_var.get())
        except ValueError:
            mic_channels = 1
        try:
            system_channels = int(system_channels_var.get())
        except ValueError:
            system_channels = 2
        return (
            capture_mode_var.get().strip(),
            mic_device_var.get().strip(),
            system_device_var.get().strip(),
            rate,
            mic_channels,
            system_channels,
        )

    def _stop_monitoring() -> None:
        if not monitor["streams"]:
            return
        for stream in monitor["streams"]:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        monitor["streams"] = []
        monitor["config"] = None
        _set_status("Monitoring stopped")

    def _start_monitoring(force: bool = False, reason: str | None = None) -> None:
        cfg = _monitor_config()
        if monitor["streams"] and monitor["config"] == cfg and not force:
            return
        if monitor["streams"]:
            _stop_monitoring()
        logger.info("Monitor start%s", f" ({reason})" if reason else "")

        try:
            import sounddevice as sd
        except Exception as exc:
            logger.exception("Monitor failed")
            _set_status(f"Monitor failed: {exc}")
            return

        def _update_levels(start_idx: int, indata) -> None:
            if indata is None:
                return
            data = indata.astype("float32")
            max_abs = float(abs(data).max()) if data.size else 0.0
            data_scaled = data if max_abs <= 2.0 else data / 32768.0
            rms = float((data**2).mean() ** 0.5)
            channel_rms = (
                (data**2).mean(axis=0) ** 0.5 if data.ndim == 2 else [rms]
            )
            mono = (
                data_scaled.mean(axis=1)
                if data_scaled.ndim == 2
                else data_scaled
            )
            step = max(1, int(len(mono) / 120))
            samples = mono[::step].tolist()
            with monitor["lock"]:
                monitor["waveform"].extend(samples)
            with monitor["lock"]:
                needed = start_idx + len(channel_rms)
                if len(monitor["channels"]) < needed:
                    extend_by = needed - len(monitor["channels"])
                    monitor["channels"].extend([0.0] * extend_by)
                    monitor["peaks"].extend([0.0] * extend_by)
                for offset, value in enumerate(channel_rms):
                    idx = start_idx + offset
                    monitor["channels"][idx] = float(value)
                    monitor["peaks"][idx] = max(monitor["peaks"][idx], float(value))
                monitor["level"] = max(monitor["channels"], default=0.0)
                monitor["peak"] = max(monitor["peaks"], default=0.0)
                monitor["last_update"] = time.time()
                monitor["update_count"] += 1

        mode = capture_mode_var.get().strip()
        try:
            _log_fields("monitor_start")
            monitor["labels"] = _build_channel_map(mode)
            if mode == "dual":
                mic_device = mic_device_var.get().strip()
                system_device = system_device_var.get().strip()
                mic_requested = int(mic_channels_var.get())
                sys_requested = int(system_channels_var.get())

                try:
                    mic_info = sd.query_devices(mic_device or None, "input")
                except Exception:
                    mic_info = sd.query_devices(None, "input")
                    mic_device = ""
                    _set_status("Mic device not found, using default.")
                try:
                    sys_info = sd.query_devices(system_device or None, "output")
                except Exception:
                    sys_info = sd.query_devices(None, "output")
                    system_device = ""
                    _set_status("System device not found, using default.")

                mic_max = mic_info.get("max_input_channels", 0) or 1
                sys_max = sys_info.get("max_output_channels", 0) or 1
                mic_index = mic_info.get("index")
                sys_index = sys_info.get("index")
                mic_channels = min(mic_requested, mic_max)
                sys_channels = min(sys_requested, sys_max)
                if mic_channels != mic_requested or sys_channels != sys_requested:
                    _set_status(
                        "Monitor channels adjusted "
                        f"(mic {mic_channels}/{mic_max}, sys {sys_channels}/{sys_max})"
                    )
                monitor["labels"] = (
                    _build_channel_map("mic")[:mic_channels]
                    + _build_channel_map("system")[:sys_channels]
                )
                with monitor["lock"]:
                    monitor["channels"] = [0.0] * (mic_channels + sys_channels)
                    monitor["peaks"] = [0.0] * (mic_channels + sys_channels)

                def _cb_mic(indata, _frames, _time, status):
                    if status:
                        logger.debug("Monitor mic status: %s", status)
                    _update_levels(0, indata)

                def _cb_sys(indata, _frames, _time, status):
                    if status:
                        logger.debug("Monitor system status: %s", status)
                    _update_levels(mic_channels, indata)

                sys_settings = None
                if hasattr(sd, "WasapiSettings"):
                    try:
                        sys_settings = sd.WasapiSettings(loopback=True)
                    except TypeError:
                        sys_settings = None
                mic_stream = sd.InputStream(
                    samplerate=int(rate_var.get()),
                    channels=mic_channels,
                    dtype="int16",
                    device=mic_index if mic_index is not None else mic_device or None,
                    callback=_cb_mic,
                )
                sys_stream = sd.InputStream(
                    samplerate=int(rate_var.get()),
                    channels=sys_channels,
                    dtype="int16",
                    device=sys_index if sys_index is not None else system_device or None,
                    callback=_cb_sys,
                    extra_settings=sys_settings,
                )
                mic_stream.start()
                sys_stream.start()
                monitor["streams"] = [mic_stream, sys_stream]
            else:
                monitor_device = (
                    system_device_var.get().strip()
                    if mode == "system"
                    else mic_device_var.get().strip()
                )
                requested_channels = (
                    int(system_channels_var.get())
                    if mode == "system"
                    else int(mic_channels_var.get())
                )
                device_index = None
                try:
                    dev_info = sd.query_devices(
                        monitor_device or None,
                        "output" if mode == "system" else "input",
                    )
                    device_index = dev_info.get("index")
                except Exception:
                    dev_info = sd.query_devices(
                        None, "output" if mode == "system" else "input"
                    )
                    device_index = dev_info.get("index")
                    monitor_device = ""
                    _set_status("Device not found, using default.")
                max_in = (
                    dev_info.get("max_output_channels", 0)
                    if mode == "system"
                    else dev_info.get("max_input_channels", 0)
                )
                monitor_channels = min(requested_channels, max_in) if max_in else 1
                if monitor_channels != requested_channels:
                    _set_status(
                        f"Monitor channels adjusted to {monitor_channels} (max {max_in})"
                    )
                monitor["labels"] = _build_channel_map(mode)[:monitor_channels]
                with monitor["lock"]:
                    monitor["channels"] = [0.0] * monitor_channels
                    monitor["peaks"] = [0.0] * monitor_channels

                def _cb(indata, _frames, _time, status):
                    if status:
                        logger.debug("Monitor status: %s", status)
                    _update_levels(0, indata)

                extra_settings = None
                if mode == "system" and hasattr(sd, "WasapiSettings"):
                    try:
                        extra_settings = sd.WasapiSettings(loopback=True)
                    except TypeError:
                        extra_settings = None
                stream = sd.InputStream(
                    samplerate=int(rate_var.get()),
                    channels=monitor_channels,
                    dtype="int16",
                    device=device_index if device_index is not None else None,
                    callback=_cb,
                    extra_settings=extra_settings,
                )
                stream.start()
                monitor["streams"] = [stream]
            monitor["config"] = cfg
            _set_status(f"Monitoring levels ({mode})...")
        except Exception as exc:
            logger.exception("Monitor failed")
            _set_status(f"Monitor failed: {exc}")
            monitor["config"] = None

    def _ensure_monitoring(reason: str = "auto") -> None:
        if monitor["streams"] and monitor["config"] == _monitor_config():
            return
        _start_monitoring(force=True, reason=reason)

    def _schedule_monitor_refresh(reason: str = "config_change") -> None:
        nonlocal monitor_refresh_job
        if monitor_refresh_job is not None:
            root.after_cancel(monitor_refresh_job)
        monitor_refresh_job = root.after(300, lambda: _ensure_monitoring(reason))

    def _open_hud() -> None:
        logger.info("Open HUD")
        if monitor["hud"] is not None:
            return
        hud = tk.Toplevel(root)
        hud.title("EchoFrame Levels")
        hud.resizable(False, False)
        canvas = tk.Canvas(hud, width=320, height=180, bg="black")
        canvas.grid(row=0, column=0, padx=6, pady=6)
        monitor["hud"] = hud
        monitor["hud_canvas"] = canvas
        hud.protocol("WM_DELETE_WINDOW", _close_hud)

    def _close_hud() -> None:
        logger.info("Close HUD")
        if monitor["hud"] is not None:
            monitor["hud"].destroy()
        monitor["hud"] = None
        monitor["hud_canvas"] = None

    def _reset_peaks() -> None:
        logger.info("Reset peaks")
        with monitor["lock"]:
            monitor["peak"] = 0.0
            monitor["peaks"] = [0.0 for _ in monitor["peaks"]]
        _set_status("Peaks reset")

    def _append_feed(text: str) -> None:
        feed_box.configure(state="normal")
        feed_box.insert("end", text + "\n")
        feed_box.see("end")
        lines = int(feed_box.index("end-1c").split(".")[0])
        if lines > feed["max_lines"]:
            feed_box.delete("1.0", f"{lines - feed['max_lines']}.0")
        feed_box.configure(state="disabled")

    def _poll_feed() -> None:
        while True:
            try:
                item = feed["queue"].get_nowait()
            except queue.Empty:
                break
            _append_feed(str(item))
        root.after(200, _poll_feed)

    def _poll_transcribe_progress() -> None:
        while True:
            try:
                item = transcribe["progress_queue"].get_nowait()
            except queue.Empty:
                break
            if item == "start":
                progress_var.set(0)
                progress_label_var.set("Final transcription 0%")
                transcribe["stage"] = "transcribing"
                transcribe["ratio"] = 0.0
            elif item == "done":
                progress_var.set(100)
                progress_label_var.set("Final transcription complete")
                transcribe["stage"] = "transcribed"
                transcribe["ratio"] = 1.0
            elif item == "diarize_start":
                progress_var.set(0)
                progress_label_var.set("Diarization 0%")
                transcribe["stage"] = "diarizing"
                transcribe["ratio"] = 0.0
            elif item == "diarize_done":
                progress_var.set(100)
                progress_label_var.set("Diarization complete")
                transcribe["stage"] = "diarized"
                transcribe["ratio"] = 1.0
            elif isinstance(item, float):
                pct = int(item * 100)
                progress_var.set(pct)
                label = (
                    "Final transcription" if progress_label_var.get().startswith("Final")
                    else "Diarization"
                )
                progress_label_var.set(f"{label} {pct}%")
                transcribe["ratio"] = min(max(item, 0.0), 1.0)
        root.after(200, _poll_transcribe_progress)

    def _stop_live_transcriber() -> None:
        live["stop_event"].set()
        if live["audio_queue"] is not None:
            try:
                live["audio_queue"].put_nowait(None)
            except Exception:
                pass
        live["audio_queue"] = None

    def _start_live_transcriber(sample_rate_hz: int, channels: int) -> None:
        if not live_transcribe_var.get():
            return
        live["stop_event"].clear()
        live["audio_queue"] = queue.Queue(maxsize=50)
        live["text_queue"].put("[Live transcription starting...]\n")

        def _worker() -> None:
            try:
                import numpy as np
                from faster_whisper import WhisperModel
            except Exception as exc:
                live["text_queue"].put(f"\n[Live transcription unavailable: {exc}]\n")
                return

            model_name = live_model_var.get().strip() or "tiny"
            kwargs = {}
            if device_pref_var.get().strip():
                kwargs["device"] = device_pref_var.get().strip()
            if compute_type_var.get().strip():
                kwargs["compute_type"] = compute_type_var.get().strip()
            model = WhisperModel(model_name, **kwargs)

            chunk_seconds = 4
            overlap_seconds = 0.5
            chunk_samples = int(sample_rate_hz * chunk_seconds)
            overlap_samples = int(sample_rate_hz * overlap_seconds)
            buffer = np.zeros((0, channels), dtype=np.float32)
            language = language_var.get().strip() or None

            while True:
                try:
                    item = live["audio_queue"].get(timeout=0.25)
                except queue.Empty:
                    if live["stop_event"].is_set():
                        break
                    continue
                if item is None:
                    if live["stop_event"].is_set():
                        break
                    continue

                chunk = item
                if chunk.ndim == 1:
                    chunk = chunk.reshape(-1, 1)
                if chunk.dtype != np.float32:
                    chunk = chunk.astype(np.float32) / 32768.0
                buffer = np.concatenate([buffer, chunk], axis=0)

                while buffer.shape[0] >= chunk_samples:
                    segment = buffer[:chunk_samples]
                    if overlap_samples > 0:
                        buffer = buffer[chunk_samples - overlap_samples :]
                    else:
                        buffer = buffer[chunk_samples:]
                    if segment.shape[1] > 1:
                        audio_mono = segment.mean(axis=1)
                    else:
                        audio_mono = segment[:, 0]
                    try:
                        segments, _info = model.transcribe(
                            audio_mono, language=language
                        )
                    except Exception as exc:
                        live["text_queue"].put(
                            f"\n[Live transcription error: {exc}]\n"
                        )
                        continue
                    text = " ".join(s.text.strip() for s in segments).strip()
                    if text:
                        live["text_queue"].put(text + " ")

            if buffer.shape[0] > 0:
                if buffer.shape[1] > 1:
                    audio_mono = buffer.mean(axis=1)
                else:
                    audio_mono = buffer[:, 0]
                try:
                    segments, _info = model.transcribe(audio_mono, language=language)
                except Exception:
                    return
                text = " ".join(s.text.strip() for s in segments).strip()
                if text:
                    live["text_queue"].put(text + " ")

        live["thread"] = threading.Thread(target=_worker, daemon=True)
        live["thread"].start()

    def _update_hud(
        levels: list[float], peaks: list[float], labels: list[str]
    ) -> None:
        canvas = monitor["hud_canvas"]
        if canvas is None:
            return
        canvas.delete("all")
        bar_w = 40
        gap = 10
        max_h = 120
        for idx, level in enumerate(levels):
            x0 = 10 + idx * (bar_w + gap)
            x1 = x0 + bar_w
            h = min(max_h, int(level * max_h))
            if level < 0.6:
                color = "lime"
            elif level < 0.85:
                color = "yellow"
            else:
                color = "red"
            canvas.create_rectangle(
                x0, 10 + (max_h - h), x1, 10 + max_h, fill=color
            )
            if idx < len(peaks):
                ph = min(max_h, int(peaks[idx] * max_h))
                canvas.create_line(
                    x0, 10 + (max_h - ph), x1, 10 + (max_h - ph), fill="red"
                )
            label = labels[idx] if idx < len(labels) else f"ch{idx+1}"
            canvas.create_text(
                x0 + bar_w / 2, 10 + max_h + 12, text=label, fill="white"
            )

    def _render_meters(
        levels: list[float], peaks: list[float], labels: list[str]
    ) -> None:
        if meter_canvas is None:
            return
        canvas = meter_canvas
        canvas.delete("all")
        if not levels:
            canvas.create_text(
                10,
                10,
                anchor="nw",
                text="No active levels yet. Waiting for input device.",
                fill="#6aa6ff",
            )
            return
        width = int(canvas.winfo_width() or 520)
        height = int(canvas.winfo_height() or 120)
        left_margin = 10
        top_margin = 10
        max_h = max(30, height - 30)
        count = len(levels)
        gap = 6
        usable = max(10, width - left_margin * 2 - gap * (count - 1))
        bar_w = max(10, int(usable / max(1, count)))
        for idx, level in enumerate(levels):
            x0 = left_margin + idx * (bar_w + gap)
            x1 = x0 + bar_w
            h = min(max_h, int(level * max_h))
            if level < 0.6:
                color = "#32ff7e"
            elif level < 0.85:
                color = "#ff9f43"
            else:
                color = "#ff4d6d"
            canvas.create_rectangle(
                x0, top_margin + (max_h - h), x1, top_margin + max_h, fill=color
            )
            if idx < len(peaks):
                ph = min(max_h, int(peaks[idx] * max_h))
                canvas.create_line(
                    x0,
                    top_margin + (max_h - ph),
                    x1,
                    top_margin + (max_h - ph),
                fill="#ff5bd1",
            )
            label = labels[idx] if idx < len(labels) else f"ch{idx+1}"
            canvas.create_text(
                x0 + bar_w / 2,
                top_margin + max_h + 10,
                text=label,
                fill="#8bd3ff",
            )

    def _render_waveform(samples: list[float]) -> None:
        if waveform_canvas is None:
            return
        canvas = waveform_canvas
        canvas.delete("all")
        if not samples:
            canvas.create_text(
                10,
                10,
                anchor="nw",
                text="Waiting for input...",
                fill="#6aa6ff",
            )
            return
        width = int(canvas.winfo_width() or 520)
        height = int(canvas.winfo_height() or 120)
        mid_y = int(height / 2)
        max_amp = max(max(samples, default=0.0), abs(min(samples, default=0.0)))
        max_amp = max(max_amp, 0.05)
        scale = (height / 2 - 8) / max_amp
        count = len(samples)
        points = []
        for idx, sample in enumerate(samples):
            x = int(idx * (width - 2) / max(1, count - 1)) + 1
            y = int(mid_y - sample * scale)
            points.append((x, y))

        stage = transcribe["stage"]
        ratio = float(transcribe["ratio"] or 0.0)
        if state["recording"]:
            stage = "recording"
            ratio = 0.0
        color_map = {
            "recording": "#2de2e6",
            "transcribing": "#ff4d6d",
            "transcribed": "#ff9f43",
            "diarizing": "#ff9f43",
            "diarized": "#32ff7e",
            "idle": "#6aa6ff",
        }
        base_color = "#233044"
        progress_color = color_map.get(stage, "#6aa6ff")

        def _flatten(items: list[tuple[int, int]]) -> list[int]:
            flat = []
            for x, y in items:
                flat.extend([x, y])
            return flat

        split_idx = int(ratio * (count - 1)) if count > 1 else 0
        if split_idx > 1:
            canvas.create_line(
                _flatten(points[: split_idx + 1]),
                fill=progress_color,
                width=2,
            )
        if split_idx < count - 1:
            canvas.create_line(
                _flatten(points[split_idx:]),
                fill=base_color,
                width=2,
            )

        if stage in ("transcribing", "diarizing"):
            progress_x = int(ratio * (width - 2)) + 1
            canvas.create_line(
                progress_x,
                6,
                progress_x,
                height - 6,
                fill=progress_color,
                width=2,
            )

    def _update_waveform() -> None:
        with monitor["lock"]:
            samples = list(monitor["waveform"])
        if len(samples) > waveform_render_max:
            samples = samples[-waveform_render_max:]
        _render_waveform(samples)
        root.after(waveform_refresh_ms, _update_waveform)

    def _build_channel_map(mode: str) -> list[str]:
        mic_count = int(mic_channels_var.get())
        sys_count = int(system_channels_var.get())
        if mic_count <= 2:
            mic_labels = ["left", "right"][:mic_count]
        else:
            mic_labels = ["front_left", "front_right", "rear_left", "rear_right"][
                :mic_count
            ]
        sys_labels = ["system_left", "system_right", "system_rl", "system_rr"][
            :sys_count
        ]
        if mode == "dual":
            return mic_labels + sys_labels
        if mode == "system":
            return sys_labels
        return mic_labels

    def _format_segments(segments: list) -> str:
        lines = []
        for seg in segments:
            label = f"{seg.speaker}: " if getattr(seg, "speaker", None) else ""
            lines.append(f"{label}{seg.text.strip()}")
        return "\n".join(lines) + ("\n" if lines else "")

    def _start_recording(context_type: str) -> None:
        if state["recording"]:
            return
        logger.info("Start recording requested (%s)", context_type)
        state["active_contact"] = contact_var.get().strip()
        state["active_contact_id"] = contact_id_var.get().strip()
        state["pending_contact"] = ""
        state["recording"] = True
        state["start_time"] = time.time()
        state["stop_event"].clear()
        timer_var.set("00:00")
        state["timestamped_notes"] = []
        with monitor["lock"]:
            monitor["waveform"].clear()
        _refresh_timestamped_notes()
        _set_status(f"Recording ({context_type})...")
        _save_last_used()
        _ensure_monitoring("recording_start")
        _log_fields("recording_start")

        title = title_var.get().strip() or context_type
        paths = get_output_dirs(
            config.base_dir,
            context_type=context_type,
            use_type_folders=use_type_folders_var.get(),
        )
        out_dir = paths["recordings"]
        basename = build_session_basename(title, datetime.now())
        output_path = os.path.join(out_dir, f"{basename}.wav")
        logger.info("Start recording: %s", output_path)

        recording_start = datetime.now()

        def _worker() -> None:
            try:
                mode = capture_mode_var.get()
                try:
                    mic_count = int(mic_channels_var.get())
                except ValueError:
                    mic_count = 1
                try:
                    system_count = int(system_channels_var.get())
                except ValueError:
                    system_count = 1
                def _enqueue_audio(chunk) -> None:
                    if live["audio_queue"] is None:
                        return
                    try:
                        live["audio_queue"].put_nowait(chunk)
                    except queue.Full:
                        pass

                if mode == "dual":
                    record_result = record_audio_stream_dual(
                        output_path=output_path,
                        sample_rate_hz=int(rate_var.get()),
                        mic_channels=int(mic_channels_var.get()),
                        system_channels=int(system_channels_var.get()),
                        mic_device_name=mic_device_var.get().strip() or None,
                        system_device_name=system_device_var.get().strip() or None,
                        stop_event=state["stop_event"],
                        on_chunk=_enqueue_audio,
                    )
                else:
                    record_result = record_audio_stream(
                        output_path=output_path,
                        sample_rate_hz=int(rate_var.get()),
                        channels=int(system_channels_var.get())
                        if mode == "system"
                        else int(mic_channels_var.get()),
                        device_name=system_device_var.get().strip() or None
                        if mode == "system"
                        else mic_device_var.get().strip() or None,
                        stop_event=state["stop_event"],
                        loopback=mode == "system",
                        on_chunk=_enqueue_audio,
                    )

                state["recording"] = False
                state["start_time"] = None
                _stop_live_transcriber()
                _set_status("Transcribing...")
                transcribe["progress_queue"].put("start")

                transcribe_path = output_path
                if mode == "dual":
                    mic_count = int(mic_channels_var.get())
                    segments_dir = paths["segments"]
                    ensure_dir(segments_dir)
                    mic_only_path = os.path.join(
                        segments_dir, f"{basename}.mic.wav"
                    )
                    extract_channels(
                        output_path, mic_only_path, list(range(0, mic_count))
                    )
                    transcribe_path = mic_only_path
                elif mode == "mic":
                    mic_count = int(mic_channels_var.get())
                    if mic_count > 2:
                        segments_dir = paths["segments"]
                        ensure_dir(segments_dir)
                        front_path = os.path.join(
                            segments_dir, f"{basename}.front.wav"
                        )
                        extract_channels(output_path, front_path, [0, 1])
                        transcribe_path = front_path

                total_duration_s = (
                    record_result.duration_seconds
                    if record_result and record_result.duration_seconds
                    else None
                )

                def _progress_cb(ratio: float) -> None:
                    transcribe["progress_queue"].put(ratio)

                segments = transcribe_audio(
                    transcribe_path,
                    model_name=model_var.get().strip() or "small",
                    language=language_var.get().strip() or None,
                    device=device_pref_var.get().strip() or None,
                    compute_type=compute_type_var.get().strip() or None,
                    progress_cb=_progress_cb,
                    total_duration_s=total_duration_s,
                )
                transcribe["progress_queue"].put("done")
                if segments:
                    _set_status("Final transcription ready")

                _set_status("Diarizing...")
                transcribe["progress_queue"].put("diarize_start")
                try:
                    speaker_map = {}
                    for pair in speaker_map_var.get().split(","):
                        if ":" in pair:
                            k, v = pair.split(":", 1)
                            speaker_map[k.strip()] = v.strip()
                    segments = diarize_segments(
                        transcribe_path,
                        segments,
                        speaker_map=speaker_map or None,
                        hf_token=hf_token_var.get().strip() or None,
                    )
                    _set_status("Diarization complete")
                    transcribe["progress_queue"].put("diarize_done")
                except Exception as exc:
                    logger.exception("Diarization failed")
                    _set_status(f"Diarization failed: {exc}")

                title = title_var.get().strip() or context_type
                date_str = datetime.now().strftime("%Y-%m-%d")
                audio_filename = os.path.basename(output_path)

                participants = []
                if user_name_var.get().strip():
                    participants.append(user_name_var.get().strip())
                if contact_var.get().strip():
                    participants.append(contact_var.get().strip())
                if attendees_var.get().strip():
                    participants.extend(
                        [p.strip() for p in attendees_var.get().split(",") if p.strip()]
                    )

                tags = [t.strip() for t in tags_var.get().split(",") if t.strip()]
                if auto_tags_var.get():
                    if context_type and context_type not in tags:
                        tags.append(context_type)
                    if project_var.get().strip() and project_var.get().strip() not in tags:
                        tags.append(project_var.get().strip())

                end_ts = datetime.now()
                debug_log = _collect_debug_log(recording_start, end_ts)

                contact_name = (
                    state["active_contact"] or contact_var.get().strip() or "Unknown"
                )
                contact_id = state["active_contact_id"] or contact_id_var.get().strip() or None
                organization = org_var.get().strip() or None
                project = project_var.get().strip() or None
                location = location_var.get().strip() or None
                channel = channel_var.get().strip() or None

                notes_root = base_paths["notes"]
                note_path = _contact_daily_note_path(
                    notes_root, contact_name, date_str
                )
                mic_device_display = (
                    _describe_device(mic_device_var.get().strip(), "input")
                    if mode != "system"
                    else None
                )
                system_device_display = (
                    _describe_device(system_device_var.get().strip(), "output")
                    if mode != "mic"
                    else None
                )
                system_channels = (
                    int(system_channels_var.get()) if mode != "mic" else None
                )
                section = render_recording_section(
                    title=title,
                    date=date_str,
                    audio_filename=audio_filename,
                    segments=segments,
                    participants=participants or None,
                    tags=tags or None,
                    duration_seconds=record_result.duration_seconds,
                    capture_mode=mode,
                    mic_device=mic_device_display,
                    system_device=system_device_display,
                    sample_rate_hz=int(rate_var.get()),
                    bit_depth=16,
                    channels=int(
                        mic_channels_var.get()
                        if mode != "system"
                        else system_channels_var.get()
                    ),
                    system_channels=system_channels,
                    channel_map=_build_channel_map(mode),
                    context_type=context_type,
                    context_notes=notes_box.get("1.0", "end").strip() or None,
                    timestamped_notes=state["timestamped_notes"],
                    debug_log=debug_log or None,
                    started_at=recording_start.isoformat(timespec="seconds"),
                    ended_at=end_ts.isoformat(timespec="seconds"),
                )
                if not os.path.exists(note_path):
                    header = render_contact_note_header(
                        date_str,
                        contact_name,
                        contact_id=contact_id,
                        organization=organization,
                        project=project,
                        location=location,
                        channel=channel,
                        tags=tags or None,
                    )
                    with open(note_path, "w", encoding="utf-8") as handle:
                        handle.write(f"{header}{section}")
                else:
                    with open(note_path, "a", encoding="utf-8") as handle:
                        handle.write("\n" + section)

                segments_path = os.path.join(
                    paths["segments"], f"{basename}.segments.json"
                )
                session_path = os.path.join(
                    paths["sessions"], f"{basename}.session.json"
                )
                save_segments(segments_path, segments)
                session = Session(
                    session_id=basename,
                    title=title,
                    started_at=date_str,
                    duration_seconds=record_result.duration_seconds,
                    audio_path=output_path,
                    segments=segments,
                    note_path=note_path,
                    ai_summary=None,
                    ai_sentiment=None,
                    context_type=context_type,
                    contact_name=contact_name,
                    contact_id=contact_id,
                    organization=organization,
                    project=project,
                    location=location,
                    channel=channel,
                    context_notes=notes_box.get("1.0", "end").strip() or None,
                    timestamped_notes=list(state["timestamped_notes"]),
                )
                save_session(session_path, session)

                _set_status(f"Saved: {note_path}")
                logger.info("Note saved: %s", note_path)
                _cleanup_recordings(base_paths["recordings"], hours=48)
            except Exception as exc:
                logger.exception("Recording workflow failed")
                _set_status(f"Recording failed: {exc}")
            finally:
                if state["recording"]:
                    state["recording"] = False
                state["start_time"] = None
                _stop_live_transcriber()
                if state["pending_contact"]:
                    state["active_contact"] = state["pending_contact"]
                    state["active_contact_id"] = contact_id_var.get().strip()
                    state["pending_contact"] = ""
                _update_note_controls()

        state["thread"] = threading.Thread(target=_worker, daemon=True)
        state["thread"].start()

    def _stop_recording() -> None:
        if not state["recording"]:
            return
        logger.info("Stop recording requested")
        state["stop_event"].set()
        _stop_live_transcriber()
        _save_last_used()
        _set_status("Stopping...")

    def _close_contact() -> None:
        if state["recording"]:
            proceed = messagebox.askyesno(
                "Close contact",
                "Stop recording and close this contact file?",
            )
            if not proceed:
                return
            state["suppress_contact_prompt"] = True
            _stop_recording()
        else:
            state["suppress_contact_prompt"] = True
        state["active_contact"] = ""
        state["active_contact_id"] = ""
        state["pending_contact"] = ""
        contact_var.set("")
        contact_id_var.set("")
        state["timestamped_notes"] = []
        _refresh_timestamped_notes()
        _update_note_controls()
        state["suppress_contact_prompt"] = False
        _set_status("Contact closed. Ready for next contact.")

    def _start_custom() -> None:
        context_type = context_type_var.get().strip() or "Session"
        _start_recording(context_type)

    def _apply_profile_by_name(name: str) -> None:
        if not name:
            return
        logger.info("Apply profile: %s", name)
        match = next(
            (p for p in presets["profiles"] if p.get("name") == name), None
        )
        if not match:
            return
        context_type_var.set(match.get("context_type", context_type_var.get()))
        channel_var.set(match.get("channel", channel_var.get()))
        if match.get("project"):
            project_var.set(match.get("project"))
        if match.get("organization"):
            org_var.set(match.get("organization"))
        if match.get("tags"):
            tags_var.set(", ".join(match.get("tags", [])))
        _log_fields("apply_profile")

    def _apply_profile(_event=None) -> None:
        _apply_profile_by_name(profile_var.get().strip())

    def _apply_context_type(label: str) -> None:
        context_type_var.set(label)
        profile_var.set("")
        _apply_profile_by_name(label)
        if not title_var.get().strip():
            title_var.set(label)
        if auto_tags_var.get():
            tags = [t.strip() for t in tags_var.get().split(",") if t.strip()]
            if label and label not in tags:
                tags.append(label)
                tags_var.set(", ".join(tags))
        _log_fields("apply_context_type")

    def _handle_contact_change() -> None:
        if state["suppress_contact_prompt"]:
            return
        new_contact = contact_var.get().strip()
        if not state["active_contact"]:
            state["active_contact"] = new_contact
            state["active_contact_id"] = contact_id_var.get().strip()
            _update_note_controls()
            return
        if new_contact == state["active_contact"]:
            _update_note_controls()
            return
        if state["recording"]:
            proceed = messagebox.askyesno(
                "Split session",
                "Contact changed during recording. Stop now and start a new file for the new contact?",
            )
            if proceed:
                state["pending_contact"] = new_contact
                _stop_recording()
                _set_status("Recording stopped for contact split. Press Start to continue.")
            else:
                state["suppress_contact_prompt"] = True
                contact_var.set(state["active_contact"])
                state["suppress_contact_prompt"] = False
            _update_note_controls()
            return
        if state["timestamped_notes"]:
            proceed = messagebox.askyesno(
                "Clear contact notes",
                "Contact changed. Clear timestamped notes from the previous contact?",
            )
            if proceed:
                state["timestamped_notes"] = []
                _refresh_timestamped_notes()
        state["active_contact"] = new_contact
        state["active_contact_id"] = contact_id_var.get().strip()
        _update_note_controls()

    def _save_profile() -> None:
        name = profile_name_var.get().strip()
        if not name:
            _set_status("Profile name required")
            return
        logger.info("Save profile: %s", name)
        profile = {
            "name": name,
            "context_type": context_type_var.get().strip(),
            "channel": channel_var.get().strip(),
            "project": project_var.get().strip() or None,
            "organization": org_var.get().strip() or None,
            "tags": [t.strip() for t in tags_var.get().split(",") if t.strip()],
        }
        presets["profiles"] = [p for p in presets["profiles"] if p.get("name") != name]
        presets["profiles"].append(profile)
        profile_combo["values"] = [p.get("name") for p in presets["profiles"]]
        profile_var.set(name)
        _log_fields("save_profile")
        _set_status("Profile saved")

    def _clear_fields() -> None:
        logger.info("Clear fields")
        title_var.set("")
        user_name_var.set(config.context.get("user_name", ""))
        attendees_var.set("")
        contact_var.set("")
        contact_id_var.set("")
        org_var.set("")
        project_var.set("")
        location_var.set("")
        notes_box.delete("1.0", "end")
        tags_var.set("")
        context_type_var.set(
            config.context.get("default_context_type", presets["context_types"][0])
        )
        state["active_contact"] = ""
        state["timestamped_notes"] = []
        _refresh_timestamped_notes()
        _update_note_controls()
        channel_var.set(
            config.context.get("default_channel", presets["channels"][0])
        )
        profile_var.set("")
        profile_name_var.set("")
        _log_fields("clear_fields")
        _set_status("Cleared")

    menubar = tk.Menu(root)
    settings_menu = tk.Menu(menubar, tearoff=0)
    view_menu = tk.Menu(menubar, tearoff=0)
    help_menu = tk.Menu(menubar, tearoff=0)
    dev_menu = tk.Menu(help_menu, tearoff=0)
    root.config(menu=menubar)
    menubar.add_cascade(label="Settings", menu=settings_menu)
    menubar.add_cascade(label="View", menu=view_menu)
    menubar.add_cascade(label="Help", menu=help_menu)
    help_menu.add_cascade(label="Developer", menu=dev_menu)

    def _open_log_viewer() -> None:
        logger.info("Open log viewer")
        win = tk.Toplevel(root)
        win.title("EchoFrame Log")
        win.resizable(True, True)
        text = tk.Text(win, width=100, height=30)
        text.grid(row=0, column=0, columnspan=2, sticky="nsew")
        scroll = ttk.Scrollbar(win, command=text.yview)
        scroll.grid(row=0, column=2, sticky="ns")
        text.configure(yscrollcommand=scroll.set)

        def _refresh() -> None:
            text.delete("1.0", "end")
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as handle:
                    text.insert("end", handle.read())
            else:
                text.insert("end", "Log file not found.\n")

        ttk.Button(win, text="Refresh", command=_refresh).grid(
            row=1, column=0, sticky="w", pady=(6, 6), padx=(6, 0)
        )
        ttk.Button(win, text="Close", command=win.destroy).grid(
            row=1, column=1, sticky="e", pady=(6, 6), padx=(0, 6)
        )
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)
        _refresh()

    def _open_log_folder() -> None:
        logger.info("Open log folder")
        log_dir = os.path.dirname(log_path)
        try:
            os.startfile(log_dir)  # type: ignore[attr-defined]
        except Exception as exc:
            _set_status(f"Open log folder failed: {exc}")

    def _enable_debug() -> None:
        logger.info("Enable debug logging")
        logger.setLevel(logging.DEBUG)
        debug_enabled_var.set(True)
        config.context["debug_logging"] = True
        save_config(config_path, config)
        _update_debug_badge()
        _set_status("Debug logging enabled")

    def _toggle_debug() -> None:
        logger.info("Toggle debug logging")
        enabled = not debug_enabled_var.get()
        debug_enabled_var.set(enabled)
        logger.setLevel(logging.DEBUG if enabled else logging.INFO)
        config.context["debug_logging"] = enabled
        save_config(config_path, config)
        _update_debug_badge()
        _set_status("Debug logging enabled" if enabled else "Debug logging disabled")

    dev_menu.add_command(label="View Log", command=_open_log_viewer)
    dev_menu.add_command(label="Open Log Folder", command=_open_log_folder)
    dev_menu.add_command(label="Enable Debug Logging", command=_enable_debug)
    dev_menu.add_command(label="Toggle Debug Logging", command=_toggle_debug)

    def _open_audio_settings() -> None:
        logger.info("Open audio settings")
        win = tk.Toplevel(root)
        win.title("Audio settings")
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=8)
        frame.grid(row=0, column=0, sticky="nsew")

        device_choices = []
        system_choices = []
        all_devices = []
        hostapis = []
        try:
            devices = list_input_devices(loopback=False)
            device_choices = [d.get("name") for d in devices if d.get("name")]
        except Exception as exc:
            logger.debug("Device list failed: %s", exc)
        try:
            outputs = list_input_devices(loopback=True)
            system_choices = [d.get("name") for d in outputs if d.get("name")]
        except Exception as exc:
            logger.debug("System device list failed: %s", exc)
        try:
            import sounddevice as sd

            all_devices = sd.query_devices()
            hostapis = sd.query_hostapis()
        except Exception as exc:
            logger.debug("sounddevice details unavailable: %s", exc)

        ttk.Label(frame, text="Capture mode").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            frame,
            textvariable=capture_mode_var,
            values=["mic", "system", "dual"],
            width=12,
            state="readonly",
        ).grid(row=0, column=1, sticky="w")
        _ToolTip(frame.winfo_children()[-1], "Capture source: mic, system, or both.")
        ttk.Label(
            frame,
            text="System uses WASAPI loopback. Dual records mic + system together.",
            foreground="#6aa6ff",
        ).grid(row=0, column=2, sticky="w")

        ttk.Label(frame, text="Mic device").grid(row=1, column=0, sticky="w")
        mic_device_combo = ttk.Combobox(
            frame, textvariable=mic_device_var, values=device_choices, width=60
        )
        mic_device_combo.grid(
            row=1, column=1, sticky="w"
        )
        _ToolTip(mic_device_combo, "Select mic input device (Zoom, headset, etc.).")

        ttk.Label(frame, text="System device").grid(row=2, column=0, sticky="w")
        system_device_combo = ttk.Combobox(
            frame, textvariable=system_device_var, values=system_choices, width=60
        )
        system_device_combo.grid(
            row=2, column=1, sticky="w"
        )
        _ToolTip(system_device_combo, "Select output device for loopback capture.")

        details_frame = ttk.LabelFrame(
            frame, text="Selected device details", style="Neo.TLabelframe"
        )
        details_frame.grid(row=1, column=2, rowspan=6, sticky="n", padx=(8, 0))
        details_box = tk.Text(details_frame, width=48, height=10, wrap="word")
        details_box.grid(row=0, column=0, padx=6, pady=6)
        details_box.configure(state="disabled")

        ttk.Label(frame, text="Sample rate").grid(row=3, column=0, sticky="w")
        ttk.Entry(frame, textvariable=rate_var, width=12).grid(
            row=3, column=1, sticky="w"
        )
        _ToolTip(frame.winfo_children()[-1], "Sample rate in Hz (44100 or 48000).")

        ttk.Label(frame, text="Mic channels").grid(row=4, column=0, sticky="w")
        mic_channels_combo = ttk.Combobox(
            frame, textvariable=mic_channels_var, values=["1", "2", "4"], width=6
        )
        mic_channels_combo.grid(row=4, column=1, sticky="w")
        _ToolTip(mic_channels_combo, "Mic channel count (device limit applies).")

        ttk.Label(frame, text="System channels").grid(row=5, column=0, sticky="w")
        ttk.Combobox(
            frame, textvariable=system_channels_var, values=["1", "2", "4"], width=6
        ).grid(row=5, column=1, sticky="w")
        _ToolTip(frame.winfo_children()[-1], "Loopback channel count.")

        def _find_device_by_name(name: str) -> dict | None:
            if not name:
                return None
            exact = next((d for d in all_devices if d.get("name") == name), None)
            if exact:
                return exact
            name_lower = name.lower()
            return next(
                (d for d in all_devices if name_lower in d.get("name", "").lower()),
                None,
            )

        def _format_device_info(label: str, name: str) -> list[str]:
            info = _find_device_by_name(name)
            if not info:
                return [f"{label}: (not set)"]
            hostapi_name = ""
            host_idx = info.get("hostapi")
            if host_idx is not None and host_idx < len(hostapis):
                hostapi_name = hostapis[host_idx].get("name", "")
            lines = [
                f"{label}: {info.get('name', '')}",
                f"Index: {info.get('index', '')}",
                f"Host API: {hostapi_name}",
                f"Max input channels: {info.get('max_input_channels', 0)}",
                f"Max output channels: {info.get('max_output_channels', 0)}",
                f"Default sample rate: {info.get('default_samplerate', '')}",
                f"Default low input latency: {info.get('default_low_input_latency', '')}",
                f"Default high input latency: {info.get('default_high_input_latency', '')}",
                f"Default low output latency: {info.get('default_low_output_latency', '')}",
                f"Default high output latency: {info.get('default_high_output_latency', '')}",
                "HWID: unavailable via sounddevice",
            ]
            return lines

        def _update_device_details() -> None:
            mic_lines = _format_device_info("Mic", mic_device_var.get().strip())
            sys_lines = _format_device_info("System", system_device_var.get().strip())
            details_box.configure(state="normal")
            details_box.delete("1.0", "end")
            details_box.insert("end", "\n".join(mic_lines + [""] + sys_lines))
            details_box.configure(state="disabled")

        def _refresh_devices() -> None:
            try:
                refreshed = list_input_devices(loopback=False)
            except Exception as exc:
                _set_status(f"Device list failed: {exc}")
                return
            choices = [d.get("name") for d in refreshed if d.get("name")]
            mic_device_combo["values"] = choices
            try:
                refreshed_out = list_input_devices(loopback=True)
                out_choices = [d.get("name") for d in refreshed_out if d.get("name")]
                system_device_combo["values"] = out_choices
            except Exception as exc:
                _set_status(f"System device list failed: {exc}")
            _update_device_details()
            _set_status("Device list refreshed")
            _schedule_monitor_refresh("devices_refresh")

        def _apply_mic_device(_event=None) -> None:
            name = mic_device_var.get().strip()
            if not name:
                return
            try:
                devices = list_input_devices(loopback=False)
            except Exception:
                return
            match = next((d for d in devices if d.get("name") == name), None)
            max_in = match.get("max_input_channels", 0) if match else 0
            if max_in:
                mic_channels_combo["values"] = [str(c) for c in (1, 2, 4) if c <= max_in]
                if int(mic_channels_var.get() or "1") > max_in:
                    mic_channels_var.set(str(max_in))
                _set_status(f"Mic channels max {max_in}")
            _schedule_monitor_refresh("mic_device")

        mic_device_combo.bind("<<ComboboxSelected>>", _apply_mic_device)
        mic_device_combo.bind(
            "<<ComboboxSelected>>", lambda _e: _update_device_details()
        )

        def _apply_system_device(_event=None) -> None:
            _update_device_details()
            _schedule_monitor_refresh("system_device")

        system_device_combo.bind("<<ComboboxSelected>>", _apply_system_device)
        _update_device_details()

        ttk.Button(frame, text="Refresh devices", command=_refresh_devices).grid(
            row=6, column=0, sticky="w", pady=(6, 0)
        )

        def _close_audio_settings() -> None:
            win.destroy()
            _ensure_monitoring("audio_settings_close")

        ttk.Button(frame, text="Close", command=_close_audio_settings).grid(
            row=6, column=1, sticky="e", pady=(6, 0)
        )

    def _open_mic_setup_wizard() -> None:
        logger.info("Open mic setup wizard")
        win = tk.Toplevel(root)
        win.title("Mic setup wizard")
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=8)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(
            frame,
            text="Say this sentence clearly at your normal volume:",
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        sample_sentence = "The quick brown fox jumps over the lazy dog."
        ttk.Label(frame, text=sample_sentence, foreground="#6aa6ff").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 8)
        )

        status_var = tk.StringVar(value="Press Start to begin the level check.")
        result_var = tk.StringVar(value="")
        progress_var = tk.IntVar(value=0)
        running = {"active": False}

        ttk.Button(
            frame, text="Start test", command=lambda: _start_mic_test()
        ).grid(row=2, column=0, sticky="w")
        ttk.Progressbar(
            frame,
            maximum=100,
            variable=progress_var,
            length=240,
            style="Neo.Horizontal.TProgressbar",
        ).grid(row=2, column=1, sticky="w", padx=(8, 0))

        ttk.Label(frame, textvariable=status_var).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        ttk.Label(frame, textvariable=result_var, foreground="#9ad1ff").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )

        def _start_mic_test() -> None:
            if running["active"]:
                return
            running["active"] = True
            status_var.set("Recording sample...")
            result_var.set("")
            progress_var.set(0)

            def _worker() -> None:
                try:
                    import sounddevice as sd
                    import numpy as np
                except Exception as exc:
                    root.after(
                        0, lambda: status_var.set(f"Audio capture unavailable: {exc}")
                    )
                    running["active"] = False
                    return

                try:
                    sample_rate = int(rate_var.get())
                except ValueError:
                    sample_rate = 44100
                try:
                    channels = max(1, int(mic_channels_var.get()))
                except ValueError:
                    channels = 1

                duration_s = 6
                target_frames = duration_s * sample_rate
                frames_seen = 0
                sum_squares = 0.0
                total_samples = 0
                peak = 0.0
                clipped = 0

                def _callback(indata, frames, _time, status):
                    nonlocal frames_seen, sum_squares, total_samples, peak, clipped
                    if status:
                        pass
                    data = indata.astype("float32")
                    frames_seen += frames
                    peak = max(peak, float(abs(data).max()) if data.size else 0.0)
                    sum_squares += float((data**2).sum())
                    total_samples += data.size
                    clipped += int((abs(data) >= 32760).sum())

                try:
                    with sd.InputStream(
                        samplerate=sample_rate,
                        channels=channels,
                        dtype="int16",
                        device=mic_device_var.get().strip() or None,
                        callback=_callback,
                    ):
                        while frames_seen < target_frames:
                            sd.sleep(100)
                            ratio = min(frames_seen / target_frames, 1.0)
                            root.after(
                                0, lambda r=ratio: progress_var.set(int(r * 100))
                            )
                except Exception as exc:
                    root.after(
                        0, lambda: status_var.set(f"Capture failed: {exc}")
                    )
                    running["active"] = False
                    return

                if total_samples <= 0:
                    root.after(0, lambda: status_var.set("No audio captured."))
                    running["active"] = False
                    return

                rms = (sum_squares / total_samples) ** 0.5
                if rms <= 0:
                    rms_db = -120.0
                else:
                    rms_db = 20.0 * np.log10(rms / 32768.0)
                peak_db = 20.0 * np.log10(max(peak, 1.0) / 32768.0)
                clip_ratio = clipped / max(1, total_samples)

                if clip_ratio > 0.001 or peak_db > -1.0:
                    verdict = "Too hot: lower mic gain."
                elif rms_db < -30.0:
                    verdict = "Too low: raise mic gain."
                else:
                    verdict = "Good level for transcription."

                def _finish() -> None:
                    status_var.set("Level check complete.")
                    result_var.set(
                        f"RMS {rms_db:.1f} dBFS, Peak {peak_db:.1f} dBFS, "
                        f"Clipped {clip_ratio:.2%}. {verdict}"
                    )
                    running["active"] = False

                root.after(0, _finish)

            threading.Thread(target=_worker, daemon=True).start()

        ttk.Button(frame, text="Close", command=win.destroy).grid(
            row=5, column=1, sticky="e", pady=(8, 0)
        )

    def _open_transcription_settings() -> None:
        logger.info("Open transcription settings")
        win = tk.Toplevel(root)
        win.title("Transcription settings")
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=8)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text="Final model").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=model_var, width=12).grid(
            row=0, column=1, sticky="w"
        )
        _ToolTip(frame.winfo_children()[-1], "Whisper model for final transcript.")

        ttk.Label(frame, text="Language").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=language_var, width=12).grid(
            row=1, column=1, sticky="w"
        )
        _ToolTip(frame.winfo_children()[-1], "Optional language code (e.g., en).")

        ttk.Label(frame, text="Device pref").grid(row=2, column=0, sticky="w")
        ttk.Entry(frame, textvariable=device_pref_var, width=12).grid(
            row=2, column=1, sticky="w"
        )
        _ToolTip(frame.winfo_children()[-1], "Compute device preference (cpu/cuda).")

        ttk.Label(frame, text="Compute type").grid(row=3, column=0, sticky="w")
        ttk.Entry(frame, textvariable=compute_type_var, width=12).grid(
            row=3, column=1, sticky="w"
        )
        _ToolTip(frame.winfo_children()[-1], "Compute precision (int8/float16).")

        diarize_cb = ttk.Checkbutton(
            frame, text="Diarize", variable=diarize_var, state="disabled"
        )
        diarize_cb.grid(row=4, column=0, columnspan=2, sticky="w")
        _ToolTip(diarize_cb, "Always on: speaker diarization runs after transcription.")

        ttk.Label(frame, text="HF token").grid(row=5, column=0, sticky="w")
        ttk.Entry(frame, textvariable=hf_token_var, width=32, show="*").grid(
            row=5, column=1, sticky="w"
        )
        _ToolTip(frame.winfo_children()[-1], "HuggingFace token for diarization models.")

        ttk.Label(frame, text="Speaker map").grid(row=6, column=0, sticky="w")
        ttk.Entry(frame, textvariable=speaker_map_var, width=32).grid(
            row=6, column=1, sticky="w"
        )
        _ToolTip(frame.winfo_children()[-1], "Map speaker IDs (Speaker_0:Name).")

        ttk.Button(frame, text="Close", command=win.destroy).grid(
            row=7, column=1, sticky="e", pady=(6, 0)
        )

    def _open_output_settings() -> None:
        logger.info("Open output settings")
        win = tk.Toplevel(root)
        win.title("Output settings")
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=8)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Checkbutton(
            frame, text="Type folders", variable=use_type_folders_var
        ).grid(row=0, column=0, sticky="w")

        ttk.Button(frame, text="Close", command=win.destroy).grid(
            row=1, column=0, sticky="e", pady=(6, 0)
        )

    def _open_my_profile() -> None:
        logger.info("Open my profile")
        win = tk.Toplevel(root)
        win.title("My profile")
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=8)
        frame.grid(row=0, column=0, sticky="nsew")

        my_name_var = tk.StringVar(value=my_profile.get("user_name", user_name_var.get()))
        my_org_var = tk.StringVar(value=my_profile.get("org", org_var.get()))
        my_project_var = tk.StringVar(value=my_profile.get("project", project_var.get()))
        my_channel_var = tk.StringVar(value=my_profile.get("channel", channel_var.get()))
        my_tags_var = tk.StringVar(value=my_profile.get("tags", tags_var.get()))
        my_location_var = tk.StringVar(value=my_profile.get("location", location_var.get()))
        my_language_var = tk.StringVar(value=my_profile.get("language", language_var.get()))
        my_context_var = tk.StringVar(
            value=my_profile.get("default_context_type", context_type_var.get())
        )

        ttk.Label(frame, text="Your name").grid(row=0, column=0, sticky="w")
        name_entry = ttk.Entry(frame, textvariable=my_name_var, width=30)
        name_entry.grid(row=0, column=1, sticky="w")
        _ToolTip(name_entry, "Default name used on launch.")

        ttk.Label(frame, text="Org").grid(row=1, column=0, sticky="w")
        org_entry = ttk.Entry(frame, textvariable=my_org_var, width=30)
        org_entry.grid(row=1, column=1, sticky="w")
        _ToolTip(org_entry, "Default organization on launch.")

        ttk.Label(frame, text="Project").grid(row=2, column=0, sticky="w")
        project_entry = ttk.Entry(frame, textvariable=my_project_var, width=30)
        project_entry.grid(row=2, column=1, sticky="w")
        _ToolTip(project_entry, "Default project on launch.")

        ttk.Label(frame, text="Channel").grid(row=3, column=0, sticky="w")
        channel_entry = ttk.Entry(frame, textvariable=my_channel_var, width=30)
        channel_entry.grid(row=3, column=1, sticky="w")
        _ToolTip(channel_entry, "Default channel on launch.")

        ttk.Label(frame, text="Tags").grid(row=4, column=0, sticky="w")
        tags_entry = ttk.Entry(frame, textvariable=my_tags_var, width=30)
        tags_entry.grid(row=4, column=1, sticky="w")
        _ToolTip(tags_entry, "Default tags on launch.")

        ttk.Label(frame, text="Location").grid(row=5, column=0, sticky="w")
        location_entry = ttk.Entry(frame, textvariable=my_location_var, width=30)
        location_entry.grid(row=5, column=1, sticky="w")
        _ToolTip(location_entry, "Default location on launch.")

        ttk.Label(frame, text="Language").grid(row=6, column=0, sticky="w")
        language_entry = ttk.Entry(frame, textvariable=my_language_var, width=30)
        language_entry.grid(row=6, column=1, sticky="w")
        _ToolTip(language_entry, "Default language for transcription.")

        ttk.Label(frame, text="Default type").grid(row=7, column=0, sticky="w")
        type_entry = ttk.Entry(frame, textvariable=my_context_var, width=30)
        type_entry.grid(row=7, column=1, sticky="w")
        _ToolTip(type_entry, "Default context type on launch.")

        def _save_my_profile() -> None:
            my_profile.clear()
            my_profile.update(
                {
                    "user_name": my_name_var.get().strip(),
                    "org": my_org_var.get().strip(),
                    "project": my_project_var.get().strip(),
                    "channel": my_channel_var.get().strip(),
                    "tags": my_tags_var.get().strip(),
                    "location": my_location_var.get().strip(),
                    "language": my_language_var.get().strip(),
                    "default_context_type": my_context_var.get().strip(),
                }
            )
            config.context["my_profile"] = dict(my_profile)
            save_config(config_path, config)
            _apply_my_profile(my_profile)
            _set_status("My profile saved")
            win.destroy()

        save_btn = ttk.Button(frame, text="Save and Close", command=_save_my_profile)
        save_btn.grid(
            row=8, column=0, sticky="w", pady=(6, 0)
        )
        cancel_btn = ttk.Button(frame, text="Cancel", command=win.destroy)
        cancel_btn.grid(
            row=8, column=1, sticky="e", pady=(6, 0)
        )
        _ToolTip(save_btn, "Save defaults and apply them immediately.")
        _ToolTip(cancel_btn, "Close without saving.")

    def _open_manage_lists() -> None:
        logger.info("Open manage lists")
        win = tk.Toplevel(root)
        win.title("Manage lists")
        win.resizable(True, True)
        frame = ttk.Frame(win, padding=8)
        frame.grid(row=0, column=0, sticky="nsew")
        notebook = ttk.Notebook(frame)
        notebook.grid(row=0, column=0, sticky="nsew")

        def _build_list_tab(label: str, items: list[str]) -> ttk.Frame:
            tab = ttk.Frame(notebook)
            list_var = tk.StringVar(value=items)
            listbox = tk.Listbox(tab, listvariable=list_var, height=8, width=30)
            listbox.grid(row=0, column=0, rowspan=4, padx=(0, 6), sticky="ns")
            _ToolTip(listbox, f"{label} list. Select an item to edit or delete.")

            entry_var = tk.StringVar()
            entry = ttk.Entry(tab, textvariable=entry_var, width=26)
            entry.grid(row=0, column=1, sticky="w")
            _ToolTip(entry, f"Enter a {label.lower()} value.")

            def _refresh():
                list_var.set(items)

            def _add():
                value = entry_var.get().strip()
                if value and value not in items:
                    items.append(value)
                    _refresh()

            def _edit():
                sel = listbox.curselection()
                if not sel:
                    return
                idx = sel[0]
                value = entry_var.get().strip()
                if value:
                    items[idx] = value
                    _refresh()

            def _delete():
                sel = listbox.curselection()
                if not sel:
                    return
                idx = sel[0]
                items.pop(idx)
                _refresh()

            add_btn = ttk.Button(tab, text="Add", command=_add)
            add_btn.grid(row=1, column=1, sticky="w")
            edit_btn = ttk.Button(tab, text="Edit", command=_edit)
            edit_btn.grid(row=2, column=1, sticky="w")
            del_btn = ttk.Button(tab, text="Delete", command=_delete)
            del_btn.grid(row=3, column=1, sticky="w")
            _ToolTip(add_btn, f"Add the {label.lower()} value.")
            _ToolTip(edit_btn, f"Replace the selected {label.lower()} value.")
            _ToolTip(del_btn, f"Delete the selected {label.lower()} value.")
            return tab

        notebook.add(_build_list_tab("Organizations", presets["organizations"]), text="Organizations")
        notebook.add(_build_list_tab("Projects", presets["projects"]), text="Projects")
        notebook.add(_build_list_tab("Channels", presets["channels"]), text="Channels")
        notebook.add(_build_list_tab("Context Types", presets["context_types"]), text="Context Types")
        notebook.add(_build_list_tab("Tags", presets["tags"]), text="Tags")

        profiles_tab = ttk.Frame(notebook)
        notebook.add(profiles_tab, text="Profiles")
        profile_names = [p.get("name", "") for p in presets["profiles"]]
        profile_var_list = tk.StringVar(value=profile_names)
        profile_listbox = tk.Listbox(
            profiles_tab, listvariable=profile_var_list, height=8, width=30
        )
        profile_listbox.grid(row=0, column=0, rowspan=4, padx=(0, 6), sticky="ns")
        _ToolTip(profile_listbox, "Saved profiles for quick metadata fill.")

        def _refresh_profiles():
            profile_var_list.set([p.get("name", "") for p in presets["profiles"]])
            profile_combo["values"] = [p.get("name") for p in presets["profiles"]]

        def _profile_dialog(existing: dict | None = None) -> None:
            win_p = tk.Toplevel(win)
            win_p.title("Profile")
            win_p.resizable(False, False)
            f = ttk.Frame(win_p, padding=8)
            f.grid(row=0, column=0, sticky="nsew")

            name_var = tk.StringVar(value=existing.get("name", "") if existing else "")
            ctx_var = tk.StringVar(value=existing.get("context_type", "") if existing else "")
            chan_var = tk.StringVar(value=existing.get("channel", "") if existing else "")
            org_var_p = tk.StringVar(value=existing.get("organization", "") if existing else "")
            proj_var = tk.StringVar(value=existing.get("project", "") if existing else "")
            tags_var_p = tk.StringVar(
                value=", ".join(existing.get("tags", [])) if existing else ""
            )

            ttk.Label(f, text="Name").grid(row=0, column=0, sticky="w")
            name_entry = ttk.Entry(f, textvariable=name_var, width=24)
            name_entry.grid(row=0, column=1, sticky="w")
            _ToolTip(name_entry, "Profile name.")
            ttk.Label(f, text="Context").grid(row=1, column=0, sticky="w")
            ctx_entry = ttk.Entry(f, textvariable=ctx_var, width=24)
            ctx_entry.grid(row=1, column=1, sticky="w")
            _ToolTip(ctx_entry, "Context type to apply.")
            ttk.Label(f, text="Channel").grid(row=2, column=0, sticky="w")
            chan_entry = ttk.Entry(f, textvariable=chan_var, width=24)
            chan_entry.grid(row=2, column=1, sticky="w")
            _ToolTip(chan_entry, "Channel to apply.")
            ttk.Label(f, text="Org").grid(row=3, column=0, sticky="w")
            org_entry = ttk.Entry(f, textvariable=org_var_p, width=24)
            org_entry.grid(row=3, column=1, sticky="w")
            _ToolTip(org_entry, "Organization to apply.")
            ttk.Label(f, text="Project").grid(row=4, column=0, sticky="w")
            proj_entry = ttk.Entry(f, textvariable=proj_var, width=24)
            proj_entry.grid(row=4, column=1, sticky="w")
            _ToolTip(proj_entry, "Project to apply.")
            ttk.Label(f, text="Tags").grid(row=5, column=0, sticky="w")
            tags_entry = ttk.Entry(f, textvariable=tags_var_p, width=24)
            tags_entry.grid(row=5, column=1, sticky="w")
            _ToolTip(tags_entry, "Comma-separated tags.")

            def _save_profile_edit() -> None:
                name = name_var.get().strip()
                if not name:
                    return
                profile = {
                    "name": name,
                    "context_type": ctx_var.get().strip(),
                    "channel": chan_var.get().strip(),
                    "organization": org_var_p.get().strip() or None,
                    "project": proj_var.get().strip() or None,
                    "tags": [t.strip() for t in tags_var_p.get().split(",") if t.strip()],
                }
                presets["profiles"] = [p for p in presets["profiles"] if p.get("name") != name]
                presets["profiles"].append(profile)
                _refresh_profiles()
                win_p.destroy()

            save_btn = ttk.Button(f, text="Save", command=_save_profile_edit)
            save_btn.grid(
                row=6, column=0, sticky="w", pady=(6, 0)
            )
            cancel_btn = ttk.Button(f, text="Cancel", command=win_p.destroy)
            cancel_btn.grid(
                row=6, column=1, sticky="e", pady=(6, 0)
            )
            _ToolTip(save_btn, "Save profile changes.")
            _ToolTip(cancel_btn, "Close without saving.")

        def _add_profile():
            _profile_dialog()

        def _edit_profile():
            sel = profile_listbox.curselection()
            if not sel:
                return
            name = profile_listbox.get(sel[0])
            existing = next((p for p in presets["profiles"] if p.get("name") == name), None)
            if existing:
                _profile_dialog(existing)

        def _delete_profile():
            sel = profile_listbox.curselection()
            if not sel:
                return
            name = profile_listbox.get(sel[0])
            presets["profiles"] = [p for p in presets["profiles"] if p.get("name") != name]
            _refresh_profiles()

        add_btn = ttk.Button(profiles_tab, text="Add", command=_add_profile)
        add_btn.grid(
            row=1, column=1, sticky="w"
        )
        edit_btn = ttk.Button(profiles_tab, text="Edit", command=_edit_profile)
        edit_btn.grid(
            row=2, column=1, sticky="w"
        )
        del_btn = ttk.Button(profiles_tab, text="Delete", command=_delete_profile)
        del_btn.grid(
            row=3, column=1, sticky="w"
        )
        _ToolTip(add_btn, "Create a new profile.")
        _ToolTip(edit_btn, "Edit the selected profile.")
        _ToolTip(del_btn, "Delete the selected profile.")

        def _save_lists() -> None:
            config.context["context_types"] = presets["context_types"]
            config.context["channels"] = presets["channels"]
            config.context["projects"] = presets["projects"]
            config.context["organizations"] = presets["organizations"]
            config.context["tags"] = presets["tags"]
            config.context["profiles"] = presets["profiles"]
            save_config(config_path, config)
            org_combo["values"] = presets["organizations"]
            project_combo["values"] = presets["projects"]
            channel_combo["values"] = presets["channels"]
            context_combo["values"] = presets["context_types"]
            profile_combo["values"] = [p.get("name") for p in presets["profiles"]]
            _set_status("Lists saved")

        btn_row_lists = ttk.Frame(frame)
        btn_row_lists.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        save_btn = ttk.Button(btn_row_lists, text="Save", command=_save_lists)
        save_btn.grid(
            row=0, column=0, sticky="w"
        )
        close_btn = ttk.Button(btn_row_lists, text="Close", command=win.destroy)
        close_btn.grid(
            row=0, column=1, sticky="e", padx=(6, 0)
        )
        _ToolTip(save_btn, "Persist list changes to config.")
        _ToolTip(close_btn, "Close the list manager.")

    def _save_profile_dialog() -> None:
        logger.info("Open save profile dialog")
        win = tk.Toplevel(root)
        win.title("Save profile")
        win.resizable(False, False)
        frame = ttk.Frame(win, padding=8)
        frame.grid(row=0, column=0, sticky="nsew")
        profile_name_var.set(profile_var.get().strip())
        ttk.Label(frame, text="Profile name").grid(row=0, column=0, sticky="w")
        name_entry = ttk.Entry(frame, textvariable=profile_name_var, width=24)
        name_entry.grid(
            row=0, column=1, sticky="w"
        )
        _ToolTip(name_entry, "Name for saving the current metadata as a profile.")

        def _save_and_close() -> None:
            _save_profile()
            win.destroy()

        save_btn = ttk.Button(frame, text="Save", command=_save_and_close)
        save_btn.grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        cancel_btn = ttk.Button(frame, text="Cancel", command=win.destroy)
        cancel_btn.grid(
            row=1, column=1, sticky="e", pady=(6, 0)
        )
        _ToolTip(save_btn, "Save the profile and close.")
        _ToolTip(cancel_btn, "Close without saving.")

    settings_menu.add_command(label="Audio settings...", command=_open_audio_settings)
    settings_menu.add_command(label="Mic setup wizard...", command=_open_mic_setup_wizard)
    settings_menu.add_command(
        label="Transcription settings...", command=_open_transcription_settings
    )
    settings_menu.add_command(label="Output settings...", command=_open_output_settings)
    settings_menu.add_separator()
    settings_menu.add_command(label="Save defaults", command=_save_defaults)
    settings_menu.add_command(label="Save profile...", command=_save_profile_dialog)
    settings_menu.add_command(label="My profile...", command=_open_my_profile)
    settings_menu.add_command(label="Manage lists...", command=_open_manage_lists)
    settings_menu.add_command(label="Clear metadata", command=_clear_fields)


    main = ttk.Frame(root, padding=8)
    main.grid(row=0, column=0, sticky="nsew")

    ttk.Label(
        main,
        text="Step 1: setup -> Step 2: people/context -> Step 3: record.",
    ).grid(row=0, column=0, sticky="w", pady=(0, 2))
    ttk.Label(
        main,
        text="Audio device settings live in the Settings menu (mic/system/dual).",
        foreground="#6aa6ff",
    ).grid(row=1, column=0, sticky="w", pady=(0, 6))

    title_var = tk.StringVar(value=_last_used_value("title", ""))
    user_name_var = tk.StringVar(
        value=_last_used_value("user_name", config.context.get("user_name", ""))
    )
    attendees_var = tk.StringVar(value=_last_used_value("attendees", ""))
    contact_var = tk.StringVar(value=_last_used_value("contact", ""))
    contact_id_var = tk.StringVar(value=_last_used_value("contact_id", ""))
    org_var = tk.StringVar(value=_last_used_value("org", ""))
    project_var = tk.StringVar(value=_last_used_value("project", ""))
    location_var = tk.StringVar(value=_last_used_value("location", ""))
    channel_var = tk.StringVar(
        value=_last_used_value(
            "channel", config.context.get("default_channel", presets["channels"][0])
        )
    )
    tags_var = tk.StringVar(value=_last_used_value("tags", ""))
    auto_tags_var = tk.BooleanVar(value=last_used.get("auto_tags", True))
    context_type_var = tk.StringVar(
        value=_last_used_value(
            "context_type",
            config.context.get("default_context_type", presets["context_types"][0]),
        )
    )
    profile_var = tk.StringVar(value=_last_used_value("profile", ""))
    profile_name_var = tk.StringVar()
    notes_box = None
    notes_list = None
    notes_entry = None
    add_note_btn = None

    capture_mode_var = tk.StringVar(
        value=_last_used_value("capture_mode", "mic")
    )
    if capture_mode_var.get() not in ("mic", "system", "dual"):
        capture_mode_var.set("mic")
    mic_device_var = tk.StringVar(
        value=_last_used_value("mic_device", config.device_name or "")
    )
    system_device_var = tk.StringVar(value=_last_used_value("system_device", ""))
    rate_var = tk.StringVar(
        value=_last_used_value("rate", str(config.audio.sample_rate_hz))
    )
    mic_channels_var = tk.StringVar(
        value=_last_used_value("mic_channels", str(config.audio.channels))
    )
    system_channels_var = tk.StringVar(
        value=_last_used_value("system_channels", "2")
    )

    model_var = tk.StringVar(value=_last_used_value("model", config.whisper_model))
    live_model_var = tk.StringVar(value=_last_used_value("live_model", "tiny"))
    language_var = tk.StringVar(value=_last_used_value("language", ""))
    device_pref_var = tk.StringVar(value=_last_used_value("device_pref", ""))
    compute_type_var = tk.StringVar(value=_last_used_value("compute_type", ""))
    diarize_var = tk.BooleanVar(value=True)
    hf_token_var = tk.StringVar(value=_last_used_value("hf_token", ""))
    speaker_map_var = tk.StringVar(value=_last_used_value("speaker_map", ""))
    use_type_folders_var = tk.BooleanVar(
        value=bool(last_used.get("use_type_folders", config.context.get("use_type_folders", False)))
    )
    live_transcribe_var = tk.BooleanVar(
        value=bool(last_used.get("live_transcribe", False))
    )

    def _bind_monitor_refresh(var: tk.Variable) -> None:
        var.trace_add("write", lambda *_: _schedule_monitor_refresh("config_change"))

    for _var in (
        capture_mode_var,
        mic_device_var,
        system_device_var,
        rate_var,
        mic_channels_var,
        system_channels_var,
    ):
        _bind_monitor_refresh(_var)

    def _auto_configure_system_device() -> None:
        if system_device_var.get().strip():
            return
        try:
            outputs = list_input_devices(loopback=True)
        except Exception as exc:
            logger.debug("Auto-detect system device failed: %s", exc)
            return
        if not outputs:
            return
        preferred = next(
            (
                d
                for d in outputs
                if "sound mapper" not in d.get("name", "").lower()
            ),
            outputs[0],
        )
        name = preferred.get("name")
        if name:
            system_device_var.set(name)
            logger.info("Auto-configured system device: %s", name)

    def _auto_configure_h2() -> None:
        try:
            devices = list_input_devices(loopback=False)
        except Exception as exc:
            logger.debug("Auto-detect H2 failed: %s", exc)
            return
        current_name = mic_device_var.get().strip()
        current_match = (
            next((d for d in devices if d.get("name") == current_name), None)
            if current_name
            else None
        )
        zoom_name = find_zoom_name_from_candidates(devices)
        if current_match is None and zoom_name:
            mic_device_var.set(zoom_name)
            capture_mode_var.set("mic")
            system_device_var.set("")
            match = next((d for d in devices if d.get("name") == zoom_name), None)
            max_in = match.get("max_input_channels", 0) if match else 0
            if max_in:
                mic_channels_var.set(str(min(4, max_in)))
                if max_in < 4:
                    logger.info("Zoom device supports %s channels", max_in)
            logger.info("Auto-configured H2 mic: %s", zoom_name)

    if capture_mode_var.get() in ("system", "dual"):
        _auto_configure_system_device()
    _auto_configure_h2()
    _apply_my_profile(my_profile)

    setup_frame = ttk.LabelFrame(main, text="Step 1: Session setup", style="Neo.TLabelframe")
    setup_frame.grid(row=2, column=0, sticky="ew", pady=(0, 6))
    setup_frame.columnconfigure(1, weight=1)
    setup_frame.columnconfigure(3, weight=1)

    ttk.Label(setup_frame, text="Title").grid(row=0, column=0, sticky="w")
    title_entry = ttk.Entry(setup_frame, textvariable=title_var, width=52)
    title_entry.grid(row=0, column=1, columnspan=3, sticky="ew")
    _ToolTip(title_entry, "Session title used for file names and notes.")

    ttk.Label(setup_frame, text="Type").grid(row=1, column=0, sticky="w")
    context_combo = ttk.Combobox(
        setup_frame,
        textvariable=context_type_var,
        values=presets["context_types"],
        width=22,
    )
    context_combo.grid(row=1, column=1, sticky="ew")
    _ToolTip(context_combo, "Context type used in frontmatter.")

    ttk.Label(setup_frame, text="Profile").grid(row=1, column=2, sticky="w")
    profile_combo = ttk.Combobox(
        setup_frame,
        textvariable=profile_var,
        values=[p.get("name") for p in presets["profiles"]],
        width=22,
    )
    profile_combo.grid(row=1, column=3, sticky="ew")
    profile_combo.bind("<<ComboboxSelected>>", _apply_profile)
    _ToolTip(profile_combo, "Apply a saved profile to auto-fill fields.")

    ttk.Label(setup_frame, text="Tags").grid(row=2, column=0, sticky="w")
    tags_entry = ttk.Entry(setup_frame, textvariable=tags_var, width=24)
    tags_entry.grid(row=2, column=1, sticky="ew")
    _ToolTip(tags_entry, "Comma-separated tags for Obsidian.")
    auto_tags_cb = ttk.Checkbutton(
        setup_frame, text="Auto tags", variable=auto_tags_var
    )
    auto_tags_cb.grid(row=2, column=2, columnspan=2, sticky="w")
    _ToolTip(auto_tags_cb, "Auto-add context type and project to tags.")

    btn_row = ttk.Frame(setup_frame)
    btn_row.grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))
    for idx, label in enumerate(presets["context_types"]):
        btn = ttk.Button(
            btn_row, text=label, command=lambda l=label: _apply_context_type(l)
        )
        btn.grid(row=0, column=idx, padx=2)
        _ToolTip(btn, f"Apply {label} metadata without starting recording.")

    context_frame = ttk.LabelFrame(
        main, text="Step 2: People & context", style="Neo.TLabelframe"
    )
    context_frame.grid(row=3, column=0, sticky="ew", pady=(0, 6))
    context_frame.columnconfigure(1, weight=1)
    context_frame.columnconfigure(3, weight=1)

    ttk.Label(context_frame, text="Your name").grid(row=0, column=0, sticky="w")
    user_name_entry = ttk.Entry(context_frame, textvariable=user_name_var, width=24)
    user_name_entry.grid(row=0, column=1, sticky="ew")
    _ToolTip(user_name_entry, "Your name for participants metadata.")
    ttk.Label(context_frame, text="Attendees").grid(row=0, column=2, sticky="w")
    attendees_entry = ttk.Entry(context_frame, textvariable=attendees_var, width=24)
    attendees_entry.grid(row=0, column=3, sticky="ew")
    _ToolTip(attendees_entry, "Comma-separated list of attendees.")

    ttk.Label(context_frame, text="Contact").grid(row=1, column=0, sticky="w")
    contact_entry = ttk.Entry(context_frame, textvariable=contact_var, width=24)
    contact_entry.grid(row=1, column=1, sticky="ew")
    _ToolTip(contact_entry, "Primary contact for the session (notes require this).")
    contact_var.trace_add("write", lambda *_: _handle_contact_change())
    ttk.Label(context_frame, text="ID").grid(row=1, column=2, sticky="w")
    contact_id_entry = ttk.Entry(context_frame, textvariable=contact_id_var, width=24)
    contact_id_entry.grid(row=1, column=3, sticky="ew")
    _ToolTip(contact_id_entry, "Internal contact/client ID.")

    ttk.Label(context_frame, text="Org").grid(row=2, column=0, sticky="w")
    org_combo = ttk.Combobox(
        context_frame, textvariable=org_var, values=presets["organizations"], width=22
    )
    org_combo.grid(row=2, column=1, sticky="ew")
    _ToolTip(org_combo, "Organization or client company.")
    ttk.Label(context_frame, text="Project").grid(row=2, column=2, sticky="w")
    project_combo = ttk.Combobox(
        context_frame, textvariable=project_var, values=presets["projects"], width=22
    )
    project_combo.grid(row=2, column=3, sticky="ew")
    _ToolTip(project_combo, "Project or initiative label.")

    ttk.Label(context_frame, text="Location").grid(row=3, column=0, sticky="w")
    location_entry = ttk.Entry(context_frame, textvariable=location_var, width=24)
    location_entry.grid(row=3, column=1, sticky="ew")
    _ToolTip(location_entry, "Physical location or meeting room.")
    ttk.Label(context_frame, text="Channel").grid(row=3, column=2, sticky="w")
    channel_combo = ttk.Combobox(
        context_frame, textvariable=channel_var, values=presets["channels"], width=22
    )
    channel_combo.grid(row=3, column=3, sticky="ew")
    _ToolTip(channel_combo, "Session channel (in_person/phone/webchat).")

    ttk.Label(context_frame, text="Notes").grid(row=4, column=0, sticky="nw")
    notes_box = tk.Text(
        context_frame,
        width=52,
        height=3,
        bg="#0b0f14",
        fg="#d8e1ff",
        insertbackground="#8bd3ff",
        highlightthickness=0,
        bd=0,
        relief="flat",
    )
    notes_box.grid(row=4, column=1, columnspan=3, sticky="ew")
    notes_box.insert("1.0", _last_used_value("notes", ""))
    _ToolTip(notes_box, "Freeform notes to capture context during recording.")

    notes_frame = ttk.LabelFrame(
        context_frame, text="Timestamped notes", style="Neo.TLabelframe"
    )
    notes_frame.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(6, 0))
    notes_frame.columnconfigure(0, weight=1)
    notes_entry_var = tk.StringVar()
    notes_entry = ttk.Entry(notes_frame, textvariable=notes_entry_var, width=52)
    notes_entry.grid(row=0, column=0, sticky="ew", padx=(6, 4), pady=6)
    add_note_btn = ttk.Button(notes_frame, text="Add note")
    add_note_btn.grid(row=0, column=1, sticky="w", padx=(0, 6), pady=6)
    notes_list = tk.Listbox(
        notes_frame, height=3, bg="#0b0f14", fg="#d8e1ff", highlightthickness=0, bd=0
    )
    notes_list.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))
    _ToolTip(
        notes_entry,
        "Add a timestamped note tied to the current recording time (requires Contact).",
    )
    _ToolTip(add_note_btn, "Capture a timestamped note.")
    _ToolTip(notes_list, "Notes captured during recording (stored in the note).")

    control_row = ttk.Frame(main)
    control_row.grid(row=4, column=0, sticky="w", pady=(6, 0))
    ttk.Button(control_row, text="Start", command=_start_custom).grid(
        row=0, column=0, padx=2
    )
    ttk.Button(control_row, text="Stop", command=_stop_recording).grid(
        row=0, column=1, padx=2
    )
    ttk.Button(control_row, text="Close Contact", command=_close_contact).grid(
        row=0, column=2, padx=2
    )
    ttk.Button(control_row, text="Clear", command=_clear_fields).grid(
        row=0, column=3, padx=2
    )
    buttons = control_row.winfo_children()
    _ToolTip(buttons[0], "Start recording with current metadata.")
    _ToolTip(buttons[1], "Stop recording and begin transcription.")
    _ToolTip(buttons[2], "Close the current contact and prepare for the next.")
    _ToolTip(buttons[3], "Clear metadata fields (keeps defaults).")

    def _add_timestamped_note(_event=None) -> None:
        if not contact_var.get().strip():
            _set_status("Contact required to add timestamped notes")
            return
        text = notes_entry_var.get().strip()
        if not text:
            return
        elapsed = 0
        if state["recording"] and state["start_time"]:
            elapsed = time.time() - state["start_time"]
        stamp = _format_timestamp(elapsed)
        state["timestamped_notes"].append(
            {
                "timestamp": stamp,
                "text": text,
                "contact": contact_var.get().strip(),
                "contact_id": contact_id_var.get().strip() or None,
            }
        )
        notes_entry_var.set("")
        _refresh_timestamped_notes()
        _set_status(f"Timestamped note added at {stamp}")

    add_note_btn.configure(command=_add_timestamped_note)
    notes_entry.bind("<Return>", _add_timestamped_note)

    meter_canvas = None

    waveform_frame = ttk.LabelFrame(main, text="Live waveform", style="Neo.TLabelframe")
    waveform_frame.grid(row=5, column=0, sticky="ew", pady=(6, 0))
    waveform_canvas = tk.Canvas(
        waveform_frame,
        width=520,
        height=120,
        bg="#0f1a2a",
        highlightthickness=0,
        bd=0,
    )
    waveform_canvas.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
    _ToolTip(waveform_canvas, "Live waveform with transcription progress overlay.")

    feed_frame = ttk.LabelFrame(main, text="System feed", style="Neo.TLabelframe")
    feed_frame.grid(row=6, column=0, sticky="ew", pady=(6, 0))
    feed_box = tk.Text(
        feed_frame,
        width=60,
        height=5,
        wrap="word",
        bg="#0b0f14",
        fg="#d8e1ff",
        insertbackground="#8bd3ff",
        highlightthickness=0,
        bd=0,
        relief="flat",
    )
    feed_box.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
    feed_box.configure(state="disabled")
    _ToolTip(feed_box, "Process updates, device changes, and recording status.")

    progress_frame = ttk.Frame(main)
    progress_frame.grid(row=7, column=0, sticky="ew", pady=(6, 0))
    progress_label_var = tk.StringVar(value="Final transcription idle")
    ttk.Label(progress_frame, textvariable=progress_label_var).grid(
        row=0, column=0, sticky="w"
    )
    progress_var = tk.IntVar(value=0)
    ttk.Progressbar(
        progress_frame,
        maximum=100,
        variable=progress_var,
        length=220,
        style="Neo.Horizontal.TProgressbar",
    ).grid(
        row=0, column=1, sticky="w", padx=(8, 0)
    )
    _ToolTip(progress_frame, "Progress for final transcription and diarization.")

    status_row = ttk.Frame(main)
    status_row.grid(row=8, column=0, sticky="ew", pady=(6, 0))
    timer_var = tk.StringVar(value="00:00")
    ttk.Label(status_row, textvariable=timer_var).grid(row=0, column=0, sticky="w")
    status_var = tk.StringVar(value="Idle")
    ttk.Label(status_row, textvariable=status_var).grid(row=0, column=1, sticky="w", padx=(12, 0))

    debug_enabled_var = tk.BooleanVar(value=debug_enabled)
    debug_badge = ttk.Label(status_row, text="DEBUG", foreground="red")
    if debug_enabled_var.get():
        debug_badge.grid(row=0, column=2, sticky="e", padx=(12, 0))

    def _update_debug_badge() -> None:
        if debug_enabled_var.get():
            debug_badge.grid(row=0, column=2, sticky="e", padx=(12, 0))
        else:
            debug_badge.grid_forget()

    def _bind_preset_updates() -> None:
        bindings = [
            (title_entry, "title"),
            (user_name_entry, "user_name"),
            (attendees_entry, "attendees"),
            (contact_entry, "contact"),
            (contact_id_entry, "contact_id"),
            (org_combo, "org"),
            (project_combo, "project"),
            (location_entry, "location"),
            (channel_combo, "channel"),
            (tags_entry, "tags"),
            (context_combo, "context_type"),
            (profile_combo, "profile"),
            (notes_box, "notes"),
        ]
        for widget, field_name in bindings:
            widget.bind("<FocusOut>", lambda _e, n=field_name: _log_field_change(n))
        org_combo.bind(
            "<FocusOut>",
            lambda _e: _remember_preset("organizations", org_var.get()),
        )
        project_combo.bind(
            "<FocusOut>",
            lambda _e: _remember_preset("projects", project_var.get()),
        )
        channel_combo.bind(
            "<FocusOut>",
            lambda _e: _remember_preset("channels", channel_var.get()),
        )
        context_combo.bind(
            "<FocusOut>",
            lambda _e: _remember_preset("context_types", context_type_var.get()),
        )
        tags_entry.bind(
            "<FocusOut>",
            lambda _e: [
                _remember_preset("tags", t) for t in tags_var.get().split(",")
            ],
        )

    def _on_close() -> None:
        logger.info("GUI closing")
        _stop_live_transcriber()
        _stop_monitoring()
        _save_last_used()
        root.destroy()

    _bind_preset_updates()
    _update_timer()
    _update_waveform()
    _poll_feed()
    _poll_transcribe_progress()
    root.after(250, lambda: _ensure_monitoring("launch"))
    _update_note_controls()
    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()
