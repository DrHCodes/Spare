# Spare — voice first, version 2

Live workout generation and an interruptible voice coach. No fixed workout selector, prerecorded narration, or browser text-to-speech. One button opens a conversation: **“How much time do you have?”** followed by **“And how intense would you like the workout to be?”**

## Status — read this first

This package contains implementation code, not a connected hosted service. Core and HTTP logic are tested with explicitly mocked model responses. The live Pipecat/Gradium/OpenAI integration has **not been run with real credentials**, and this environment could not install Pipecat. Voice quality, audible interruptions, event-model tool calling, and end-to-end WebRTC must be tested on your device. Nothing has been deployed or charged.

The previous nine-workout demo is not bundled: this is a separate replacement project. Keep your earlier ZIP as a backup.

## What's different

- One voice-led entry point; no duration or difficulty selection cards.
- A language model interprets time and intensity; the app confirms a subjective 1–8/10 target.
- New workout sequence and spoken setup/start cues are generated through **General Compute**, within a bounded exercise catalog. Warm-up, recovery, and cooldown remain application-managed.
- Supports 2–60 minutes, not just the old 3/10/30 presets.
- Code-enforced no jumping and no purchased equipment. Standing by default; some movements use a wall. Floor variations require explicit permission.
- Microphone stays connected while the bot speaks. Pipecat handles speech interruption; movement pauses on a detected user turn and waits for readiness before resuming.
- Easier alternatives and newly generated remaining workouts preserve the completed movement-timer total.
- The original finish deadline keeps running during breaks. No racing to “catch up.”
- Backup pause/end controls remain visible. End disconnects local audio and microphone immediately rather than waiting for an API response.

## Start locally on your Mac

1. Unzip this project. Install `uv` if needed: https://docs.astral.sh/uv/getting-started/installation/ . Python 3.11–3.13 is supported; 3.12 is a good choice.
2. Open **START-SPARE.command**. It may need right-click → Open; if executable permissions were removed by your unzip tool, use the equivalent commands below.
3. On first launch, the script prompts locally for provider choice and **hidden** API keys and creates `agent/.env`. It does not redeem coupons or make provider calls during setup.
4. It installs the declared dependencies, opens http://localhost:7860, and starts the Python server. Initial speech model dependencies may take time to download.
5. Click **Start talking**, grant microphone access, and keep the browser visible and your computer awake.

Equivalent commands for a coding assistant or terminal:

```sh
cd agent
uv run configure.py
uv sync --extra voice
uv run --extra voice server.py
```

The voice API is not active until a client connects. **Keys being present is not the same as keys/model access being verified.** Failure is shown, not replaced with browser narration.

## Choose speech services privately

Edit `agent/.env` and restart the server. This is a developer setting, not another choice screen for the person exercising.

| Setting | Listening | Speaking | Required accounts |
|---|---|---|---|
| `SPEECH_PROVIDER=gradium` | Gradium streaming STT | Gradium streaming TTS | General Compute + Gradium |
| `SPEECH_PROVIDER=openai` | OpenAI realtime STT | OpenAI `gpt-4o-mini-tts` | General Compute + OpenAI |
| `SPEECH_PROVIDER=hybrid` | Gradium streaming STT | OpenAI `gpt-4o-mini-tts` | All three |

General Compute remains the reasoning and workout-generation provider in every mode. No silent model or speech-provider fallback.

OpenAI defaults: `OPENAI_STT_MODEL=gpt-realtime-whisper`, `OPENAI_TTS_MODEL=gpt-4o-mini-tts`, `OPENAI_TTS_VOICE=marin`. Try `cedar` to compare. This is a **chained streaming speech pipeline**, not GPT-Live/native speech-to-speech and not the ChatGPT read-aloud product.

Gradium defaults to its documented voice ID. Select another voice in your dashboard and change `GRADIUM_VOICE_ID`. No promise that a provider default fits your preferred voice; audition it with real coaching language.

## Upload to your GitHub repository

Upload the contents of this folder, preserving directories:

```text
web/             Voice-first static frontend
agent/           Python server, voice pipeline, generation and state
scripts/         Static frontend build and preview
 tests/          Logic, server, frontend tests
 docs/           Setup, architecture, test status, source references
START-SPARE.command
package.json
vercel.json
```

Do not upload `.env`, `.venv`, caches, or API keys. `.env.example` is safe because it has blank key values. Secret values are never read by frontend build scripts.

## Vercel is optional, and only hosts the interface

- Root directory: repository root.
- Framework: Other.
- Build: `npm run build`.
- Output: `dist`.
- Frontend API-key variables: **none**.

This uploads only four static web files. **A Vercel page alone cannot run this live voice agent.** Keep the Python server running locally for a local demo, or deploy it to an appropriate long-running service for remote users.

For a public frontend, use Connection settings to specify your HTTPS backend. On the backend, add that exact frontend origin to `ALLOWED_ORIGINS` and set a random `SPARE_ACCESS_TOKEN`. The frontend holds the access code only in memory. Do not use a provider key as this access code.

Local WebRTC uses host candidates. Public internet audio may require STUN and TURN servers; set authorized `ICE_SERVERS_JSON` entries. An HTTPS tunnel for signaling alone does not guarantee that media traverses a restrictive network. No remote-media deployment is verified in this package.

## Effort: what the numbers mean

These are **product starting targets**, not measured exertion or scientifically calibrated exercise equivalences:

- Easy: 3/10.
- Medium: 6/10; “Lagree-like” is the user's personal reference for controlled challenge.
- Hard: 8/10, with recovery and alternating movements.

Lagree is not a universal intensity standard or an equipment-free exercise modality. The app does not claim to duplicate a Lagree class. “Fast push-ups the whole time” is interpreted as a desire for high effort, never literally prescribed.

The model proposes scores for less familiar descriptions. Known anchors and numerical self-ratings are normalized in `agent/effort.py`. Ambiguous comparisons require clarification; every initial target is confirmed out loud. Unsupported maximal targets are capped and should be explained to the user. No jumping is ever added to increase intensity.

There is no camera, verified rep count, or measured intensity. Ask for easier or harder based on how the movement feels. The library/validation layer is a prototype, not an individualized medical or exercise-professional assessment.

## Run tests

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
npm test
```

The Python HTTP tests require `fastapi` and `httpx`; `uv sync --extra test` installs them in the agent environment. With that environment: `cd agent && uv run --extra test python -m unittest discover -s ../tests -p 'test_*.py' -v`.

See `docs/TEST-REPORT.md` for exactly what was and was not verified.
