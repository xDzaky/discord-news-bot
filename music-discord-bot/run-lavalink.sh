#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/dzaky/Desktop/coding-project/music-discord-bot"
LAVALINK_DIR="$PROJECT_ROOT/Vocard/lavalink"
LAVALINK_JAR="$PROJECT_ROOT/Lavalink.jar"

if [[ ! -f "$LAVALINK_JAR" ]]; then
  echo "Lavalink.jar not found at $LAVALINK_JAR"
  echo "Download it with:"
  echo "curl -L -o $LAVALINK_JAR https://github.com/lavalink-devs/Lavalink/releases/latest/download/Lavalink.jar"
  exit 1
fi

cd "$LAVALINK_DIR"
exec java -jar "$LAVALINK_JAR"
