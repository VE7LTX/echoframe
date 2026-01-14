"""Tkinter GUI for a compact recording bar."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime

from .config import Config, load_config, save_config
from .diarizer import diarize_segments
from .recorder import record_audio_stream
from .renderer import render_note
from .storage import build_session_basename, ensure_dir
from .transcriber import transcribe_audio


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
    }

    def _set_status(text: str) -> None:
        status_var.set(text)

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
        meter_var.set(min(100, int(level * 100)))
        level_var.set(f"{level:.2f}")
        peak_var.set(f"{peak:.2f}")
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
            _set_status(f"Monitor failed: {exc}")
            return

        def _cb(indata, _frames, _time, status):
            if status:
                return
            rms = float(np.sqrt(np.mean(indata.astype("float32") ** 2)))
            with monitor["lock"]:
                monitor["level"] = rms
                monitor["peak"] = max(monitor["peak"], rms)

        try:
            extra_settings = None
            if loopback_var.get() and hasattr(sd, "WasapiSettings"):
                extra_settings = sd.WasapiSettings(loopback=True)
            stream = sd.InputStream(
                samplerate=int(rate_var.get()),
                channels=int(channels_var.get()),
                dtype="int16",
                device=device_var.get().strip() or None,
                callback=_cb,
                extra_settings=extra_settings,
            )
            stream.start()
            monitor["stream"] = stream
            _set_status("Monitoring levels...")
        except Exception as exc:
            _set_status(f"Monitor failed: {exc}")

    def _start_recording(context_type: str) -> None:
        if state["recording"]:
            return
        state["recording"] = True
        state["start_time"] = time.time()
        state["stop_event"].clear()
        timer_var.set("00:00")
        _set_status(f"Recording ({context_type})...")

        title = title_var.get().strip() or context_type
        out_dir = "Recordings"
        ensure_dir(out_dir)
        basename = build_session_basename(title, datetime.now())
        output_path = os.path.join(out_dir, f"{basename}.wav")

        def _worker() -> None:
            record_result = record_audio_stream(
                output_path=output_path,
                sample_rate_hz=int(rate_var.get()),
                channels=int(channels_var.get()),
                device_name=device_var.get().strip() or None,
                stop_event=state["stop_event"],
                loopback=loopback_var.get(),
            )
            state["recording"] = False
            state["start_time"] = None
            _set_status("Transcribing...")

            segments = transcribe_audio(
                output_path,
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
                        output_path,
                        segments,
                        speaker_map=speaker_map or None,
                        hf_token=hf_token_var.get().strip() or None,
                    )
                except Exception as exc:
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
                device=device_var.get().strip() or None,
                sample_rate_hz=int(rate_var.get()),
                bit_depth=16,
                channels=int(channels_var.get()),
                context_type=context_type,
                contact_name=contact_var.get().strip() or None,
                contact_id=contact_id_var.get().strip() or None,
                organization=org_var.get().strip() or None,
                project=project_var.get().strip() or None,
                location=location_var.get().strip() or None,
                channel=channel_var.get().strip() or None,
                context_notes=notes_box.get("1.0", "end").strip() or None,
            )

            notes_dir = "Notes"
            ensure_dir(notes_dir)
            note_path = os.path.join(notes_dir, f"{basename}.md")
            with open(note_path, "w", encoding="utf-8") as handle:
                handle.write(note_text)

            _set_status(f"Saved: {note_path}")

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

    main = ttk.Frame(root, padding=8)
    main.grid(row=0, column=0, sticky="nsew")

    ttk.Label(main, text="Title").grid(row=0, column=0, sticky="w")
    title_var = tk.StringVar()
    ttk.Entry(main, textvariable=title_var, width=36).grid(
        row=0, column=1, columnspan=3, sticky="w"
    )

    ttk.Label(main, text="Your name").grid(row=1, column=0, sticky="w")
    user_name_var = tk.StringVar(value=config.context.get("user_name", ""))
    ttk.Entry(main, textvariable=user_name_var, width=20).grid(
        row=1, column=1, sticky="w"
    )
    ttk.Label(main, text="Attendees").grid(row=1, column=2, sticky="w")
    attendees_var = tk.StringVar()
    ttk.Entry(main, textvariable=attendees_var, width=12).grid(
        row=1, column=3, sticky="w"
    )

    ttk.Label(main, text="Contact").grid(row=2, column=0, sticky="w")
    contact_var = tk.StringVar()
    ttk.Entry(main, textvariable=contact_var, width=20).grid(
        row=2, column=1, sticky="w"
    )
    ttk.Label(main, text="ID").grid(row=2, column=2, sticky="w")
    contact_id_var = tk.StringVar()
    ttk.Entry(main, textvariable=contact_id_var, width=12).grid(
        row=2, column=3, sticky="w"
    )

    ttk.Label(main, text="Org").grid(row=3, column=0, sticky="w")
    org_var = tk.StringVar()
    org_combo = ttk.Combobox(
        main, textvariable=org_var, values=presets["organizations"], width=18
    )
    org_combo.grid(row=3, column=1, sticky="w")
    ttk.Label(main, text="Project").grid(row=3, column=2, sticky="w")
    project_var = tk.StringVar()
    project_combo = ttk.Combobox(
        main, textvariable=project_var, values=presets["projects"], width=10
    )
    project_combo.grid(row=3, column=3, sticky="w")

    ttk.Label(main, text="Location").grid(row=4, column=0, sticky="w")
    location_var = tk.StringVar()
    ttk.Entry(main, textvariable=location_var, width=20).grid(
        row=4, column=1, sticky="w"
    )
    ttk.Label(main, text="Channel").grid(row=4, column=2, sticky="w")
    channel_var = tk.StringVar(
        value=config.context.get("default_channel", presets["channels"][0])
    )
    channel_combo = ttk.Combobox(
        main, textvariable=channel_var, values=presets["channels"], width=18
    )
    channel_combo.grid(row=4, column=3, sticky="w")

    ttk.Label(main, text="Notes").grid(row=5, column=0, sticky="nw")
    notes_box = tk.Text(main, width=36, height=3)
    notes_box.grid(row=5, column=1, columnspan=3, sticky="w")

    ttk.Label(main, text="Tags").grid(row=6, column=0, sticky="w")
    tags_var = tk.StringVar()
    tags_entry = ttk.Entry(main, textvariable=tags_var, width=20)
    tags_entry.grid(row=6, column=1, sticky="w")

    auto_tags_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(main, text="Auto tags", variable=auto_tags_var).grid(
        row=6, column=2, sticky="w"
    )

    ttk.Label(main, text="Type").grid(row=6, column=3, sticky="w")
    context_type_var = tk.StringVar(
        value=config.context.get("default_context_type", presets["context_types"][0])
    )
    context_combo = ttk.Combobox(
        main,
        textvariable=context_type_var,
        values=presets["context_types"],
        width=18,
    )
    context_combo.grid(row=7, column=3, sticky="w")

    ttk.Label(main, text="Profile").grid(row=7, column=0, sticky="w")
    profile_var = tk.StringVar()
    profile_combo = ttk.Combobox(
        main,
        textvariable=profile_var,
        values=[p.get("name") for p in presets["profiles"]],
        width=18,
    )
    profile_combo.grid(row=7, column=1, sticky="w")
    profile_combo.bind("<<ComboboxSelected>>", _apply_profile)
    profile_name_var = tk.StringVar()
    ttk.Entry(main, textvariable=profile_name_var, width=18).grid(
        row=7, column=2, sticky="w"
    )

    ttk.Label(main, text="Device").grid(row=8, column=0, sticky="w")
    device_var = tk.StringVar(value=config.device_name or "")
    ttk.Entry(main, textvariable=device_var, width=20).grid(
        row=8, column=1, sticky="w"
    )
    loopback_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(main, text="System audio", variable=loopback_var).grid(
        row=8, column=2, sticky="w"
    )
    ttk.Label(main, text="Rate").grid(row=8, column=3, sticky="w")
    rate_var = tk.StringVar(value=str(config.audio.sample_rate_hz))
    ttk.Entry(main, textvariable=rate_var, width=8).grid(
        row=8, column=4, sticky="w"
    )

    ttk.Label(main, text="Channels").grid(row=9, column=0, sticky="w")
    channels_var = tk.StringVar(value=str(config.audio.channels))
    ttk.Combobox(
        main,
        textvariable=channels_var,
        values=["1", "2", "4"],
        width=6,
    ).grid(row=9, column=1, sticky="w")

    ttk.Label(main, text="Model").grid(row=9, column=2, sticky="w")
    model_var = tk.StringVar(value=config.whisper_model)
    ttk.Entry(main, textvariable=model_var, width=8).grid(
        row=9, column=3, sticky="w"
    )

    ttk.Label(main, text="Language").grid(row=10, column=0, sticky="w")
    language_var = tk.StringVar()
    ttk.Entry(main, textvariable=language_var, width=8).grid(
        row=10, column=1, sticky="w"
    )
    ttk.Label(main, text="Device pref").grid(row=10, column=2, sticky="w")
    device_pref_var = tk.StringVar()
    ttk.Entry(main, textvariable=device_pref_var, width=8).grid(
        row=10, column=3, sticky="w"
    )

    ttk.Label(main, text="Compute").grid(row=11, column=0, sticky="w")
    compute_type_var = tk.StringVar()
    ttk.Entry(main, textvariable=compute_type_var, width=8).grid(
        row=11, column=1, sticky="w"
    )
    diarize_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(main, text="Diarize", variable=diarize_var).grid(
        row=11, column=2, sticky="w"
    )

    ttk.Label(main, text="HF token").grid(row=12, column=0, sticky="w")
    hf_token_var = tk.StringVar()
    ttk.Entry(main, textvariable=hf_token_var, width=20).grid(
        row=12, column=1, sticky="w"
    )
    ttk.Label(main, text="Speaker map").grid(row=12, column=2, sticky="w")
    speaker_map_var = tk.StringVar()
    ttk.Entry(main, textvariable=speaker_map_var, width=12).grid(
        row=12, column=3, sticky="w"
    )

    btn_row = ttk.Frame(main)
    btn_row.grid(row=13, column=0, columnspan=5, sticky="w", pady=(6, 0))
    for idx, label in enumerate(presets["context_types"]):
        ttk.Button(
            btn_row, text=label, command=lambda l=label: _start_recording(l)
        ).grid(row=0, column=idx, padx=2)

    ttk.Button(main, text="Start", command=_start_custom).grid(
        row=14, column=0, sticky="w", pady=(6, 0)
    )
    ttk.Button(main, text="Save Defaults", command=_save_defaults).grid(
        row=14, column=1, sticky="w", pady=(6, 0)
    )
    ttk.Button(main, text="Save Profile", command=_save_profile).grid(
        row=14, column=2, sticky="w", pady=(6, 0)
    )
    ttk.Button(main, text="Stop", command=_stop_recording).grid(
        row=14, column=3, sticky="w", pady=(6, 0)
    )

    timer_var = tk.StringVar(value="00:00")
    ttk.Label(main, textvariable=timer_var).grid(
        row=15, column=0, sticky="w", pady=(6, 0)
    )

    ttk.Button(main, text="Clear", command=_clear_fields).grid(
        row=15, column=1, sticky="w", pady=(6, 0)
    )

    ttk.Button(main, text="Monitor", command=_toggle_monitor).grid(
        row=15, column=2, sticky="w", pady=(6, 0)
    )

    meter_var = tk.IntVar(value=0)
    ttk.Progressbar(main, maximum=100, variable=meter_var, length=120).grid(
        row=15, column=3, sticky="w", pady=(6, 0)
    )

    level_var = tk.StringVar(value="0.00")
    peak_var = tk.StringVar(value="0.00")
    ttk.Label(main, text="Level").grid(row=16, column=0, sticky="w", pady=(6, 0))
    ttk.Label(main, textvariable=level_var).grid(
        row=16, column=1, sticky="w", pady=(6, 0)
    )
    ttk.Label(main, text="Peak").grid(row=16, column=2, sticky="w", pady=(6, 0))
    ttk.Label(main, textvariable=peak_var).grid(
        row=16, column=3, sticky="w", pady=(6, 0)
    )

    status_var = tk.StringVar(value="Idle")
    ttk.Label(main, textvariable=status_var).grid(
        row=17, column=0, columnspan=5, sticky="w", pady=(6, 0)
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
