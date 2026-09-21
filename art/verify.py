#!/usr/bin/env python3
"""art/verify.py —— 校验生成出来的美术资产。

生成的资产不能靠肉眼验收。这个脚本检查五件事：
  ① 清单里每个文件都在，且 SVG 是【合法 XML】
  ② 声明尺寸 == 逻辑尺寸 × authorScale（Pixi 靠这个算缩放，错了就糊或者错位）
  ③ 没有 NaN / undefined / null 混进坐标
  ④ 所有 url(#id) 都指得到对应的 <pattern>（引用不到 = 那块直接不画）
  ⑤ 所有 fill/stroke 都是合法颜色或 url(#)
用法: python art/verify.py
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ART = Path(__file__).resolve().parent
OUT = ART / "out"
STYLE = json.loads((ART / "style.json").read_text(encoding="utf-8"))
PX = STYLE["authorScale"]

HEX = re.compile(r"^#[0-9a-fA-F]{3,8}$")
NAMED = {"none", "currentColor", "transparent"}
PAINT_ATTRS = ("fill", "stroke")
URLPAT = re.compile(r"url\(#([^)]+)\)")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    man = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    assets = man["assets"]
    errors: list[str] = []
    warn: list[str] = []

    print(f"清单: {len(assets)} 个资产 · authorScale={PX} · grid={man['grid']}")

    by_layer: dict[str, int] = {}
    total_bytes = 0
    for a in assets:
        f = OUT / a["file"]
        by_layer[a["layer"]] = by_layer.get(a["layer"], 0) + 1

        # ① 文件在 + 合法 XML
        if not f.exists():
            errors.append(f"{a['file']}: 文件不存在")
            continue
        raw = f.read_text(encoding="utf-8")
        total_bytes += len(raw.encode())
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            errors.append(f"{a['file']}: SVG 不是合法 XML（{e}）")
            continue

        # ② 声明尺寸 == 逻辑 × authorScale
        want = (a["w"] * PX, a["h"] * PX)
        got = (float(root.get("width", 0)), float(root.get("height", 0)))
        if abs(got[0] - want[0]) > 0.01 or abs(got[1] - want[1]) > 0.01:
            errors.append(f"{a['file']}: 声明尺寸 {got} ≠ 逻辑 {a['w']}×{a['h']} × {PX} = {want}")

        # ③ 脏值
        for bad in ("NaN", "undefined", "null", "Infinity"):
            if bad in raw:
                errors.append(f"{a['file']}: 出现 {bad}")

        # ④ url(#id) 必须指得到 <pattern>
        defined = {el.get("id") for el in root.iter() if el.get("id")}
        for m in URLPAT.finditer(raw):
            if m.group(1) not in defined:
                errors.append(f"{a['file']}: url(#{m.group(1)}) 找不到对应的定义（那块不会画）")

        # ⑤b 图形不许超出画布（头被顶边切掉就是这么来的）
        # SVG 的用户坐标是 authorScale 倍，所以比的是 2× 的尺寸
        w_l, h_l = a["w"] * PX, a["h"] * PX
        for el in root.iter():
            tag = el.tag.split("}")[-1]
            def f(x):
                try: return float(x)
                except Exception: return None
            if tag == "rect":
                x0, y0 = f(el.get("x", 0)), f(el.get("y", 0))
                ww, hh = f(el.get("width", 0)), f(el.get("height", 0))
                if None not in (x0, y0, ww, hh) and (x0 < -0.5 or y0 < -0.5
                        or x0 + ww > w_l + 0.5 or y0 + hh > h_l + 0.5):
                    errors.append(f"{a['file']}: rect 出界 "
                                  f"({x0},{y0},{ww}×{hh}) 画布 {w_l}×{h_l}")
            elif tag == "circle":
                ccx, ccy, r = f(el.get("cx", 0)), f(el.get("cy", 0)), f(el.get("r", 0))
                if None not in (ccx, ccy, r) and (ccx - r < -0.5 or ccy - r < -0.5
                        or ccx + r > w_l + 0.5 or ccy + r > h_l + 0.5):
                    errors.append(f"{a['file']}: circle 出界 "
                                  f"(cx={ccx} cy={ccy} r={r}) 画布 {w_l}×{h_l}")
            elif tag == "ellipse":
                ccx, ccy = f(el.get("cx", 0)), f(el.get("cy", 0))
                rx, ry = f(el.get("rx", 0)), f(el.get("ry", 0))
                if None not in (ccx, ccy, rx, ry) and (ccx - rx < -0.5 or ccy - ry < -0.5
                        or ccx + rx > w_l + 0.5 or ccy + ry > h_l + 0.5):
                    errors.append(f"{a['file']}: ellipse 出界 "
                                  f"(cx={ccx} cy={ccy} rx={rx} ry={ry}) 画布 {w_l}×{h_l}")
            elif tag == "path":
                # 只处理"半圆帽"那种 M...A rx ry .. x y 的形式（头发就是这个）
                m = re.search(r"A\s+([\d.]+)\s+([\d.]+)\s+[\d.]+\s+[01]\s+([01])\s+([\d.]+)\s+([\d.]+)", el.get("d", ""))
                if m:
                    ry = float(m.group(2)); ey = float(m.group(5))
                    if ey - ry < -0.5:
                        errors.append(f"{a['file']}: path 圆弧顶出画布 (y={ey} ry={ry})")

        # ⑥ 颜色合法
        for el in root.iter():
            for attr in PAINT_ATTRS:
                v = el.get(attr)
                if v is None or v in NAMED or URLPAT.match(v) or HEX.match(v):
                    continue
                if v.startswith("rgb") or v.startswith("hsl"):
                    continue
                errors.append(f"{a['file']}: {attr}=\"{v}\" 不是合法颜色")

    # 额外：人物帧是否齐
    people = [a for a in assets if "person" in a["tags"]]
    ids = sorted({t for a in people for t in a["tags"] if t.startswith(("n_", "me"))})
    dirs = STYLE["person"]["directions"]
    frames = STYLE["person"]["walkFrames"]
    for cid in ids:
        for d in dirs:
            for fr in range(frames):
                if not any(cid in a["tags"] and d in a["tags"] and f"f{fr}" in a["tags"]
                           for a in people):
                    errors.append(f"人物 {cid} 缺 {d} 走路第 {fr} 帧")
            if not any(cid in a["tags"] and d in a["tags"] and "idle" in a["tags"]
                       for a in people):
                errors.append(f"人物 {cid} 缺 {d} 站立帧")

    print(f"按图层: " + "  ".join(f"{k}:{v}" for k, v in sorted(by_layer.items())))
    print(f"总体积: {total_bytes / 1024:.0f} KB")
    print(f"人物: {len(ids)} 人 × {len(dirs)} 向 × {frames + 1} 帧 = {len(people)} 个文件")

    if errors:
        print(f"\n✗ {len(errors)} 个问题:")
        for e in errors[:40]:
            print("   " + e)
        if len(errors) > 40:
            print(f"   … 还有 {len(errors) - 40} 条")
        return 1
    print("\n✓ 全部通过（文件齐 / XML 合法 / 尺寸对 / 无脏值 / 图案引用有效 / 颜色合法）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
