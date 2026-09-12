@echo off
rem ============================================================
rem  Start only the citysim backend (WS :8765) for the Godot observer.
rem  Override port:  set BE_PORT=xxxx
rem  Load an editor-exported scene:
rem      set CITYSIM_SCENE=..\godot_editor\scene.json
rem  Ctrl+C to stop.
rem ============================================================
cd /d "%~dp0.."
if not defined BE_PORT set BE_PORT=8765
rem 优先用仓库 .venv(依赖装在这里), 否则回退 PATH 的 python
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=%CD%\.venv\Scripts\python.exe"
if defined CITYSIM_SCENE echo [backend] scene: %CITYSIM_SCENE%
echo [backend] http://127.0.0.1:%BE_PORT%/   ws://127.0.0.1:%BE_PORT%/ws
echo [backend] python: %PY%
"%PY%" -m uvicorn citysim.gateway.server:app --port %BE_PORT%
