#!/usr/bin/env fish

set root_dir /home/dzaky/Desktop/coding-project/music-discord-bot/Vocard

if not test -x "$root_dir/.venv/bin/python"
    echo "Python virtualenv not found at $root_dir/.venv/bin/python"
    echo "Run: cd $root_dir; python3 -m venv .venv; ./.venv/bin/pip install -r requirements.txt"
    exit 1
end

cd $root_dir
$root_dir/.venv/bin/python -u main.py
