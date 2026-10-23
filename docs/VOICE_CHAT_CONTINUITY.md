# Voice chat — Lúmen continuity

## Original product intent

Lúmen should be able to build and use a continuous voice conversation from inside its own UI, not merely accept a one-shot transcription. The original requested experience includes a young-sounding feminine voice (perceived age no older than 25), while maintaining clear, natural Portuguese conversation.

## Target end-to-end flow

UI voice control → microphone capture → speech-to-text (STT) → normal Lúmen Agent/runtime → text response → text-to-speech (TTS) → audio playback → next turn, with interruption/cancel, microphone permission state, device errors, and clear listening/thinking/speaking indicators.

## Integration requirements

- Reuse the existing configured Lúmen AI provider and memory; do not create a parallel chatbot brain.
- Keep STT/TTS behind provider interfaces so local/offline engines can be substituted and tested.
- Prefer local processing where practical; never upload microphone audio without an explicit provider configuration and user consent.
- Do not persist raw microphone audio by default. Audit sanitized metadata only.
- Provide push-to-talk first; continuous listening should be an explicit user-controlled mode with a visible indicator and a reliable stop control.
- Audio playback must be cancellable; a new user utterance should be able to interrupt TTS cleanly.
- Test STT and TTS independently, then the integrated loop through the real UI and physical microphone/speakers.

## Evidence status

A prior mission prompt recorded the target flow and voice preference. This document preserves the requirement; it does not claim the full voice loop is implemented or physically tested. Inspect the current UI and voice-related code before adding duplicate modules. Any release claim must link to a test run and evidence from the actual Windows UI.
