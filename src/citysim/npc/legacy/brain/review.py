"""重评时钟 ReviewClock —— 单个体自持的"距下次重评间隔"。

D7: 决策是间歇性的。清醒度高 => 勤重评(间隔短)；困 => 少重评(间隔长)。
每 tick 用线性拟合(≈零算力)把清醒度(0..1)映射成 tick 间隔，避免每 tick 全量重决策。

本对象"每 Person 各持一份"(内建到分层 Person 的 review 槽): 故不再维护
person_id -> 倒计时的全局映射; 剩余 tick 就是这个对象自己的状态。

只决定"何时想"，不决定"想什么/怎么做"(那是 utility / 后续行为层)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 清醒度 -> 重评间隔 tick 的线性映射参数。
# arousal=1.0(极清醒) => MIN_INTERVAL; arousal=0.0(极困) => MAX_INTERVAL。
# 注: tick=1 游戏分钟, 故间隔单位即"分钟"。
MIN_INTERVAL_TICKS = 1      # 最清醒时每 tick(=1分钟)都想一次
MAX_INTERVAL_TICKS = 48     # 最困时约每 48 分钟才重评一次; 可调上限


def interval_from_arousal(arousal: float, *, rng: Any = None) -> int:
    """把清醒度(0..1)线性映射成"距下次重评的 tick 间隔"。>=1。"""
    a = max(0.0, min(1.0, float(arousal)))
    # 清醒度高 => 间隔接近 MIN; 线性插值
    span = MAX_INTERVAL_TICKS - MIN_INTERVAL_TICKS
    interval = MAX_INTERVAL_TICKS - span * a
    interval = max(MIN_INTERVAL_TICKS, int(round(interval)))
    # 可选抖动, 避免所有人同拍共振
    if rng is not None:
        interval = max(MIN_INTERVAL_TICKS, interval + int(rng.randint(-1, 1)))
    return interval


@dataclass
class ReviewClock:
    """单个体自持的重评时钟。

    语义与旧 ReviewManager 对齐, 但**不按人索引**: 一人一份即是自己, 去掉
    person_id 形参。``remaining_ticks <= 0`` 视为"已到点该重评"(未排程从 0 起
    = 默认到点, 安全)。

    生命周期: ``step()`` 每 tick 推进倒计时; 到点 → 调用方(常为 Person)做一次
    全量重决策后再 ``refresh()`` 按当下清醒度重排下一次。首排用 ``register()``。
    """

    remaining_ticks: int = 0        # 距下次重评还剩几 tick; 0=已到点
    _tick_count: int = field(default=0, repr=False)  # 已推进 tick 数(观测用)

    # --- 生命周期 -----------------------------------------------------
    def register(self, arousal: float, *, rng: Any = None) -> None:
        """首排: 按当前清醒度定首次重评间隔。"""
        self.remaining_ticks = interval_from_arousal(arousal, rng=rng)

    def refresh(self, arousal: float, *, rng: Any = None) -> None:
        """重评后重排下一次; 语义与首排 register 相同(保留别名便于迁移)。"""
        self.remaining_ticks = interval_from_arousal(arousal, rng=rng)

    def schedule_ticks(self, ticks: int) -> None:
        """把下次重评显式排到 ticks tick 之后(如入睡=480/8小时)。

        调用方据此覆盖按清醒度推断的间隔, 用于"这段时间我固定不重评"的场景。
        """
        self.remaining_ticks = max(1, int(ticks))

    def forget(self) -> None:
        """复位为"到点"(立即想重评); 对应旧 ReviewManager.forget(pid)。"""
        self.remaining_ticks = 0

    def step(self) -> None:
        """每 tick 推进一次: 未到点则倒计时 -1。"""
        self._tick_count += 1
        if self.remaining_ticks > 0:
            self.remaining_ticks -= 1

    # --- 查询 ---------------------------------------------------------
    def is_due(self) -> bool:
        """本 tick 是否到点该重评(排程触发 A)。"""
        return self.remaining_ticks <= 0

    def remaining(self) -> int:
        """距下次重评还剩几 tick(D8 观测); >=0(<=0 视为已到点=0)。"""
        return max(0, self.remaining_ticks)
