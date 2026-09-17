"""EventBus —— 世界广播"刚刚发生了什么"(观测流)。

订阅方(subscribe_log): 前端事件日志(`ui_events`)、`narrate.py`、回放、测试断言。

`payload["audience"]` = 这条事件还【跟谁有关】(缺省 = subject_id; 目前只有
rumor 的 `told` 会填成听者)。用它的只有观察器 —— 界面上看"这个人最近经历了什么"
时, 除了 subject 是自己, 还要算上"别人讲给我听"。

★ 以前它还有第二半 —— 【NPC 信箱】(publish 按 audience 投进各 NPC 的 deque,
NPC 每次 perceive 取走变成 `Percept.events`)。但 NPC 只真正消费其中一种事件
(`bought` 的送货细节), 所以那个口已经并进 `Person.notify(Bought(...))` 了。
现在 world → NPC 只有 notify / assign 两个口, 这里只剩广播。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    tick: int
    kind: str
    subject_id: str                       # 主要相关方(npc_id 或 entity_id)
    payload: Mapping[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[Callable[[Event], None]] = []
        self.seq: int = 0                 # 事件 id 序号(保证确定性)

    # --- 发布 ---------------------------------------------------------
    def make(self, tick: int, kind: str, subject_id: str,
             payload: Mapping[str, Any] | None = None) -> Event:
        self.seq += 1
        return Event(event_id=f"ev{self.seq}", tick=tick, kind=kind,
                     subject_id=subject_id, payload=dict(payload or {}))

    def publish(self, ev: Event) -> None:
        """广播给观测方(前端事件日志/回放/工具/测试)。"""
        for fn in self._listeners:
            fn(ev)

    def subscribe_log(self, fn: Callable[[Event], None]) -> None:
        self._listeners.append(fn)
