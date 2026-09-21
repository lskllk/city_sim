#!/usr/bin/env bash
# 一条命令重画全部资产。改完 style.json / characters.json 就跑它。
set -e
cd "$(dirname "$0")"
node gen.mjs "$@"
python verify.py
node preview.mjs
