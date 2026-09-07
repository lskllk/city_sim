@echo off
rem ============================================================
rem  One-click CitySim: backend (WS :8765) + Observatory frontend (:5173)
rem  Windows cmd 版本。Ctrl+C 或直接关掉两个弹出的窗口即可停止。
rem  如需修改端口: set BE_PORT=xxxx 后再运行。
rem ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not defined BE_PORT set BE_PORT=8765
if not defined FE_PORT set FE_PORT=5173

echo [dev] freeing stale ports...
call :free_port %BE_PORT%
call :free_port %FE_PORT%

echo [dev] starting backend on port %BE_PORT% ...
start "CitySim backend (%BE_PORT%)" cmd /k "cd /d ""%~dp0"" && python -m uvicorn citysim.gateway.server:app --port %BE_PORT%"

if not exist "frontend\node_modules" (
  echo [dev] installing frontend deps...
  pushd frontend
  call npm install
  popd
)

echo [dev] starting frontend on port %FE_PORT% ...
start "CitySim frontend (%FE_PORT%)" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"

timeout /t 3 >nul
start http://localhost:%FE_PORT%
echo [dev] Observatory -> http://localhost:%FE_PORT%
echo [dev] Backend WS    -> ws://localhost:%BE_PORT%/ws
exit /b 0

:free_port
set _p=%1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr LISTENING ^| findstr ":%_p% "') do (
  taskkill /PID %%a /F >nul 2>&1
  echo [dev] freed port %_p% (pid %%a)
)
exit /b 0
