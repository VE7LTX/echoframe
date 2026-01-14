---
title: Getting Started
type: guide
status: draft
created: 2026-01-13
updated: 2026-01-13
owner: Matt Schafer VE7LTX
purpose: Step-by-step setup for EchoFrame on Windows.
scope: Installation and first run.
audience: Users
related:
  - README.md
  - docs/frontmatter-schema.md
  - docs/implementation-plan.md
schema: 1
---
# Getting Started

## Requirements
- Windows 10/11
- Python 3.10+
- Zoom H2/H4 or another mic (headset/webcam supported)
- Optional: HuggingFace token for pyannote diarization

## Install dependencies
```powershell
pip install sounddevice numpy faster-whisper pyannote.audio
```

## Create a basic config
Create `echoframe_config.yml` in the repo root:
```
base_dir: "D:/Obsidian/Research Audio/EchoFrame"
device_name: "Zoom H2"
whisper_model: "small"
audio:
  sample_rate_hz: 44100
  channels: 2
context:
  user_name: "Matt Schafer"
  default_context_type: "Interview"
  default_channel: "in_person"
```
Note: some Zoom H2/H4 modes expose only 2 channels to Windows. EchoFrame clamps
to the max channels reported by the device.

## Run the GUI
```powershell
$env:PYTHONPATH='C:\echoframe\src'
python -m echoframe.cli gui
```

## First-run setup
1) Settings > My profile: set your defaults (name, org, tags, language).
2) Settings > Manage lists: add orgs, projects, channels, tags, and profiles.
3) Settings > Audio settings: pick the mic device (Zoom H2/H4).
4) Settings > Transcription settings: set final and live models.

## Capture modes
- mic: Zoom H2/H4 or any mic
- system: Windows app audio via WASAPI loopback
- dual: mic + system in one multichannel WAV

## Isolate app audio (no virtual cable)
1) Windows Settings > System > Sound > App volume and device preferences.
2) Route Zoom/Teams/Meet output to the device you enter in the GUI under System device.
3) Use Capture: system or dual.

## Notes output
Notes and media are written under `base_dir`:
```
Recordings/
Notes/
Segments/
Sessions/
Logs/
```

## Troubleshooting
- If devices are not listed, verify Windows sound settings and permissions.
- If diarization fails, confirm your HuggingFace token.
- If system audio is silent, ensure the app output device matches the GUI System device.
