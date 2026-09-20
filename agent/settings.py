"""Private server configuration. Provider selection never comes from untrusted web input."""
from __future__ import annotations
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_env():
    p = HERE / '.env'
    if p.exists():
        for raw in p.read_text().splitlines():
            s = raw.strip()
            if s and not s.startswith('#') and '=' in s:
                k, v = s.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('\"').strip("'"))


def settings():
    load_env()
    provider = os.getenv('SPEECH_PROVIDER', 'gradium').lower()
    if provider not in {'gradium', 'openai', 'hybrid'}:
        raise ValueError('SPEECH_PROVIDER must be gradium, openai, or hybrid.')
    return {
        'speech_provider': provider,
        'general_key': os.getenv('GENERAL_COMPUTE_API_KEY', ''),
        'general_url': os.getenv('GENERAL_COMPUTE_BASE_URL', 'https://api.generalcompute.com/v1').rstrip('/'),
        'general_model': os.getenv('GENERAL_COMPUTE_MODEL', 'gemma-4-31B-it'),
        'gradium_key': os.getenv('GRADIUM_API_KEY', ''),
        'gradium_voice': os.getenv('GRADIUM_VOICE_ID', '_6Aslh2DxfmnRLmP'),
        'openai_key': os.getenv('OPENAI_API_KEY', ''),
        'openai_stt': os.getenv('OPENAI_STT_MODEL', 'gpt-realtime-whisper'),
        'openai_tts': os.getenv('OPENAI_TTS_MODEL', 'gpt-4o-mini-tts'),
        'openai_voice': os.getenv('OPENAI_TTS_VOICE', 'marin'),
        'access_token': os.getenv('SPARE_ACCESS_TOKEN', ''),
        'origins': [x.strip() for x in os.getenv('ALLOWED_ORIGINS', 'http://localhost:7860,http://127.0.0.1:7860').split(',') if x.strip()],
        'max_minutes': min(75, max(5, int(os.getenv('MAX_CONNECTION_MINUTES', '70')))),
        'max_designs': min(15, max(1, int(os.getenv('MAX_DESIGNS_PER_CALL', '8')))),
        'ice_servers': json.loads(os.getenv('ICE_SERVERS_JSON', '[]')),
    }


def missing_keys(cfg):
    required = [('GENERAL_COMPUTE_API_KEY', cfg['general_key'])]
    if cfg['speech_provider'] in {'gradium', 'hybrid'}:
        required.append(('GRADIUM_API_KEY', cfg['gradium_key']))
    if cfg['speech_provider'] in {'openai', 'hybrid'}:
        required.append(('OPENAI_API_KEY', cfg['openai_key']))
    return [name for name, key in required if not key or key.startswith(('replace', 'your_'))]


def public_config():
    c = settings()
    return {'speech_provider': c['speech_provider'], 'model': c['general_model'],
            'missing': missing_keys(c), 'access_required': bool(c['access_token']),
            'ice_servers': c['ice_servers'], 'version': '2.0.0',
            'notice': 'Configuration only. A key being present does not mean it has been verified.'}
