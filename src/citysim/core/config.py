"""SimConfig 加载器：把 config/sim.toml 读成 frozen 配置对象。

信号全集 0.3 在此定死：后续加信号改 config 而非代码。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

# 信号全集（0..1 float, 1=充足/健康, 0=耗尽）。唯一表示, 禁 0..100 int 存储。
SIGNALS: tuple[str, ...] = (
    "energy", "hunger", "thirst", "bladder",
    "temperature", "health", "fun", "social", "comfort", "hp",
)


@dataclass(frozen=True)
class SimConfig:
    ticks_per_day: int
    metabolism: dict[str, float]     # 全信号 delta; 缺省信号补 0.0
    wake_energy: float
    asleep_review_ticks: int
    bladder_convert: float
    eat_hunger_threshold: float
    default_duration_ticks: int
    review_min_ticks: int
    review_max_ticks: int
    half_life_ticks: int = 10080   # M5 知识半衰期(tick; 7 天)
    utility_power: float = 3.0     # 需求急迫度幂次(m5-rectify 13)
    utility_threshold: float = 0.08
    move_ticks: int = 30           # 跨地点移动耗时

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> "SimConfig":
        meta = data.get("metabolism", {})
        full_meta = {s: float(meta.get(s, 0.0)) for s in SIGNALS}
        return cls(
            ticks_per_day=int(data["time"]["ticks_per_day"]),
            metabolism=full_meta,
            wake_energy=float(data["sleep"]["wake_energy"]),
            asleep_review_ticks=int(data["sleep"]["asleep_review_ticks"]),
            bladder_convert=float(data["bladder"]["convert_per_tick"]),
            eat_hunger_threshold=float(data["eat"]["hunger_threshold"]),
            default_duration_ticks=int(data["interaction"]["default_duration_ticks"]),
            review_min_ticks=int(data["review"]["min_ticks"]),
            review_max_ticks=int(data["review"]["max_ticks"]),
            half_life_ticks=int(data.get("knowledge", {}).get("half_life_ticks", 10080)),
            utility_power=float(data.get("utility", {}).get("power", 3.0)),
            utility_threshold=float(data.get("utility", {}).get("threshold", 0.08)),
            move_ticks=int(data.get("motion", {}).get("move_ticks", 30)),
        )


def load_config(path: str | Path = "config/sim.toml") -> SimConfig:
    """从 TOML 读配置。默认相对当前工作目录。"""
    with Path(path).open("rb") as f:
        data = tomllib.load(f)
    return SimConfig.from_toml(data)
