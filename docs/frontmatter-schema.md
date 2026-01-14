---
title: Frontmatter Schema
type: spec
status: draft
created: 2026-01-13
updated: 2026-01-13
owner: Matt Schafer VE7LTX
purpose: Define the Obsidian frontmatter schema and audio standards.
scope: Note metadata and audio capture standards for EchoFrame.
audience: Developers and users
related:
  - README.md
  - docs/implementation-plan.md
schema: 1
---
# Frontmatter schema

This schema defines the Markdown note frontmatter and audio standards used by EchoFrame.

## File intent
- Provide a stable schema for note metadata.
- Document audio capture standards and device expectations.
- Keep future tooling compatible with existing notes.

## Relationships
- [[README]]
- [[docs/implementation-plan]]

## Processing policy
Transcription and diarization are always local. Personal.ai is text-only and never used for ASR or diarization.

## Schema version
- schema: 1

## Required fields
- title: string
- date: YYYY-MM-DD
- audio: file name of the recording (WAV preferred)

## Optional fields
- type: e.g. Interview, Fieldwork, InternalSync
- participants: list of strings
- tags: list of strings
- duration_seconds: integer
- device: e.g. "Zoom H2" or "Zoom H4n"
- sample_rate_hz: 44100 or 48000
- bit_depth: 16
- channels: 1, 2, or 4
- capture_mode: mic | system | dual
- mic_device: string
- system_device: string
- system_channels: 1, 2, or 4
- channel_map: list of channel labels (e.g., front_left, front_right, rear_left, rear_right)
- context_type: interview | client_call | internal_meeting | fieldwork | webchat
- contact_name: string
- contact_id: string
- organization: string
- project: string
- location: string
- channel: in_person | phone | webchat | other
- context_notes: string
- summary: string
- sentiment: string
- schema: integer

## Example
```
---
schema: 1
title: ClientA Interview
date: 2026-01-12
type: Interview
participants:
  - Alice
  - Bob
tags: [research, client]
audio: 2026-01-12--ClientA-Interview.wav
context_type: interview
contact_name: Bob ClientA
contact_id: CA-2047
organization: ClientA
project: Project X
location: Vancouver Office
channel: in_person
context_notes: "Initial discovery interview focused on onboarding."
device: "Zoom H2"
sample_rate_hz: 44100
bit_depth: 16
channels: 1
capture_mode: mic
mic_device: "Zoom H2"
system_device: "Speakers (Realtek)"
system_channels: 2
channel_map:
  - front_left
  - front_right
  - rear_left
  - rear_right
duration_seconds: 2730
summary: "..."
sentiment: "neutral"
---
```

## Audio standards
EchoFrame targets uncompressed WAV PCM for consistent offline processing.

Recommended capture formats:
- WAV PCM, 16-bit, 44.1 kHz or 48 kHz
- Mono for transcription; stereo optional if you want room ambience or later separation

PCM bitrate reference:
- 44.1 kHz, 16-bit, mono: 705.6 kbps
- 44.1 kHz, 16-bit, stereo: 1411.2 kbps
- 44.1 kHz, 16-bit, 4-channel: 2822.4 kbps
- 48 kHz, 16-bit, mono: 768 kbps
- 48 kHz, 16-bit, stereo: 1536 kbps
- 48 kHz, 16-bit, 4-channel: 3072 kbps

## Zoom H2 / H4 device notes
EchoFrame can record from either device as a USB audio input. Use one or both depending on availability.

Zoom H2:
- Typical USB mic mode: 44.1 kHz or 48 kHz, 16-bit, stereo
- Good for compact fieldwork; onboard mic array offers wide coverage
- 4-channel mode provides dual-stereo (front L/R and rear L/R) streams (use channel_map in notes)

Zoom H4n:
- Typical USB mic mode: 44.1 kHz or 48 kHz, 16-bit, stereo
- XLR inputs allow external mics for higher quality or targeted pickup

## Device selection guidance
- Prefer the device with the cleanest mic placement for the session.
- For multi-speaker rooms, stereo capture can help with later analysis, but mono is fine for transcription.
- Always record uncompressed WAV to avoid artifacts that reduce ASR accuracy.
- Mic inputs can include USB recorders (H2/H4), headset mics, or webcam mics.
