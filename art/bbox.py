"""SVG 内容包围盒 —— 量「画的东西占画布多少」。

为什么需要：一张图在代码里看不出"画得太小"。32×32 的画布上画个 5×5 的图形，
XML 合法、尺寸合规、颜色合法，所有检查都过 —— 但人一看就是大小不一。

所以把「填充率」变成可检查的数字。
"""
from __future__ import annotations

import pathlib
import re

NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


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
                out += [(cur[0] - abs(a[0]), cur[1] - abs(a[1])),
                        (cur[0] + abs(a[0]), cur[1] + abs(a[1]))]
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
