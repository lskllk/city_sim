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

# 注: REFLEX_SIGNALS(致命信号白名单)已在 2026-09-14 删除。
# 它原本用于“哪些信号能产生候选 / 哪些需求能抢占计划” —— 现在两者都不需要:
#   - 候选不再过滤(记忆里的行全部参与打分), 阀值只落在得分上(utility.threshold)
#   - 抢占只看得分比(preempt_ratio), 不看信号白名单
# 详见 docs/design.md §2。


@dataclass(frozen=True)
class SimConfig:
    ticks_per_day: int
    metabolism: dict[str, float]     # 全信号 delta; 缺省信号补 0.0
    bladder_convert: float
    half_life_ticks: int = 2880   # M5 知识半衰期(tick; 2 天)
    utility_power: float = 3.0     # 需求急迫度幂次(m5-rectify 13)
    # 每种需求可以有自己的幂次 —— power 越大, “不太困/不太饿”时分数越低,
    # 于是【不到真难受就不去】。精力尤其需要钝一点: 否则一累就去躺。
    power_by_signal: dict[str, float] = field(default_factory=dict)
    # 【唯一阈值】就设在这里(得分上), 不再有"候选收集门槛"那一层。
    # 低于此分什么都不做 —— 它同时承担了"琐碎需求别动"与"别乱走"两件事。
    utility_threshold: float = 0.05
    move_ticks: int = 30           # 跨地点移动耗时(无路网时的降级)
    move_m_per_tick: float = 10.0  # 有路网时: 每 tick 可走米数
    # —— 生命三态(docs/design.md §2) ——
    #   hp ↓  hunger==0 或 energy==0
    #   hp ↑  hunger ≥ floor 且 energy ≥ floor
    #   其他  不动(中间带 —— 否则咬一口饭 hp 就开始涨, “饿死”永远发生不了)
    hp_decay: float = 0.0005        # 饥饿/精力归零时 hp 每 tick 下降
    hp_regen: float = 0.0005        # 两者都满足到阀值时 hp 回升最大速率(×均值)
    hp_regen_floor: float = 0.5     # “吃饱/睡够”的阀值(中间带下界)
    # hp 低于此 → 日程失去拉力(命比钱大): 计划不执行、也让位给需求
    hp_override: float = 0.5
    # —— 成本模型(比价 / 比距离 / 顺路) ——
    # eff = (need^power × value × personality × believe) / (1 + cost_lambda × cost)
    # cost = price×qty + price×(1−believe)     (纯钱 + 不确定性)
    # 不再有 move_penalty: 异地成本由【真实移动 tick】表达(走路是有代价的)。
    cost_lambda: float = 0.02      # 成本权重(λ): 越大越"抠"
    # 迟滞: 新的比当前这件【好这么多倍】才麻炊地改主意。
    # 1.0 = 随时见异思迁(会抽风); 太大 = 快饿死了还在睡。
    preempt_ratio: float = 1.5
    # 传播: 【说】和【听】各掷一次骰子, 都过才搭桥(见 engine._notify_due)。
    #   tell_p   = 我这一轮想说给谁听的概率(乘个体 tell_bias)
    #   listen_p = 被搭话的人愿意停下来的概率(默认 1.0 = 都愿意听)
    # 实际成交 ≈ tell_p × listen_p。0 = 不传谣。
    tell_p: float = 0.3
    listen_p: float = 1.0
    # 【跟谁说话】的权重: 同屋(同一个 home = 同一层)的人愿意聊, 路人很少搭话。
    # 这是"关系"的第一块: 信息因此主要在家里流动, 陌生人之间很难传开。
    tell_same_home: float = 1.0
    tell_stranger: float = 0.15
    # —— energy 的【昼夜倍率】(乘在 metabolism.energy 的基准消耗上) ——
    # 白天慢、夜里快: 夜里掉得快 → 困 → 去睡(不是“到点睡觉”的脚本)。
    # 控制点 [(当天分钟, 倍率)], 线性插值; 空 = 恒 1.0。
    energy_rhythm: tuple[tuple[float, float], ...] = ()
    busy_energy_mul: float = 1.8  # 在做事(交互/赶路)时额外消耗倍数
    # —— 囤货 = 目标存量模型(plan.md §6) ——
    # 【没有“每种东西囤几个”的魔法数字】: 目标存量由【保质期】推导 ——
    #     目标 = 每天消耗份数 × 保质期天数 × stock_fill × thrift
    # 也就是“在坏掉之前我吃得完多少”。短保的东西自然囤得少。
    stock_fill: float = 0.8            # 囤到保质期的几成(1.0 = 一直在临期边缘)
    stock_default_days: float = 3.0    # 不会坏的东西(无保质期)按几天囤
    stock_future_weight: float = 1.0   # 预期需求在 urgency 里的权重(w)
    # 计划(承诺)的【基础拉力】: 它参与打分, 不是一个“指令”。
    # 需求要超过 plan_pull × preempt_ratio 才能把日程顶掉 ——
    # 否则任何琐碎需求都会把计划踢开(计划表就等于没用)。
    plan_pull: float = 0.15

    def rhythm_at(self, hour_f: float) -> float:
        """hour_f(0..24) → energy 消耗倍率。纯函数, 供 heartbeat 每 tick 调用。"""
        pts = self.energy_rhythm
        if not pts:
            return 1.0
        minute = (float(hour_f) % 24.0) * 60.0
        prev_m, prev_v = pts[0]
        if minute <= prev_m:
            return prev_v
        for m, v in pts[1:]:
            if minute <= m:
                span = m - prev_m
                if span <= 0.0:
                    return v
                return prev_v + (v - prev_v) * (minute - prev_m) / span
            prev_m, prev_v = m, v
        return prev_v

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
            power_by_signal={str(k): float(v) for k, v in
                             (util.get("power_by_signal") or {}).items()},
            utility_threshold=float(util.get("threshold", 0.05)),
            move_ticks=int(data.get("motion", {}).get("move_ticks", 30)),
            move_m_per_tick=float(data.get("motion", {}).get("move_m_per_tick", 10.0)),
            hp_decay=float(health.get("hp_decay", health.get("decay", 0.0005))),
            hp_regen=float(health.get("hp_regen", health.get("regen", 0.0005))),
            hp_regen_floor=float(health.get("hp_regen_floor", 0.5)),
            hp_override=float(health.get("hp_override", 0.5)),
            cost_lambda=float(util.get("cost_lambda", 0.02)),
            preempt_ratio=float(util.get("preempt_ratio", 1.5)),
            tell_p=float(data.get("social", {}).get("tell_p", 0.3)),
            listen_p=float(data.get("social", {}).get("listen_p", 1.0)),
            tell_same_home=float(data.get("social", {}).get(
                "tell_same_home", 1.0)),
            tell_stranger=float(data.get("social", {}).get(
                "tell_stranger", 0.15)),
            energy_rhythm=tuple(
                (float(m), float(v))
                for m, v in data.get("energy_rhythm", {}).get("points", [])),
            busy_energy_mul=float(
                data.get("activity", {}).get("busy_energy_mul", 1.8)),
            stock_fill=float(data.get("stock", {}).get("fill", 0.8)),
            stock_default_days=float(
                data.get("stock", {}).get("default_days", 3.0)),
            stock_future_weight=float(
                data.get("stock", {}).get("future_weight", 1.0)),
            plan_pull=float(util.get("plan_pull", 0.15)),
        )


def load_config(path: str | Path = "config/sim.toml") -> SimConfig:
    """从 TOML 读配置。默认相对当前工作目录。"""
    with Path(path).open("rb") as f:
        data = tomllib.load(f)
    return SimConfig.from_toml(data)
