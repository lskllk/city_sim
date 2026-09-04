"""M3 DoD: 时间轮 TimingWheel。"""
from __future__ import annotations

from citysim.world.scheduler import TimingWheel


def test_schedule_fires_after_delay() -> None:
    w = TimingWheel()
    w.schedule("a", 3, now=0)
    assert w.pop_due(1) == []
    assert w.pop_due(2) == []
    assert w.pop_due(3) == ["a"]
    assert w.pop_due(4) == []


def test_schedule_overwrites_previous() -> None:
    w = TimingWheel()
    w.schedule("a", 100, now=0)
    w.schedule("a", 5, now=0)   # 覆盖旧档
    assert w.pop_due(3) == []
    assert w.pop_due(5) == ["a"]
    assert w.pop_due(101) == []


def test_wheel_overflow() -> None:
    """delay 远超轮程(horizon)仍正确到期。"""
    w = TimingWheel(horizon=64)
    w.schedule("a", 10000, now=0)
    assert w.pop_due(9999) == []
    assert w.pop_due(10000) == ["a"]


def test_due_order_sorted_deterministic() -> None:
    w = TimingWheel()
    w.schedule("npc_b", 1, now=0)
    w.schedule("npc_a", 1, now=0)
    assert w.pop_due(1) == ["npc_a", "npc_b"]
