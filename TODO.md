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

## Core pipeline
- [x] Project scaffold and module stubs
- [x] Device detection (Zoom H2/H4 preference)
- [x] CLI device listing
- [x] Fixed-duration recording to WAV
- [x] Streaming recording with manual stop
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

## Packaging and validation
- [x] pyproject.toml scaffolding
- [ ] Dependency pins and extras
- [ ] Basic tests for config, naming, rendering
- [ ] Windows build check (PyInstaller)
