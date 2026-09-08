"""item_memory —— 以实体为中心的"以为世界"骨架(docs/kb_design.md 目标形态)。

独立于现有 relation 三元组 KnowledgeBase; 尚未接入 decide/perception。
每个 NPC 一份稀疏记忆: dict[item_id -> ItemRow]。

行 = 内容(我以为的真值, 与 Entity 同构) + believe(证据强度) + remember(记忆强度)。

两个正交轴:
- believe  : 我信不信(来源天花板 OBSERVED>INFERRED, TOLD 封顶; 现场反证才显著降)。
- remember : 我还记不记得(obs/told 都提神重置; 随时间衰减, <FORGET 删行遗忘)。

规则(docs/kb_design.md §4/§6):
- observe  : 亲眼 → 内容=现场真值, believe=OBSERVED 天花板, remember=1。
- hear     : told   → 可建行/提神; 弱来源不拉低强来源的 believe。
- contradict: 现场反证/失败纠错 → believe 显著降(内容常随 obs 覆盖)。
- decay    : remember 半衰衰减, < FORGET 整行删除(遗忘)。

依赖红线: 本模块属 npc 层, 不得 import citysim.world。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SourceKind = Literal["OBSERVED", "TOLD", "INFERRED"]

# 各来源的证据强度天花板(docs §4.1): 一种来源到不了比它更高的分。
_SOURCE_CAP: dict[SourceKind, float] = {
    "OBSERVED": 1.0,
    "TOLD": 0.6,
    "INFERRED": 0.4,
}

FORGET_THRESHOLD = 0.1     # remember 低于此 → 遗忘删除
REMEMBER_FULL = 1.0        # 每次 obs/told 后 remember 重置到满


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


@dataclass(slots=True)
class ItemRow:
    """NPC 对单个 item 的"我以为"记忆单元。"""
    item_id: str
    # —— 内容(与 Entity 同构)——
    located: str = ""          # 我以为它在哪(易变)
    owner: str = ""            # 我以为归谁: me | place_id | person_id
    claimed: bool = False      # 我以为是否被占用(易变)
    afford: str = ""           # 它能提供什么信号(obs/told 自动填)
    value: float = 0.0         # 提供多少
    price: float = 0.0         # 我以为的现价(会变: 调价/促销)
    stock: int = 0             # 我以为的库存(-1=无限; 会变: 消耗/补货)
    attrs: dict[str, Any] = field(default_factory=dict)
    # —— 证据强度(信几分)——
    believe: float = 0.0
    source_kind: SourceKind = "OBSERVED"
    # —— 记忆强度(记不记得)——
    remember: float = 0.0
    last_seen: int = 0

    def cap(self) -> float:
        return _SOURCE_CAP[self.source_kind]


class ItemMemory:
    """item 中心稀疏记忆: 检索看 remember, 打分看 believe×value。"""

    def __init__(self) -> None:
        self.rows: dict[str, ItemRow] = {}

    # --- 检索 ---------------------------------------------------------
    def get(self, item_id: str) -> ItemRow | None:
        return self.rows.get(item_id)

    def items(self) -> tuple[ItemRow, ...]:
        """当前记得的行(remember > 遗忘阈值)。"""
        return tuple(r for r in self.rows.values()
                     if r.remember >= FORGET_THRESHOLD)

    def __contains__(self, item_id: str) -> bool:
        return item_id in self.rows

    def __len__(self) -> int:
        return len(self.rows)

    # --- 写入 ---------------------------------------------------------
    def _touch(self, r: ItemRow, tick: int) -> None:
        """obs/told 都重置记忆: 我重新想起了它(但不改变 believe)。"""
        r.remember = REMEMBER_FULL
        r.last_seen = tick

    def observe(self, item_id: str, tick: int, *, located: str = "",
                owner: str = "", claimed: bool = False, afford: str = "",
                value: float = 0.0, price: float | None = None,
                stock: int | None = None,
                attrs: dict | None = None) -> ItemRow:
        """亲眼: 内容 = 现场真值(全覆盖); believe=OBSERVED 顶, remember=1。"""
        r = self.rows.get(item_id)
        if r is None:
            r = ItemRow(item_id=item_id)
            self.rows[item_id] = r
        r.located = located
        r.owner = owner
        r.claimed = claimed
        if afford:
            r.afford = afford
            r.value = _clamp(value)
        if price is not None:
            r.price = price
        if stock is not None:
            r.stock = stock
        if attrs:
            r.attrs = dict(attrs)
        r.source_kind = "OBSERVED"
        r.believe = _SOURCE_CAP["OBSERVED"]
        self._touch(r, tick)
        return r

    def hear(self, item_id: str, tick: int, *, located: str | None = None,
             owner: str | None = None, afford: str | None = None,
             value: float | None = None, price: float | None = None,
             stock: int | None = None) -> ItemRow:
        """听说(told): 可建行/提神。证据合并两条:

        - 现状已被 OBSERVED(更强)主导 → told 是弱消息: 不拉低 believe、
          不覆盖已亲眼知道的内容(只补未知字段)。
        - 现状是 TOLD/INFERRED(≤ told) → told 主导: believe 升到 told 天花板(0.6),
          来源变 TOLD, told 提供的内容覆盖。
        - 无论强弱, told 都重置 remember(被提起=重新想起)。
        """
        cap = _SOURCE_CAP["TOLD"]
        r = self.rows.get(item_id)
        if r is None:
            r = ItemRow(item_id=item_id, source_kind="TOLD", believe=cap)
            self.rows[item_id] = r
            if located is not None:
                r.located = located
            if owner is not None:
                r.owner = owner
            if afford is not None:
                r.afford = afford
                r.value = _clamp(value) if value is not None else r.value
            if price is not None:
                r.price = price
            if stock is not None:
                r.stock = stock
        elif r.source_kind == "OBSERVED":
            # 强来源已主导: told 是弱消息 —— 只补未知字段, 不降 believe/不覆盖
            if located is not None and not r.located:
                r.located = located
            if owner is not None and not r.owner:
                r.owner = owner
            if afford is not None and not r.afford:
                r.afford = afford
                r.value = _clamp(value) if value is not None else r.value
            # price/stock: 弱 told 不覆盖强来源(即便为 0 也不顶)
        else:
            # told 主导(现状 ≤ TOLD): 升到 told 天花板, 覆盖 told 内容
            r.source_kind = "TOLD"
            r.believe = max(r.believe, cap)
            if located is not None:
                r.located = located
            if owner is not None:
                r.owner = owner
            if afford is not None:
                r.afford = afford
                r.value = _clamp(value) if value is not None else r.value
            if price is not None:
                r.price = price
            if stock is not None:
                r.stock = stock
        self._touch(r, tick)
        return r

    def contradict(self, item_id: str, tick: int, *, factor: float = 0.5) -> None:
        """现场反证/失败纠错(负证据): believe 显著降; 只降不信, 不影响 remember。"""
        r = self.rows.get(item_id)
        if r is None:
            return
        r.believe = max(0.0, min(r.believe, r.believe * factor))
        # 反证是一次"想起"(仍在检索), 也刷新记忆但内容现场为准另由 observe 覆盖。

    def forget_row(self, item_id: str) -> None:
        self.rows.pop(item_id, None)

    # --- 遗忘 ---------------------------------------------------------
    def decay(self, now_tick: int, half_life_ticks: int) -> None:
        """remember 半衰衰减; < FORGET 整行删除(真忘了)。

        与 believe 无关: 遗忘管"记不记得", 不靠"信不信归零"。
        """
        for item_id, r in list(self.rows.items()):
            dt = max(0, now_tick - r.last_seen)
            if dt <= 0:
                continue
            factor = 0.5 ** (dt / max(1, half_life_ticks))
            rem = r.remember * factor
            if rem < FORGET_THRESHOLD:
                del self.rows[item_id]
            else:
                r.remember = rem

    # --- 追溯/观测辅助 ------------------------------------------------
    def to_dicts(self) -> list[dict]:
        """导出(观测/快照): 只含记得的行。"""
        return [
            {"item_id": r.item_id, "located": r.located, "owner": r.owner,
             "claimed": r.claimed, "afford": r.afford, "value": r.value,
             "price": r.price, "stock": r.stock,
             "believe": round(r.believe, 3),
             "remember": round(r.remember, 3), "last_seen": r.last_seen,
             "source": r.source_kind}
            for r in self.items()
        ]

    def __repr__(self) -> str:  # pragma: no cover
        return f"ItemMemory({len(self.rows)} rows)"
