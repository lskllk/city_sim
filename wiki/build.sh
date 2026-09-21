#!/usr/bin/env bash
# 一条命令重建 wiki（数据改了就跑它）
set -e
cd "$(dirname "$0")"
node gen.mjs
python verify.py
