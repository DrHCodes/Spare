# Private setup and partner credits

The event quickstart: https://gist.github.com/kwindla/63fa9139e3bcece8404692f26367f6a2

It supplies instructions, **not API keys**. It explicitly offers Gradium as an option when you do not already have preferred low-latency STT/TTS services.

## General Compute
Create/sign in at the account link in the gist; obtain event credits and create a key. Put it in `GENERAL_COMPUTE_API_KEY` in `agent/.env` only.
The event's model (`gemma-4-31B-it`) and endpoint (`https://api.generalcompute.com/v1`) are prefilled. Verify model access and tool calling with the event organizers if requests fail. Do not silently substitute another provider while claiming sponsor usage.

## Gradium
Create/sign in at https://gradium.ai/ and apply `HACKATHON-202609` in the provider's coupon flow. Confirm your credited balance. Put the resulting API key in `GRADIUM_API_KEY`; choose a voice ID in `GRADIUM_VOICE_ID`. Coupon redemption is not performed by this code, and no particular credit amount is assumed.

## OpenAI (optional)
Create an API key with access to the speech models and an API billing arrangement. Put it in `OPENAI_API_KEY`. ChatGPT subscription access is separate from API billing. The code does not charge the General Compute account for OpenAI or Gradium speech.

## Which mode to start with
For the hackathon, start with `SPEECH_PROVIDER=gradium` to use the supplied speech-credit route. Compare actual audio with `hybrid` (Gradium STT, OpenAI TTS) or `openai` after adding the additional key. Changing `.env` requires a server restart.

Never paste actual keys into this chat, a GitHub issue, the browser interface, or a public repository. You can report “General Compute ready; Gradium ready; OpenAI missing” without sharing secret values. Browser Connection settings take a private **Spare access code**, not any provider key.

## Spending controls
One concurrent call, a 70-minute default connection limit, and eight workout design attempts per connection are implemented. These are **not** an aggregate $30 billing cap; they reset on new connections/restarts, and conversational/speech calls also incur usage. Set provider-side controls where available, monitor balances, and shut down/revoke keys after the event. No paid requests were made during this build.
