"""Swappable real speech providers. No speechSynthesis, recordings, or fake voice fallback."""
VOICE_DIRECTION = '''Speak as a clear, conversational adult fitness coach. Firm but kind.
Use natural inflection and brief sentence pauses. No whispering, breathy meditation delivery,
announcer voice, cutesy wording, or overexcited emphasis. Give one instruction at a time.'''


def make_speech(cfg):
    p=cfg['speech_provider']
    if p in {'gradium','hybrid'}:
        from pipecat.services.gradium.stt import GradiumSTTService
        stt=GradiumSTTService(api_key=cfg['gradium_key'])
    else:
        from pipecat.services.openai.stt import OpenAIRealtimeSTTService
        stt=OpenAIRealtimeSTTService(api_key=cfg['openai_key'],turn_detection=False,
            settings=OpenAIRealtimeSTTService.Settings(model=cfg['openai_stt'],noise_reduction='near_field'))
    if p=='gradium':
        from pipecat.services.gradium.tts import GradiumTTSService
        tts=GradiumTTSService(api_key=cfg['gradium_key'],
            settings=GradiumTTSService.Settings(voice=cfg['gradium_voice']))
        rate=48000
    else:
        from pipecat.services.openai.tts import OpenAITTSService
        tts=OpenAITTSService(api_key=cfg['openai_key'],settings=OpenAITTSService.Settings(
            model=cfg['openai_tts'],voice=cfg['openai_voice'],instructions=VOICE_DIRECTION,speed=1.0))
        rate=24000
    return stt,tts,rate
