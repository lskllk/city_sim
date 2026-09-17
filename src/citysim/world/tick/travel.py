"""world/travel —— 跨地点移动(世界进程, 归 World 层)。

记录逻辑 region 时间线(from region → to region, depart/arrive tick), 供世界判
"在途/忙碌"与前端做动画时间轴。

`waypoints` 是**有路网时**的折线(世界坐标, 含两端门点), 供前端按
`(now_tick - depart) / (arrive - depart)` 沿折线插值 —— 前端只画不算。
无路网(或接不上路网)时为空元组, 前端退化为"两地之间直插"。
"""
from __future__ import annotations

from dataclasses import dataclass

Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Travel:
    """跨地点移动: 出发/到达 region + tick + 可选路网折线。"""
    from_loc: str
    to_loc: str
    depart_tick: int
    arrive_tick: int
    waypoints: tuple[Point, ...] = ()


@dataclass(frozen=True, slots=True)
class Roam:
    """一段【闲逛会话】(world 侧登记, 只为去重/busy/展示; fun 由 NPC 自己消化)。"""
    dest: str
    handle: str
    until: int
