#!/usr/bin/env bash
# Ai-Lens — create python/venv with the optional `anthropic` package so the
# server can translate headlines (Arabic ⇄ English) with Claude.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -m venv "$ROOT/python/venv"
"$ROOT/python/venv/bin/pip" install -q -r "$ROOT/python/requirements.txt"
echo "Done. Set ANTHROPIC_API_KEY in .env (or run 'ant auth login'), then tools/stop.sh && tools/start.sh"
