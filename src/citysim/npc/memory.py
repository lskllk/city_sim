"""memory —— NPC 记忆库(纯数据库式骨架)。


TODO(由上层逐项接线, 本模块保持无脑):
- [brain]  写入: 感知 obs / 传闻 told 何时给 believe 多高; 强来源不降等合并规则在此实现。
- [brain]  读取: decide 用 query(afford=…)/query(located=…) 取候选集打分。
- [percep] 映射: 真实 Entity → MemItem(obs 覆盖 located/owner/claimed/price/stock…)。
- [brain]  遗忘: 用 last_seen/remember 字段自实现 remember 衰减+删行; 何时调/半衰/阈值自定。
- [设计]   afford 现为单值; 若要完全对齐 Entity.affordances(dict) 需把 afford/value 换成 dict。
- 溯源 trace / 来源 ref: 本版不纳入(如要再加字段)。

依赖红线: npc 层, 不得 import citysim.world。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemItem:
    """NPC 对单个 item 的"我以为"。纯数据可变行。"""
    item_id: str
    # —— 内容(与 Entity 同构, 值由上层填)——
    located: str = ""            # 我以为它在哪(易变)
    owner: str = ""              # 我以为归谁: ""=无主/公共 | person_id | company_id
    claimed: bool = False        # 我以为是否被占用(易变)
    afford: str = ""             # 它能提供什么信号(obs/told 填)
    value: float = 0.0           # 提供多少
    carryable: bool = False      # 能不能装进背包(take)
    item_type: str = ""          # 物品类型 id(去重/合并用)
    price: float = 0.0           # 我以为的现价(易变)
    stock: int = 0               # 我以为的库存(-1=无限; 易变)
    attrs: dict[str, Any] = field(default_factory=dict)
    # —— 元(本层只存, 不计算)——
    believe: float = 0.0         # 证据强度(0..1): 我信几分
    remember: float = 0.0        # 记忆强度(0..1): 我还记不记得
    last_seen: int = 0           # 最近一次被写的 tick(供遗忘算距上次多久)
    cool_until: int = 0          # 交互失败屏蔽到某 tick(被占/不可打断等, 到时再看)


class MemBase:
    """每 NPC 的记忆库 = 薄 CRUD(增删改查), 无策略。"""

    _FIELDS = frozenset({
        "located", "owner", "claimed", "afford", "value", "carryable",
        "item_type", "price", "stock", "attrs", "believe", "remember",
        "last_seen", "cool_until",
    })

    def __init__(self) -> None:
        self._rows: dict[str, MemItem] = {}

    # --- 查(读) -------------------------------------------------------
    def get(self, item_id: str) -> MemItem | None:
        """主键取一行。"""
        return self._rows.get(item_id)

    def query(self, *, afford: str | None = None,
              located: str | None = None,
              owner: str | None = None,
              min_believe: float = 0.0,
              min_remember: float = 0.0) -> tuple[MemItem, ...]:
        """按字段过滤检索(缺省条件=不过滤)。供 decide 取候选。"""
        out = []
        for r in self._rows.values():
            if afford is not None and r.afford != afford:
                continue
            if located is not None and r.located != located:
                continue
            if owner is not None and r.owner != owner:
                continue
            if r.believe < min_believe or r.remember < min_remember:
                continue
            out.append(r)
        return tuple(out)

    def items(self) -> tuple[MemItem, ...]:
        """全量快照(观测/导出)。"""
        return tuple(self._rows.values())

    def __len__(self) -> int:
        return len(self._rows)

    def __contains__(self, item_id: str) -> bool:
        return item_id in self._rows

    # --- 增 / 改 / 删(写) ---------------------------------------------
    def set(self, item: MemItem) -> None:
        """增或整行覆盖(以 item_id 为键 upsert)。"""
        self._rows[item.item_id] = item

    def update(self, item_id: str, **fields: Any) -> MemItem | None:
        """只改给出的字段。返回更新后的行; 无此行返回 None。"""
        r = self._rows.get(item_id)
        if r is None:
            return None
        for k, v in fields.items():
            if k not in self._FIELDS:
                raise ValueError(f"未知字段 {k!r}")
            setattr(r, k, v)
        return r

    def delete(self, item_id: str) -> bool:
        """删一行。"""
        return self._rows.pop(item_id, None) is not None

    def clear(self) -> None:
        self._rows.clear()

    # --- 导出 ---------------------------------------------------------
    def to_dicts(self) -> list[dict]:
        return [
            {"item_id": r.item_id, "located": r.located, "owner": r.owner,
             "claimed": r.claimed, "afford": r.afford, "value": r.value,
             "carryable": r.carryable, "item_type": r.item_type,
             "price": r.price, "stock": r.stock,
             "believe": round(r.believe, 3),
             "remember": round(r.remember, 3), "last_seen": r.last_seen,
             "cool_until": r.cool_until}
            for r in self._rows.values()
        ]

    def __repr__(self) -> str:  # pragma: no cover
        return f"MemBase({len(self._rows)} rows)"
