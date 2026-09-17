"""EventBus —— 事件发布与 NPC 信箱投递。

路由规则(定死): publish 按 payload.get(\"audience\", [subject_id]) 投递到各
NPC 信箱(deque, maxlen=64); 另可挂 subscribe_log 监听(调试/录制回放)。
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from citysim.core.types import EventView


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    tick: int
    kind: str
    subject_id: str                       # 主要相关方(npc_id 或 entity_id)
    payload: Mapping[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._mailboxes: dict[str, deque[Event]] = {}
        self._listeners: list[Callable[[Event], None]] = []
        self.seq: int = 0                 # 事件 id 序号(保证确定性)

    # --- 发布 ---------------------------------------------------------
    def make(self, tick: int, kind: str, subject_id: str,
             payload: Mapping[str, Any] | None = None) -> Event:
        self.seq += 1
        return Event(event_id=f"ev{self.seq}", tick=tick, kind=kind,
                     subject_id=subject_id, payload=dict(payload or {}))

    def publish(self, ev: Event) -> None:
        audience = ev.payload.get("audience", (ev.subject_id,))
        if isinstance(audience, str):
            audience = (audience,)
        for npc_id in audience:
            box = self._mailboxes.setdefault(str(npc_id), deque(maxlen=64))
            box.append(ev)
        for fn in self._listeners:
            fn(ev)

    def drain_for(self, npc_id: str) -> tuple[EventView, ...]:
        """取走并清空该 NPC 信箱, 转成不可变 EventView。"""
        box = self._mailboxes.pop(npc_id, None)
        if not box:
            return ()
        out = tuple(
            EventView(event_id=ev.event_id, tick=ev.tick, kind=ev.kind,
                      payload=dict(ev.payload))
            for ev in box
        )
        return out

    def subscribe_log(self, fn: Callable[[Event], None]) -> None:
        self._listeners.append(fn)
