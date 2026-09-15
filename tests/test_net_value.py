"""净收益 = value − 路上需求自己掉的量。

用户提的模型: 在家吃梨立刻补 0.30; 出门买苹果虽然 value 0.35, 但走 N tick
的路上饿掉一部分 → 真正到手没那么多。**任何需求通用**(hunger/energy/bladder)。

这样"出门的代价"就是需求自己的物理消耗(不再靠"走路折多少钱"那种估算);
长途尤其明显 —— 这也是"更近的店"该有的优势。
"""
from __future__ import annotations

from citysim.core.config import load_config
from citysim.npc.brain import _net_value, drain_per_tick

CFG = load_config("config/sim.toml")


def test_drain_is_generic_over_signals() -> None:
    """任何信号都能问"每 tick 掉多少" —— 不写死 hunger。"""
    for sig in ("hunger", "energy", "bladder"):
        assert drain_per_tick(CFG, sig, 12.0) > 0.0, sig
    assert drain_per_tick(CFG, "hp", 12.0) == 0.0     # hp 不是代谢掉的
    assert drain_per_tick(CFG, "nope", 12.0) == 0.0


def test_energy_drain_follows_day_night_curve() -> None:
    """energy 用昼夜曲线: 入夜(21:00)掉得比正午快(所以"入夜出门"更亏)。"""
    dusk = drain_per_tick(CFG, "energy", 21.0)
    noon = drain_per_tick(CFG, "energy", 12.0)
    assert dusk > noon * 3.0, (dusk, noon)


def test_net_value_subtracts_the_trip() -> None:
    """走 N tick → 净收益 = value − 路上掉掉的量 × 走路放大系数; 不走 = 原值。"""
    m = 12.0          # 小时(与 SimConfig.rhythm_at 同单位)
    per = 1.0
    ticks = 100
    loss = drain_per_tick(CFG, "hunger", m, per, busy=True) * ticks         * CFG.travel_penalty
    assert loss > 0.0
    assert abs(_net_value(CFG, "hunger", 0.5, ticks, per, m) - (0.5 - loss)) < 1e-9
    assert _net_value(CFG, "hunger", 0.5, 0, per, m) == 0.5      # 不用走 → 不打折


def test_travel_penalty_makes_distance_hurt_more() -> None:
    """走路放大系数 > 1 = 近距离偏好: 同样一趟, 远的更亏。"""
    assert CFG.travel_penalty >= 1.0
    m, per = 12.0, 1.0
    far_1x = _net_value(CFG, "hunger", 0.5, 60, per, m)
    # 直接验系数: 走 0 tick 不打折; 走得越远扣得越多(单调)
    assert _net_value(CFG, "hunger", 0.5, 0, per, m) == 0.5
    assert _net_value(CFG, "hunger", 0.5, 30, per, m)         > _net_value(CFG, "hunger", 0.5, 60, per, m)
    assert far_1x < 0.5


def test_trip_cost_is_amortized_over_quantity() -> None:
    """一趟的路费按【买几份】摊: 只买 1 个 → 近的好; 一次囤 16 份 → 远近差不多。

    这是用户定的口径: 买一个近点好, 买得多路费不该成为劣势。
    """
    m, per = 12.0, 1.0
    one = _net_value(CFG, "hunger", 0.30, 29, per, m, qty=1)
    many = _net_value(CFG, "hunger", 0.30, 29, per, m, qty=16)
    assert many > one, (many, one)                    # 摊薄 → 亏得少
    # 摊到 16 份 ≈ 原价的 1/16 那么点损失
    base = 0.30
    assert abs((base - many) - (base - one) / 16.0) < 1e-9


def test_near_shop_wins_when_buying_one_far_shop_ties_when_bulk() -> None:
    """买 1 个: 近店 > 远店; 买 16 份: 两者几乎一样。"""
    m, per = 12.0, 1.0
    near1 = _net_value(CFG, "hunger", 0.30, 5, per, m, qty=1)
    far1 = _net_value(CFG, "hunger", 0.30, 29, per, m, qty=1)
    near16 = _net_value(CFG, "hunger", 0.30, 5, per, m, qty=16)
    far16 = _net_value(CFG, "hunger", 0.30, 29, per, m, qty=16)
    assert near1 > far1 * 1.1                         # 买一个 → 近店明显好
    assert abs(near16 - far16) < 0.01                 # 囤货 → 差不多


def test_net_value_never_goes_negative() -> None:
    """走太远 → 净收益 0(而不是负数: 去过一趟反而更饿, 不该变成"倒赔")。"""
    assert _net_value(CFG, "hunger", 0.05, 5000, 1.0, 12.0) == 0.0


def test_long_trip_kills_a_slightly_better_option() -> None:
    """远一点但"更好"的东西, 长途之后净收益反而不如近的。"""
    m = 12.0          # 小时(与 SimConfig.rhythm_at 同单位)
    near = _net_value(CFG, "hunger", 0.35, 10, 1.0, m)      # 近: 略好但走一段
    far = _net_value(CFG, "hunger", 0.40, 400, 1.0, m)      # 远: 更好但走很久
    assert far < near, (far, near)
