"""soak —— 7 天日行为统计追踪器(供 soak_report 与 test_behavior_soak 共用)。

按 testM0~M3.md 第二步断言口径统计:
  - 每人每天 吃/喝/如厕 次数; 睡眠段(次数 + 时长)
  - 信号卡 0 的最长连续 tick
  - 连续 idle 且有信号<0.3 的最长 tick
  - intent_failed 占比
  - 60 tick 窗口内同一目标重复 claim(抖动)报警
"""
from __future__ import annotations

THRESH_SIGNAL = 0.3      # "有需求却不行动"判据
THRESH_STUCK = 300       # 卡 0 报警
THRESH_IDLE_NEED = 120   # 2 小时(tick=1 分钟)
THRESH_FAIL_RATIO = 0.15
REPEAT_WINDOW = 60
REPEAT_MAX = 5

NEED_SIGNALS = ("energy", "hunger", "thirst", "bladder")


def parse_decisions(log_lines: list[str]):
    """从回放日志解析 decide 次数与 (pid->target->tick 列表)。"""
    decisions = 0
    claims: dict[str, dict[str, list[int]]] = {}
    for line in log_lines:
        if not line.startswith("D\t"):
            continue
        parts = line.split("\t")
        tick, pid, kind, target = int(parts[1]), parts[2], parts[3], parts[4]
        decisions += 1
        if kind == "interact" and target:
            claims.setdefault(pid, {}).setdefault(target, []).append(tick)
    return decisions, claims


class SoakTracker:
    def __init__(self, world, systems) -> None:
        self.world = world
        self.systems = systems
        self.day = 0
        self.eat: dict[str, dict[int, int]] = {}
        self.drink: dict[str, dict[int, int]] = {}
        self.toilet: dict[str, dict[int, int]] = {}
        self.sleep_segs: dict[str, list[tuple[int, int]]] = {}
        self._sleep_on: dict[str, int] = {}
        self.max_stuck: dict[str, dict[str, int]] = {}
        self._stuck_run: dict[str, dict[str, int]] = {}
        self.max_idle_need: dict[str, tuple[int, str]] = {}
        self._idle_run: dict[str, tuple[int, str]] = {}
        self.failed = 0
        self.decisions = 0
        self.claims: dict[str, dict[str, list[int]]] = {}
        self._completed: list[tuple[int, str, str]] = []

        def _on_ev(ev):
            if ev.kind == "interaction_done":
                self._completed.append((ev.tick, ev.subject_id,
                                        ev.payload.get("entity", "")))
            elif ev.kind == "intent_failed":
                self.failed += 1

        world.bus.subscribe_log(_on_ev)

    # --- 每 tick 调用(run_tick 之后) --------------------------------
    def observe(self) -> None:
        day = self.world.clock_tick // 1440 + 1
        for pid, npc in self.world.npcs.items():
            for s in NEED_SIGNALS:
                run = self._stuck_run.setdefault(pid, {}).get(s, 0)
                run = run + 1 if npc.signals.get(s, 1.0) <= 0.0 else 0
                self._stuck_run[pid][s] = run
                best = self.max_stuck.setdefault(pid, {}).get(s, 0)
                self.max_stuck[pid][s] = max(best, run)
            asleep = self._asleep(pid)
            active = pid in self.systems.interaction.active
            need = min(npc.signals.get(s, 1.0) for s in NEED_SIGNALS)
            if not asleep and not active and need < THRESH_SIGNAL:
                r, who = self._idle_run.get(pid, (0, ""))
                s_min = min(NEED_SIGNALS,
                            key=lambda s: npc.signals.get(s, 1.0))
                self._idle_run[pid] = (r + 1, s_min)
                best, _ = self.max_idle_need.get(pid, (0, ""))
                self.max_idle_need[pid] = (max(best, r + 1), s_min)
            else:
                self._idle_run[pid] = (0, "")
            if asleep and pid not in self._sleep_on:
                self._sleep_on[pid] = self.world.clock_tick
            elif not asleep and pid in self._sleep_on:
                start = self._sleep_on.pop(pid)
                self.sleep_segs.setdefault(pid, []).append(
                    (start, self.world.clock_tick))
        done = self._completed
        self._completed = []
        for (tick, pid, eid) in done:
            d = tick // 1440 + 1
            ent = self.world.entities.get(eid)
            tags = ent.tags if ent else set()
            if "edible" in tags:
                self.eat.setdefault(pid, {}).setdefault(d, 0)
                self.eat[pid][d] += 1
            elif "drink" in tags:
                self.drink.setdefault(pid, {}).setdefault(d, 0)
                self.drink[pid][d] += 1
            if "toilet" in tags:
                self.toilet.setdefault(pid, {}).setdefault(d, 0)
                self.toilet[pid][d] += 1
        self.day = day

    def load_decisions(self, log_lines: list[str]) -> None:
        self.decisions, self.claims = parse_decisions(log_lines)

    def _asleep(self, pid: str) -> bool:
        act = self.systems.interaction.active.get(pid)
        if act is None:
            return False
        ent = self.world.entities.get(act.entity_id)
        return ent is not None and "sleepable" in ent.tags

    def sleep_durations(self, pid: str) -> list[tuple[int, int]]:
        return self.sleep_segs.get(pid, [])

    def repeat_claim_violations(self) -> list[str]:
        """60 tick 窗口内同一目标 claim >5 次 → 抖动报警。"""
        out = []
        for pid, targets in self.claims.items():
            for tgt, ticks in targets.items():
                ticks.sort()
                for i in range(len(ticks)):
                    j = i
                    while (j < len(ticks)
                           and ticks[j] - ticks[i] <= REPEAT_WINDOW):
                        j += 1
                    if j - i > REPEAT_MAX:
                        out.append(f"{pid} 60t内重复claim {tgt} "
                                   f"{j - i}次 @tick{ticks[i]}")
                        break
        return out

    def failure_ratio(self) -> float:
        return self.failed / max(1, self.decisions)
