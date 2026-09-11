@echo off
setlocal enableextensions
rem ============================================================
rem  CitySim 一键运行 (Windows)
rem
rem    run.cmd            自动: 起后端 + 观察器(有 Godot 用 Godot, 否则浏览器)
rem    run.cmd godot      后端 + Godot 观察器
rem    run.cmd web        后端 + 浏览器前端(React/Vite)
rem    run.cmd backend    只起后端(WebSocket :8765)
rem
rem  可选环境变量:
rem    BE_PORT=8765                     后端端口
rem    GODOT_EXE=D:\Godot_v4.x.exe      Godot 可执行文件路径
rem    NO_INSTALL=1                     跳过依赖自检/安装
rem    KILL_STALE=0                     不清理占用端口的旧进程
rem
rem  提示: Godot 观察器自身也会自动拉起后端(见 godot/scripts/net/backend.gd),
rem        并会跳过已在监听的后端。若旧后端把端口占住, 本脚本会先清理。
rem ============================================================
cd /d "%~dp0"

rem ---- 找 Python -------------------------------------------------
set "PY=python"
where python >nul 2>nul
if errorlevel 1 set "PY=py"
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo [x] 未找到 Python。请安装 Python 3.10+ 并加入 PATH。
  pause
  exit /b 1
)

if not defined BE_PORT set "BE_PORT=8765"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=auto"

rem ---- 依赖自检(可 NO_INSTALL=1 跳过) ----------------------------
if not defined NO_INSTALL (
  %PY% -c "import citysim" >nul 2>nul
  if errorlevel 1 (
    echo [setup] 安装 citysim(editable) ...
    %PY% -m pip install -e .
  )
  %PY% -c "import uvicorn, fastapi" >nul 2>nul
  if errorlevel 1 (
    echo [setup] 安装 viz 依赖 (fastapi, uvicorn) ...
    %PY% -m pip install -e ".[viz]"
  )
)

rem ---- 清理占用端口的旧进程(KILL_STALE=0 跳过) -------------------
if /I "%KILL_STALE%"=="0" goto :no_kill
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%BE_PORT% " ^| findstr LISTENING') do (
  echo [setup] 端口 %BE_PORT% 被 PID %%P 占用, 清理中 ...
  taskkill /F /PID %%P >nul 2>nul
)
:no_kill

rem ---- 起后端(新窗口) -------------------------------------------
echo [run] 后端  http://127.0.0.1:%BE_PORT%/   ws://127.0.0.1:%BE_PORT%/ws
start "CitySim backend :%BE_PORT%" cmd /k "cd /d ""%~dp0"" && %PY% -m uvicorn citysim.gateway.server:app --port %BE_PORT%"

if /I "%MODE%"=="backend" goto :done

rem ---- 选择观察器 -------------------------------------------------
if /I "%MODE%"=="godot" goto :godot
if /I "%MODE%"=="web"   goto :web

rem auto: 优先 Godot, 找不到就用浏览器前端
if defined GODOT_EXE goto :godot
if exist "%ProgramFiles%\Godot\godot.exe" set "GODOT_EXE=%ProgramFiles%\Godot\godot.exe"
if not defined GODOT_EXE if exist "D:\Godot_v4.7.2-stable_win64.exe" set "GODOT_EXE=D:\Godot_v4.7.2-stable_win64.exe"
if defined GODOT_EXE goto :godot
goto :web

:godot
if not defined GODOT_EXE (
  echo [x] 未找到 Godot。请设置:  set GODOT_EXE=D:\path\to\Godot_v4.x-stable_win64.exe
  pause
  exit /b 1
)
timeout /t 2 >nul
echo [run] 启动 Godot 观察器: %GODOT_EXE%
"%GODOT_EXE%" --path "%~dp0godot"
goto :done

:web
timeout /t 2 >nul
echo [run] 启动浏览器前端: http://localhost:5173
pushd "%~dp0frontend"
if not exist node_modules (
  echo [setup] npm install ...
  call npm install
)
start "" "http://localhost:5173"
call npm run dev
popd
goto :done

:done
echo.
echo [done] 关闭后端窗口即可停止模拟。日志见 .logs\
endlocal
