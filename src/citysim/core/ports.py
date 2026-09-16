"""ports —— world ↔ npc 的【主动拉】契约(中立层, 两端都能 import)。

不变量(违反就失去意义):
  1. 暴露【动词】, 不暴露数据句柄 —— 绝不给 NPC `World` / `Entity`。
  2. 一次 request 在 world 内原子(校验 → 改账 → 发事件, 不可被打断)。
  3. NPC 只对【已存在的】世界对象发动词, 不能断言事实 / 创建物品
     (造物只能走 world 自己的配方)。
  4. 响应是可序列化的纯数据 —— 回放与测试唯一能钉的东西。

本模块不 import `citysim.world`, 也不 import `citysim.npc`(契约层)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from citysim.core.types import Percept


@dataclass(frozen=True, slots=True)
class Ack:
    """【动作类】请求的回执(不需要把"一份可用之物"交出来时用它)。"""
    ok: bool = True
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Deny:
    """请求被世界否决(存在性 / 权属 / 资源 / 权限)。"""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Grant:
    """世界签发的【一份可用之物】= 纯数据 + 不透明持有凭证。

    ★ 它**不是所有权本身**: 东西仍在世界账本里(held_by=pid)。`handle` 只是校验
      用的 token, NPC 伪造不了。
    """
    handle: str
    entity_id: str
    signal: str = ""                       # 作用在哪个信号("hunger"/"energy"/…)
    value: float = 0.0                     # 总共补多少
    duration_ticks: int = 1                # 分多少 tick 补
    mode: str = "add"                      # "add"=逐 tick 加 / "freeze"=期间冻结
    pending: tuple[Mapping[str, Any], ...] = ()   # on_start 编译结果(结构化, 不用 op 名)
    on_done: tuple[Mapping[str, Any], ...] = ()   # on_complete 编译结果
    tags: tuple[str, ...] = ()             # 供 NPC 判断用途(edible/sleepable/toilet)


class WorldPort(Protocol):
    """NPC 主动使用的世界能力接口。

    实现体在 world 侧(`world/port.py`); 权限与仲裁都在实现里, NPC 只能"请求"。
    """

    def observe(self, pid: str) -> Percept:
        """主动观察: 返回该 NPC 当前可感知的只读快照(含信箱事件)。"""
        ...

    def try_move(self, pid: str, dest: str) -> Ack:
        """请求移动(异地); 世界做 entry_check / 路线 / 预占。"""
        ...

    def try_take(self, pid: str, entity_id: str) -> "Grant | Deny":
        """请求【免费使用】一个已知实体(吃/睡/上厕所/自家物品)。"""
        ...

    def try_buy(self, pid: str, item_id: str, qty: int) -> Ack:
        """请求购买。★ 异步: `ok=True` 只表示【已入队】, 成交另走事件。"""
        ...

    def release(self, pid: str, handle: str) -> Ack:
        """归还/放弃一个持有(不消耗): 还回容器或丢下。"""
        ...

    def consume(self, pid: str, handle: str) -> Ack:
        """消耗掉一个持有(吃完/用完): 世界据此回收实体。"""
        ...
