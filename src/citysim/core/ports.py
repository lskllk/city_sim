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

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from citysim.core.types import Percept


@dataclass(frozen=True, slots=True)
class Ack:
    """【动作类】请求的回执(不需要把"一份可用之物"交出来时用它)。"""
    ok: bool = True
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Deny:
    """请求被世界否决(存在性 / 权属 / 资源 / 权限)。

    `retry_ticks`: 给 NPC 的冷却提示(0 = 用默认)。世界不替 NPC 写记忆 ——
    它只把理由和提示交回去, NPC 自己 `on_failure`。
    """
    reason: str = ""
    retry_ticks: int = 0


@dataclass(frozen=True, slots=True)
class Grant:
    """世界签发的【一份可用之物】= 纯数据 + 不透明持有凭证。

    ★ 它**不是所有权本身**: 东西还在世界账本里, 【谁正在用它】由
      `InteractionSystem.active` 那本账表达 —— 不在实体上加字段(那会变成
      第二份真相)。`handle` 是去重/校验用的 token: NPC 侧靠它防止"同一份
      重复收", 世界侧收尾时对一遍(`finish` 校验 handle 才算数)。
    """
    handle: str
    entity_id: str
    name: str = ""                         # 这件东西叫什么(NPC 自报"我在吃苹果"用)
    signal: str = ""                       # 作用在哪个信号("hunger"/"energy"/…)
    value: float = 0.0                     # 总共补多少
    duration_ticks: int = 1                # 分多少 tick 补
    tags: tuple[str, ...] = ()             # 供 NPC 判断用途(edible/sleepable/toilet)


class WorldPort(Protocol):
    """NPC 主动使用的世界能力接口。

    实现体在 world 侧(`world/edge/port.py`); 权限与仲裁都在实现里, NPC 只能"请求"。
    """

    def observe(self, pid: str) -> Percept:
        """主动观察: 返回该 NPC 当前可感知的只读快照(含信箱事件)。"""
        ...

    def here(self, pid: str) -> str:
        """我【在哪】—— 便宜的那一半: 只回地点 id, 不建可见列表。

        单独有它是因为 `observe`(看得见什么)很贵, 而 NPC 不是每 tick 都要看;
        但"我在哪"每 tick 都要知道(决策要它)。
        """
        ...

    def now(self) -> int:
        """世界此刻的 tick —— 决策/冷却/时间窗都要用, 所以给个便宜的查询。"""
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

        ...
