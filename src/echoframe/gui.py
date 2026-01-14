"""Tkinter GUI for a compact recording bar."""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime

from .config import Config, load_config, save_config
from .diarizer import diarize_segments
from .recorder import record_audio_stream, record_audio_stream_dual
from .renderer import render_note
from .storage import build_session_basename, ensure_dir, ensure_structure, get_output_dirs
from .transcriber import transcribe_audio
from .logging_utils import setup_logging
from .audio_utils import extract_channels


def launch_gui() -> None:
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("EchoFrame")
    root.resizable(False, False)

    config_path = "echoframe_config.yml"
    if os.path.exists(config_path):
        try:
            config = load_config(config_path)
        except Exception:
            config = Config(base_dir="")
    else:
        config = Config(base_dir="")

    base_paths = ensure_structure(config.base_dir)
    logger, log_path = setup_logging(log_dir=base_paths["logs"])

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

    state = {
        "recording": False,
        "start_time": None,
        "stop_event": threading.Event(),
        "thread": None,
    }
    monitor = {
        "stream": None,
        "level": 0.0,
        "peak": 0.0,
        "lock": threading.Lock(),
        "channels": [],
        "peaks": [],
        "hud": None,
        "hud_canvas": None,
    }

    class _ToolTip:
        def __init__(self, widget, text: str) -> None:
            self.widget = widget
            self.text = text
            self.tip = None
            widget.bind("<Enter>", self._show)
            widget.bind("<Leave>", self._hide)

        def _show(self, _event=None) -> None:
            if self.tip or not self.text:
                return
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + 20
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry(f"+{x}+{y}")
            label = tk.Label(
                self.tip,
                text=self.text,
                background="#ffffe0",
                relief="solid",
                borderwidth=1,
                font=("Segoe UI", 9),
                justify="left",
            )
            label.pack(ipadx=4, ipady=2)

        def _hide(self, _event=None) -> None:
            if self.tip:
                self.tip.destroy()
                self.tip = None

    def _set_status(text: str) -> None:
        status_var.set(text)
        logger.info(text)

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
        save_config(config_path, config)
        _set_status("Defaults saved")

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
        meter_var.set(min(100, int(level * 100)))
        level_var.set(f"{level:.2f}")
        peak_var.set(f"{peak:.2f}")
        if monitor["hud_canvas"] is not None:
            _update_hud(channels, peaks)
        root.after(200, _update_meter)

    def _toggle_monitor() -> None:
        if monitor["stream"] is not None:
            try:
                monitor["stream"].stop()
                monitor["stream"].close()
            except Exception:
                pass
            monitor["stream"] = None
            _set_status("Monitor stopped")
            return

        try:
            import sounddevice as sd
            import numpy as np
        except Exception as exc:
            logger.exception("Monitor failed")
            _set_status(f"Monitor failed: {exc}")
            return

        def _cb(indata, _frames, _time, status):
            if status:
                return
            data = indata.astype("float32")
            rms = float((data**2).mean() ** 0.5)
            channel_rms = (
                (data**2).mean(axis=0) ** 0.5 if data.ndim == 2 else [rms]
            )
            with monitor["lock"]:
                monitor["level"] = rms
                monitor["peak"] = max(monitor["peak"], rms)
                monitor["channels"] = list(channel_rms)
                if not monitor["peaks"] or len(monitor["peaks"]) != len(channel_rms):
                    monitor["peaks"] = [0.0] * len(channel_rms)
                monitor["peaks"] = [
                    max(p, c) for p, c in zip(monitor["peaks"], channel_rms)
                ]

        mode = capture_mode_var.get()
        monitor_device = (
            system_device_var.get().strip()
            if mode == "system"
            else mic_device_var.get().strip()
        )
        monitor_channels = (
            int(system_channels_var.get())
            if mode == "system"
            else int(mic_channels_var.get())
        )
        extra_settings = None
        try:
            if mode == "system" and hasattr(sd, "WasapiSettings"):
                extra_settings = sd.WasapiSettings(loopback=True)
            stream = sd.InputStream(
                samplerate=int(rate_var.get()),
                channels=monitor_channels,
                dtype="int16",
                device=monitor_device or None,
                callback=_cb,
                extra_settings=extra_settings,
            )
            stream.start()
            monitor["stream"] = stream
            _set_status("Monitoring levels...")
        except Exception as exc:
            logger.exception("Monitor failed")
            _set_status(f"Monitor failed: {exc}")

    def _open_hud() -> None:
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
        if monitor["hud"] is not None:
            monitor["hud"].destroy()
        monitor["hud"] = None
        monitor["hud_canvas"] = None

    def _reset_peaks() -> None:
        with monitor["lock"]:
            monitor["peak"] = 0.0
            monitor["peaks"] = [0.0 for _ in monitor["peaks"]]
        _set_status("Peaks reset")

    def _update_hud(levels: list[float], peaks: list[float]) -> None:
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
            canvas.create_text(
                x0 + bar_w / 2, 10 + max_h + 12, text=f"ch{idx+1}", fill="white"
            )

    def _build_channel_map(mode: str) -> list[str]:
        mic_count = int(mic_channels_var.get())
        sys_count = int(system_channels_var.get())
        mic_labels = ["front_left", "front_right", "rear_left", "rear_right"][:mic_count]
        sys_labels = ["system_left", "system_right", "system_rl", "system_rr"][
            :sys_count
        ]
        if mode == "dual":
            return mic_labels + sys_labels
        if mode == "system":
            return sys_labels
        return mic_labels

    def _start_recording(context_type: str) -> None:
        if state["recording"]:
            return
        state["recording"] = True
        state["start_time"] = time.time()
        state["stop_event"].clear()
        timer_var.set("00:00")
        _set_status(f"Recording ({context_type})...")

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

        def _worker() -> None:
            mode = capture_mode_var.get()
            if mode == "dual":
                record_result = record_audio_stream_dual(
                    output_path=output_path,
                    sample_rate_hz=int(rate_var.get()),
                    mic_channels=int(mic_channels_var.get()),
                    system_channels=int(system_channels_var.get()),
                    mic_device_name=mic_device_var.get().strip() or None,
                    system_device_name=system_device_var.get().strip() or None,
                    stop_event=state["stop_event"],
                )
            else:
                record_result = record_audio_stream(
                    output_path=output_path,
                    sample_rate_hz=int(rate_var.get()),
                    channels=int(
                        system_channels_var.get())
                        if mode == "system"
                        else int(mic_channels_var.get()),
                    device_name=system_device_var.get().strip() or None
                    if mode == "system"
                    else mic_device_var.get().strip() or None,
                    stop_event=state["stop_event"],
                    loopback=mode == "system",
                )

            state["recording"] = False
            state["start_time"] = None
            _set_status("Transcribing...")

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

            segments = transcribe_audio(
                transcribe_path,
                model_name=model_var.get().strip() or "small",
                language=language_var.get().strip() or None,
                device=device_pref_var.get().strip() or None,
                compute_type=compute_type_var.get().strip() or None,
            )

            if diarize_var.get():
                _set_status("Diarizing...")
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

            note_text = render_note(
                title=title,
                date=date_str,
                audio_filename=audio_filename,
                segments=segments,
                participants=participants or None,
                tags=tags or None,
                duration_seconds=record_result.duration_seconds,
                device=mic_device_var.get().strip() or None,
                sample_rate_hz=int(rate_var.get()),
                bit_depth=16,
                channels=int(
                    mic_channels_var.get()
                    if mode != "system"
                    else system_channels_var.get()
                ),
                capture_mode=mode,
                mic_device=mic_device_var.get().strip() or None,
                system_device=system_device_var.get().strip() or None,
                system_channels=int(system_channels_var.get()),
                channel_map=_build_channel_map(mode),
                context_type=context_type,
                contact_name=contact_var.get().strip() or None,
                contact_id=contact_id_var.get().strip() or None,
                organization=org_var.get().strip() or None,
                project=project_var.get().strip() or None,
                location=location_var.get().strip() or None,
                channel=channel_var.get().strip() or None,
                context_notes=notes_box.get("1.0", "end").strip() or None,
            )

            notes_dir = paths["notes"]
            note_path = os.path.join(notes_dir, f"{basename}.md")
            with open(note_path, "w", encoding="utf-8") as handle:
                handle.write(note_text)

            _set_status(f"Saved: {note_path}")
            logger.info("Note saved: %s", note_path)

        state["thread"] = threading.Thread(target=_worker, daemon=True)
        state["thread"].start()

    def _stop_recording() -> None:
        if not state["recording"]:
            return
        state["stop_event"].set()
        _set_status("Stopping...")

    def _start_custom() -> None:
        context_type = context_type_var.get().strip() or "Session"
        _start_recording(context_type)

    def _apply_profile(_event=None) -> None:
        name = profile_var.get().strip()
        if not name:
            return
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

    def _save_profile() -> None:
        name = profile_name_var.get().strip()
        if not name:
            _set_status("Profile name required")
            return
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
        _set_status("Profile saved")

    def _clear_fields() -> None:
        title_var.set("")
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
        channel_var.set(
            config.context.get("default_channel", presets["channels"][0])
        )
        profile_var.set("")
        profile_name_var.set("")
        _set_status("Cleared")

    menubar = tk.Menu(root)
    help_menu = tk.Menu(menubar, tearoff=0)
    dev_menu = tk.Menu(help_menu, tearoff=0)
    root.config(menu=menubar)
    menubar.add_cascade(label="Help", menu=help_menu)
    help_menu.add_cascade(label="Developer", menu=dev_menu)

    def _open_log_viewer() -> None:
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
        log_dir = os.path.dirname(log_path)
        try:
            os.startfile(log_dir)  # type: ignore[attr-defined]
        except Exception as exc:
            _set_status(f"Open log folder failed: {exc}")

    def _enable_debug() -> None:
        logger.setLevel(logging.DEBUG)
        _set_status("Debug logging enabled")

    dev_menu.add_command(label="View Log", command=_open_log_viewer)
    dev_menu.add_command(label="Open Log Folder", command=_open_log_folder)
    dev_menu.add_command(label="Enable Debug Logging", command=_enable_debug)

    main = ttk.Frame(root, padding=8)
    main.grid(row=0, column=0, sticky="nsew")

    ttk.Label(
        main,
        text="EchoFrame setup: fill context, pick capture mode, then Start.",
    ).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 6))

    ttk.Label(main, text="Title").grid(row=1, column=0, sticky="w")
    title_var = tk.StringVar()
    title_entry = ttk.Entry(main, textvariable=title_var, width=36)
    title_entry.grid(row=1, column=1, columnspan=4, sticky="w")
    _ToolTip(title_entry, "Session title used in filenames and notes.")

    ttk.Label(main, text="Your name").grid(row=2, column=0, sticky="w")
    user_name_var = tk.StringVar(value=config.context.get("user_name", ""))
    user_name_entry = ttk.Entry(main, textvariable=user_name_var, width=20)
    user_name_entry.grid(row=2, column=1, sticky="w")
    _ToolTip(user_name_entry, "Your name for participants metadata.")
    ttk.Label(main, text="Attendees").grid(row=2, column=2, sticky="w")
    attendees_var = tk.StringVar()
    attendees_entry = ttk.Entry(main, textvariable=attendees_var, width=18)
    attendees_entry.grid(row=2, column=3, sticky="w")
    _ToolTip(attendees_entry, "Comma-separated list of other attendees.")

    ttk.Label(main, text="Contact").grid(row=3, column=0, sticky="w")
    contact_var = tk.StringVar()
    contact_entry = ttk.Entry(main, textvariable=contact_var, width=20)
    contact_entry.grid(row=3, column=1, sticky="w")
    _ToolTip(contact_entry, "Primary contact name for the session.")
    ttk.Label(main, text="ID").grid(row=3, column=2, sticky="w")
    contact_id_var = tk.StringVar()
    contact_id_entry = ttk.Entry(main, textvariable=contact_id_var, width=18)
    contact_id_entry.grid(row=3, column=3, sticky="w")
    _ToolTip(contact_id_entry, "Internal contact ID or client ID.")

    ttk.Label(main, text="Org").grid(row=4, column=0, sticky="w")
    org_var = tk.StringVar()
    org_combo = ttk.Combobox(
        main, textvariable=org_var, values=presets["organizations"], width=18
    )
    org_combo.grid(row=4, column=1, sticky="w")
    _ToolTip(org_combo, "Organization or client company.")
    ttk.Label(main, text="Project").grid(row=4, column=2, sticky="w")
    project_var = tk.StringVar()
    project_combo = ttk.Combobox(
        main, textvariable=project_var, values=presets["projects"], width=18
    )
    project_combo.grid(row=4, column=3, sticky="w")
    _ToolTip(project_combo, "Project or research initiative.")

    ttk.Label(main, text="Location").grid(row=5, column=0, sticky="w")
    location_var = tk.StringVar()
    location_entry = ttk.Entry(main, textvariable=location_var, width=20)
    location_entry.grid(row=5, column=1, sticky="w")
    _ToolTip(location_entry, "Physical location or meeting room.")
    ttk.Label(main, text="Channel").grid(row=5, column=2, sticky="w")
    channel_var = tk.StringVar(
        value=config.context.get("default_channel", presets["channels"][0])
    )
    channel_combo = ttk.Combobox(
        main, textvariable=channel_var, values=presets["channels"], width=18
    )
    channel_combo.grid(row=5, column=3, sticky="w")
    _ToolTip(channel_combo, "How the session happened (in_person/phone/webchat).")

    ttk.Label(main, text="Notes").grid(row=6, column=0, sticky="nw")
    notes_box = tk.Text(main, width=36, height=3)
    notes_box.grid(row=6, column=1, columnspan=4, sticky="w")
    _ToolTip(notes_box, "Context notes to compare against the transcript.")

    ttk.Label(main, text="Tags").grid(row=7, column=0, sticky="w")
    tags_var = tk.StringVar()
    tags_entry = ttk.Entry(main, textvariable=tags_var, width=20)
    tags_entry.grid(row=7, column=1, sticky="w")
    _ToolTip(tags_entry, "Comma-separated tags for Obsidian.")
    auto_tags_var = tk.BooleanVar(value=True)
    auto_tags_cb = ttk.Checkbutton(main, text="Auto tags", variable=auto_tags_var)
    auto_tags_cb.grid(row=7, column=2, sticky="w")
    _ToolTip(auto_tags_cb, "Auto-add context type and project.")

    ttk.Label(main, text="Type").grid(row=7, column=3, sticky="w")
    context_type_var = tk.StringVar(
        value=config.context.get("default_context_type", presets["context_types"][0])
    )
    context_combo = ttk.Combobox(
        main,
        textvariable=context_type_var,
        values=presets["context_types"],
        width=18,
    )
    context_combo.grid(row=8, column=3, sticky="w")
    _ToolTip(context_combo, "Context type used in frontmatter.")

    use_type_folders_var = tk.BooleanVar(
        value=config.context.get("use_type_folders", False)
    )
    use_type_folders_cb = ttk.Checkbutton(
        main, text="Type folders", variable=use_type_folders_var
    )
    use_type_folders_cb.grid(row=8, column=4, sticky="w")
    _ToolTip(use_type_folders_cb, "Organize recordings/notes by context type.")

    ttk.Label(main, text="Profile").grid(row=8, column=0, sticky="w")
    profile_var = tk.StringVar()
    profile_combo = ttk.Combobox(
        main,
        textvariable=profile_var,
        values=[p.get("name") for p in presets["profiles"]],
        width=18,
    )
    profile_combo.grid(row=8, column=1, sticky="w")
    profile_combo.bind("<<ComboboxSelected>>", _apply_profile)
    profile_name_var = tk.StringVar()
    profile_name_entry = ttk.Entry(main, textvariable=profile_name_var, width=18)
    profile_name_entry.grid(row=8, column=2, sticky="w")
    _ToolTip(profile_combo, "Load a preset of multiple fields.")
    _ToolTip(profile_name_entry, "Name to save current fields as a profile.")

    ttk.Label(main, text="Capture").grid(row=9, column=0, sticky="w")
    capture_mode_var = tk.StringVar(value="mic")
    capture_combo = ttk.Combobox(
        main,
        textvariable=capture_mode_var,
        values=["mic", "system", "dual"],
        width=10,
        state="readonly",
    )
    capture_combo.grid(row=9, column=1, sticky="w")
    _ToolTip(capture_combo, "Mic/system/dual capture mode.")

    ttk.Label(main, text="Mic device").grid(row=9, column=2, sticky="w")
    mic_device_var = tk.StringVar(value=config.device_name or "")
    mic_device_entry = ttk.Entry(main, textvariable=mic_device_var, width=18)
    mic_device_entry.grid(row=9, column=3, sticky="w")
    _ToolTip(mic_device_entry, "Mic device name substring (Zoom H2).")

    ttk.Label(main, text="System device").grid(row=10, column=0, sticky="w")
    system_device_var = tk.StringVar()
    system_device_entry = ttk.Entry(main, textvariable=system_device_var, width=20)
    system_device_entry.grid(row=10, column=1, sticky="w")
    _ToolTip(system_device_entry, "Output device for app audio via loopback.")
    ttk.Label(main, text="Rate").grid(row=10, column=2, sticky="w")
    rate_var = tk.StringVar(value=str(config.audio.sample_rate_hz))
    rate_entry = ttk.Entry(main, textvariable=rate_var, width=8)
    rate_entry.grid(row=10, column=3, sticky="w")
    _ToolTip(rate_entry, "Sample rate (44100 or 48000).")

    ttk.Label(main, text="Mic channels").grid(row=11, column=0, sticky="w")
    mic_channels_var = tk.StringVar(value=str(config.audio.channels))
    mic_channels_combo = ttk.Combobox(
        main,
        textvariable=mic_channels_var,
        values=["1", "2", "4"],
        width=6,
    )
    mic_channels_combo.grid(row=11, column=1, sticky="w")
    _ToolTip(mic_channels_combo, "Mic input channels (H2 supports 4).")
    ttk.Label(main, text="System channels").grid(row=11, column=2, sticky="w")
    system_channels_var = tk.StringVar(value="2")
    system_channels_combo = ttk.Combobox(
        main,
        textvariable=system_channels_var,
        values=["1", "2", "4"],
        width=6,
    )
    system_channels_combo.grid(row=11, column=3, sticky="w")
    _ToolTip(system_channels_combo, "System output channels for loopback.")

    ttk.Label(main, text="Model").grid(row=12, column=0, sticky="w")
    model_var = tk.StringVar(value=config.whisper_model)
    model_entry = ttk.Entry(main, textvariable=model_var, width=8)
    model_entry.grid(row=12, column=1, sticky="w")
    _ToolTip(model_entry, "Whisper model size (tiny/base/small/medium/large).")
    ttk.Label(main, text="Language").grid(row=12, column=2, sticky="w")
    language_var = tk.StringVar()
    language_entry = ttk.Entry(main, textvariable=language_var, width=8)
    language_entry.grid(row=12, column=3, sticky="w")
    _ToolTip(language_entry, "Optional language code (e.g., en).")

    ttk.Label(main, text="Device pref").grid(row=13, column=0, sticky="w")
    device_pref_var = tk.StringVar()
    device_pref_entry = ttk.Entry(main, textvariable=device_pref_var, width=8)
    device_pref_entry.grid(row=13, column=1, sticky="w")
    _ToolTip(device_pref_entry, "Preferred compute device (cpu/cuda).")
    ttk.Label(main, text="Compute").grid(row=13, column=2, sticky="w")
    compute_type_var = tk.StringVar()
    compute_entry = ttk.Entry(main, textvariable=compute_type_var, width=8)
    compute_entry.grid(row=13, column=3, sticky="w")
    _ToolTip(compute_entry, "Compute type (e.g., int8, float16).")

    diarize_var = tk.BooleanVar(value=False)
    diarize_cb = ttk.Checkbutton(main, text="Diarize", variable=diarize_var)
    diarize_cb.grid(row=14, column=0, sticky="w")
    _ToolTip(diarize_cb, "Enable speaker diarization.")
    ttk.Label(main, text="HF token").grid(row=14, column=1, sticky="w")
    hf_token_var = tk.StringVar()
    hf_token_entry = ttk.Entry(main, textvariable=hf_token_var, width=20)
    hf_token_entry.grid(row=14, column=2, sticky="w")
    _ToolTip(hf_token_entry, "HuggingFace token for pyannote model.")

    ttk.Label(main, text="Speaker map").grid(row=15, column=0, sticky="w")
    speaker_map_var = tk.StringVar()
    speaker_map_entry = ttk.Entry(main, textvariable=speaker_map_var, width=12)
    speaker_map_entry.grid(row=15, column=1, sticky="w")
    _ToolTip(speaker_map_entry, "Map speakers (Speaker_0:Matt,...).")

    btn_row = ttk.Frame(main)
    btn_row.grid(row=16, column=0, columnspan=5, sticky="w", pady=(6, 0))
    for idx, label in enumerate(presets["context_types"]):
        ttk.Button(
            btn_row, text=label, command=lambda l=label: _start_recording(l)
        ).grid(row=0, column=idx, padx=2)

    ttk.Button(main, text="Start", command=_start_custom).grid(
        row=17, column=0, sticky="w", pady=(6, 0)
    )
    ttk.Button(main, text="Save Defaults", command=_save_defaults).grid(
        row=17, column=1, sticky="w", pady=(6, 0)
    )
    ttk.Button(main, text="Save Profile", command=_save_profile).grid(
        row=17, column=2, sticky="w", pady=(6, 0)
    )
    ttk.Button(main, text="Stop", command=_stop_recording).grid(
        row=17, column=3, sticky="w", pady=(6, 0)
    )

    timer_var = tk.StringVar(value="00:00")
    ttk.Label(main, textvariable=timer_var).grid(
        row=18, column=0, sticky="w", pady=(6, 0)
    )
    ttk.Button(main, text="Clear", command=_clear_fields).grid(
        row=18, column=1, sticky="w", pady=(6, 0)
    )
    ttk.Button(main, text="Monitor", command=_toggle_monitor).grid(
        row=18, column=2, sticky="w", pady=(6, 0)
    )
    ttk.Button(main, text="HUD", command=_open_hud).grid(
        row=18, column=3, sticky="w", pady=(6, 0)
    )
    ttk.Button(main, text="Reset Peaks", command=_reset_peaks).grid(
        row=18, column=4, sticky="w", pady=(6, 0)
    )

    meter_var = tk.IntVar(value=0)
    ttk.Progressbar(main, maximum=100, variable=meter_var, length=120).grid(
        row=19, column=0, sticky="w", pady=(6, 0)
    )

    level_var = tk.StringVar(value="0.00")
    peak_var = tk.StringVar(value="0.00")
    ttk.Label(main, text="Level").grid(row=19, column=1, sticky="w", pady=(6, 0))
    ttk.Label(main, textvariable=level_var).grid(
        row=19, column=2, sticky="w", pady=(6, 0)
    )
    ttk.Label(main, text="Peak").grid(row=19, column=3, sticky="w", pady=(6, 0))
    ttk.Label(main, textvariable=peak_var).grid(
        row=19, column=4, sticky="w", pady=(6, 0)
    )

    status_var = tk.StringVar(value="Idle")
    ttk.Label(main, textvariable=status_var).grid(
        row=20, column=0, columnspan=5, sticky="w", pady=(6, 0)
    )

    def _bind_preset_updates() -> None:
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
        profile_combo.bind("<<ComboboxSelected>>", _apply_profile)

    _bind_preset_updates()
    _update_timer()
    _update_meter()
    root.mainloop()
