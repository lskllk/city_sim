"""物品定义加载 —— config/items/*.json。

仅标准库 + 数据类; 供 world 侧(交互/生成/感知)使用, 不反向依赖 world。
字段对应 M4 4.1 定死的物品 schema。

加载即校验(testm4 Step 1, fail-fast):
  - affordances 的 key 必须 ∈ SIGNALS
  - on_start/on_complete 里的 op 必须是已注册 op
  - wake_condition 仅 "signal>=float"(正则)
  - duration_ticks >= 1
  - provides 引用的 item_type 必须存在(允许前向引用, 加载完统一校验)
任何一条不过 → 抛 ConfigError 并指明文件+字段, 禁止静默跳过。
"""
from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from citysim.core.config import SIGNALS

_ITEMS_DIR = Path(__file__).resolve().parents[3] / "config" / "items"
_WAKE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*>=\s*-?\d+(?:\.\d+)?$")


class ConfigError(Exception):
    """物品/动作配置校验失败; message 含 文件 + 字段。"""


def _registered_ops() -> set[str]:
    """延迟导入避免模块级环(effects -> world -> itemdefs)。"""
    from citysim.world.effects import OPS  # noqa: PLC0415
    return set(OPS)


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


def _validate(path: Path, d: ItemDef, known: set[str], ops: set[str]) -> None:
    if d.duration_ticks < 1:
        raise ConfigError(f"{path.name}: {d.item_type} duration_ticks<1")
    if d.wake_condition is not None and not _WAKE_RE.match(d.wake_condition):
        raise ConfigError(
            f"{path.name}: {d.item_type} wake_condition 非法格式 "
            f"{d.wake_condition!r}(需 signal>=float)")
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
    for p in d.provides:
        if p not in known:
            raise ConfigError(
                f"{path.name}: {d.item_type} provides 悬空引用 {p!r}")


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
    known = set(parsed)
    for it, d in parsed.items():
        _validate(paths[it], d, known, ops)
    return parsed


def load_item_defs(directory: str | Path | None = None) -> dict[str, ItemDef]:
    """读 config/items/*.json -> {item_type: ItemDef}。缺省指向工程 config/items。"""
    d = _ITEMS_DIR if directory is None else Path(directory)
    return _read_dir(str(d))


def clear_cache() -> None:
    """测试动态增删 JSON 后清缓存。"""
    _read_dir.cache_clear()
