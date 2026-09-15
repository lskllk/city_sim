"""schedule —— 计划表(当天有序 Intent 脚本)。纯数据/纯逻辑, 不 import world。

模型: 计划 = [(at_tick, Intent)] 有序序列。
- current  = 第一条未结束(pending/active)的条目。
- deadline = 下一条的 at_tick(当前条目的硬中止时刻)。
- 同刻多条按列表原顺序保留(sorted 稳定), 串行执行。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from citysim.core.types import Intent

PENDING = "pending"
ACTIVE = "active"
DONE = "done"
DROPPED = "dropped"
_LIVE = (PENDING, ACTIVE)


@dataclass
class PlanEntry:
    """一条计划: 某时刻直接下发的 Intent。

    daily=True 表示【每天重复】(上班这种长期承诺): 计划只在应聘/离职那天写一次,
    之后跨天自动顺延到同一时刻, 不需要谁去重写它。
    """
    entry_id: str
    at_tick: int
    intent: Intent
    status: str = PENDING
    daily: bool = False


class Schedule:
    """当天计划表(可变)。指针由条目 status 体现, 无隐藏索引。"""

    def __init__(self, entries: Sequence[PlanEntry] = ()) -> None:
        # sorted 稳定: 相同 at_tick 保持传入顺序(同刻串行)
        self._entries: list[PlanEntry] = sorted(entries, key=lambda e: e.at_tick)
        self._day: int = -1

    def roll_day(self, now_tick: int, ticks_per_day: int) -> bool:
        """跨天处理(每天第一次决策时调一次)。

        · daily 条目: 顺延到新的一天同一时刻, 状态回到 pending
          (这就是"计划写一次就不用再动"的落地处)
        · 一次性条目: 昨天没做完的直接丢弃(不跨天补做, 与 D3 同口径)
        返回是否真的跨天了。
        """
        if ticks_per_day <= 0:
            return False
        day = now_tick // ticks_per_day
        if self._day < 0:
            self._day = day
            return False
        if day == self._day:
            return False
        delta = (day - self._day) * ticks_per_day
        self._day = day
        for e in self._entries:
            if e.daily:
                e.at_tick += delta
                e.status = PENDING
            elif e.status in _LIVE and e.at_tick < day * ticks_per_day:
                e.status = DROPPED
        return True

    def entries(self) -> tuple[PlanEntry, ...]:
        return tuple(self._entries)

    def _live(self) -> list[PlanEntry]:
        return [e for e in self._entries if e.status in _LIVE]

    def current(self) -> PlanEntry | None:
        """当前条目(第一条未结束); 空则 None。"""
        live = self._live()
        return live[0] if live else None

    def peek_next(self) -> PlanEntry | None:
        """当前条目的下一条(未结束), 无则 None。"""
        live = self._live()
        return live[1] if len(live) > 1 else None

    def deadline(self) -> int | None:
        """当前条目的截止 tick = 下一条 at_tick; 无下一条/同刻(串行)则 None。

        同刻多条是同一组串行任务, 不能互相抢占; 只有严格更晚的下一条才构成截止。
        """
        cur = self.current()
        nxt = self.peek_next()
        if cur is None or nxt is None or nxt.at_tick <= cur.at_tick:
            return None
        return nxt.at_tick

    def commit(self) -> PlanEntry | None:
        """把当前条目置 active 并返回(开始执行)。"""
        e = self.current()
        if e is not None and e.status == PENDING:
            e.status = ACTIVE
        return e

    def complete(self) -> None:
        """当前条目自然完成。"""
        e = self.current()
        if e is not None:
            e.status = DONE

    def drop(self) -> None:
        """当前条目被跳过(截止/失败)。"""
        e = self.current()
        if e is not None:
            e.status = DROPPED

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
