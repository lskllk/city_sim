@echo off
chcp 65001 >nul
cd /d "%~dp0"
title citysim

rem 一键启动：起后端 + 自动开浏览器。参数会透传（--port 9000 / --no-open）
python tools\run.py %*
if errorlevel 9009 (
  rem 9009 = 找不到命令；退回 Windows 的 py 启动器再试一次
  echo 找不到 python，试 py -3 ...
  py -3 tools\run.py %*
)

echo.
echo 按任意键关闭这个窗口（后端也跟着停）
pause >nul
