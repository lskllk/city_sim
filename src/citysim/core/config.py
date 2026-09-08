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


@dataclass(frozen=True)
class SimConfig:
    ticks_per_day: int
    metabolism: dict[str, float]     # 全信号 delta; 缺省信号补 0.0
    bladder_convert: float
    review_min_ticks: int
    review_max_ticks: int
    half_life_ticks: int = 2880   # M5 知识半衰期(tick; 2 天)
    utility_power: float = 3.0     # 需求急迫度幂次(m5-rectify 13)
    utility_threshold: float = 0.08
    move_ticks: int = 30           # 跨地点移动耗时
    hp_decay: float = 0.0005       # 饥饿/饥渴为 0 时 hp 每 tick 下降
    hp_regen: float = 0.0005       # 两者满足时 hp 回升最大速率(×均值)
    move_penalty: float = 0.6      # 异地(MoveTo)候选效用折扣(移动耗时/精力成本)
    buy_margin: float = 1.0        # 愿买度缓冲: willing=clamp01((money-price)/(price*margin))
    # —— 生物钟 / 清醒度(简化: 单余弦 + 系数, 见 brain.circadian/arousal) ——
    peak_hour: float = 15.0        # 最清醒时刻(h); 谷=峰±12h
    circadian_min: float = 0.15    # 生物钟谷值
    circadian_amp: float = 0.85    # 生物钟振幅(峰=min+amp)
    energy_floor: float = 0.4      # 清醒度里 energy 的基准系数
    energy_gain: float = 0.6       # 清醒度里 energy 的增益
    hunger_penalty: float = 0.2    # 饥饿对清醒度的拖累

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> "SimConfig":
        meta = data.get("metabolism", {})
        full_meta = {s: float(meta.get(s, 0.0)) for s in SIGNALS}
        return cls(
            ticks_per_day=int(data["time"]["ticks_per_day"]),
            metabolism=full_meta,
            bladder_convert=float(data["bladder"]["convert_per_tick"]),
            review_min_ticks=int(data["review"]["min_ticks"]),
            review_max_ticks=int(data["review"]["max_ticks"]),
            half_life_ticks=int(data.get("knowledge", {}).get("half_life_ticks", 2880)),
            utility_power=float(data.get("utility", {}).get("power", 3.0)),
            utility_threshold=float(data.get("utility", {}).get("threshold", 0.08)),
            move_ticks=int(data.get("motion", {}).get("move_ticks", 30)),
            hp_decay=float(data.get("health", {}).get("decay", 0.0005)),
            hp_regen=float(data.get("health", {}).get("regen", 0.0005)),
            move_penalty=float(data.get("utility", {}).get("move_penalty", 0.6)),
            buy_margin=float(data.get("utility", {}).get("buy_margin", 1.0)),
            peak_hour=float(data.get("wake", {}).get("peak_hour", 15.0)),
            circadian_min=float(data.get("wake", {}).get("circadian_min", 0.15)),
            circadian_amp=float(data.get("wake", {}).get("circadian_amp", 0.85)),
            energy_floor=float(data.get("wake", {}).get("energy_floor", 0.4)),
            energy_gain=float(data.get("wake", {}).get("energy_gain", 0.6)),
            hunger_penalty=float(data.get("wake", {}).get("hunger_penalty", 0.2)),
        )


def load_config(path: str | Path = "config/sim.toml") -> SimConfig:
    """从 TOML 读配置。默认相对当前工作目录。"""
    with Path(path).open("rb") as f:
        data = tomllib.load(f)
    return SimConfig.from_toml(data)
