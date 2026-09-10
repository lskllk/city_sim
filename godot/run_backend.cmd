@echo off
rem ============================================================
rem  Start only the citysim backend (WS :8765) for the Godot observer.
rem  Override port:  set BE_PORT=xxxx
rem  Ctrl+C to stop.
rem ============================================================
cd /d "%~dp0.."
if not defined BE_PORT set BE_PORT=8765
echo [backend] http://127.0.0.1:%BE_PORT%/   ws://127.0.0.1:%BE_PORT%/ws
python -m uvicorn citysim.gateway.server:app --port %BE_PORT%
