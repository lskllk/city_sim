"""物品定义加载 —— config/items/*.json。

仅标准库 + 数据类; 供 world 侧(交互/生成/感知)使用, 不反向依赖 world。
字段对应 M4 4.1 定死的物品 schema。
"""
from __future__ import annotations

import json
import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

_ITEMS_DIR = Path(__file__).resolve().parents[3] / "config" / "items"


@dataclass(frozen=True)
class ItemDef:
    item_type: str
    name: str = ""
    tags: frozenset[str] = frozenset()
    affordances: Mapping[str, float] = field(default_factory=dict)
    duration_ticks: int = 30
    interruptible: bool = True
    wake_condition: str | None = None
    on_start: tuple[Mapping[str, Any], ...] = ()
    on_complete: tuple[Mapping[str, Any], ...] = ()
    provides: tuple[str, ...] = ()
    attrs: Mapping[str, Any] = field(default_factory=dict)
    stock: int = 1


def _parse(data: dict) -> ItemDef:
    return ItemDef(
        item_type=data["item_type"],
        name=data.get("name", data["item_type"]),
        tags=frozenset(data.get("tags", [])),
        affordances=dict(data.get("affordances", {})),
        duration_ticks=int(data.get("duration_ticks", 30)),
        interruptible=bool(data.get("interruptible", True)),
        wake_condition=data.get("wake_condition"),
        on_start=tuple(dict(x) for x in data.get("on_start", [])),
        on_complete=tuple(dict(x) for x in data.get("on_complete", [])),
        provides=tuple(data.get("provides", [])),
        attrs=dict(data.get("attrs", {})),
        stock=int(data.get("stock", 1)),
    )


@functools.lru_cache(maxsize=4)
def _read_dir(directory: str) -> dict[str, ItemDef]:
    out: dict[str, ItemDef] = {}
    for p in sorted(Path(directory).glob("*.json")):
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if "item_type" not in data:
            continue
        d = _parse(data)
        out[d.item_type] = d
    return out


def load_item_defs(directory: str | Path | None = None) -> dict[str, ItemDef]:
    """读 config/items/*.json -> {item_type: ItemDef}。缺省指向工程 config/items。"""
    d = _ITEMS_DIR if directory is None else Path(directory)
    return _read_dir(str(d))
