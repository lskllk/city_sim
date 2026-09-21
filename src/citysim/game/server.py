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
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from citysim import api
from citysim.game.commands import handle_cmd, send
from citysim.game.logging_setup import tee_to_log_file
from citysim.game.runner import SimRunner

# 【import 期副作用】: 必须在 uvicorn 绑定日志 handler 之前接管输出。
tee_to_log_file()

# 前端在 src/web/（vanilla ES module + PixiJS）。
# 从后端发出去而不是另开一个 dev server: 这样 WS 是同源的, 一条命令就能开。
ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "src" / "web"

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
    """健康探针; 前端在 /game/（src/web/）。"""
    return {"service": "citysim", "status": "ok",
            "ws": "/ws", "game": "/game/",
            "observer": "(归档) archive/godot-observer"}


# 美术产物: 前端按 art/xxx.svg 取（manifest.json 里的 file 字段就是这个前缀）。
# 只在目录存在时挂 —— 没见过 art/out 的人（比如只装内核）不会因为缺目录起不来。
if (ROOT / "art" / "out").is_dir():
    app.mount("/art", StaticFiles(directory=str(ROOT / "art" / "out")), name="art")

class NoCacheStatic(StaticFiles):
    """给前端加 no-store。

    ★ 为什么必须这么做：ES module 一旦被浏览器缓存，
      **改了 js 但页面还是老的** —— 用户会以为"你根本没改"。
      （我自己测的时候就得在 CDP 里加 ignoreCache 硬重载才看得见改动，
       这本身就是信号：正常用户没有那个开关。）
      前端没有构建步骤、文件名也不带 hash，所以只能靠不缓存。
    """

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        return resp


if WEB.is_dir():
    # /game/ → src/web/（html=True 让目录访问回到 index.html）。
    # 挂在最后: 上面两个先匹配。
    app.mount("/game", NoCacheStatic(directory=str(WEB), html=True), name="game")

    @app.get("/game")
    async def _game() -> FileResponse:
        return FileResponse(str(WEB / "index.html"))


# ══════════════════════════════════════════════════════════════════════════
# 编辑器要读写场景文件 —— 端点就这四个。
#
# 原则上编辑器只改 `map`（nodes/edges/buildings）和由它派生的 `locations`，
# 人的那份（npcs/entities/companies/knowledge）原样透传 —— 地图编辑器和
# 人物设计器是两个独立的部分，各改各的字段，不互相踩。
# ══════════════════════════════════════════════════════════════════════════
SCENES_DIR = ROOT / "config" / "scenes"
LAST_SCENE = ROOT / ".logs" / "last_scene"        # 编辑器"默认加载最近的地图"


def _scene_path(name: str) -> Path:
    """只允许 config/scenes/ 下面的 .json —— 不接受任意路径。"""
    p = (SCENES_DIR / name).resolve()
    if p.suffix != ".json" or p.parent != SCENES_DIR.resolve():
        raise HTTPException(400, "场景名不合法（只收 config/scenes/*.json）")
    return p


@app.get("/api/scenes")
async def list_scenes() -> dict:
    if not SCENES_DIR.is_dir():
        return {"scenes": [], "last": ""}
    last = ""
    try:
        last = LAST_SCENE.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    out = []
    for f in sorted(SCENES_DIR.glob("*.json")):
        st = f.stat()
        out.append({"name": f.name, "bytes": st.st_size,
                    "mtime": int(st.st_mtime)})
    # 最近编辑的排最前：编辑器的"默认加载"就是它
    out.sort(key=lambda s: (s["name"] != last, -s["mtime"]))
    return {"scenes": out, "last": last}


@app.get("/api/scene")
async def get_scene(name: str = "scene.json") -> dict:
    p = _scene_path(name)
    if not p.is_file():
        raise HTTPException(404, f"场景不存在: {name}")
    return json.loads(p.read_text(encoding="utf-8"))


@app.put("/api/scene")
async def put_scene(body: dict, name: str = "scene.json") -> dict:
    """保存。**先备份再写** —— 编辑器一个误操作能洗掉一天的地图。"""
    p = _scene_path(name)
    if p.is_file():
        (p.parent / (p.name + ".bak")).write_bytes(p.read_bytes())
    p.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    LAST_SCENE.parent.mkdir(exist_ok=True)
    LAST_SCENE.write_text(p.name, encoding="utf-8")
    return {"ok": True, "name": p.name, "bytes": p.stat().st_size}


@app.get("/api/catalog")
async def catalog() -> dict:
    """编辑器左侧的调色盘：建筑类型 + 它们的默认占地。

    占地公式与后端一致（见 world/model/buildings.py）: 面积 ∝ 容量。
    放在服务端算一遍，免得两边公式漂。
    """
    import math
    # ★ 编辑器摆房子用的占地公式：面积 ∝ 容量，1 capacity ≈ 20 m²。
    #   和后端【自动布局】不是一回事 —— 那边是"等比缩放进画布"（后端无 x/y 时才用）。
    #   编辑器导出的场景里 location 带显式 x/y/w/h，后端会原样保留，
    #   所以两套公式不会打架：编辑器定的就是真值。
    #   （对齐归档的 Godot 编辑器 map_doc.gd: AREA_PER_CAPACITY = 20.0）
    area_per_capacity = 20.0
    types = []
    d = ROOT / "config" / "buildings"
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            t = json.loads(f.read_text(encoding="utf-8"))
            area = float(t.get("capacity", 12)) * area_per_capacity
            aspect = float(t.get("aspect", 1.0)) or 1.0
            w = math.sqrt(area * aspect)
            types.append({"type": t.get("type", f.stem),
                          "name": t.get("name", f.stem),
                          "kind": t.get("kind", ""),
                          "capacity": t.get("capacity", 0),
                          "aspect": aspect,
                          "doors": t.get("doors", []),
                          "size": [round(w, 3), round(w / aspect, 3)]})
    return {"buildings": types, "area_per_capacity": area_per_capacity}
