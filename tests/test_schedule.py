"""TASK006: Schedule(计划表)纯逻辑单测。"""
from __future__ import annotations

from citysim.core.types import Interact, MoveTo
from citysim.npc.schedule import DONE, DROPPED, PlanEntry, Schedule


def _e(eid: str, at: int, dest: str = "x") -> PlanEntry:
    return PlanEntry(eid, at, MoveTo(dest=dest))


def test_sorted_by_at_tick_stable_for_ties() -> None:
    s = Schedule([_e("c", 9), _e("a", 1), _e("b", 9)])
    # 相同 at_tick 保持传入顺序(同刻串行)
    assert [e.entry_id for e in s.entries()] == ["a", "c", "b"]


def test_current_peek_deadline() -> None:
    s = Schedule([_e("a", 1), _e("b", 10), _e("c", 20)])
    assert s.current().entry_id == "a"
    assert s.peek_next().entry_id == "b"
    assert s.deadline() == 10                     # 当前条目截止 = 下一条 at_tick


def test_commit_complete_advance() -> None:
    s = Schedule([_e("a", 1), _e("b", 10)])
    assert s.commit().entry_id == "a"
    assert s.commit().entry_id == "a"             # 幂等
    s.complete()
    assert s.current().entry_id == "b"
    assert s.deadline() is None                   # 最后一条无截止


def test_drop_advances() -> None:
    s = Schedule([_e("a", 1), _e("b", 10)])
    s.drop()
    assert s.current().entry_id == "b"
    assert s.entries()[0].status == DROPPED


def test_deadline_none_for_same_tick_group() -> None:
    # 同刻多条 = 串行一组, 互相不构成截止
    s = Schedule([_e("a", 1), _e("b", 1), _e("c", 10)])
    assert s.deadline() is None          # a/b 同刻
    s.complete()
    assert s.deadline() == 10            # b 的下一条 c 严格更晚


def test_empty_schedule() -> None:
    s = Schedule()
    assert s.current() is None
    assert s.deadline() is None
    assert len(s) == 0


def test_intent_carried() -> None:
    it = Interact(target_id="food")
    s = Schedule([PlanEntry("a", 1, it)])
    assert s.current().intent is it
    assert s.commit().status != DONE
