@echo off
rem ============================================================
rem  One-click: start backend (new window) + launch Godot observer.
rem  Override:  set BE_PORT=xxxx
rem             set GODOT_EXE=D:\path\to\Godot_v4.x-stable_win64.exe
rem ============================================================
cd /d "%~dp0.."
if not defined BE_PORT set BE_PORT=8765
if not defined GODOT_EXE set GODOT_EXE=D:\Godot_v4.7.2-stable_win64.exe

echo [run] starting backend on :%BE_PORT% ...
start "CitySim backend (%BE_PORT%)" cmd /k "cd /d ""%~dp0.."" && python -m uvicorn citysim.gateway.server:app --port %BE_PORT%"

timeout /t 3 >nul
echo [run] launching Godot observatory ...
"%GODOT_EXE%" --path "%~dp0"
