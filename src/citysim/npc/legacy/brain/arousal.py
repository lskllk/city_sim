"""清醒度 arousal —— 决定"人有多警觉、多愿意重新评估处境"。

D7: 清醒度是融合产物 = f(时间相位/生物钟, 精力, 饥饿)，非线性。
时间不并列输入——时间通过生物钟曲线影响清醒度。

返回 0..1：越高越清醒 => 越该高频重评。
"""
from __future__ import annotations

from math import cos, pi

# 生物钟曲线: 深夜(约 3 点)低谷, 下午(约 15 点)峰值。用一条余弦拟合。
TROUGH_HOUR = 3.0   # 低谷时刻(困)
PEAK_HOUR = 15.0    # 峰值时刻(最清醒)


def circadian(hour_f: float) -> float:
    """纯生物钟分量(0..1): 由当日时刻决定, 与个体状态无关。

    用余弦: 在 PEAK_HOUR 最高、TROUGH_HOUR 最低。线性缩放低谷≈0.15、峰值≈1.0。
    """
    # 距峰值的天文相位
    phase = 2.0 * pi * (hour_f - PEAK_HOUR) / 24.0
    base = (cos(phase) + 1.0) / 2.0  # 0..1, 峰值=1
    return 0.15 + 0.85 * base


def arousal(hour_f: float, energy: float, hunger: float) -> float:
    """清醒度 0..1。

    - hour_f : 当日时刻(可含分钟小数, 如 14.5)
    - energy : 精力 0..1(高=精力足)
    - hunger : 饱腹 0..1(高=吃饱; 饿会分神/犯晕)

    组合: 生物钟是主基调, 精力做乘性放大, 饥饿做减性拖累。
    """
    energy = max(0.0, min(1.0, float(energy)))
    hunger = max(0.0, min(1.0, float(hunger)))
    circ = circadian(hour_f)
    # 精力低 => 整体下调(即便生物钟说是白天)
    level = circ * (0.4 + 0.6 * energy)
    # 饥饿(饱腹低) => 轻微拖累清醒
    level -= 0.2 * (1.0 - hunger)
    return max(0.0, min(1.0, level))
