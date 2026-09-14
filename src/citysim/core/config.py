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
    "energy", "hunger", "bladder", "hp",
)

# 兜底 reflex 只覆盖"致命/强生理"信号; 非致命需求交给计划表系统。
# 见 2026-09-11 讨论（计划表 + 中断系统）。
REFLEX_SIGNALS: tuple[str, ...] = ("energy", "hunger", "bladder")


@dataclass(frozen=True)
class SimConfig:
    ticks_per_day: int
    metabolism: dict[str, float]     # 全信号 delta; 缺省信号补 0.0
    bladder_convert: float
    half_life_ticks: int = 2880   # M5 知识半衰期(tick; 2 天)
    utility_power: float = 3.0     # 需求急迫度幂次(m5-rectify 13)
    # 【唯一阈值】就设在这里(得分上), 不再有"候选收集门槛"那一层。
    # 低于此分什么都不做 —— 它同时承担了"琐碎需求别动"与"别乱走"两件事。
    utility_threshold: float = 0.05
    move_ticks: int = 30           # 跨地点移动耗时(无路网时的降级)
    move_m_per_tick: float = 10.0  # 有路网时: 每 tick 可走米数
    hp_decay: float = 0.0005       # 饥饿/饥渴为 0 时 hp 每 tick 下降
    hp_regen: float = 0.0005       # 两者满足时 hp 回升最大速率(×均值)
    # —— 成本模型(比价 / 比距离 / 顺路) ——
    # eff = (need^power × value × personality × believe) / (1 + cost_lambda × cost)
    # cost = price×qty + time_value×travel_ticks + price×(1−believe)
    # 不再有 move_penalty: 异地成本由【真实移动 tick】表达(走路是有代价的)。
    cost_lambda: float = 0.02      # 成本权重(λ): 越大越"抠"
    time_value: float = 0.05       # 走 1 tick 折合多少钱(决定"顺路"值多少)
    # 迟滞: 新的比当前这件【好这么多倍】才麻炊地改主意。
    # 1.0 = 随时见异思迁(会抽风); 太大 = 快饿死了还在睡。
    preempt_ratio: float = 1.5
    tell_p: float = 0.3          # 传播概率(场景可覆盖; 0 = 不传谣)

    @classmethod
    def from_toml(cls, data: dict[str, Any]) -> "SimConfig":
        meta = data.get("metabolism", {})
        full_meta = {s: float(meta.get(s, 0.0)) for s in SIGNALS}
        health = data.get("health", {})
        util = data.get("utility", {})
        return cls(
            ticks_per_day=int(data["time"]["ticks_per_day"]),
            metabolism=full_meta,
            bladder_convert=float(data["bladder"]["convert_per_tick"]),
            half_life_ticks=int(data.get("knowledge", {}).get("half_life_ticks", 2880)),
            utility_power=float(util.get("power", 3.0)),
            utility_threshold=float(util.get("threshold", 0.05)),
            move_ticks=int(data.get("motion", {}).get("move_ticks", 30)),
            move_m_per_tick=float(data.get("motion", {}).get("move_m_per_tick", 10.0)),
            hp_decay=float(health.get("hp_decay", health.get("decay", 0.0005))),
            hp_regen=float(health.get("hp_regen", health.get("regen", 0.0005))),
            cost_lambda=float(util.get("cost_lambda", 0.02)),
            time_value=float(util.get("time_value", 0.05)),
            preempt_ratio=float(util.get("preempt_ratio", 1.5)),
            tell_p=float(data.get("social", {}).get("tell_p", 0.3)),
        )


def load_config(path: str | Path = "config/sim.toml") -> SimConfig:
    """从 TOML 读配置。默认相对当前工作目录。"""
    with Path(path).open("rb") as f:
        data = tomllib.load(f)
    return SimConfig.from_toml(data)
