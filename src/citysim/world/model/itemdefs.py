"""物品定义加载 —— config/items/*.json。

仅标准库 + 数据类; 供 world 侧(交互/生成/感知)使用, 不反向依赖 world。
字段就是物品 schema(改字段 = 改数据契约)。

加载即校验(fail-fast):
  - affordances 的 key 必须 ∈ SIGNALS
  - on_start/on_complete 里的 op 必须是已注册 op
  - duration_ticks >= 1
任何一条不过 → 抛 ConfigError 并指明文件+字段, 禁止静默跳过。
"""
from __future__ import annotations

import functools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from citysim.core.config import SIGNALS

_ITEMS_DIR = Path(__file__).resolve().parents[4] / "config" / "items"


class ConfigError(Exception):
    """物品/动作配置校验失败; message 含 文件 + 字段。"""


# 认知侧 op: 不是由 world 执行的, 而是被 compile_effects 编译成【结构数据】
# 交给 NPC 自己应用 —— 所以它们不在 OPS 里, 但仍是合法的 op。
COGNITIVE_OPS: tuple[str, ...] = ("add_signal", "set_signal", "add_pending")


def _registered_ops() -> set[str]:
    """合法的 op = 认知侧(改自己的信号) ∪ 世界侧(已 @register 的)。"""
    from citysim.world.mechanism.effects import OPS  # noqa: PLC0415
    return set(COGNITIVE_OPS) | set(OPS)


@dataclass(frozen=True)
class ItemDef:
    item_type: str
    name: str = ""
    tags: frozenset[str] = frozenset()
    affordances: Mapping[str, float] = field(default_factory=dict)
    duration_ticks: int = 30
    on_start: tuple[Mapping[str, Any], ...] = ()
    on_complete: tuple[Mapping[str, Any], ...] = ()
    attrs: Mapping[str, Any] = field(default_factory=dict)
    stock: int = 1
    price: float = 0.0           # 零售/批发【售价】(>0 才算可卖的货)
    build_cost: float = 0.0      # 装修件【放置成本】(只给 tag=fixture 的件用; 不是售价)
    persist_empty: bool = False   # stock 归 0 不被回收(容器/货架持续存在)
    shelf_life_ticks: int = 0     # 保质期(0 = 不会坏)。到点变质 → stock 归 0


def _parse(data: dict) -> ItemDef:
    return ItemDef(
        item_type=data["item_type"],
        name=data.get("name", data["item_type"]),
        tags=frozenset(data.get("tags", [])),
        affordances=dict(data.get("affordances", {})),
        duration_ticks=int(data.get("duration_ticks", 30)),
        on_start=tuple(dict(x) for x in data.get("on_start", [])),
        on_complete=tuple(dict(x) for x in data.get("on_complete", [])),
        attrs=dict(data.get("attrs", {})),
        stock=int(data.get("stock", 1)),
        price=float(data.get("price", 0.0)),
        build_cost=float(data.get("build_cost", 0.0)),
        persist_empty=bool(data.get("persist_empty", False)),
        shelf_life_ticks=int(data.get("shelf_life_ticks", 0)),
    )


def _validate(path: Path, d: ItemDef, ops: set[str]) -> None:
    if d.duration_ticks < 1:
        raise ConfigError(f"{path.name}: {d.item_type} duration_ticks<1")
    for s in d.affordances:
        if s not in SIGNALS:
            raise ConfigError(
                f"{path.name}: {d.item_type} affordance key {s!r} 不在 SIGNALS")
    for group in ("on_start", "on_complete"):
        for eff in getattr(d, group):
            op = eff.get("op")
            if op not in ops:
                raise ConfigError(
                    f"{path.name}: {d.item_type} {group} 未注册 op {op!r}")

@functools.lru_cache(maxsize=4)
def _read_dir(directory: str) -> dict[str, ItemDef]:
    paths: dict[str, Path] = {}
    parsed: dict[str, ItemDef] = {}
    for p in sorted(Path(directory).glob("*.json")):
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if "item_type" not in data:
            continue
        d = _parse(data)
        paths[d.item_type] = p
        parsed[d.item_type] = d
    ops = _registered_ops()
    for it, d in parsed.items():
        _validate(paths[it], d, ops)
    return parsed


def load_item_defs(directory: str | Path | None = None) -> dict[str, ItemDef]:
    """读 config/items/*.json -> {item_type: ItemDef}。缺省指向工程 config/items。"""
    d = _ITEMS_DIR if directory is None else Path(directory)
    return _read_dir(str(d))



# ---------------------------------------------------------------------------
# 效果分流: 物品的效果写在 JSON 里, 但要分成"谁去执行"
# ---------------------------------------------------------------------------
#   认知侧(add_signal / set_signal / add_pending) → 编译成【不带 op 名】的
#       结构数据, 塞进 Grant.pending, 由 Person 自己应用 ——
#       这样 npc/ 完全不认识 config/items 里的 op 名。
#   世界侧(spawn_item / consume_self 等) → 原样交回 world 执行。
#
# ★ 为什么它跟着【物品定义】走而不跟着任一侧: 拆分规则必须同时知道两边的
#   词汇(JSON 的 op 名 + NPC 的结构字段), 所以它是物品格式的一部分。
def compile_effects(effects) -> tuple[tuple[dict, ...], list[dict]]:
    """把一列效果拆成 (认知侧, 世界侧)。见上。"""
    npc: list[dict] = []
    world: list[dict] = []
    for e in (effects or ()):
        op = e.get("op")
        if op not in COGNITIVE_OPS:
            world.append(e)
        elif op == "add_signal":
            npc.append({"signal": e["signal"],
                        "add": float(e.get("delta", e.get("value", 0.0)))})
        elif op == "set_signal":
            npc.append({"signal": e["signal"],
                        "set": float(e.get("value", 0.0))})
        else:                          # add_pending
            npc.append({"field": str(e.get("field", "")),
                        "amount": float(e.get("amount", 0.0))})
    return tuple(npc), world
