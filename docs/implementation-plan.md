---
title: Implementation Plan
type: plan
status: draft
created: 2026-01-13
updated: 2026-01-13
owner: Matt Schafer VE7LTX
purpose: Full implementation plan for EchoFrame, including requirements, workflows, and design.
scope: System design and implementation details.
audience: Maintainers, contributors, and users
related:
  - README.md
  - docs/frontmatter-schema.md
  - AGENTS.md
schema: 1
---
# EchoFrame Implementation Plan

This document mirrors the full implementation plan from [[README]] and preserves the end-to-end design details in a dedicated reference location.

Primary goal: live local transcription and speaker diarization, fully offline by default. Personal.ai is text-only and never used for transcription or diarization. Windows loopback capture enables system audio and dual-track capture without virtual cables.

## System overview
EchoFrame is a local personal research assistant designed to record and transcribe audio interactions, then integrate the results into a personal knowledge base. The system leverages a Zoom H2 or H4 Handy Recorder (used as a USB microphone) for high-quality audio capture, processes the audio entirely offline using state-of-the-art speech recognition (OpenAI Whisper or Faster-Whisper) and optional speaker diarization (pyannote), and outputs structured Markdown notes (with YAML metadata) suitable for an Obsidian vault. It also integrates with the Personal.ai API for advanced post-processing such as generating summaries, tagging sentiment, or enabling question-answering on the transcripts using the user's personal AI model. The focus is on developer clarity, modular design, and extensibility, ensuring each component (recording, transcription, diarization, AI integration) can be maintained or upgraded independently.

## Current implementation status
- Tkinter GUI bar with context fields, presets, and profiles
- Mic/system/dual capture modes with Windows WASAPI loopback
- Local recording to WAV with timestamped filenames
- Faster-Whisper transcription with timestamps
- Optional pyannote diarization with speaker mapping
- Obsidian-ready Markdown notes with YAML frontmatter

## User requirements
EchoFrame must meet these requirements:

- Audio input via Zoom H2: recognize the H2 as a USB input device and capture audio in real time.
- Local audio recording with timestamps: record high-quality WAV and timestamp sessions via filenames or metadata.
- Accurate transcription (ASR): run Whisper or Faster-Whisper locally with timestamps.
- Speaker diarization (optional): use pyannote to label speakers and align segments.
- Structured output for Obsidian: Markdown with YAML frontmatter, timestamps, and speaker labeling.
- Personal.ai integration: upload transcripts, generate summaries and sentiment, enable Q&A.
- Knowledge system organization: support discovery research workflows with tags or folder structure.
- Local installation and reusability: CLI or desktop app, offline-first, optional AI calls online.

## File and folder structure
A clear layout keeps recordings and notes aligned and easy to query.

Base directory (configurable):
```
ObsidianVault/Research Audio/EchoFrame/
```

Audio recordings:
- Subfolder: `Recordings/`
- Filename format: `YYYY-MM-DD--Short-Title.wav`

Transcripts/notes:
- Subfolder: `Notes/`
- Filename mirrors audio: `YYYY-MM-DD--Short-Title.md`

Segments and session metadata:
- `Segments/` for ASR outputs
- `Sessions/` for session metadata

Logs:
- `Logs/` for runtime logs

Optional category structure:
```
EchoFrame/Interviews/2026-01-12--Interview-with-ClientA.md
EchoFrame/Fieldwork/2026-02-01--SiteObservation.md
EchoFrame/InternalSync/2026-02-05--TeamMeeting.md
```

Config and logs:
- `echoframe_config.yml` (base directory or user home)
- `Logs/` for runtime logs

Linking audio to notes:
- Obsidian supports audio embeds, e.g. `![[2026-01-12--Interview-with-ClientA.wav]]`

## Config specification
Configuration lives in `echoframe_config.yml` and can be overridden by CLI flags.

Example:
```
base_dir: "D:/Obsidian/Research Audio/EchoFrame"
device_name: "Zoom H2"
whisper_model: "small"
language: "en"
diarization: false
save_audio: true
audio:
  sample_rate_hz: 44100
  bit_depth: 16
  channels: 4
notes:
  add_summary_section: true
  add_action_items_section: false
  embed_audio: true
context:
  user_name: "Matt Schafer"
  default_context_type: "Interview"
  default_channel: "in_person"
  context_types: ["Interview", "Client Call", "Internal", "Fieldwork", "Webchat"]
  channels: ["in_person", "phone", "webchat", "other"]
  projects: ["Project X", "Project Y"]
  organizations: ["ClientA", "ClientB"]
  tags: ["research", "client"]
  profiles:
    - name: "Interview"
      context_type: "Interview"
      channel: "in_person"
      tags: ["interview"]
  use_type_folders: true
personal_ai:
  enabled: false
  api_key: "..."
  domain_name: "..."
  summary_prompt: "Summarize the key points in 3-5 bullets."
  sentiment_prompt: "Describe the overall sentiment in one sentence."
  context_check_prompt: "Check the context fields against the transcript and flag discrepancies."
```

Rules:
- CLI flags override config values.
- Per-run overrides are not persisted unless a `--save-config` flag is added later.
- Audio standards should follow `docs/frontmatter-schema.md` for consistency.

## Audio handling and capture
Zoom H2 or H4 devices act as USB audio inputs. EchoFrame should:

- Enumerate input devices and default to H2/H4 if detected.
- Record at 44.1 kHz or 48 kHz, 16-bit WAV.
- Use mono for transcription by default; allow stereo as an option.
- Provide simple start/stop control (CLI or GUI).
- Report status (recording indicator, duration, basic levels if possible).

Device considerations:
- Windows may default H2/H4 to 48 kHz. Ensure matching sample rate to avoid distortion.
- Stereo can help with later analysis but is not required for transcription.
- Zoom H2 supports 4-channel dual-stereo capture (front L/R + rear L/R).
- Other mic sources (headset, webcam, USB mics) are supported as input devices.

Implementation options:
- `sounddevice` for high-level capture with NumPy arrays
- `pyaudio` (PortAudio wrapper) for low-level streaming
- Use Python `wave` to write incrementally to WAV

System audio capture (Windows):
- Use WASAPI loopback via `sounddevice.WasapiSettings(loopback=True)`.
- This allows capturing webcall/video chat audio from output devices.
- Expose a loopback toggle and output-device selection in the GUI/CLI.
- Support dual-track capture (mic + system) in a single multichannel WAV.
- Dual-track layout: mic channels first, then system channels.
- System capture targets speakers/output devices without virtual cables.

Processing logic (recording):
```
1. Resolve device by name or default.
2. Open input stream at configured sample rate/channels/bit depth.
3. Stream frames and write to WAV incrementally.
4. On stop, finalize WAV header and return file path + metadata.
```

## Transcription pipeline
EchoFrame uses Whisper or Faster-Whisper for offline ASR.

Steps:
- Load chosen model (tiny/base/small/medium/large).
- Downsample to 16 kHz mono as needed.
- Run transcription with timestamps (segment or word-level when available).
- Preserve segments for alignment and note formatting.

Performance:
- Faster-Whisper offers strong CPU performance with quantization.
- GPU acceleration is optional but improves speed.
- Provide progress feedback for long sessions.

Processing logic (transcription):
```
1. Load audio and resample to 16 kHz mono for ASR.
2. Run ASR with timestamps to produce segments.
3. Persist segments to JSON for downstream steps.
4. Return segments + basic stats (duration, word count).
```

## Diarization strategy (optional)
Use `pyannote.audio` to separate speakers:

- Run diarization on the WAV file.
- Align transcript segments to speaker segments by time overlap.
- Merge consecutive segments from the same speaker for readability.
- Default speaker labels to `Speaker_0`, `Speaker_1`, etc.
- Optionally map speaker labels to names from YAML `participants`.

Alternative:
- WhisperX can perform ASR + diarization in one pipeline, at the cost of heavier dependencies.

## Personal.ai integration
If configured, EchoFrame can enrich notes with Personal.ai. This is text-only post-processing and is never used for transcription or diarization:

- Upload transcript to memory (`/upload-text`).
- Query for summary and sentiment (`/message`).
- Optionally request action items or key insights.
- Embed outputs in YAML and/or visible sections.

Fail-safe behavior:
- If API calls fail, continue note creation without AI content.
- Allow later re-run of summary or sentiment via CLI.

Processing logic (Personal.ai):
```
1. Upload transcript text with metadata (title, tags, timestamps).
2. Request summary and sentiment using configured prompts.
3. Optionally run a context check prompt against typed context notes.
4. Store AI outputs in the Session model and note frontmatter/body.
```

Prompt guidance:
- Summary should be concise and actionable (3-5 bullets).
- Sentiment should be a single sentence or a small tag set.
- Optional follow-on prompts: action items, risks, and decisions.
- Optional context check prompt can flag mismatches between typed context and transcript.

## Obsidian output formatting
Each session produces a Markdown note:

YAML frontmatter example:
```
---
schema: 1
title: Interview with ClientA
date: 2026-01-12
time: "20:15"
duration_seconds: 2700
participants:
  - Alice (Researcher)
  - Bob (ClientA)
type: Interview
project: Project X
tags: [DiscoveryResearch, ClientA, Interview]
audio: 2026-01-12--Interview-with-ClientA.wav
device: "Zoom H2"
sample_rate_hz: 44100
bit_depth: 16
channels: 1
summary: >
  ClientA was enthusiastic about the design and raised a budget concern.
sentiment: Positive
---
```

Recommended sections:
- Summary
- Transcript
- Action Items (optional)

Transcript format:
```
[00:00:03] Alice: Thank you for meeting with me today.
[00:00:12] Bob: My pleasure. I am excited about the project.
```

Note schema and audio standards:
- See [[docs/frontmatter-schema]] for required fields and bitrate reference.

## CLI and automation workflow
Example CLI flow:

1) Start recording (mic):
```
echoframe record --title "ClientA Interview" --mode mic --mic-device "Zoom H2"
```

2) Stop recording:
- Ctrl+C or GUI stop button

3) Transcribe:
- Whisper or Faster-Whisper runs locally

4) Diarize (optional):
- Align speaker segments

5) Enrich with AI (optional):
- Upload transcript, get summary/sentiment

6) Assemble note:
- Write Markdown with YAML and transcript

Additional commands:
```
echoframe transcribe path/to/audio.wav --model small
echoframe devices
echoframe devices --loopback
echoframe record --mode system --system-device "Speakers"
echoframe record --mode dual --mic-device "Zoom H2" --system-device "Speakers"
echoframe show path/to/session.session.json
```

## GUI approach (current)
The Tkinter bar wraps the capture pipeline with a compact layout:
- Context fields: title, participants, contact, org/project, channel, notes
- Presets and profiles for quick context reuse
- My Profile defaults and list management for metadata dropdowns
- Capture mode: mic / system / dual
- Mic/system device selection and channel counts
- Live timer, status text, and audio level monitor
- Live transcript preview (fast model) and final transcript progress bar
- Optional HUD meter with colored bars and peak hold
- Transcription and diarization run after stop (final model + optional diarization)

App audio isolation (Windows, no virtual cable):
- Route Zoom/Teams/Meet output to a dedicated output device.
- Select that device in "System device" and use Capture: system or dual.

## Architecture (planned)
Core modules:
- recorder: device discovery, stream capture, WAV writing
- transcriber: audio normalization and ASR segments with timestamps
- diarizer: optional speaker labeling aligned to transcript segments
- renderer: Markdown note assembly with YAML frontmatter
- storage: naming rules, folder layout, and file I/O
- config: load/merge config and CLI overrides
- ai_client: optional Personal.ai enrichment

Core data contract:
- Session: id, title, started_at, duration, audio_path, segments, speakers, note_path, ai_summary, ai_sentiment
- Segment: start, end, text, speaker (optional)
- Frontmatter schema version (e.g. schema: 1) to keep notes upgradeable

Persistence format (suggested):
- `segments.json` for raw ASR output
- `session.json` for assembled metadata and AI outputs
- Markdown note is the canonical human-readable output

Error handling:
- Recording errors should fail fast with device guidance.
- ASR/diarization errors should produce a note with a warning block.
- AI failures should be non-fatal and logged.

## Open source dependencies (planned)
Core runtime:
- Python 3.10+
- FFmpeg (audio decoding and resampling)
- sounddevice (PortAudio) or PyAudio for recording
- Faster-Whisper (or openai-whisper) for ASR
- PyTorch + torchaudio (backend for ASR/diarization)
- pyannote.audio for speaker diarization (optional)
- PyYAML for frontmatter
- rich or textual for CLI output (optional)
- typer or click for CLI parsing
- requests or httpx for Personal.ai API calls

Packaging and install:
- pyproject.toml with console_scripts entry point
- pip installation for dev use
- PyInstaller for a standalone desktop executable (Windows/Mac/Linux)

## Local installation and packaging considerations
- Cross-platform audio capture is the most error-prone area.
- Prefer `sounddevice` for easier installation over `pyaudio`.
- Whisper models download on first use; document cache location.
- GPU acceleration requires user-installed PyTorch CUDA build.
- FFmpeg may be required for resampling and decoding.
- Standalone builds (PyInstaller) will be large due to ML dependencies.

Testing and validation:
- Unit tests for config parsing, filename generation, and note rendering.
- Integration tests for segment alignment and diarization mapping.
- Manual tests for device discovery and recording start/stop.
- Golden-file tests for Markdown output formatting.

## Future features and stretch goals
- Real-time transcription (streaming)
- Obsidian plugin integration
- Speaker profile calibration
- NLP annotations (topics, action items, entities, emotion)
- Multi-modal inputs (video, images)
- Alternate ASR backends (Vosk, Kaldi, cloud services)
- Rich GUI with waveform editor
- Mobile capture workflow
- Continuous discovery insights tagging
- Model fine-tuning for user-specific vocabulary

## Sources
- Real Python: Playing and Recording Sound in Python
- Modal Blog: Choosing between Whisper variants
- Scalastic: Whisper and Pyannote for transcription and diarization
- Personal.ai Documentation: Upload Document API
- The Sweet Setup: Obsidian YAML and Dataview
