"""server —— FastAPI app + WebSocket 端点。**接线与启动**。

启动: uvicorn citysim.game.server:app --port 8765

这是唯一允许同时知道"内核"与"游戏"的地方(组合根), 但它自己**不含逻辑**,
只负责把三样东西接起来:

    SimRunner       `runner.py`   拥有世界 · 推进 · 推送
    handle_cmd      `commands.py` 玩家说的话 → 动作
    hello / 健康探针  本文件

一个进程一个 runner(`runner` 全局单例), 由 `startup` 拉起它的 60Hz 循环。
"推进由 runner 独占; 一切读写都在 asyncio 事件循环内"—— 这条铁律的边界
就是这个文件: 事件循环之外不许碰 world。

副作用提醒: import 本模块会立刻接管 stdout/stderr 到 `.logs/backend.log`
(见 `logging_setup.py` 说明为什么必须在 import 期间做)。
"""
from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from citysim import api
from citysim.game.commands import handle_cmd, send
from citysim.game.logging_setup import tee_to_log_file
from citysim.game.runner import SimRunner

# 【import 期副作用】: 必须在 uvicorn 绑定日志 handler 之前接管输出。
tee_to_log_file()

app = FastAPI()
runner = SimRunner()


@app.on_event("startup")
async def _start() -> None:
    app.state.task = asyncio.create_task(runner.loop())


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    runner.clients.add(ws)
    runner.note_client_joined()          # 让下一帧带一份完整快照
    await send(ws, {"kind": "hello", **api.hello_payload(runner)})
    try:
        while True:
            cmd = json.loads(await ws.receive_text())
            await handle_cmd(runner, ws, cmd)
    except WebSocketDisconnect:
        runner.clients.discard(ws)


@app.get("/")
async def _root() -> dict:
    """健康探针; 观察器 UI 由独立 Godot 项目 godot/ 提供(连接 /ws)。"""
    return {"service": "citysim", "status": "ok",
            "ws": "/ws", "observer": "run godot/ (Godot Editor)"}
