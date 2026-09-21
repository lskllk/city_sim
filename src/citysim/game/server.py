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


@app.middleware("http")
async def no_store(request, call_next):
    """★ 一律 no-store。

    踩过：/game/ 的静态文件早加了 no-store，但【API 没有】——
    于是编辑器 GET /api/scene 拿到的是浏览器缓存里的旧场景：
    你刚保存、再打开编辑器，看到的还是改之前那张图。
    开发期这些响应都很小，别缓存最省心。
    """
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


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
    """保存。

    ★ 不再写 .bak：撤销栈（Ctrl+Z，60 步）已经覆盖了"误操作"这件事，
      而 .bak 会混进 config/scenes/ 被当成一个"场景"列出来。
    """
    p = _scene_path(name)
    p.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    LAST_SCENE.parent.mkdir(exist_ok=True)
    LAST_SCENE.write_text(p.name, encoding="utf-8")
    return {"ok": True, "name": p.name, "bytes": p.stat().st_size}


@app.delete("/api/scene")
async def delete_scene(name: str) -> dict:
    """删场景 —— 给回归脚本收尾用（它存到 _regress_tmp.json）。
    只允许删 config/scenes/ 下的，且**不允许**删最后一个场景。"""
    p = _scene_path(name)
    if not p.is_file():
        raise HTTPException(404, f"场景不存在: {name}")
    if len(list(SCENES_DIR.glob("*.json"))) <= 1:
        raise HTTPException(400, "这是最后一个场景，不能删")
    p.unlink()
    return {"ok": True, "name": name}


@app.get("/api/npc-parts")
async def npc_parts(name: str = "scene.json") -> dict:
    """人物设计器要的一切「可选项」——全部从内核侧的配置和美术里算出来，
    前端不硬编码任何一份。改 config/ 或 art/ 这里就跟着变。

    含：外观（8 套美术）、住宅（带容量和已住人数）、名字池、特性池、
        信号名（性格倍率）、性别的合法取值。
    """
    import json as _json

    BODY_ZH = {"slim": "瘦", "medium": "中等", "stocky": "壮"}
    scene = _json.loads(_scene_path(name).read_text(encoding="utf-8"))

    # 外观：直接用美术里那 8 个人（每人 3 向 × 5 帧 + 头像都已生成）。
    # ★ 任意捏脸（自由组合体型/发型/上衣）要现生成 SVG，那是另一件事 ——
    #   现在先让人挑"长得像谁"，列表里的头像和世界里的精灵都跟着变。
    looks = []
    chars_path = ROOT / "art" / "characters.json"
    if chars_path.is_file():
        ch = _json.loads(chars_path.read_text(encoding="utf-8"))
        for c in ch.get("characters", []):
            hair = ch.get("hairStyles", {}).get(c.get("hair"), {})
            looks.append({"id": c["id"], "name": c.get("name", c["id"]),
                          "body": c.get("body"), "hair": hair.get("label", c.get("hair")),
                          "skin": c.get("skin"), "top": c.get("top"),
                          "acc": c.get("acc")})
    body_labels = {}
    style_path = ROOT / "art" / "style.json"
    if style_path.is_file():
        st = _json.loads(style_path.read_text(encoding="utf-8"))
        body_labels = {k: v.get("label", BODY_ZH.get(k, k))
                       for k, v in ((st.get("person") or {}).get("bodies") or {}).items()}

    # 住宅：容量来自 config/buildings 的 capacity；已住人数从场景的 npcs 数出来
    btypes = {}
    bdir = ROOT / "config" / "buildings"
    if bdir.is_dir():
        for f in bdir.glob("*.json"):
            b = _json.loads(f.read_text(encoding="utf-8"))
            btypes[b.get("type")] = b
    used: dict[str, int] = {}
    for n in scene.get("npcs", []):
        h = str(n.get("home", ""))
        if h:
            used[h] = used.get(h, 0) + 1
    homes = []
    for lid, spec in (scene.get("locations") or {}).items():
        bt = btypes.get(spec.get("type"))
        if not bt or bt.get("kind") != "home":
            continue
        cap = int(bt.get("capacity", 1))
        homes.append({"id": lid, "name": spec.get("name") or lid,
                      "capacity": cap, "used": used.get(lid, 0),
                      "full": used.get(lid, 0) >= cap})

    names = {}
    npath = ROOT / "config" / "names.json"
    if npath.is_file():
        names = _json.loads(npath.read_text(encoding="utf-8"))

    # ★ 走门面，不直接 import 内核 —— game/ 只许 import citysim.api（红线 #2）
    return {"looks": looks, "bodyLabels": body_labels,
            "homes": sorted(homes, key=lambda h: h["id"]),
            "surnames": names.get("surnames", []),
            "given": names.get("given", {"female": [], "male": []}),
            "traits": names.get("traits", []),
            "genders": ["female", "male"],
            "signals": list(api.SIGNALS)}


@app.get("/api/building-parts")
async def building_parts(name: str = "scene.json") -> dict:
    """建筑编辑器要的可选项。和 /api/npc-parts 一个路子：全从内核侧算，前端不硬编码。

    · types  改建筑类型用（容量/尺寸跟着变）
    · items  "里面摆什么"用（config/items 全表）
    · companies  这个场景里已有的公司（建筑可以挂在某家名下）
    """
    import json as _json
    import math

    scene = _json.loads(_scene_path(name).read_text(encoding="utf-8"))
    apc = 20.0  # 面积 ∝ 容量，1 capacity ≈ 20 m²（和编辑器摆房子同一套）

    types = []
    bdir = ROOT / "config" / "buildings"
    if bdir.is_dir():
        for f in sorted(bdir.glob("*.json")):
            b = _json.loads(f.read_text(encoding="utf-8"))
            area = float(b.get("capacity", 12)) * apc
            aspect = float(b.get("aspect", 1.0)) or 1.0
            w = math.sqrt(area * aspect)
            types.append({"type": b.get("type", f.stem), "name": b.get("name", f.stem),
                          "kind": b.get("kind", ""), "capacity": b.get("capacity", 0),
                          "size": [round(w, 3), round(w / aspect, 3)]})

    items = []
    idir = ROOT / "config" / "items"
    if idir.is_dir():
        for f in sorted(idir.glob("*.json")):
            it = _json.loads(f.read_text(encoding="utf-8"))
            ty = it.get("item_type", f.stem)
            items.append({"type": ty, "name": it.get("name", f.stem),
                          # 有没有图标 —— 前端照着决定是贴图还是占位
                          "icon": (ROOT / "art" / "out" / "items" /
                                   ("icon_" + ty + ".svg")).is_file(),
                          "tags": sorted(it.get("tags", [])),
                          "price": it.get("price", 0), "stock": it.get("stock", 1),
                          "build_cost": it.get("build_cost", 0),
                          "affordances": sorted((it.get("affordances") or {}).keys())})

    return {"types": types, "items": items,
            "companies": [{"id": c.get("id"), "name": c.get("name"), "kind": c.get("kind")}
                          for c in scene.get("companies", [])]}


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
