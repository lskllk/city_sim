#!/usr/bin/env bash
# 一条命令重画全部资产，然后用 wiki 验收。
# 改完 style.json / characters.json 就跑它。
set -e
cd "$(dirname "$0")"
node gen.mjs "$@"
python verify.py
cd ..
node wiki/gen.mjs
python wiki/verify.py
