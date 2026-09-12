"""buildings —— 建筑类型库 + 场景自动布局。纯几何, 不依赖 world/渲染。

设计见 docs/building_abstraction.md:
- 类型库 config/buildings/*.json: {type, name, kind, capacity, pattern, aspect, doors}
  doors = 进出口定义(资产逻辑): [{"side": north|south|east|west, "offset": -0.5..0.5}]
- 场景 locations 只写 {type, name?} —— 不写坐标;
- 自动布局: 面积 ∝ capacity(边长=sqrt(cap*aspect)), 按 kind 分区、shelf 打包、
  整体等比缩放铺进画布(等比缩放不破坏"面积∝容量")。
"""
from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass
from math import sqrt
from pathlib import Path

_DIR = Path(__file__).resolve().parents[3] / "config" / "buildings"

_DOOR_RE = re.compile(r"_(\d+)$")   # 地点 id 末尾序号 → 门牌号

GAP = 0.5          # 单位空间里的街道间隙(相对 sqrt(capacity))
MARGIN = 24.0      # 画布留边(px)

# 缺省进出口: 南面临街。doors 属于"资产逻辑定义", 与视觉(资产定义)分离。
DEFAULT_DOOR: dict = {"side": "south", "offset": 0.0}
DOOR_SIDES = ("north", "south", "east", "west")


@dataclass(frozen=True)
class BuildingType:
    type: str
    name: str = ""
    kind: str = "public"
    capacity: int = 10
    pattern: str = "plain"
    aspect: float = 1.0
    doors: tuple[dict, ...] = (DEFAULT_DOOR,)


def _parse_doors(raw) -> tuple[dict, ...]:
    """校验并归一化 doors; 非法项丢弃, 全非法则回退缺省南门。"""
    out: list[dict] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            side = str(item.get("side", "south"))
            if side not in DOOR_SIDES:
                continue
            out.append({"side": side,
                        "offset": max(-0.5, min(0.5, float(item.get("offset", 0.0))))})
    return tuple(out) or (DEFAULT_DOOR,)


def _parse(d: dict) -> BuildingType:
    return BuildingType(
        type=d["type"], name=d.get("name", d["type"]),
        kind=str(d.get("kind", "public")),
        capacity=int(d.get("capacity", 10)),
        pattern=str(d.get("pattern", "plain")),
        aspect=float(d.get("aspect", 1.0)),
        doors=_parse_doors(d.get("doors")),
    )


def door_points(geom: dict, doors) -> list[dict]:
    """房间几何(x,y,w,h) + doors 定义 → 世界坐标进出口点。

    - side: 门所在的外墙(未旋转的房间局部坐标);
    - offset: 沿该墙的归一化偏移(-0.5..0.5), 0=居中; 垂直于墙的边用它;
    - 返回 {side, offset, x, y, nx, ny}: (x,y)=门世界点, (nx,ny)=朝外法线。
    """
    x, y = float(geom.get("x", 0.0)), float(geom.get("y", 0.0))
    w, h = float(geom.get("w", 0.0)), float(geom.get("h", 0.0))
    out: list[dict] = []
    for d in doors or (DEFAULT_DOOR,):
        side = str(d.get("side", "south"))
        off = float(d.get("offset", 0.0))
        if side == "south":
            px, py, nx, ny = x + w * (0.5 + off), y + h, 0.0, 1.0
        elif side == "north":
            px, py, nx, ny = x + w * (0.5 + off), y, 0.0, -1.0
        elif side == "east":
            px, py, nx, ny = x + w, y + h * (0.5 + off), 1.0, 0.0
        else:  # west
            px, py, nx, ny = x, y + h * (0.5 + off), -1.0, 0.0
        out.append({"side": side, "offset": off,
                    "x": round(px, 1), "y": round(py, 1),
                    "nx": nx, "ny": ny})
    return out


@functools.lru_cache(maxsize=2)
def _read(directory: str) -> dict[str, BuildingType]:
    out: dict[str, BuildingType] = {}
    for p in sorted(Path(directory).glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if "type" in d:
            out[d["type"]] = _parse(d)
    return out


def load_building_types(directory: str | Path | None = None) -> dict[str, BuildingType]:
    return _read(str(_DIR if directory is None else Path(directory)))


def clear_cache() -> None:
    _read.cache_clear()


def _pack(need: dict[str, dict], w_canvas: float, h_canvas: float) -> dict[str, dict]:
    """shelf 打包: 按 (kind, -capacity, id) 排序(同类聚成片区), 再等比缩放进画布。"""
    if not need:
        return {}
    order = sorted(need.items(),
                   key=lambda kv: (kv[1]["kind"], -kv[1]["capacity"], kv[0]))
    items: list[tuple[str, float, float]] = []
    for loc_id, v in order:
        cap = max(1, int(v["capacity"]))
        asp = max(0.25, float(v.get("aspect", 1.0)))
        items.append((loc_id, sqrt(cap * asp), sqrt(cap / asp)))

    sum_area = sum(w * h for _, w, h in items)
    # 目标行宽: 让整体块大致匹配画布长宽比
    row_w = max(sqrt(sum_area * (w_canvas / h_canvas)) * 1.2, 1.0)

    pos: dict[str, tuple[float, float, float, float]] = {}
    x = 0.0
    y = 0.0
    row_h = 0.0
    for loc_id, w, h in items:
        if x > 0.0 and x + w > row_w:
            x = 0.0
            y += row_h + GAP
            row_h = 0.0
        pos[loc_id] = (x, y, w, h)
        x += w + GAP
        row_h = max(row_h, h)

    bbox_w = max(x0 + w for x0, _, w, _ in pos.values())
    bbox_h = max(y0 + h for _, y0, _, h in pos.values())
    aw = max(w_canvas - 2.0 * MARGIN, 1.0)
    ah = max(h_canvas - 2.0 * MARGIN, 1.0)
    scale = min(aw / bbox_w, ah / bbox_h)
    ox = (w_canvas - bbox_w * scale) / 2.0
    oy = (h_canvas - bbox_h * scale) / 2.0
    return {
        loc_id: {
            "x": round(ox + x0 * scale, 1),
            "y": round(oy + y0 * scale, 1),
            "w": round(w * scale, 1),
            "h": round(h * scale, 1),
        }
        for loc_id, (x0, y0, w, h) in pos.items()
    }


def _door_no(loc_id: str) -> str:
    """地点 id 的序号后缀 → 门牌号(如 apt_001 → "1 号")。无序号则空。"""
    m = _DOOR_RE.search(loc_id)
    return f"{int(m.group(1))} 号" if m else ""


def build_locations(data: dict) -> dict[str, dict]:
    """scene data → {loc_id: {name, kind, capacity, pattern, x, y, w, h}}。

    - location 带已知 `type` → 解出 kind/capacity/pattern, 由自动布局算几何;
    - 展示名优先级: 显式 `name` > id 序号派生的门牌号 `N 号` > 类型名;
    - location 已带显式 x/y/w/h(向后兼容) → 原样保留;
    - 其余字段透传。
    """
    canvas = data.get("canvas", {})
    w_canvas = float(canvas.get("w", 1280))
    h_canvas = float(canvas.get("h", 800))
    specs = data.get("locations", {})
    types = load_building_types()

    resolved: dict[str, dict] = {}
    for loc_id, spec in specs.items():
        if not isinstance(spec, dict):
            continue
        t = types.get(spec.get("type"))
        if t is not None:
            owner = str(spec.get("owner", ""))
            open_to = [str(x) for x in (spec.get("open_to") or [])]
            resolved[loc_id] = {
                "name": spec.get("name") or _door_no(loc_id) or t.name,
                "kind": t.kind,
                "capacity": int(spec.get("capacity", t.capacity)),
                "pattern": t.pattern,
                "aspect": float(spec.get("aspect", t.aspect)),
                "doors": [dict(d) for d in t.doors],
                # 进入权限: owner=户主, open_to=额外允许的 npc id; public 未指定(None)
                # 时由 World.resolve_access() 根据“有无 owner”封口。
                "owner": owner,
                "open_to": open_to,
                "public": spec.get("public"),
            }
            # 显式几何(编辑器导出的地图)优先: 带 x/y/w/h 就原样保留, 不参与自动布局。
            for gk in ("x", "y", "w", "h"):
                if gk in spec:
                    resolved[loc_id][gk] = float(spec[gk])
        else:
            resolved[loc_id] = dict(spec)

    need = {k: v for k, v in resolved.items() if "x" not in v}
    geom = _pack(need, w_canvas, h_canvas)
    out: dict[str, dict] = {}
    for k, v in resolved.items():
        merged = {**v, **geom.get(k, {})}
        # 进出口世界点(资产逻辑): 用最终几何算, 未知类型回退南门。
        merged["door_points"] = door_points(merged, v.get("doors"))
        out[k] = merged
    return out
