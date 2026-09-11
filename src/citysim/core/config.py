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
    "energy", "hunger", "thirst", "bladder", "fun", "hp",
)

# 兜底 reflex 只覆盏"致命/强生理"信号; fun 等非致命需求交给计划(LLM)。
# 见 docs/task006.md 与 2026-09-11 讨论。
REFLEX_SIGNALS: tuple[str, ...] = ("energy", "hunger", "thirst", "bladder")


@dataclass(frozen=True)
class SimConfig:
    ticks_per_day: int
    metabolism: dict[str, float]     # 全信号 delta; 缺省信号补 0.0
    bladder_convert: float
    half_life_ticks: int = 2880   # M5 知识半衰期(tick; 2 天)
    utility_power: float = 3.0     # 需求急迫度幂次(m5-rectify 13)
    utility_threshold: float = 0.0   # 效用最低分(兜底策略下置 0: 到 need 下限即行动)
    move_ticks: int = 30           # 跨地点移动耗时
    hp_decay: float = 0.0005       # 饥饿/饥渴为 0 时 hp 每 tick 下降
    hp_regen: float = 0.0005       # 两者满足时 hp 回升最大速率(×均值)
    move_penalty: float = 0.6      # 异地(MoveTo)候选效用折扣(移动耗时/精力成本)
    fallback_need: float = 0.9     # 兜底触发下限: 仅 need>=此值才纳入候选(信号<=10%)

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> "SimConfig":
        meta = data.get("metabolism", {})
        full_meta = {s: float(meta.get(s, 0.0)) for s in SIGNALS}
        health = data.get("health", {})
        return cls(
            ticks_per_day=int(data["time"]["ticks_per_day"]),
            metabolism=full_meta,
            bladder_convert=float(data["bladder"]["convert_per_tick"]),
            half_life_ticks=int(data.get("knowledge", {}).get("half_life_ticks", 2880)),
            utility_power=float(data.get("utility", {}).get("power", 3.0)),
            utility_threshold=float(data.get("utility", {}).get("threshold", 0.0)),
            move_ticks=int(data.get("motion", {}).get("move_ticks", 30)),
            hp_decay=float(health.get("hp_decay", health.get("decay", 0.0005))),
            hp_regen=float(health.get("hp_regen", health.get("regen", 0.0005))),
            move_penalty=float(data.get("utility", {}).get("move_penalty", 0.6)),
            fallback_need=float(data.get("utility", {}).get("fallback_need", 0.9)),
        )


def load_config(path: str | Path = "config/sim.toml") -> SimConfig:
    """从 TOML 读配置。默认相对当前工作目录。"""
    with Path(path).open("rb") as f:
        data = tomllib.load(f)
    return SimConfig.from_toml(data)
