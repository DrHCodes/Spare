# Architecture and operational boundaries

Browser microphone + speaker ↔ native WebRTC ↔ Pipecat SmallWebRTCTransport

Pipecat: speech recognition → user turn aggregation (Silero + Smart Turn) → General Compute LLM → streaming TTS → output.

Speech is configurable as Gradium, OpenAI, or mixed. There are no prerecorded workout audio files and no Web Speech API synthesis/recognition fallback. Initial and safety prompts are fixed text synthesized at runtime. The sponsor model generates each main workout sequence and its setup/start wording within a bounded, no-jump catalog; generic rest and warmup text is application-authored.

Tools are bound to one Controller per peer. The controller owns initial conversational state (time → effort → confirmed preference → design → readiness → workout). Stop/pause have a narrow direct-transcript fast path. A detected speech turn pauses running movement before an LLM response. This conservative policy can cause unnecessary pauses from noise and must be tuned on-device, especially during heavy breathing.

The workout engine tracks a wall-clock finish budget separately from movement interval time. It does not credit a paused, skipped, or not-yet-announced work interval. Queued work introductions require an audio-completion signal before their movement timers run. The scheduler defers routine cues while the user or bot is speaking; explicit interruption cancels queued speech. Provider failures and timing gaps pause movement. No background/locked-screen reliability guarantee.

Audio completion is integrated with Pipecat BotStoppedSpeakingFrame. Streaming chunk boundaries and interruption event ordering require end-to-end device testing; unit tests cannot validate audible behavior.

Generated drafts have basic validation: supported IDs, no jump/equipment tags, explicit floor consent, positive durations and exact initial budget, recovery floors, balanced split-squat sides, alternating muscle groups, and bounded wording. This is not a clinically validated exercise prescription system. It cannot guarantee a particular physiological effort.

Mid-generation changes invalidate the pending generation; stale results are discarded. Easier substitutions pause and re-explain as necessary. Revision uses the sponsor model for the remaining time and preserves movement-timer history. No automatic resume after a break: the person must say ready.

A protected read-only status route updates the small optional screen. HTTP pause/stop/disconnect are backup controls. End immediately stops client audio and microphone before attempting server cleanup.

Security: no keys in frontend, local-only default, allowed-origin checks, remote access code, random session IDs, one concurrent session, bounded design requests, and no local transcript/audio files. Loguru logs are restricted to WARNING; external provider retention still applies. This is a single-user prototype, not production authentication, tenant isolation, or a formal security review.

The frontend can deploy on Vercel; the continuously running Python process cannot deploy as this static site. WebRTC media routing for remote users is a separate deployment concern (ICE/STUN/TURN).
