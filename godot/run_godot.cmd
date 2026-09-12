@echo off
rem ============================================================
rem  One-click: start backend (new window) + launch Godot observer.
rem  Load an editor-exported scene:
rem      run_godot.cmd godot_editor\scene.json
rem  Override:  set BE_PORT=xxxx
rem             set GODOT_EXE=D:\path\to\Godot_v4.x-stable_win64.exe
rem ============================================================
cd /d "%~dp0.."
if not defined BE_PORT set BE_PORT=8765
if not defined GODOT_EXE set GODOT_EXE=D:\Godot_v4.7.2-stable_win64.exe
if not "%~1"=="" set "CITYSIM_SCENE=%~1"
if defined CITYSIM_SCENE echo [run] scene: %CITYSIM_SCENE%

echo [run] starting backend on :%BE_PORT% ...
rem 复用 run_backend.cmd(内含 .venv 优先逻辑)
start "CitySim backend (%BE_PORT%)" cmd /k call "%~dp0run_backend.cmd"

timeout /t 3 >nul
echo [run] launching Godot observatory ...
"%GODOT_EXE%" --path "%~dp0"
