"""world/travel —— 跨地点移动(世界进程, 归 World 层)。

只记录逻辑 region 时间线(from region → to region, depart/arrive tick), 供世界判
"在途/忙碌"与前端做动画时间轴。**不含像素坐标**: 画面插值由可视化层按房间几何自己算。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Travel:
    """跨地点移动: 记录出发/到达 region 与 tick(画面动画由可视化层按几何算)。"""
    from_loc: str
    to_loc: str
    depart_tick: int
    arrive_tick: int
