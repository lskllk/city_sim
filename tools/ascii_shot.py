#!/usr/bin/env python3
"""tools/ascii_shot.py —— 把截图转成 ASCII，给看不见图的人（我）核对。

为什么要这个：验收时"数颜色像素"只能证明"有东西"，证明不了"位置对"。
ASCII 是低分辨率的眼睛 —— 铺满没有、路连没连上、房子有没有压在路上、
UI 面板压没压住地图，一眼就看出来。

用法:
    python tools/ascii_shot.py _g.png [每格像素数]
"""
from __future__ import annotations

import sys
from collections import Counter

# 颜色 → 字符。值取 art/style.json 的 palette，不是随便挑的。
CLS = {
    ".": (0x6d, 0x8a, 0x52),   # 草地
    ":": (0x5f, 0x7a, 0x47),   # 草地深
    "#": (0x4c, 0x4a, 0x4a),   # 沥青
    "=": (0xb8, 0xb3, 0xa6),   # 人行道 / 路缘
    "P": (0xf7, 0xf4, 0xee),   # 纸（面板）
    "p": (0xef, 0xeb, 0xe1),   # 纸（次级）
    "S": (0x8c, 0x5b, 0x48),   # 屋顶·砖（商铺）
    "h": (0x7a, 0x6a, 0x5a),   # 屋顶·瓦（住宅）
    "F": (0x6b, 0x71, 0x76),   # 屋顶·灰（工厂/办公）
    "G": (0x8d, 0x9a, 0x86),   # 公共（广场）
    "T": (0x4f, 0x7a, 0x45),   # 树
    "w": (0xd6, 0xc6, 0xa5),   # 墙·米
    "n": (0x1b, 0x2f, 0x52),   # 夜色
    "r": (0xb4, 0x55, 0x2d),   # 强调（选中 / 门）
    "n": (0x26, 0x22, 0x1c),   # 墨（文字）
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    from PIL import Image

    path = sys.argv[1] if len(sys.argv) > 1 else "_g.png"
    cell = int(sys.argv[2]) if len(sys.argv) > 2 else 16
    im = Image.open(path).convert("RGB")
    px = im.load()
    w, h = im.size
    items = list(CLS.items())
    grid = []
    counts = Counter()
    for y in range(0, h, cell):
        row = []
        for x in range(0, w, cell):
            # 取这一小格的中点，别被单像素噪声带跑
            p = px[min(x + cell // 2, w - 1), min(y + cell // 2, h - 1)]
            best, bd = "?", 40
            for ch, c in items:
                d = abs(p[0] - c[0]) + abs(p[1] - c[1]) + abs(p[2] - c[2])
                if d < bd:
                    bd, best = d, ch
            row.append(best)
            counts[best] += 1
        grid.append("".join(row))
    print(f"  {path}  {w}×{h}  每格 {cell}px")
    print(f"  图例  {' '.join(f'{ch}={name}' for ch, name in LEGEND.items())}")
    for i, r in enumerate(grid):
        print(f"  {i * cell:4d} {r}")
    print(f"\n  占比: " + "  ".join(f"{ch} {n * 100 // (len(grid) * len(grid[0]))}%"
                                   for ch, n in counts.most_common(8)))
    return 0


LEGEND = {".": "草", "#": "路", "=": "人行道", "P": "纸", "S": "商", "h": "住",
          "F": "厂", "G": "广场", "T": "树", "w": "墙", "r": "强调", "n": "墨"}

if __name__ == "__main__":
    sys.exit(main())
