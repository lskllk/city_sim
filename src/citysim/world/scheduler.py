"""时间轮 TimingWheel —— 每 NPC 单一下次重评点调度。

正确性语义: 每人只保留一个 next-due(新 schedule 覆盖旧档), 到期 pop 时按
npc_id 排序保证确定性。overflow(delay 超长)无需二次入轮, 直接以绝对 due 留存;
内部用 slot 桶近似设计 3.6 的轮式结构。与 plan 一致: delay 必 >= 1。
"""
from __future__ import annotations


class TimingWheel:
    def __init__(self, horizon: int = 4096) -> None:
        self.horizon = horizon
        self.current = 0
        self._by_npc: dict[str, int] = {}          # npc_id -> 绝对 due tick
        self._slots: list[list[str]] = [[] for _ in range(horizon)]

    def schedule(self, npc_id: str, delay_ticks: int, now: int | None = None) -> None:
        """排 npc 在 delay tick 后重评; 覆盖该 npc 已有的旧档。

        now 缺省用 self.current(上次 pop 推进处); 交互链推进时调用方应显式传
        当前 tick 以免基准过期。
        """
        delay = max(1, int(delay_ticks))
        due = (self.current if now is None else now) + delay
        old = self._by_npc.pop(npc_id, None)
        if old is not None:
            slot = old % self.horizon
            bucket = self._slots[slot]
            if npc_id in bucket:
                bucket.remove(npc_id)
        self._by_npc[npc_id] = due
        self._slots[due % self.horizon].append(npc_id)

    def pop_due(self, now_tick: int) -> list[str]:
        """推进到 now_tick, 返回此刻到点的 npc_id(排序, 确定性)。"""
        self.current = now_tick
        # 轮槽到期
        slot = now_tick % self.horizon
        fired: list[str] = []
        for npc_id in self._slots[slot]:
            if self._by_npc.get(npc_id, -1) <= now_tick:
                fired.append(npc_id)
                del self._by_npc[npc_id]
        self._slots[slot] = [n for n in self._slots[slot]
                             if n not in fired]
        # overflow: 绝对 due <= now 的兜底
        for npc_id, due in list(self._by_npc.items()):
            if due <= now_tick:
                fired.append(npc_id)
                del self._by_npc[npc_id]
        fired.sort()
        return fired

    def has(self, npc_id: str) -> bool:
        return npc_id in self._by_npc

    def next_due(self, npc_id: str) -> int | None:
        return self._by_npc.get(npc_id)
