#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/dzaky/Desktop/coding-project/music-discord-bot/Vocard"

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "Python virtualenv not found at $ROOT_DIR/.venv/bin/python"
  echo "Run: cd $ROOT_DIR && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt"
  exit 1
fi

cd "$ROOT_DIR"
exec "$ROOT_DIR/.venv/bin/python" -u main.py
