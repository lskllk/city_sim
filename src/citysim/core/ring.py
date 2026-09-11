"""core/ring —— 固定容量环形缓冲(定长内存)。

只保留最近 `capacity` 条; 带单调 `total` 序号, 支持"从游标增量取"。
用于 Systems.ui_events, 避免长跑时事件列表无限增长。
"""
from __future__ import annotations

from collections import deque
from itertools import islice
from typing import Any, Iterator


class RingBuffer:
    __slots__ = ("capacity", "_buf", "_total")

    def __init__(self, capacity: int = 8192) -> None:
        self.capacity = max(1, int(capacity))
        self._buf: deque = deque(maxlen=self.capacity)
        self._total = 0

    def append(self, item: Any) -> None:
        self._buf.append(item)
        self._total += 1

    @property
    def total(self) -> int:
        """累计 append 过的条数(单调递增; 作为游标基准)。"""
        return self._total

    def drain(self, cursor: int) -> tuple[list, int]:
        """取游标之后仍保留的条目, 返回 (items, new_cursor=total)。

        若游标早于最旧保留项(发生过溢出), 只返回仍保留的部分(丢失部分跳过)。
        """
        oldest = self._total - len(self._buf)
        lo = max(int(cursor), oldest)
        skip = lo - oldest
        return list(islice(self._buf, skip, None)), self._total

    def clear(self) -> None:
        self._buf.clear()
        self._total = 0

    def __len__(self) -> int:
        return len(self._buf)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._buf)

    def __reversed__(self) -> Iterator[Any]:
        return reversed(self._buf)

    def __getitem__(self, i):
        return self._buf[i]

    def __bool__(self) -> bool:
        return len(self._buf) > 0

    def __repr__(self) -> str:  # pragma: no cover
        return f"RingBuffer({len(self._buf)}/{self.capacity}, total={self._total})"
