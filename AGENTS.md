---
title: AGENTS
type: guide
status: draft
created: 2026-01-13
updated: 2026-01-13
owner: Matt Schafer VE7LTX
purpose: Guidance for automated agents working in the repository.
scope: Automation and tooling behavior in this repo.
audience: Automation agents and maintainers
related:
  - README.md
  - CONTRIBUTING.md
  - SECURITY.md
  - docs/implementation-plan.md
schema: 1
---
# AGENTS.md

EchoFrame is currently a documentation-only repository. There is no code or tests yet.

## File intent
- Document how automated agents should behave in this repository.
- Keep automation aligned with the project intent in [[README]].
- Reduce accidental changes to non-goal areas.

## Relationships
- [[README]]
- [[CONTRIBUTING]]
- [[SECURITY]]
- [[docs/implementation-plan]]

## Guidance
- Keep documentation concise and ASCII-only.
- When adding code, update README.md with setup and usage details.
- Prefer small, modular components with clear CLI entry points.
- Avoid committing large binary assets or model files.
- If adding new docs, place them at the repo root or under a docs/ folder.
- Transcription and diarization must remain local; Personal.ai is text-only.
