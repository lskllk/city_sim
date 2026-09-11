"""RingBuffer: 定长内存 + 游标增量读取。"""
from __future__ import annotations

from citysim.core.ring import RingBuffer


def test_append_len_and_total() -> None:
    r = RingBuffer(3)
    for i in range(3):
        r.append(i)
    assert len(r) == 3 and r.total == 3
    assert list(r) == [0, 1, 2]


def test_overflow_keeps_recent() -> None:
    r = RingBuffer(3)
    for i in range(6):
        r.append(i)
    assert len(r) == 3               # 定长
    assert list(r) == [3, 4, 5]      # 只留最近 3
    assert r.total == 6              # 累计单调


def test_drain_incremental() -> None:
    r = RingBuffer(10)
    r.append("a")
    r.append("b")
    evs, cur = r.drain(0)
    assert evs == ["a", "b"] and cur == 2
    # 无新事件
    evs2, cur2 = r.drain(cur)
    assert evs2 == [] and cur2 == 2
    r.append("c")
    evs3, cur3 = r.drain(cur2)
    assert evs3 == ["c"] and cur3 == 3


def test_drain_after_overflow_skips_lost() -> None:
    r = RingBuffer(3)
    for i in range(6):
        r.append(i)                  # 保留 3,4,5; total=6
    evs, cur = r.drain(0)            # 游标 0 早于最旧(3) → 只给保留部分
    assert evs == [3, 4, 5] and cur == 6


def test_clear() -> None:
    r = RingBuffer(4)
    r.append(1)
    r.clear()
    assert len(r) == 0 and r.total == 0 and not r
