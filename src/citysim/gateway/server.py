"""server —— FastAPI + WebSocket 网关(display_m5_ui G1)。

只读观察者(design 第三节铁律): 推进由本 runner 独占; 一切读写都在 asyncio
事件循环内; 未知指令静默忽略(不回退 eval)。
启动: uvicorn citysim.gateway.server:app --port 8765
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
import json
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from citysim.core.config import load_config

log = logging.getLogger("citysim.server")
from citysim.gateway.scenarios import build_scenario
from citysim.gateway.snapshot import (
    build_snapshot,
    do_query,
    encode_event,
    envelope,
    hello_payload,
)
from citysim.sim.loop import attach_replay, run_tick

SPEED_TPS = {"pause": 0, "1x": 1, "10x": 10, "100x": 100, "1000x": 1000}
PUSH_HZ = 60          # 状态快照推送频率。
                      # 60Hz 之所以安全, 靠的是【观察驱动】: 只推渲染状态变了的 NPC
                      # + 选中的那个; 静止时一帧 0 个 NPC(实测 ~6.6KB/帧)。
                      # 若退回全量推送, 60Hz × 百人快照会拖成长超时断线。
# 单个客户端的单条发送最长等待秒数。超时 → 【丢这一帧】(不断线):
# 快照是全量状态, 丢了下一帧会补齐; 断开只会引发客户端无限重连。
# 真正的断开/协议错误仍走 except → 清掉该客户端。
CLIENT_SEND_TIMEOUT = 1.5

# 仓库根(src/citysim/gateway/server.py → parents[3]); 配置用绝对路径,
# 这样后端进程的工作目录无关紧要(Godot 自动拉起时尤其重要)。
_ROOT = Path(__file__).resolve().parents[3]

# TASK004-ext: legacy gateway/static 观察器已删除; server 只作 WS 推流端点。
# UI 由独立 Godot 观察器 godot/ 提供(见 godot/README.md)。


class _Tee(io.TextIOBase):
    """把 stdout/stderr 同时写向原流与日志文件(原流不可写时静默跳过)。"""

    def __init__(self, *streams) -> None:
        self._streams = streams

    def write(self, text: str) -> int:  # noqa: D102
        for st in self._streams:
            try:
                st.write(text)
            except Exception:  # noqa: BLE001  (无控制台时 stdout 可能不可写)
                pass
        return len(text)

    def flush(self) -> None:  # noqa: D102
        for st in self._streams:
            try:
                st.flush()
            except Exception:  # noqa: BLE001
                pass


def _tee_to_log_file() -> Path | None:
    """后端默认【无控制台窗口】后台运行 → 日志改落 .logs/backend.log。

    在 import 期间接管 stdout/stderr: uvicorn 的日志 handler 绑定的是当时的
    sys.stderr, 所以这样能连 uvicorn 自己的日志一起收。
    超过 8MB 时启动前轮转为 .1(只保留一份备份, 不无限长)。
    """
    logdir = _ROOT / ".logs"
    try:
        logdir.mkdir(exist_ok=True)
        path = logdir / "backend.log"
        if path.exists() and path.stat().st_size > 8_000_000:
            path.replace(logdir / "backend.1.log")
        f = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    sys.stdout = _Tee(sys.stdout, f)   # type: ignore[assignment]
    sys.stderr = _Tee(sys.stderr, f)   # type: ignore[assignment]
    return path


LOG_PATH = _tee_to_log_file()


def _real_tps(speed: str) -> int:
    """当前档位真实 ticks/秒(1x=1 tick/秒, 供前端 tick 外推)。"""
    return SPEED_TPS[speed]


class SimRunner:
    """单实例、单线程(asyncio)拥有 world; 所有读写都在事件循环里。"""

    def __init__(self) -> None:
        self.cfg = load_config(_ROOT / "config" / "sim.toml")
        self.clients: set[WebSocket] = set()
        self.speed = "pause"          # 启动即暂停, 方便观察初态
        self.log_cursor = 0
        self.event_seq = 0            # drain 兜底 event_id 序号
        # scenario="" = 用「存在的那个」默认场景(见 scenarios.default_scene_path);
        # 写死名字的话, 文件一被删后端就起不来。
        # tell_p / listen_p【不在这里硬写】: 传 None = 不覆盖, 用场景 JSON
        # 或 config/sim.toml [social] 的值。以前这里写 0.1, 会把 sim.toml
        # 的 0.3 悄悄盖掉 —— 配置说的和实际跑的不是一个数。
        self.params = dict(scenario="", seed=3, n_npc=6,
                           tell_p=None, listen_p=None)
        self.build_error: str = ""     # 场景加载失败的原因(给 UI 看, 不再闪退)
        self._pushed_tick: int | None = None   # 上次推送时的 tick(None=需重推)
        # 观察驱动: 只下发「渲染状态变了」的 NPC + 当前选中的那个。
        self._npc_sig: dict[str, tuple] = {}   # pid -> 上次推送时的渲染签名
        # 【观察集】: 客户端正在看谁 / 看哪栋楼 —— 这些每帧全量下发。
        # 为什么必须要: signals 每 tick 都在变(进度条/生命条), 但它不属于
        # “渲染签名”(否则所有人都每帧脏)。所以静止的 NPC 靠“被看见”而刷新。
        self.focus_npc: str = ""
        self.focus_loc: str = ""
        self.watch_limit: int = 64             # 单处最多盯多少人(建筑可能很大)
        # 上帧世界里还存在哪些 id → 用来算 gone(死亡/消耗), 供客户端删除镜像
        self._seen_npcs: set[str] = set()
        self._seen_entities: set[str] = set()
        # 物品几乎不变 → 变了才推(否则每帧白带 ~8KB)
        self._ent_sig: dict[str, tuple] = {}
        # 观察集【轮转分批】: 1000x 下变化很大, 一次全推会顶爆单帧,
        # 拆成多批每帧一批 → 每个人的进度条 ~watch_hz 刷新一次。
        self.watch_per_frame: int = 24
        self._watch_cursor: int = 0
        # 详情(memory/events/intent)推送间隔: Inspector 自己就是 10Hz 刷新
        # (UiPage.bind ~100ms), 60Hz 重发只是白烧带宽。
        # 客户端是 merge —— 不推的帧保留上次值, 不会缺。
        self.rich_every: int = 6          # 60Hz / 6 = 10Hz
        self._push_seq: int = 0
        self._build()

    def note_client_joined(self) -> None:
        """新客户端接入 → 下一帧强制推一份完整快照(全部 NPC 重算为 dirty)。"""
        self._pushed_tick = None
        self._npc_sig.clear()
        self._ent_sig.clear()
        self._watch_cursor = 0
        self._push_seq = 0
        self._seen_npcs.clear()     # 新客户端脑子里什么都没有 → 不发 tombstone
        self._seen_entities.clear()

    def _build(self) -> None:
        try:
            self.world, self.systems, self.rng_pool = build_scenario(
                **self.params)
            self.build_error = ""
        except Exception as exc:      # noqa: BLE001
            # 【不闪退】: 场景坏了也要能起服务, 把原因告诉前端。
            # 以前这里是裸调用 → 删了个场景文件, 后端 import 阶段就死, 前端只看到断开。
            import traceback
            self.build_error = "%s: %s" % (type(exc).__name__, exc)
            log.error("场景加载失败, 用空世界启动: %s", self.build_error)
            traceback.print_exc()
            from citysim.world.world import World
            from citysim.sim.loop import make_systems
            self.world = World()
            self.systems = make_systems(log=True)
            self.rng_pool = {}
        attach_replay(self.world, self.systems)   # log_lines 承载 D/E 行
        self.log_cursor = 0
        self._pushed_tick = None
        self._npc_sig.clear()
        self._ent_sig.clear()
        self._watch_cursor = 0
        self._push_seq = 0
        self._seen_npcs.clear()
        self._seen_entities.clear()
        self.focus_npc = ""
        self.focus_loc = ""

    def watch_set(self) -> set[str]:
        """我关注的人(选中的那个 + 选中建筑里的人)。**无副作用** ——
        气泡过滤要用它, 不能动 _watched() 的轮转游标。"""
        out: set[str] = set()
        if self.focus_npc in self.world.npcs:
            out.add(self.focus_npc)
        loc = self.focus_loc
        if loc:
            pref = loc + "_f"
            for pid in self.world.npcs:
                at = self.world.loc_of(pid)
                if at == loc or at.startswith(pref):
                    out.add(pid)
        return out

    def _watched(self) -> set[str]:
        """客户端正在看的 NPC。

        - **选中的那个**: 每帧全量(带 memory/events, Inspector 要实时)。
        - **选中建筑里的人**: 只负责让进度条动 —— 轮转分批, 每帧一批,
          所以单帧不会因为“盯着一整栋百人大楼”而爆。
        """
        out: set[str] = set()
        if self.focus_npc and self.focus_npc in self.world.npcs:
            out.add(self.focus_npc)
        loc = self.focus_loc
        if not loc:
            return out
        pref = loc + "_f"
        here: list[str] = []
        for pid in self.world.npcs:
            at = self.world.loc_of(pid)
            if at == loc or at.startswith(pref):
                here.append(pid)
        here.sort()
        here = here[:self.watch_limit]
        if not here:
            return out
        n = max(1, min(self.watch_per_frame, len(here)))
        for i in range(n):
            out.add(here[(self._watch_cursor + i) % len(here)])
        self._watch_cursor = (self._watch_cursor + n) % len(here)
        return out

    def _ent_sig_of(self, e) -> tuple:
        return (e.location_id, e.stock, round(float(e.price), 4), e.owner,
                e.claimed_by, e.position, bool(e.persist_empty))

    def _dirty_entities(self) -> set[str]:
        """物品很少变 → 变了才推。客户端 merge + gone 删除, 不会错。"""
        now: dict[str, tuple] = {}
        out: set[str] = set()
        for eid, e in self.world.entities.items():
            s = self._ent_sig_of(e)
            now[eid] = s
            if self._ent_sig.get(eid) != s:
                out.add(eid)
        self._ent_sig = now
        return out

    def _render_sig(self, pid: str) -> tuple:
        """NPC 的【渲染状态】签名: 地点 / 活动 / 是否在途(目的地+出发到达刻)。

        刻意不含 signals/memory/events —— 它们只有「选中的那个」才需要,
        且每 tick 都在变; 放进签名会让每个 NPC 每帧都算「变了」。
        在家静止的人签名恒定 → 不推位置。
        """
        tv = self.systems.travel.get(pid)
        return (
            self.world.loc_of(pid),
            self.world.npcs[pid].current_activity,
            None if tv is None else (tv.to_loc, tv.depart_tick, tv.arrive_tick),
        )

    def _dirty_npcs(self) -> set[str]:
        """本帧要下发的 NPC = 渲染状态变了的 ∪ {选中的}。"""
        sig_now: dict[str, tuple] = {}
        dirty: set[str] = set()
        tick = self.world.clock_tick
        for pid, p in self.world.npcs.items():
            s = self._render_sig(pid)
            sig_now[pid] = s
            if self._npc_sig.get(pid) != s:
                dirty.add(pid)
            # 正在冒泡的人也要推 —— 气泡是【事件】, 不改渲染签名。
            # (推完就不脏了: 下次靠 until 过期, 前端自己收尾)
            b = getattr(p, "bubble", None)
            if b is not None and int(b[1]) > tick:
                dirty.add(pid)
        self._npc_sig = sig_now
        dirty |= self._watched()        # 选中的 + 选中建筑里的人(实时信号)
        return dirty

    def advance(self, n: int) -> None:
        # 气泡只在【我关注的地方】冒: 把观察集喂给 engine(空集 = 一个都不冒)
        self.systems.bubble_watch = self.watch_set()
        for _ in range(n):
            run_tick(self.world, self.systems, self.cfg, self.rng_pool)

    def drain_log(self) -> list[dict]:
        evs, self.log_cursor = self.systems.ui_events.drain(self.log_cursor)
        out = []
        for i, e in enumerate(evs, self.event_seq):
            d = dict(e)
            d.setdefault("event_id", f"g{i}")   # 兜底 id(生产端缺失时)
            out.append(d)
        self.event_seq += len(evs)
        return out

    async def loop(self) -> None:
        """固定 60Hz 推送 (PUSH_HZ), 与倍率无关。

        关键: 给【推进】设时间预算 —— 一轮最多花 70% 的间隔在算 tick 上,
        剩下的时间一定留给推送。否则 1000x 会把单轮拖到几十毫秒,
        推送频率掉到 20~30Hz, 前端就看不到 60Hz 的帧了。
        推进不完的 tick 留到下一轮(但设上限, 不许无限积压)。
        """
        interval = 1.0 / PUSH_HZ
        budget = interval * 0.7
        acc = 0.0                      # 分数 tick 累加器
        last = time.perf_counter()
        while True:
            t0 = time.perf_counter()
            # 【用真实经过的时间】累加, 而不是标称 interval。
            # 用标称值时: 一轮实际耗时 = 计算 + 推送 + sleep > interval
            # → 循环只有 ~30Hz → 1x 只推进 0.5 tick/s(实测), 游戏时间比
            # 墙钟慢一半, 而且客户端的本地时钟立刻超到前面去(见前端 _advance_clock)。
            dt = min(t0 - last, interval * 4.0)      # 夹住, 防长停顿后暴冲
            last = t0
            tps = SPEED_TPS[self.speed]
            if tps == 0:
                acc = 0.0
            else:
                acc += tps * dt
                n = int(acc)
                done = 0
                while done < n:
                    self.advance(1)
                    done += 1
                    if time.perf_counter() - t0 >= budget:
                        break
                acc -= done
                # 防雪球: 最多积压两个间隔的量(跑不动就认了, 不拖垮推送)
                acc = min(acc, max(1.0, tps * interval * 2.0))
            await self.push()
            rest = interval - (time.perf_counter() - t0)
            if rest > 0:
                await asyncio.sleep(rest)

    async def push(self) -> None:
        if not self.clients:
            self.drain_log()          # 无人观看也要推进游标, 防积压
            return
        evs = self.drain_log()
        tick = self.world.clock_tick
        dirty = self._dirty_npcs()
        # 状态未变(暂停/无人移动且无事件) → 不重复推: 省掉暂停时的全量空转。
        # 新客户端接入/重置/步进 会把 _pushed_tick 置 None 或推进 tick。
        if self._pushed_tick == tick and not evs and not dirty:
            return
        self._pushed_tick = tick
        self._push_seq += 1
        # 被选中的那个: 每帧在观察集里(信号实时), 但详情每 rich_every 帧才带一次
        rich: set[str] = set()
        if self.focus_npc in self.world.npcs:
            dirty.add(self.focus_npc)
            if self._push_seq % max(1, self.rich_every) == 0:
                rich.add(self.focus_npc)
        dirty_ents = self._dirty_entities()
        # 消失的 id(死亡/消耗): 客户端是合并式更新, 必须显式告诉它删
        cur_npcs = set(self.world.npcs)
        cur_ents = set(self.world.entities)
        gone = {"npcs": sorted(self._seen_npcs - cur_npcs),
                "entities": sorted(self._seen_entities - cur_ents)}
        self._seen_npcs = cur_npcs
        self._seen_entities = cur_ents
        # TASK002: Snapshot 与 Event 走独立消息; snapshot 不再内嵌事件流
        # 观察驱动: 只带 dirty 的 NPC(在家不动的座位不上车)
        msgs = [json.dumps(envelope(
            "snapshot",
            build_snapshot(self.world, self.systems, self.cfg,
                           self.speed, [], tps=_real_tps(self.speed),
                           only=dirty, gone=gone, rich=rich,
                           entities_only=dirty_ents)),
            ensure_ascii=False)]
        msgs += [json.dumps(envelope("event", encode_event(ev)),
                            ensure_ascii=False) for ev in evs]
        dead = []
        for ws in list(self.clients):
            try:
                for m in msgs:
                    await asyncio.wait_for(ws.send_text(m),
                                           timeout=CLIENT_SEND_TIMEOUT)
            except asyncio.TimeoutError:
                # 客户端只是慢(解析大快照没跟上) —— 【丢这一帧】, 但不断线:
                # 下一帧仍是完整状态, 丢了不会错。断开反而会引发疯狂重连。
                continue
            except Exception:  # noqa: BLE001  (断开/协议错误)
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)
            # 关闭也可能阻塞, 丢到后台任务, 不占用主循环。
            asyncio.create_task(_safe_close(ws))


async def _safe_close(ws: WebSocket) -> None:
    try:
        await asyncio.wait_for(ws.close(), timeout=1.0)
    except Exception:  # noqa: BLE001
        pass


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
    await _send(ws, {"kind": "hello", **hello_payload(runner)})
    try:
        while True:
            cmd = json.loads(await ws.receive_text())
            await handle_cmd(runner, ws, cmd)
    except WebSocketDisconnect:
        runner.clients.discard(ws)


async def _send(ws: WebSocket, payload: dict) -> None:
    """统一出口: 全部 WS 消息都走 envelope(kind/protocol_version/payload)。"""
    await ws.send_text(json.dumps(envelope(payload.pop("kind", "message"),
                                           payload), ensure_ascii=False))


def _admin_company(r, op: str, args: dict) -> dict:
    """游戏内的经营动作(上帝视角/老板面板用)。**只改世界真值** —— P8 ✓。

    op:
      register  点一个商铺建筑 → 注册公司 {location, name, cash}
      update    改参数 {company, cash/open_minute/close_minute/wage_per_hour/restock_to}
      hire      发布/撤回招聘启事 {company, slots}   ← 招不招人是公司说了算
      restock   向市场进货 {company, shop?, item_type, qty}
    注: 招聘只是【发布启事】, 真正撮合还是每天 hire_minute 那次(媒婆)。
    """
    from citysim.world.companies import Company
    from citysim.world.market import purchase
    world = r.world
    op = str(op)
    if op == "register":
        loc = str(args.get("location", ""))
        loc_rec = world.locations.get(loc)
        if not loc_rec:
            return {"ok": False, "why": "没有这个建筑", "company": ""}
        if loc_rec.get("company"):
            return {"ok": False, "why": "这栋楼已经登记过公司了",
                    "company": str(loc_rec["company"])}
        if str(loc_rec.get("kind", "")) != "shop":
            return {"ok": False, "why": "只有商铺才能注册公司", "company": ""}
        name = str(args.get("name", "")).strip()
        if name == "":
            return {"ok": False, "why": "公司名不能空", "company": ""}
        cid = "org_%s" % loc
        world.companies[cid] = Company(
            company_id=cid, name=name,
            cash=float(args.get("cash", 1000.0)), shops=(loc,))
        loc_rec["company"] = cid
        return {"ok": True, "why": None, "company": cid,
                "companies": _company_list(world)}
    cid = str(args.get("company", ""))
    comp = world.companies.get(cid)
    if comp is None:
        return {"ok": False, "why": "没有这家公司", "company": cid}
    if op == "update":
        for k in ("cash", "wage_per_hour", "restock_to"):
            if k in args:
                setattr(comp, k, float(args[k]))
        for k in ("open_minute", "close_minute"):
            if k in args:
                setattr(comp, k, int(args[k]))
        if args.get("name"):
            comp.name = str(args["name"])
        return {"ok": True, "why": None, "company": cid,
                "companies": _company_list(world)}
    if op == "hire":
        slots = max(0, int(args.get("slots", 0)))
        comp.hiring_slots = slots
        comp.hiring_open = slots > 0
        if "wage_per_hour" in args:
            comp.wage_per_hour = float(args["wage_per_hour"])
        return {"ok": True, "why": None, "company": cid,
                "companies": _company_list(world)}
    if op == "restock":
        shop = str(args.get("shop", "") or (comp.shops[0] if comp.shops else ""))
        item = str(args.get("item_type", ""))
        qty = int(args.get("qty", 0))
        res = purchase(world, comp, shop, item, qty)
        res["company"] = cid
        return res
    return {"ok": False, "why": "未知操作 %s" % op, "company": cid}


def _company_list(world) -> list:
    return [{"id": cid, "name": c.name, "cash": round(c.cash, 2),
             "owner": c.owner, "shops": list(c.shops),
             "open_minute": c.open_minute, "close_minute": c.close_minute,
             "wage_per_hour": c.wage_per_hour, "restock_to": c.restock_to,
             "hiring_open": c.hiring_open, "hiring_slots": c.hiring_slots,
             "staff": [{"npc": n, "wage": w} for n, w in c.staff]}
            for cid, c in sorted(world.companies.items())]


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
        await _send(ws, {"kind": "hello", **hello_payload(r)})
        await r.push()
    elif name == "query":
        data = do_query(r, args)
        await _send(ws, {"kind": "reply",
                         "type": "reply", "req_id": rid,
                         "ok": data is not None,
                         "data": data,
                         "why": None if data is not None else "not found"})
    elif name == "register_company":
        # 游戏内【注册公司】: 点商铺建筑 → 注册。没注册的店不能卖、不能招人。
        admin = _admin_company(r, "register", args)
        await _send(ws, {"kind": "reply", "type": "reply", "req_id": rid,
                         "ok": admin["ok"], "data": admin, "why": admin["why"]})
    elif name == "company_update":
        admin = _admin_company(r, "update", args)
        await _send(ws, {"kind": "reply", "type": "reply", "req_id": rid,
                         "ok": admin["ok"], "data": admin, "why": admin["why"]})
    elif name == "company_hire":
        admin = _admin_company(r, "hire", args)
        await _send(ws, {"kind": "reply", "type": "reply", "req_id": rid,
                         "ok": admin["ok"], "data": admin, "why": admin["why"]})
    elif name == "company_restock":
        admin = _admin_company(r, "restock", args)
        await _send(ws, {"kind": "reply", "type": "reply", "req_id": rid,
                         "ok": admin["ok"], "data": admin, "why": admin["why"]})
    elif name == "hire_now":
        from citysim.world.engine import hire_at
        hired = hire_at(r.world, r.systems, r.cfg)
        await _send(ws, {"kind": "reply", "type": "reply", "req_id": rid,
                         "ok": True, "data": {"hired": hired}, "why": None})
    elif name == "set_price":
        # 价格管理: 改一个在售实体的售价 —— 【只改世界真值】, 顾客要看见/听人才知道
        ent = r.world.entities.get(str(args.get("entity", "")))
        if ent is None:
            await _send(ws, {"kind": "reply", "type": "reply", "req_id": rid,
                             "ok": False, "data": None, "why": "没有这个物件"})
        else:
            ent.price = max(0.0, float(args.get("price", 0.0)))
            r.world.layout_location(ent.location_id)
            await _send(ws, {"kind": "reply", "type": "reply", "req_id": rid,
                             "ok": True,
                             "data": {"entity": ent.entity_id,
                                      "price": ent.price}, "why": None})
    elif name == "select":
        # 观察驱动: 客户端告知“我在看谁 / 看哪栋楼” → 这些每帧全量下发。
        r.focus_npc = str(args.get("npc", ""))
        r.focus_loc = str(args.get("location", ""))
    elif name == "ping":
        await _send(ws, {"kind": "pong", "type": "pong", "req_id": rid})
    else:
        # 以前是"静默忽略" → 前端点了没反应, 也不知道是自己发错了还是后端太旧。
        # 现在回一句, 前端会把 why 显示出来(最常见的两种: 后端进程没重启 / 名字拼错)。
        await _send(ws, {"kind": "reply", "type": "reply", "req_id": rid,
                         "ok": False, "data": None,
                         "why": "未知指令 %s（后端是否需要重启?）" % name})


@app.get("/")
async def _root() -> dict:
    """健康探针; 观察器 UI 由独立 Godot 项目 godot/ 提供(连接 /ws)。"""
    return {"service": "citysim", "status": "ok",
            "ws": "/ws", "observer": "run godot/ (Godot Editor)"}
