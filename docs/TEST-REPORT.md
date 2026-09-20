# Test report — September 19, 2026

## Passed here

- **47 Python tests**: effort normalization, subjective-anchor handling, confirmation, asynchronous draft cancellation, all 10 durations × 3 target scores, no-jump/floor/sequence constraints, deadline timing, speech-cue gating, breaks, easier swaps, revisions, stale audio guards, API routes, access checks, missing-key failure, and secret-path exclusion.
- **7 Node tests**: one voice entry, no preset selection controls, no browser synthesis fallback, full-duplex/echo-cancellation request, microphone teardown, HTML/JS element consistency, and static-only packaging.
- Python syntax compilation and JavaScript syntax checks.
- FastAPI serves the actual frontend locally, and `/api/config` correctly reports missing keys and unavailable voice dependencies.
- Chromium rendered injected frontend HTML/CSS/JS at desktop (1440 × 980) and mobile (390 × 844). No page JavaScript errors; no mobile horizontal overflow. Connection dialog opens/closes; insecure preview fails closed. Screenshots inspected visually.

## Important limits

- Agent-browser was unavailable. A regular browser navigation to localhost was blocked by the container's browser policy. Layout checks used the actual files injected into a Chromium page, not a live voice connection.
- The container has no external package-network access; Pipecat/voice dependencies could not be installed. The Pipecat integration was checked against official current source and syntax-compiled, but its imports and runtime path were not exercised here.
- Provider calls in logic tests were explicitly mocked. No real General Compute, Gradium, or OpenAI request was sent. No credits spent.
- Actual voice quality, recognition while moving, live interruption latency, API model access/tool behavior, and browser WebRTC negotiation are not verified.
- No Vercel or voice backend deployment was performed.
- No exercise professional reviewed the generated content. No physical effectiveness or safety outcome was validated.

## Required live acceptance test

1. Configure keys locally, install dependencies, and start the Python server.
2. Click Start talking and hear the first question through the selected speech service.
3. Answer “seven minutes,” then “medium, like Lagree.” Confirm the proposed target.
4. Verify a real General Compute generation response and returned usage. Say “ready” after the plan is ready.
5. While a setup instruction is playing, say “I need a break.” Speech must stop and movement must pause. It must not resume without readiness.
6. Say “ready” and confirm that unfinished setup is re-explained, not skipped blindly.
7. Request easier, then a different remaining workout. Verify no jumping and unchanged completed-time history.
8. Simulate a connection failure and use the End session button. Verify microphone and audio stop immediately.
9. Compare the same session in Gradium and OpenAI/hybrid modes; approve the voice by listening, not by inspecting code.

Do not present these tests as completed until the actual device run has passed.
