#!/bin/bash
set -e
cd "$(dirname "$0")/agent"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo 'uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/'
  echo 'Then open this launcher again. Nothing was installed by this script.'
  read -r -p 'Press Return to close.'
  exit 1
fi
if [ ! -f .env ]; then uv run configure.py; fi
uv sync --extra voice
(sleep 3; open http://localhost:7860) &
uv run --extra voice server.py
