---
title: EchoFrame
type: overview
status: draft
created: 2026-01-13
updated: 2026-01-13
owner: Matt Schafer VE7LTX
purpose: Project intent, scope, architecture, dependencies, and roadmap.
scope: Repository-wide
audience: Maintainers, contributors, and users
related:
  - AGENTS.md
  - CONTRIBUTING.md
  - SECURITY.md
  - docs/frontmatter-schema.md
  - docs/implementation-plan.md
  - LICENSE
schema: 1
---
# EchoFrame

EchoFrame is a local personal research assistant for capturing audio, transcribing it offline, and emitting structured Markdown notes for Obsidian. It is optimized for research work: interviews, client calls, internal meetings, and fieldwork. Personal.ai integration is optional and text-only.

Primary goal: live local transcription and speaker diarization, fully offline by default. On Windows, EchoFrame can capture system audio via WASAPI loopback, including dual-track mic + system capture.

## Status
Prototype working: GUI bar, local recording, Faster-Whisper transcription, optional diarization, and Obsidian-ready notes.

## Key features
- Local capture from Zoom H2/H4, headset/webcam mics, or Windows system audio (loopback)
- Dual-track mode: mic + system in one multichannel WAV
- Faster-Whisper transcription with timestamps
- Optional speaker diarization with pyannote
- Obsidian YAML frontmatter + Markdown transcript
- Context metadata (participants, project, channel, notes)
- Compact Tkinter GUI with presets, profiles, and audio HUD

## Quickstart (Windows)
Install Python dependencies:
```powershell
pip install sounddevice numpy faster-whisper pyannote.audio
```

Run the GUI:
```powershell
$env:PYTHONPATH='C:\echoframe\src'
python -m echoframe.cli gui
```

## Capture modes
- mic: record from Zoom H2/H4 or other mic devices.
- system: capture app audio via WASAPI loopback.
- dual: record mic + system audio together (separate tracks).

System audio isolation (no virtual cable):
1) Windows Settings → System → Sound → App volume and device preferences.
2) Route Zoom/Teams/Meet to the output device you enter in EchoFrame.
3) Use Capture: system or dual.

## Output structure
```
<base_dir>\EchoFrame\
  Recordings\
  Notes\
  Segments\
  Sessions\
  Logs\
```

Optional category subfolders:
```
Recordings\Interview\
Notes\Interview\
```

## Docs
- [Implementation plan](docs/implementation-plan.md)
- [Frontmatter schema](docs/frontmatter-schema.md)
- [TODO](TODO.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [License](LICENSE)

## Obsidian links
- [[docs/frontmatter-schema]]
- [[docs/implementation-plan]]
- [[TODO]]
- [[CONTRIBUTING]]
- [[SECURITY]]
