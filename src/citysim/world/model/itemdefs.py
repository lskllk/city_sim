"""物品定义加载 —— config/items/*.json。

仅标准库 + 数据类; 供 world 侧(交互/生成/感知)使用, 不反向依赖 world。
字段就是物品 schema(改字段 = 改数据契约)。

加载即校验(fail-fast):
  - affordances 的 key 必须 ∈ SIGNALS
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


@dataclass(frozen=True)
class ItemDef:
    item_type: str
    name: str = ""
    tags: frozenset[str] = frozenset()
    affordances: Mapping[str, float] = field(default_factory=dict)
    duration_ticks: int = 30
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
        attrs=dict(data.get("attrs", {})),
        stock=int(data.get("stock", 1)),
        price=float(data.get("price", 0.0)),
        build_cost=float(data.get("build_cost", 0.0)),
        persist_empty=bool(data.get("persist_empty", False)),
        shelf_life_ticks=int(data.get("shelf_life_ticks", 0)),
    )


def _validate(path: Path, d: ItemDef) -> None:
    if d.duration_ticks < 1:
        raise ConfigError(f"{path.name}: {d.item_type} duration_ticks<1")
    for s in d.affordances:
        if s not in SIGNALS:
            raise ConfigError(
                f"{path.name}: {d.item_type} affordance key {s!r} 不在 SIGNALS")
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
    for it, d in parsed.items():
        _validate(paths[it], d)
    return parsed


def load_item_defs(directory: str | Path | None = None) -> dict[str, ItemDef]:
    """读 config/items/*.json -> {item_type: ItemDef}。缺省指向工程 config/items。"""
    d = _ITEMS_DIR if directory is None else Path(directory)
    return _read_dir(str(d))
