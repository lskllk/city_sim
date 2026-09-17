"""npc/person/memo —— 记忆门面: 记一笔 / 还记不记得 / 只读快照

记忆本体是 npc/memory.MemBase —— 这里只是写入口。

我拥有的字段: _mem
"""
from __future__ import annotations

from typing import Sequence
from citysim.npc.memory import MemItem


class MemoMixin:
    """见文件头(它拥有哪些字段)。"""


    # ------------------------------------------------------------------
    # 大脑 —— 感知写入记忆 + 决策(只看记忆+自身, 不看环境)
    # ------------------------------------------------------------------
    def note(self, item_id: str, tick: int = 0, *, located: str | None = None,
             owner: str | None = None, afford: str | None = None,
             value: float | None = None, price: float | None = None,
             stock: int | None = None, believe: float | None = None,
             item_type: str | None = None,
             source: str | None = None,
             shelf_life_ticks: int | None = None,
             expires_tick: int | None = None,
             tags: Sequence[str] | None = None) -> None:
        """往记忆 upsert 一行(增/改; 部分字段可省略)。供成交/事件/传闻用。

        source: "" = 亲眼所见; npc_id = 他说的; "ad:<bid>" = 广告招牌。
        """
        row = self._mem.get(item_id)
        if row is None:
            # ★ 新建的行没显式传 believe → 按【亲眼所见】算 1.0。
            # MemItem 的字段默认值是 0.0(空记忆), 而 believe=0 会让这一行
            # 在打分里 base=…×believe=0 → 永远不可能被选中:
            # “买回来的东西记不住/不信”就是这么来的(实测过: 买了简餐,
            # 家里那条 believe 是 0.00, 于是永远不回去吃)。
            row = MemItem(item_id=item_id, believe=1.0, remember=1.0)
            self._mem.set(row)
        fields: dict = {}
        if located is not None:
            fields["located"] = located
        if owner is not None:
            fields["owner"] = owner
        if afford is not None:
            fields["afford"] = afford
        if value is not None:
            fields["value"] = float(value)
        if price is not None:
            fields["price"] = float(price)
        if stock is not None:
            fields["stock"] = int(stock)
        if believe is not None:
            fields["believe"] = float(believe)
        if item_type is not None:
            fields["item_type"] = str(item_type)
        if source is not None:
            fields["source"] = str(source)
        if tags is not None:
            fields["tags"] = tuple(sorted(str(x) for x in tags))
        if shelf_life_ticks is not None:
            fields["shelf_life_ticks"] = int(shelf_life_ticks)
        if expires_tick is not None:
            fields["expires_tick"] = int(expires_tick)
        fields.setdefault("remember", 1.0)
        fields.setdefault("last_seen", tick)
        self._mem.update(item_id, **fields)


    def remembers(self, item_id: str) -> bool:
        """我记忆里有没有这一条(供“对方已知就不说”这类判断用)。"""
        return self._mem.get(item_id) is not None


    def memory_dicts(self) -> list:
        """观测: 记忆库只读快照(不对外暴露可写对象)。"""
        return self._mem.to_dicts()
