---
title: EchoFrame TODO
type: checklist
status: active
created: 2026-01-13
updated: 2026-01-13
owner: Matt Schafer VE7LTX
purpose: Track implementation progress for EchoFrame.
scope: Repository tasks and milestones.
audience: Maintainers and contributors
related:
  - README.md
  - docs/implementation-plan.md
schema: 1
---
# EchoFrame TODO

## MVP priorities
- [x] Use `base_dir` for output paths in GUI and CLI (Recordings/Notes)
- [x] Emit capture metadata in notes (capture_mode, mic/system devices, channel_map)
- [x] Ensure transcription/diarization use mic-only channels in dual-track mode
- [ ] Session metadata persistence (session.json, segments.json)
- [x] Implement folder structure creation (Recordings/Notes/Segments/Sessions/Logs)
- [x] Optional category subfolders (by context_type)

## Core pipeline
- [x] Project scaffold and module stubs
- [x] Device detection (Zoom H2/H4 preference)
- [x] CLI device listing
- [x] Fixed-duration recording to WAV
- [x] Streaming recording with manual stop
- [x] System audio capture (WASAPI loopback)
- [x] Dual-track mic + system capture
- [x] Faster-Whisper transcription with timestamps
- [x] Speaker diarization with pyannote
- [x] Alignment of diarization to transcript segments
- [x] Markdown note rendering with full frontmatter
- [x] Context metadata capture (contact, project, channel, notes)

## Config and storage
- [x] Config loader
- [ ] Config-driven CLI defaults
- [ ] Session metadata persistence (session.json, segments.json)

## Personal.ai (text-only)
- [ ] Upload transcript
- [ ] Summary prompt
- [ ] Sentiment prompt
- [ ] Optional action items prompt

## GUI (Tkinter)
- [x] Basic window and device selector
- [x] Record toggle and timer
- [x] Transcription progress indicator
- [x] Note creation status and output path
- [x] Context input fields (type, contact, project, channel, notes)
- [x] Local transcription and diarization trigger
- [x] Audio monitor and HUD meter

## Packaging and validation
- [x] pyproject.toml scaffolding
- [ ] Dependency pins and extras
- [x] Basic tests for config, naming, rendering
- [ ] Windows build check (PyInstaller)
