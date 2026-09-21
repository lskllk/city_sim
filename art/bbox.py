"""SVG 内容包围盒 —— 量「画的东西占画布多少」。

为什么需要：一张图在代码里看不出"画得太小"。32×32 的画布上画个 5×5 的图形，
XML 合法、尺寸合规、颜色合法，所有检查都过 —— 但人一看就是大小不一。

所以把「填充率」变成可检查的数字。
"""
from __future__ import annotations

import pathlib
import re

NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _arc_pts(p0, rx, ry, rot_deg, large, sweep, p1) -> list[tuple[float, float]]:
    """椭圆弧采样点。SVG 的 A 命令是终点式参数化，要先换成圆心式。

    ★ 别拿"起点 ± 半径"当控制点 —— 半圆会被算到圆心左边一大截，
      量出来的包围盒中心是歪的（踩过）。
    """
    import math

    if rx == 0 or ry == 0 or p0 == p1:
        return []
    phi = math.radians(rot_deg)
    cosp, sinp = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1p, y1p = cosp * dx + sinp * dy, -sinp * dx + cosp * dy
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:                                   # 半径不够大，按规范放大
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(num / den, 0.0)) * (-1 if large == sweep else 1)
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cosp * cxp - sinp * cyp + (p0[0] + p1[0]) / 2
    cy = sinp * cxp + cosp * cyp + (p0[1] + p1[1]) / 2

    def ang(ux, uy, vx, vy):
        d = (ux * vx + uy * vy) / (math.hypot(ux, uy) * math.hypot(vx, vy))
        a = math.acos(max(-1.0, min(1.0, d)))
        return -a if ux * vy - uy * vx < 0 else a

    th1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = ang((x1p - cxp) / rx, (y1p - cyp) / ry,
              (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    elif sweep and dth < 0:
        dth += 2 * math.pi

    pts = []
    for i in range(17):                           # 17 个采样点够量包围盒了
        th = th1 + dth * i / 16
        x, y = rx * math.cos(th), ry * math.sin(th)
        pts.append((cosp * x - sinp * y + cx, sinp * x + cosp * y + cy))
    return pts


def _pts_from_path(d: str) -> list[tuple[float, float]]:
    """把 path 的 d 拆成坐标点。曲线取控制点（略微高估，够用了）。"""
    out: list[tuple[float, float]] = []
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    cmd = ""
    i = 0
    toks = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|" + NUM.pattern, d)
    while i < len(toks):
        t = toks[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t
            i += 1
            if cmd in "Zz":
                cur = start
                continue
        lower = cmd.islower()
        def take(n: int) -> list[float]:
            nonlocal i
            vals = [float(x) for x in toks[i:i + n]]
            i += n
            return vals
        try:
            if cmd in "Mm":
                x, y = take(2)
                cur = (cur[0] + x, cur[1] + y) if lower else (x, y)
                start = cur
                cmd = "l" if lower else "L"          # 后续隐式 lineto
            elif cmd in "Ll":
                x, y = take(2)
                cur = (cur[0] + x, cur[1] + y) if lower else (x, y)
            elif cmd in "Hh":
                x = take(1)[0]
                cur = (cur[0] + x, cur[1]) if lower else (x, cur[1])
            elif cmd in "Vv":
                y = take(1)[0]
                cur = (cur[0], cur[1] + y) if lower else (cur[0], y)
            elif cmd in "Cc":
                a = take(6)
                if lower:
                    a = [a[0] + cur[0], a[1] + cur[1], a[2] + cur[0],
                         a[3] + cur[1], a[4] + cur[0], a[5] + cur[1]]
                out += [(a[0], a[1]), (a[2], a[3]), (a[4], a[5])]
                cur = (a[4], a[5])
            elif cmd in "Ss":
                a = take(4)
                if lower:
                    a = [a[0] + cur[0], a[1] + cur[1], a[2] + cur[0], a[3] + cur[1]]
                out += [(a[0], a[1]), (a[2], a[3])]
                cur = (a[2], a[3])
            elif cmd in "Qq":
                a = take(4)
                if lower:
                    a = [a[0] + cur[0], a[1] + cur[1], a[2] + cur[0], a[3] + cur[1]]
                out += [(a[0], a[1]), (a[2], a[3])]
                cur = (a[2], a[3])
            elif cmd in "Tt":
                a = take(2)
                p = (a[0] + cur[0], a[1] + cur[1]) if lower else (a[0], a[1])
                out.append(p)
                cur = p
            elif cmd in "Aa":
                a = take(7)
                p = (a[5] + cur[0], a[6] + cur[1]) if lower else (a[5], a[6])
                out += _arc_pts(cur, abs(a[0]), abs(a[1]), a[2], a[3], a[4], p)
                out.append(p)
                cur = p
            else:
                i += 1
        except (IndexError, ValueError):
            break
        out.append(cur)
    return out


def content_bbox(svg_text: str) -> tuple[float, float, float, float] | None:
    """返回被画到的 (x0, y0, x1, y1)。只看几何，不看透明度。"""
    xs: list[float] = []
    ys: list[float] = []

    def add(x: float, y: float) -> None:
        xs.append(x)
        ys.append(y)

    for m in re.finditer(
            r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"', svg_text):
        x, y, w, h = map(float, m.groups())
        add(x, y); add(x + w, y + h)
    for m in re.finditer(r'<circle cx="([-\d.]+)" cy="([-\d.]+)" r="([\d.]+)"', svg_text):
        cx, cy, r = map(float, m.groups())
        add(cx - r, cy - r); add(cx + r, cy + r)
    for m in re.finditer(
            r'<ellipse cx="([-\d.]+)" cy="([-\d.]+)" rx="([\d.]+)" ry="([\d.]+)"', svg_text):
        cx, cy, rx, ry = map(float, m.groups())
        add(cx - rx, cy - ry); add(cx + rx, cy + ry)
    for m in re.finditer(r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"',
                         svg_text):
        x1, y1, x2, y2 = map(float, m.groups())
        add(x1, y1); add(x2, y2)
    for m in re.finditer(r'<path[^>]*?\bd="([^"]+)"', svg_text):
        for x, y in _pts_from_path(m.group(1)):
            add(x, y)

    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def fill_ratio(svg_path: pathlib.Path) -> tuple[int, int, float, float] | None:
    """(画布宽, 画布高, 横向填充比, 纵向填充比)。"""
    s = svg_path.read_text(encoding="utf-8")
    m = re.search(r'width="(\d+)" height="(\d+)"', s)
    if not m:
        return None
    W, H = int(m.group(1)), int(m.group(2))
    bb = content_bbox(s)
    if not bb:
        return W, H, 0.0, 0.0
    x0, y0, x1, y1 = bb
    return W, H, (x1 - x0) / W, (y1 - y0) / H


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    d = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "art/out")
    rows = []
    for f in sorted(d.rglob("*.svg")):
        r = fill_ratio(f)
        if not r:
            continue
        rows.append((str(f.relative_to(d)), *r))
    rows.sort(key=lambda r: min(r[3], r[4]))
    print(f"{'文件':38s} {'画布':>9s} {'横向':>6s} {'纵向':>6s}")
    for n, W, H, fr, fh in rows:
        flag = "  ← 画得太小" if min(fr, fh) < 0.7 else ""
        print(f"{n:38s} {W:4d}×{H:<4d} {fr:6.2f} {fh:6.2f}{flag}")


# ── 按【颜色】取包围盒 ────────────────────────────────────────────────────
# 用途：查「头发/帽子有没有长在头上」。头和头发都是已知颜色的图形，
# 所以不用识别形状，直接按 fill 把两组分开量中心就行。

_ELEM = re.compile(r"<(rect|circle|ellipse|line|path)\b([^>]*?)/?>", re.S)


def _attrs(s: str) -> dict[str, str]:
    return {k: v for k, v in re.findall(r'([\w:-]+)="([^"]*)"', s)}


def _elem_bbox(tag: str, at: dict[str, str]) -> tuple[float, float, float, float] | None:
    try:
        if tag == "rect":
            x, y = float(at["x"]), float(at["y"])
            return x, y, x + float(at["width"]), y + float(at["height"])
        if tag == "circle":
            cx, cy, r = float(at["cx"]), float(at["cy"]), float(at["r"])
            return cx - r, cy - r, cx + r, cy + r
        if tag == "ellipse":
            cx, cy = float(at["cx"]), float(at["cy"])
            rx, ry = float(at["rx"]), float(at["ry"])
            return cx - rx, cy - ry, cx + rx, cy + ry
        if tag == "line":
            x1, y1, x2, y2 = (float(at[k]) for k in ("x1", "y1", "x2", "y2"))
            return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
        if tag == "path" and "d" in at:
            pts = _pts_from_path(at["d"])
            if pts:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                return min(xs), min(ys), max(xs), max(ys)
    except (KeyError, ValueError):
        return None
    return None


def bbox_by_fill(svg_text: str, color: str) -> tuple[float, float, float, float] | None:
    """所有 fill == color 的图形的总包围盒。"""
    want = color.lower()
    boxes = []
    for m in _ELEM.finditer(svg_text):
        at = _attrs(m.group(2))
        if at.get("fill", "").lower() != want:
            continue
        bb = _elem_bbox(m.group(1), at)
        if bb:
            boxes.append(bb)
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def biggest_circle_by_fill(svg_text: str, color: str):
    """fill == color 的最大圆 —— 小人身上就是那颗头。"""
    want, best = color.lower(), None
    for m in re.finditer(r"<circle\b([^>]*?)/?>", svg_text):
        at = _attrs(m.group(1))
        if at.get("fill", "").lower() != want:
            continue
        try:
            c = (float(at["cx"]), float(at["cy"]), float(at["r"]))
        except (KeyError, ValueError):
            continue
        if best is None or c[2] > best[2]:
            best = c
    return best


def elements_by_fill(svg_text: str, color: str) -> list[tuple[str, tuple[float, float, float, float]]]:
    """[(tag, bbox)] —— 所有 fill == color 的图形，按出现顺序。"""
    want = color.lower()
    out = []
    for m in _ELEM.finditer(svg_text):
        at = _attrs(m.group(2))
        if at.get("fill", "").lower() != want:
            continue
        bb = _elem_bbox(m.group(1), at)
        if bb:
            out.append((m.group(1), bb))
    return out


def biggest_by_fill(svg_text: str, color: str):
    """fill == color 里【包围盒面积最大】的那块。返回 (tag, bbox, 中心x)。

    为什么挑"最大的一块"而不是整个色的包围盒：
    帽子有帽顶 + 帽檐两块，把它们的包围盒合起来算中心，
    帽檐会把偏移抵消掉（踩过）—— 合起来量反而是错的。
    """
    els = elements_by_fill(svg_text, color)
    if not els:
        return None
    tag, bb = max(els, key=lambda e: (e[1][2] - e[1][0]) * (e[1][3] - e[1][1]))
    return tag, bb, (bb[0] + bb[2]) / 2
