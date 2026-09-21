#!/usr/bin/env python3
"""art/verify.py —— 校验生成出来的美术资产。

生成的资产不能靠肉眼验收。这个脚本检查六件事：
  ① 清单里每个文件都在，且 SVG 是【合法 XML】
  ② 声明尺寸 == 逻辑尺寸 × authorScale（Pixi 靠这个算缩放，错了就糊或者错位）
  ③ 没有 NaN / undefined / null 混进坐标
  ④ 所有 url(#id) 都指得到对应的 <pattern>（引用不到 = 那块直接不画）
  ⑤ 所有 fill/stroke 都是合法颜色或 url(#)
  ⑥ 固定格子类（图标/徽章/头像）必须填满画布
  ⑦ 头发/帽子必须长在头上 —— 见 ⑦ 的说明
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
CHARS = json.loads((ART / "characters.json").read_text(encoding="utf-8"))
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

    # ⑥ ★ 固定格子类必须填满自己的画布。
    #    图标/徽章/头像是同一个格子里的东西，大小不齐人一眼就看得出来。
    #    ★ 只能查这一类 —— 夜光层、路虚线、影子本来就该是零星的；
    #      一刀切会把它们全报成错，那种闸很快就会被无视。
    #    ★ 判 max(横, 纵) 而不是 min：长条工位 0.80×0.38 是对的。
    #      阈值 0.72 是按「坐标忘了乘 2」那个 bug 定的 —— 它会掉到 0.35〜0.5。
    from bbox import biggest_by_fill, biggest_circle_by_fill, fill_ratio  # noqa: E402
    FIXED_TILE = {"iicon", "badge", "marker"}
    checked = 0
    for a in assets:
        if a.get("sub") not in FIXED_TILE and a.get("cat") != "C":
            continue
        f = OUT / a["file"]
        if not f.exists():
            continue
        r = fill_ratio(f)
        if not r:
            continue
        W, H, fr, fh = r
        checked += 1
        if max(fr, fh) < 0.72:
            errors.append(f"{a['file']}: 画得太小 —— 只占画布 {fr:.2f}×{fh:.2f}"
                          f"（{W}×{H}）。是不是画的时候坐标没过 u()？")
    print(f"固定格子类: {checked} 个（图标/徽章/头像），填充率下限 0.72")

    # ⑦ ★ 头发/帽子必须【长在头上】。
    #    踩过的坑：头画在 cx+0.8、发盖画在 cx-headR*0.55、帽子和长发又画回 cx ——
    #    三个中心，侧向时帽子明显歪在脑袋旁边，而且前面露出一块光头。
    #
    #    判法：取头发色的图形里【包围盒面积最大的那块】的中心，跟头的圆心比。
    #    ★ 为什么挑最大的一块，而不是整个色的包围盒中心：
    #      帽子有帽顶 + 帽檐两块，合起来算中心时帽檐会把偏移抵消掉 —— 合起来量反而漏报。
    #    ★ 阈值 0.5×头半径：正常"侧向头发往后偏"是 0.32×头半径，
    #      而踩坑的那种偏移是 0.55×头半径 + 0.8 的头前移量 = 约 0.8×头半径，能切开。
    skin_rgb = STYLE["palette"]["skin"]
    hair_of = {c["id"]: CHARS["hairStyles"].get(c["hair"], {}) for c in CHARS["characters"]}
    skin_of = {c["id"]: skin_rgb[c["skin"]] for c in CHARS["characters"]}
    persons = [a for a in assets if "person" in a.get("tags", [])]
    off_checked = 0
    for a in persons:
        cid = next((t2 for t2 in a["tags"] if t2 in hair_of), None)
        if not cid:
            continue
        color = hair_of[cid].get("color")
        if not color:
            continue
        f = OUT / a["file"]
        if not f.exists():
            continue
        s = f.read_text(encoding="utf-8")
        head = biggest_circle_by_fill(s, skin_of[cid])
        big = biggest_by_fill(s, color)
        if not head or not big:
            continue
        off_checked += 1
        delta = abs(big[2] - head[0])
        # ★ 阈值是【固定 0.6 逻辑像素】，不是比例。
        #   头发/帽子一律正对头中心，偏移应该是 0；
        #   0.6px 只留给浮点误差，任何"挂错锚点"的错都比它大
        #   （光是把头发挂回 cx 而不是 headX，侧向就偏 0.8）。
        if delta > 1.2:                      # 1.2 = 0.6 逻辑像素 × authorScale(2)
            errors.append(f"{a['file']}: 头发/帽子没长在头中心 —— 偏了 "
                          f"{delta:.2f}px（上限 1.2 = 0.6 逻辑像素）")
    print(f"头发锚点: {off_checked} 张小人图，偏移上限 0.6 逻辑像素")

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
    print("\n✓ 全部通过（文件齐 / XML 合法 / 尺寸对 / 无脏值 / 图案引用有效 / 颜色合法 / 填充率达标 / 头发长在头上）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
