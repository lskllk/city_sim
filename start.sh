#!/usr/bin/env bash
# citysim 一键启动（git-bash / WSL / macOS / Linux）
#   bash start.sh            起在 8765，自动开浏览器
#   bash start.sh --port 9000
#   bash start.sh --no-open
cd "$(dirname "$0")"
exec python tools/run.py "$@"
