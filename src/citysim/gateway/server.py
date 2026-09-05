"""server —— FastAPI + WebSocket 网关(display_m5_ui G1)。

只读观察者(design 第三节铁律): 推进由本 runner 独占; 一切读写都在 asyncio
事件循环内; 未知指令静默忽略(不回退 eval)。
启动: uvicorn citysim.gateway.server:app --port 8765
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from citysim.core.config import load_config
from citysim.gateway.scenarios import build_scenario
from citysim.gateway.snapshot import build_snapshot, do_query, hello_payload
from citysim.sim.loop import attach_replay, run_tick

SPEED_TPS = {"pause": 0, "1x": 1, "10x": 10, "100x": 100, "1000x": 1000}
PUSH_HZ = 60
STATIC = Path(__file__).parent / "static"


def _real_tps(speed: str) -> int:
    """当前档位真实 ticks/秒(1x=1 tick/秒, 供前端 tick 外推)。"""
    return SPEED_TPS[speed]


class SimRunner:
    """单实例、单线程(asyncio)拥有 world; 所有读写都在事件循环里。"""

    def __init__(self) -> None:
        self.cfg = load_config()
        self.clients: set[WebSocket] = set()
        self.speed = "pause"          # 启动即暂停, 方便观察初态
        self.log_cursor = 0
        self.params = dict(scenario="elm_lane", seed=3, n_npc=6,
                           kb_mode="full", tell_p=0.1)
        self._build()

    def _build(self) -> None:
        self.world, self.systems, self.rng_pool = build_scenario(**self.params)
        attach_replay(self.world, self.systems)   # log_lines 承载 D/E 行
        self.log_cursor = 0

    def advance(self, n: int) -> None:
        for _ in range(n):
            run_tick(self.world, self.systems, self.cfg, self.rng_pool)

    def drain_log(self) -> list[dict]:
        evs = (self.systems.ui_events or [])[self.log_cursor:]
        self.log_cursor = len(self.systems.ui_events or [])
        return [dict(e) for e in evs]

    async def loop(self) -> None:
        interval = 1.0 / PUSH_HZ
        acc = 0.0                      # 分数 tick 累加器, 精确实现 1x=1tick/s
        while True:
            tps = SPEED_TPS[self.speed]
            if tps == 0:
                acc = 0.0
                await asyncio.sleep(interval)
            else:
                acc += tps * interval
                n = int(acc)
                if n > 0:
                    self.advance(n)
                    acc -= n
                await asyncio.sleep(interval)
            await self.push()

    async def push(self) -> None:
        if not self.clients:
            self.drain_log()          # 无人观看也要推进游标, 防积压
            return
        msg = json.dumps(build_snapshot(self.world, self.systems, self.cfg,
                                        self.speed, self.drain_log(),
                                        tps=_real_tps(self.speed)),
                         ensure_ascii=False)
        dead = []
        for ws in self.clients:
            try:
                await ws.send_text(msg)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


app = FastAPI()
runner = SimRunner()


@app.on_event("startup")
async def _start() -> None:
    app.state.task = asyncio.create_task(runner.loop())


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    runner.clients.add(ws)
    await ws.send_text(json.dumps(hello_payload(runner), ensure_ascii=False))
    try:
        while True:
            cmd = json.loads(await ws.receive_text())
            await handle_cmd(runner, ws, cmd)
    except WebSocketDisconnect:
        runner.clients.discard(ws)


async def handle_cmd(r: SimRunner, ws: WebSocket, cmd: dict) -> None:
    name, args, rid = cmd.get("name"), cmd.get("args", {}), cmd.get("req_id")
    if name == "set_speed" and args.get("speed") in SPEED_TPS:
        r.speed = args["speed"]
    elif name == "step":
        r.advance(max(1, min(int(args.get("ticks", 1)), 5000)))
        await r.push()
    elif name == "reset":
        r.params.update({k: v for k, v in args.items() if k in r.params})
        r.speed = "pause"
        r._build()
        await ws.send_text(json.dumps(hello_payload(r), ensure_ascii=False))
        await r.push()
    elif name == "query":
        data = do_query(r, args)
        await ws.send_text(json.dumps(
            {"type": "reply", "req_id": rid, "ok": data is not None,
             "data": data, "why": None if data is not None else "not found"},
            ensure_ascii=False))
    elif name == "ping":
        await ws.send_text(json.dumps({"type": "pong", "req_id": rid}))
    # 未知指令静默忽略


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
