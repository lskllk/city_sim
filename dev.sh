#!/usr/bin/env bash
# ============================================================
# 一键启动 CitySim：后端(WS :8765) + Observatory 前端(vite :5173)
# 用法:  bash dev.sh          (Git-Bash / WSL / macOS / Linux)
#        KILL_STALE=0 bash dev.sh   (不要强杀占用端口的旧进程)
# Ctrl+C 会同时关掉前后端。
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BE_PORT="${BE_PORT:-8765}"
FE_PORT="${FE_PORT:-5173}"
KILL_STALE="${KILL_STALE:-1}"
LOG_DIR="${ROOT}/.logs"
mkdir -p "${LOG_DIR}"

log() { echo "[dev] $*"; }

cleanup() {
  log "shutting down backend+frontend ..."
  [ -n "${BACKEND_PID:-}" ] && kill "${BACKEND_PID}" 2>/dev/null || true
  [ -n "${FRONTEND_PID:-}" ] && kill "${FRONTEND_PID}" 2>/dev/null || true
  # 兜底: 按端口释放(子进程可能脱离 shell 存活)
  free_port "${BE_PORT}" || true
  free_port "${FE_PORT}" || true
}
trap cleanup EXIT INT TERM

free_port() { # free_port <port>
  local port="$1" pid
  if command -v netstat >/dev/null 2>&1; then
    pid="$(netstat -ano 2>/dev/null \
      | awk -v p=":${port}" '$1 ~ /TCP/ && $4 ~ p && $4 ~ /LISTENING/ { print $NF; exit }')"
  fi
  [ -n "${pid:-}" ] || return 0
  # Windows git-bash 下 taskkill; POSIX 下直接 kill
  if command -v taskkill >/dev/null 2>&1; then
    taskkill //PID "${pid}" //F >/dev/null 2>&1
  else
    kill "${pid}" 2>/dev/null || true
  fi
  log "freed port ${port} (pid ${pid})"
}

if [ "${KILL_STALE}" = "1" ]; then
  free_port "${BE_PORT}"
  free_port "${FE_PORT}"
fi

log "starting backend (uvicorn :${BE_PORT}) ..."
(cd "${ROOT}" && python -m uvicorn citysim.gateway.server:app \
  --port "${BE_PORT}" > "${LOG_DIR}/backend.log" 2>&1) &
BACKEND_PID=$!

log "preparing frontend ..."
[ -d "${ROOT}/frontend/node_modules" ] || {
  log "frontend deps missing -> npm install"
  (cd "${ROOT}/frontend" && npm install)
}

log "starting frontend (vite :${FE_PORT}) ..."
(cd "${ROOT}/frontend" && npm run dev > "${LOG_DIR}/frontend.log" 2>&1) &
FRONTEND_PID=$!

echo
log "waiting for services ..."
for _ in $(seq 1 40); do
  backend_ok=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${BE_PORT}/" 2>/dev/null || true)
  frontend_ok=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${FE_PORT}/" 2>/dev/null || true)
  [ "${backend_ok}" = "200" ] && [ "${frontend_ok}" = "200" ] && break
  sleep 0.5
done

echo
log "──────────────────────────────────────────────"
log "  Observatory : http://localhost:${FE_PORT}"
log "  Backend WS  : ws://localhost:${BE_PORT}/ws"
log "  logs        : ${LOG_DIR}/{backend,frontend}.log"
log "  Ctrl+C 退出将同时停止前后端"
log "──────────────────────────────────────────────"

wait
