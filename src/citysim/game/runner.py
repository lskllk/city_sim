"""runner —— `SimRunner`: **谁拥有世界, 以及 60Hz 推什么**。

单实例、单线程(asyncio)拥有 world; 一切读写都在事件循环内(design 第三节
铁律: 推进由 runner 独占)。

这个模块管两件事:

**① 推进** —— `advance(n)` 是唯一的 tick 入口; `loop()` 是 60Hz 的节拍器,
按档位算出这一轮该推几个 tick, 并给推进设**时间预算**(留出时间做推送)。

**② 推送** —— `push()` 算"这一帧到底该发什么"。它的省法叫**观察驱动**:

    · 渲染状态没变的 NPC 不发(在家静坐的人签名恒定)
    · 物品几乎不变 → 变了才发
    · 客户端正在看的(选中的那个人 / 那栋楼里的人) → 每帧发, 轮转分批
    · 消失的 id 单独发 tombstone(客户端是合并式更新, 必须显式告诉它删)

60Hz 之所以安全, 全靠 ①: 静止时一帧 0 个 NPC(实测 ~6.6KB/帧)。**若退回
全量推送, 60Hz × 百人快照会拖成长超时断线。**

它【不管玩法】: 经营动作在 `actions.py`, 指令表在 `commands.py`。

也【不管传输】: 本模块不 import fastapi(`WebSocket` 只在类型标注里), 所以
`import citysim.game.runner` 不需要 viz extra —— 脏计算与推进可以无头单测
(见 `tests/test_game_layer.py`)。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING

from citysim import api
from citysim.game import ROOT, lines
from citysim.game.clock import SPEED_TPS, real_tps

if TYPE_CHECKING:            # 只在类型标注里用 —— 本模块【不依赖 fastapi】
    from fastapi import WebSocket

# 用与旧 server.py 同名的 logger, 免得日志过滤配置失效。
log = logging.getLogger("citysim.server")

PUSH_HZ = 60          # 状态快照推送频率(与倍率无关)。
# 单个客户端的单条发送最长等待秒数。超时 → 【丢这一帧】(不断线):
# 快照是全量状态, 丢了下一帧会补齐; 断开只会引发客户端无限重连。
# 真正的断开/协议错误仍走 except → 清掉该客户端。
CLIENT_SEND_TIMEOUT = 1.5


class SimRunner:
    """单实例、单线程(asyncio)拥有 world; 所有读写都在事件循环里。"""

    def __init__(self) -> None:
        self.cfg = api.load_config(ROOT / "config" / "sim.toml")
        # 台词渲染器 —— **游戏层的资产**, 注入给内核的快照投影(见 push)。
        # 内核不知道“苹果”该说成什么话; 换语言 / 换语气 / 接 LLM 都换这里。
        self.render_line = lines.renderer_for(self.cfg)
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
        self._pushed_player: str = "\x00"     # 上次推送时的玩家化身（变了就强制推一帧）
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

    # ── 世界生命周期 ───────────────────────────────────────────────────
    def note_world_changed(self) -> None:
        """世界里发生了【不推进 tick】的写(注册公司/改参数/招聘/进货)→
        下一帧强制推一份快照。

        为什么必须显式叫: push() 在暂停且无事件/无脏 NPC 时会【跳过】
        (省空转)。注册公司恰好是这样: 不推进 tick、不产生事件, 于是前端
        永远收不到带新公司的快照 → 注册按钮不消失(实测 bug)。
        """
        self._pushed_tick = None

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
            self.world, self.systems, self.rng_pool = api.build_scenario(
                **self.params)
            self.build_error = ""
        except Exception as exc:      # noqa: BLE001
            # 【不闪退】: 场景坏了也要能起服务, 把原因告诉前端。
            # 以前这里是裸调用 → 删了个场景文件, 后端 import 阶段就死,
            # 前端只看到断开。
            import traceback
            self.build_error = "%s: %s" % (type(exc).__name__, exc)
            log.error("场景加载失败, 用空世界启动: %s", self.build_error)
            traceback.print_exc()
            self.world = api.World()
            self.systems = api.make_systems(log=True)
            self.rng_pool = {}
        api.attach_replay(self.world, self.systems)   # log_lines 承载 D/E 行
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

    # ── 观察集: 客户端在看谁 ────────────────────────────────────────────
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

    # ── 脏计算: 这一帧该发谁 ────────────────────────────────────────────
    def _ent_sig_of(self, e) -> tuple:
        # ★ 不再包含位置：实体本来就没有坐标了（见 world.model.Entity）
        return (e.location_id, e.stock, round(float(e.price), 4), e.owner,
                tuple(sorted(e.claimants)), bool(e.persist_empty))

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

    # ── 推进 ────────────────────────────────────────────────────────────
    def advance(self, n: int) -> None:
        # 气泡只在【我关注的地方】冒: 把观察集喂给 engine(空集 = 一个都不冒)
        self.systems.bubble_watch = self.watch_set()
        for _ in range(n):
            api.run_tick(self.world, self.systems, self.cfg, self.rng_pool)

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
            # 墙钟慢一半, 而且客户端的本地时钟立刻超到前面去。
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

    # ── 推送 ────────────────────────────────────────────────────────────
    async def push(self) -> None:
        if not self.clients:
            self.drain_log()          # 无人观看也要推进游标, 防积压
            return
        evs = self.drain_log()
        tick = self.world.clock_tick
        dirty = self._dirty_npcs()
        # 被选中的那个: 每帧在观察集里(信号实时), 但详情每 rich_every 帧才带一次。
        # ★ 必须在下面那个早退检查【之前】算 —— 否则暂停时点了人,
        #   焦点还没进 dirty 就先 return 了, 前端永远等不到那份记忆。
        #   (点人看穿他是这个 demo 的核心动作, 而默认就是暂停开局。)
        rich: set[str] = set()
        watching = self.focus_npc in self.world.npcs
        if watching:
            dirty.add(self.focus_npc)
            if self._push_seq % max(1, self.rich_every) == 0:
                rich.add(self.focus_npc)
        # ★ 玩家操控谁 —— 变了就必须推一帧。
        #   player 是快照顶层字段，但早退检查在下面；不把它算进"有变化"，
        #   暂停时点「接管」前端会永远等不到（跟上面 focus 那个坑一模一样）。
        player = str(getattr(self.systems, "player", ""))
        if player != self._pushed_player:
            self._pushed_player = player
            self._pushed_tick = None        # 强制推一帧
        # 状态未变(暂停/无人移动且无事件) → 不重复推: 省掉暂停时的全量空转。
        # 新客户端接入/重置/步进 会把 _pushed_tick 置 None 或推进 tick。
        if self._pushed_tick == tick and not evs and not dirty and not watching:
            return
        self._pushed_tick = tick
        self._push_seq += 1
        dirty_ents = self._dirty_entities()
        # 消失的 id(死亡/消耗): 客户端是合并式更新, 必须显式告诉它删
        cur_npcs = set(self.world.npcs)
        cur_ents = set(self.world.entities)
        gone = {"npcs": sorted(self._seen_npcs - cur_npcs),
                "entities": sorted(self._seen_entities - cur_ents)}
        self._seen_npcs = cur_npcs
        self._seen_entities = cur_ents
        # Snapshot 与 Event 走独立消息: snapshot 不内嵌事件流
        # 观察驱动: 只带 dirty 的 NPC(在家不动的座位不上车)
        msgs = [json.dumps(api.envelope(
            "snapshot",
            api.build_snapshot(self.world, self.systems, self.cfg,
                               self.speed, [], tps=real_tps(self.speed),
                               only=dirty, gone=gone, rich=rich,
                               entities_only=dirty_ents,
                               render_line=self.render_line)),
            ensure_ascii=False)]
        msgs += [json.dumps(api.envelope("event", api.encode_event(ev)),
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
