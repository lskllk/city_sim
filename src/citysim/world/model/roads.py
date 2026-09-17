"""world/model/roads —— 路网图 + 最短路(纯几何/图论, 不依赖 World/Person)。

数据来源: scene 的 `map` 段(编辑器导出) = `nodes`(id→xy) + `edges`(id→{a,b,geom,oneway,speed,width})。

只做两件事:

1. **接入**: 把建筑门点(P)投影到路网上 —— 优先投影到边的线段内部(可分裂), 端点上则直接用节点。
2. **最短路**: 在节点图 + 两个临时接入点上跑 Dijkstra, 产出折线 waypoints + 里程 + 耗时。

铁律: 本模块是纯函数式的几何/图论, 不 import World, 不碰 rng, 同输入同输出。
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

Point = tuple[float, float]

_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class Route:
    """一条可渲染的路径: 折线(含门点) + 里程(米) + 耗时(tick)。"""
    waypoints: tuple[Point, ...]
    length: float
    ticks: int


# ----------------------------------------------------------------------
# 基础向量/几何
# ----------------------------------------------------------------------
def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _mul(a: Point, k: float) -> Point:
    return (a[0] * k, a[1] * k)


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _polyline_length(pts: list[Point]) -> float:
    return sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _project(p: Point, a: Point, b: Point) -> tuple[float, Point, float]:
    """p 在线段 ab 上的投影 → (参数 u∈[0,1], 投影点, 距离)。"""
    ab = _sub(b, a)
    l2 = ab[0] * ab[0] + ab[1] * ab[1]
    if l2 <= 1e-12:
        return 0.0, a, _dist(p, a)
    u = ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / l2
    u = min(1.0, max(0.0, u))
    q = _add(a, _mul(ab, u))
    return u, q, _dist(p, q)


# ----------------------------------------------------------------------
# 路网
# ----------------------------------------------------------------------
class RoadGraph:
    """scene `map` 段 → 可寻路的路网。`route()` 按需临时分裂被接入的边。"""

    def __init__(self, map_data: dict | None, m_per_tick: float = 10.0) -> None:
        self.m_per_tick = max(0.001, float(m_per_tick))
        self.coords: dict[str, Point] = {}
        self.edges: list[dict] = []
        self._build(map_data or {})

    # --- 构建 ---------------------------------------------------------
    def _build(self, m: dict) -> None:
        for nid, nd in (m.get("nodes") or {}).items():
            if not isinstance(nd, dict):
                continue
            xy = nd.get("xy")
            if isinstance(xy, list) and len(xy) >= 2:
                self.coords[str(nid)] = (float(xy[0]), float(xy[1]))
        for eid, ed in (m.get("edges") or {}).items():
            if not isinstance(ed, dict):
                continue
            a, b = str(ed.get("a", "")), str(ed.get("b", ""))
            pa, pb = self.coords.get(a), self.coords.get(b)
            if pa is None or pb is None:
                continue
            geom = [(float(p[0]), float(p[1]))
                    for p in (ed.get("geom") or [])
                    if isinstance(p, list) and len(p) >= 2]
            if len(geom) < 2:
                geom = [pa, pb]
            if _dist(geom[0], pa) > _dist(geom[-1], pa):
                geom.reverse()                    # 保证 geom 方向 = a → b
            self.edges.append({
                "id": str(eid), "a": a, "b": b, "pts": geom,
                "oneway": bool(ed.get("oneway", False)),
                "speed": max(0.05, float(ed.get("speed", 0.0) or 1.0)),
                "length": _polyline_length(geom),
            })

    @property
    def ok(self) -> bool:
        """有可用路网(至少一条边)才值得寻路; 否则交回上层降级。"""
        return bool(self.edges)

    # --- 接入 ---------------------------------------------------------
    def _attach_of(self, p: Point) -> tuple[float, int, int, float, Point, str | None] | None:
        """最近的路网接入点 → (距离, 边下标, 段下标, u, 投影点, 端点节点id|None)。

        落在折线两端 → 直接挂到节点; 落在中间 → 需要分裂该边。
        """
        best = None
        for ei, e in enumerate(self.edges):
            pts = e["pts"]
            last = len(pts) - 2
            for si in range(len(pts) - 1):
                u, q, d = _project(p, pts[si], pts[si + 1])
                if best is None or d < best[0] - _EPS:
                    node = None
                    if si == 0 and u <= _EPS:
                        node = e["a"]
                    elif si == last and u >= 1.0 - _EPS:
                        node = e["b"]
                    best = (d, ei, si, u, q, node)
        return best

    # --- 寻路 ---------------------------------------------------------
    def route(self, src: Point, dst: Point) -> Route | None:
        """门点 → 门点 的最短路。无路网 / 接不上 / 不连通 → None(上层降级)。"""
        if not self.ok:
            return None
        ha, hb = self._attach_of(src), self._attach_of(dst)
        if ha is None or hb is None:
            return None

        coords = dict(self.coords)   # 仅用于分裂时登记临时接入点(便于调试)
        graph: dict[str, list[tuple[str, float, list[Point]]]] = {}

        def link(u: str, v: str, w: float, pts: list[Point], both: bool = True) -> None:
            graph.setdefault(u, []).append((v, w, pts))
            if both:
                graph.setdefault(v, []).append(
                    (u, w, list(reversed(pts))))

        for e in self.edges:
            link(e["a"], e["b"], e["length"], list(e["pts"]), not e["oneway"])
            graph.setdefault(e["b"], [])

        attach: dict[str, tuple[str, float]] = {}
        for tag, hit in (("a", ha), ("b", hb)):
            d, ei, si, u, q, node = hit
            if node is not None:
                attach[tag] = (node, d)
                continue
            e = self.edges[ei]
            pts = e["pts"]
            vk = f"@attach_{tag}"
            coords[vk] = q
            head = pts[:si + 1] + [q]
            tail = [q] + pts[si + 1:]
            graph[e["a"]] = [x for x in graph.get(e["a"], []) if x[0] != e["b"]]
            graph[e["b"]] = [x for x in graph.get(e["b"], []) if x[0] != e["a"]]
            link(e["a"], vk, _polyline_length(head), head, not e["oneway"])
            link(vk, e["b"], _polyline_length(tail), tail, not e["oneway"])
            attach[tag] = (vk, d)

        start, da = attach["a"]
        goal, db = attach["b"]
        best = self._dijkstra(graph, start, goal)
        if best is None:
            return None

        road_pts, road_len = best
        way: list[Point] = [src, *road_pts, dst]
        total = da + road_len + db
        return Route(waypoints=tuple(way), length=total,
                     ticks=max(1, int(round(total / self.m_per_tick))))

    @staticmethod
    def _dijkstra(graph, start: str, goal: str
                  ) -> tuple[list[Point], float] | None:
        """→ (折线, 里程); 不连通返回 None。"""
        inf = float("inf")
        dist: dict[str, float] = {start: 0.0}
        prev: dict[str, tuple[str, list[Point]]] = {}
        pq: list[tuple[float, str]] = [(0.0, start)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, inf):
                continue
            if u == goal:
                break
            for v, w, pts in graph.get(u, ()):
                nd = d + w
                if nd < dist.get(v, inf) - _EPS:
                    dist[v] = nd
                    prev[v] = (u, pts)
                    heapq.heappush(pq, (nd, v))
        if goal not in dist:
            return None

        chain = [goal]
        while chain[-1] != start:
            chain.append(prev[chain[-1]][0])
        chain.reverse()

        way: list[Point] = []
        for i in range(len(chain) - 1):
            u, v = chain[i], chain[i + 1]
            pts = next(p for (vv, _w, p) in graph[u] if vv == v)
            way.extend(pts if not way else pts[1:])
        return way, dist[goal]
