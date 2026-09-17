"""npc/person/goal —— 目标: 何时重算 / 走完 / 放弃。

决策这件事分两半, 这里是【有状态】的那半:
  · 何时重算 —— 手上有 committed goal 就做完再算, 只有空闲才重算;
    唯一能打断的是 PLAN(上班)。
  · 怎么走完 —— 一步步 _advance(), 到期/失败就 _abandon()。
纯打分(给定记忆+状态选一个 Intent)在 npc/brain/decide.py, 本文件不管。

我拥有的字段: _goal, _last_intent
我只读的字段: _home, _intake, _mem, _money, _perceived_loc, _personality, _places, _schedule, _signals, _travel_costs, _work
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import zlib
from dataclasses import dataclass
from citysim.core.types import (Buy, Decision, Idle, Interact, MoveTo, Wander, intent_kind, intent_target)
from citysim.npc import brain
from citysim.npc.brain.memory_io import place_id

if TYPE_CHECKING:  # pragma: no cover
    # 只出现在类型标注里(运行时用不到) —— 别让清 import 的脚本删掉
    from citysim.core.config import SimConfig
    from citysim.core.types import Intent


@dataclass
class _Goal:
    """正在执行的【唯一】目标。

    —— 2026-09-14 删双轨 ——
    以前是 _reflex_goal / _plan_goal 两条轨 + 固定优先级抢占; 现在只有一个。
    source 只用来区分“谁在维持它”:
      "need" —— 需求(utility)驱动的, 做完再决策
      "plan" —— 日程/承诺驱动的, 到点会被下一条硬中止

    phase: to_dest=还没到目标地(异地), doing=已在目标地/正在交互。
    """
    source: str                               # "need" | "plan"
    intent: "Intent"
    phase: str = "to_dest"
    # —— 闲逛窗口(只对 source="fun" 有意义; 挂在 goal 上 → 随目标生灭) ——
    roam_until: int = 0
    roam_gain: float = 0.0


class GoalMixin:
    """见文件头(它拥有哪些字段)。"""


    def decide(self, cfg: "SimConfig", now_tick: int) -> Decision:
        """单轨决策: **需求(utility) > 日程(plan) > idle**。只读记忆+自身。

        开头先做一次跨天处理: daily 计划顺延到今天(上班写一次就不必再动)。

        节奏: **手上有事就做完再决策** —— 只有空闲时才每 tick 重算。
        唯一能打断当前动作的是 **PLAN(上班)**; 不再有迟滞/reflex 抢占。
        """
        self._schedule.roll_day(now_tick, cfg.ticks_per_day)
        # ★ 上班只在【上班开始那一刻】硬抢(不管在做什么 → 去上班)。
        #   其余时候守台是一个【committed goal】(时长 = 前台的 duration_ticks),
        #   —— 做完再决策: 需求只在每个 60t 边界被评估, 不会半路把守台打断。
        on_shift = self._on_shift(now_tick, cfg)
        plan = self._plan_intent() if on_shift else None
        minute = now_tick % max(1, cfg.ticks_per_day)
        just_started = (on_shift and bool(self._work)
                        and minute == int(self._work.get("open", -1)))
        if just_started and plan is not None:
            self._goal = _Goal("plan", plan)
            return self._record(Decision(plan, "plan"))
        while True:
            # 1) 手上有事 → 【做完再决策】: 不重算, 不被打断(只有上面的 PLAN 能)。
            #    空闲时才每 tick 决策。
            if self._goal is not None:
                # 日程条目的窗口到期(下一条已到点) → 中止当前条目, 推进计划
                if self._goal.source == "plan":
                    dl = self._schedule.deadline()
                    if dl is not None and now_tick >= dl:
                        self._schedule.drop()
                        self._goal = None
                        continue
                d = self._advance(self._goal, cfg, now_tick)
                if d is not None:
                    return self._record(d)
                continue

            # 2) 空闲 → 看需求。
            cand, _eff = self._intent_scored(cfg, now_tick)
            # 在班 + 需求不急(都 >= floor) → 不许用需求顶掉工作, 直接去守台
            if cand is not None and not (plan is not None
                                         and not self._need_to_leave_work(cfg)):
                self._goal = _Goal("need", cand)
                self._queue_intent_speech(now_tick, cand)   # 语义层: “我去买点吃的”
                continue

            # 3) 没事可做。
            #    ★ 在班但没需求可做 → 回岗守台(绝不掉 idle)。
            #    起一个 committed goal: 做完这个前台时长(60t) 再决策。
            if plan is not None:
                self._goal = _Goal("plan", plan)
                return self._record(Decision(plan, "plan"))
            #    hp 见底时【不给日程】: 计划暂时挂起(不提交也不丢弃),
            #    等 hp 回来再接着走 —— 否则会“放弃→重新选中→再放弃”转圈。
            if self._hp_low(cfg):
                return self._record(Decision(Idle(), "idle"))
            e = self._schedule.current()
            if e is None or now_tick < e.at_tick:
                return self._idle_or_wander(cfg, now_tick)
            # D3: 这条的窗口已经过去了 → 跳过, 不补做。
            # 窗口边界与 Schedule.deadline() 同一口径: **严格更晚**的下一条才构成截止;
            # 同刻多条是同一组串行任务(如 MoveTo + Interact), 不能互相跳掉。
            nxt = self._schedule.peek_next()
            if (nxt is not None and nxt.at_tick > e.at_tick
                    and nxt.at_tick <= now_tick):
                self._schedule.drop()
                continue
            self._schedule.commit()
            self._goal = _Goal("plan", e.intent)
            continue


    def _intent_scored(self, cfg: "SimConfig",
                       now_tick: int) -> "tuple[Intent | None, float]":
        """当前最想做的事 + 它的得分(Idle → (None, 0.0))。

        只在【空闲】时调 —— 手上有事就做完再决策, 不重算。
        """
        # 在班 → 把“工位 + 离岗代价(旷工扣日薪)”交给打分器。
        # 离岗 = 离开公司地点; 手边的货(located==shop)不算。
        workplace, leave_cost = "", 0.0
        if self._work and self._on_shift(now_tick, cfg):
            workplace = str(self._work.get("shop", ""))
            hours = max(0.0, float(self._work.get("close", 0))
                        - float(self._work.get("open", 0))) / 60.0
            leave_cost = hours * float(self._work.get("wage", 0.0))
        intent, eff = brain.decide_scored(
            self._signals, self._personality, self._mem,
            self._perceived_loc, cfg, now_tick, self.person_id,
            self._travel_costs or None, self._money, self._home,
            workplace=workplace, leave_cost=leave_cost)
        return (None if isinstance(intent, Idle) else intent), eff


    def _idle_or_wander(self, cfg: "SimConfig", now_tick: int) -> Decision:
        """真没事干了: fun 低 → 闲逛(最低优先级); 否则 idle。

        闲逛 = 一个 **committed goal** (source="fun"):
          · 先挑一个【随机建筑】走过去(路上 = 赶路 move);
          · 到了才开逛(闲逛 wander); 逛满 roam_ticks 收工。
        因为占着 _goal, 期间决策冷却(不重算需求)。
        """
        if self._signals.get("fun", 1.0) < cfg.fun_seek_below:
            dest = self._wander_dest(cfg, now_tick)
            if dest:
                self._goal = _Goal("fun", Wander(dest))
                return self._record(Decision(Wander(dest), "fun"))
        return self._record(Decision(Idle(), "idle"))


    def _wander_dest(self, cfg: "SimConfig", now_tick: int) -> str:
        """选一个闲逛目的地 —— 按【想去程度】加权随机抽一个(不是取最大)。

        候选 = 注入的 `_places` 里【非家】且【非当前所在地】(要真的走过去)。
        全用纯数据(记忆 + 地点表 + 距离矩阵), 不查 world。

        ★ 为什么不均匀随机: 得让"没什么东西的地方"少去、"有料的地方"多去。
          写法是"按权重抽"而不是"取最高分" —— 保留逛街的随性感,
          也让认知相同的 NPC 不会全挤到同一个地方(还有下面那道个人抖动)。
        """
        here = self._perceived_loc
        cands = [loc for loc in self._places
                 if loc and loc != self._home and loc != here]
        if not cands:                                  # 只剩家了 → 家外任意一个
            cands = [loc for loc in self._places if loc and loc != self._home]
        if not cands:
            return ""
        weights = [self._roam_draw(cfg, here, loc) for loc in cands]
        total = sum(weights)
        if total <= 0.0:                               # 全 0(不该发生) → 退化成均匀
            weights = [1.0] * len(cands)
            total = float(len(cands))
        bucket = now_tick // max(1, int(cfg.fun_roam_ticks))
        r = (zlib.crc32(f"{self.person_id}|{bucket}".encode("utf-8")) % 10_000)
        target = (r / 10_000.0) * total
        acc = 0.0
        for loc, w in zip(cands, weights):
            acc += w
            if target < acc:
                return loc
        return cands[-1]

    def _roam_draw(self, cfg: "SimConfig", here: str, loc: str) -> float:
        """「这地方值不值得去」—— 三个信号相加, 再乘距离与个人抖动。

            draw = (没去过 ? 乐观初值 : visited_base) + rich_a×这儿的【东西数】
                   + gain_b×上次收获
              · 没去过 → 乐观初值(≈"值一次白跑") → 每个地方至少会被逛一次
              · "东西多" → 行数多 → 常去
              · "上次拿到很多信息" → attrs["gain"] 高 → 后面更想去
            去过的空地方: 乐观初值没了, 只剩 1(地点行本身) + 0 → 权重很低,
            于是"几乎不再去" —— 直到它也被人忘掉(地点行被删) → 又变回"没去过"。

        距离因子(轻) + 个人抖动(稳定哈希, 人人不同 → 不扎堆)。
        """
        # 只数【东西】—— 地点行(afford="")不算, 否则空地方也至少 1 行
        rows = sum(1 for r in self._mem.items()
                   if r.located == loc and r.afford)
        prow = self._mem.get(place_id(loc))
        draw = float(cfg.fun_rich_a) * rows
        if prow is None:
            draw += float(cfg.fun_optimistic)          # 没去过 → 鼓励去一次
        else:
            draw += float(cfg.fun_visited_base)        # 去过就有一点底(不是永不再去)
            draw += float(cfg.fun_gain_b) * float(
                (prow.attrs or {}).get("gain", 0.0))
        ticks = 0
        if self._travel_costs and here and loc:
            key = "%s|%s" % (here, loc) if here <= loc else "%s|%s" % (loc, here)
            ticks = int(self._travel_costs.get(key, 0))
        near = 1.0 / (1.0 + float(cfg.fun_near_lambda) * ticks)
        jit = (zlib.crc32(("%s|%s" % (self.person_id, loc)).encode("utf-8"))
               % 1000) / 1000.0
        return max(0.0, draw) * near * (0.75 + jit / 2)  # 抖动 0.75..1.25"""


    def _plan_intent(self) -> "Intent | None":
        """班次内该做的那件事: 还没到店里 → 去店里; 到了 → 站上台。

        ★ 上班【不在计划表里】—— 它由 `_work`(应聘时绑定的公司/店/工位/班次)
          直接派生。计划表只装作者写的脚本(场景的 `plans` 段)。
        """
        shop = str(self._work.get("shop", ""))
        station = str(self._work.get("station", ""))
        if not station:
            return None
        if shop and self._perceived_loc != shop:
            return MoveTo(dest=shop)
        return Interact(target_id=station)


    def _need_to_leave_work(self, cfg: "SimConfig") -> bool:
        """强需求掉到线下 → 允许从工作台上下来。

        只认吃饭/上厕所/困到不行这三种 —— 用户原话:
        "如果很想上厕所 或者饿了要吃饭 才从工作下来吃饭"。
        """
        floor = float(getattr(cfg, "work_leave_floor", 0.35))
        return any(float(self._signals.get(s, 1.0)) < floor
                   for s in ("hunger", "energy", "bladder"))


    def _hp_low(self, cfg: "SimConfig") -> bool:
        """命快没了 → 日程失去拉力(先顾命)。"""
        return self._signals.get("hp", 1.0) < cfg.hp_override


    def _advance(self, goal: "_Goal", cfg: "SimConfig",
                 now_tick: int) -> "Decision | None":
        """推进一个 goal: 异地先 MoveTo; 到达/无需移动后返回实际 Intent。

        闲逛额外需要 cfg/now_tick —— 它要靠"窗口到期"收工并结算(见上)。
        """
        if goal.source == "fun":
            # 闲逛两段: 赶路 → 到了开一段【观察窗口】 → 窗口到期收工。
            # 判断全靠 NPC 自己(位置 + 窗口), 不查 world、不靠 Grant。
            if self._perceived_loc != goal.intent.dest:
                return Decision(goal.intent, goal.source)     # 还在赶路
            if goal.roam_until == 0:                          # 刚到 → 开窗口
                goal.roam_until = now_tick + int(cfg.fun_roam_ticks)
            if now_tick < goal.roam_until:                    # 逛着呢
                return Decision(goal.intent, goal.source)
            self._finish_roam(goal, cfg, now_tick)            # 到期 → 结算
            self._finish_goal(goal)
            return None
        if goal.phase == "to_dest":
            dest = self._dest_for(goal.intent)
            if dest and self._perceived_loc != dest:
                # ★ 把选中时的 trace 一起带上 —— 否则 "去某地" 这一步
                # 在 Inspector/事件日志里【看不到为什么选它】(ranked 是空的),
                # 调参时只能干瞪眼(用户就踩过: 分不清是打分选的还是计划推的)。
                return Decision(MoveTo(dest=dest,
                                       trace=getattr(goal.intent, "trace", None)),
                                goal.source)
            if isinstance(goal.intent, MoveTo):
                self._finish_goal(goal)            # 纯移动: 到达即完成
                return None
            goal.phase = "doing"
        return Decision(goal.intent, goal.source)


    def _dest_for(self, intent: "Intent") -> str:
        if isinstance(intent, MoveTo):
            return intent.dest
        if isinstance(intent, Interact):
            row = self._mem.get(intent.target_id)
            return row.located if row is not None else ""
        if isinstance(intent, Buy):
            row = self._mem.get(intent.item_id)
            return row.located if row is not None else ""
        return ""


    def _finish_goal(self, goal: "_Goal") -> None:
        if goal.source == "plan":
            self._schedule.complete()
        if self._goal is goal:
            self._goal = None


    def _record(self, decision: Decision) -> Decision:
        self._last_intent = decision.intent
        return decision


    def _abandon(self) -> None:
        """放弃当前目标: 计划来源的把该条标 dropped, 只清目标。"""
        if self._goal is not None and self._goal.source == "plan":
            self._schedule.drop()
        self._goal = None


    def plan_snapshot(self, now_tick: int = 0,
                      ticks_per_day: int = 1440) -> list[dict]:
        """观测: 计划表只读快照(供前端时间线渲染)。

        含两部分:
          · 真实日程表(_schedule, 计划器/脚本写的);
          · 【上班】—— 从 self._work 派生, 不入计划表。
            这样 0:00 计划器 set_plan([]) 冲不掉它(以前就被冲掉 → 时间线空)。
        """
        out = [{
            "id": e.entry_id, "at_tick": e.at_tick, "status": e.status,
            "intent": intent_kind(e.intent),
            "target": intent_target(e.intent) or "",
        } for e in self._schedule.entries()]
        if self._work and self._work.get("station"):
            minute = int(now_tick) % max(1, int(ticks_per_day))
            day_start = int(now_tick) - minute
            open_m = int(self._work.get("open", 0))
            close_m = int(self._work.get("close", 1440))
            on = open_m <= minute < close_m
            at = day_start + open_m
            out.append({"id": "work_go", "at_tick": at,
                        "status": "done" if on else "pending",
                        "intent": "move_to",
                        "target": str(self._work.get("shop", ""))})
            out.append({"id": "work_stand", "at_tick": at,
                        "status": "active" if on else "pending",
                        "intent": "interact",
                        "target": str(self._work.get("station", ""))})
            # 下班(以前只画了上班, 没有下班节点)
            out.append({"id": "work_off", "at_tick": day_start + close_m,
                        "status": "done" if minute >= close_m else "pending",
                        "intent": "move_to", "target": self._home or ""})
        return out
