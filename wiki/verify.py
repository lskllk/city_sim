#!/usr/bin/env python3
"""wiki/verify.py —— 校验生成出来的 wiki。

生成的页面不能靠肉眼验收。这个脚本查五件事：
  ① 每个 HTML 都是完整的（有 </html>），没有 undefined / NaN 漏进去
  ② 所有内部链接（href/src，剥掉 #锚点）都指得到真实文件
  ③ 每个物品 / 建筑都有对应的单页
  ④ 每个页面都能从首页走到（nav 里五个入口都在）
  ⑤ 页面上出现的物品名，全部能点回它的单页（交叉链接没漏）

用法: python wiki/verify.py
"""
from __future__ import annotations

import pathlib
import re
import sys

WIKI = pathlib.Path(__file__).resolve().parent
ROOT = WIKI.parent
OUT = WIKI / "out"
CFG = ROOT / "config"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if not OUT.exists():
        print("✗ wiki/out/ 不存在 —— 先跑 node wiki/gen.mjs")
        return 1

    pages = sorted(OUT.glob("*.html"))
    errors: list[str] = []

    import json

    items = [json.loads(p.read_text(encoding="utf-8"))
             for p in sorted((CFG / "items").glob("*.json"))]
    blds = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((CFG / "buildings").glob("*.json"))]

    # ① 完整 + 无脏值
    for f in pages:
        h = f.read_text(encoding="utf-8")
        if not h.rstrip().endswith("</html>"):
            errors.append(f"{f.name}: HTML 不完整（没有 </html>）")
        for bad in ("undefined", "NaN", "[object Object]"):
            if bad in h:
                errors.append(f"{f.name}: 出现 {bad}")

    # ② 内部链接都能落地
    for f in pages:
        h = f.read_text(encoding="utf-8")
        for m in re.finditer(r'(?:href|src)="([^"]+)"', h):
            u = m.group(1).split("#")[0]
            if not u or u.startswith(("http", "mailto:")):
                continue
            if not (f.parent / u).resolve().exists():
                errors.append(f"{f.name}: 链接指不到 → {m.group(1)}")

    # ③ 每个物品 / 建筑都有单页
    for it in items:
        if not (OUT / f"item_{it['item_type']}.html").exists():
            errors.append(f"缺页: item_{it['item_type']}.html（{it.get('name')}）")
    for b in blds:
        if not (OUT / f"building_{b['type']}.html").exists():
            errors.append(f"缺页: building_{b['type']}.html（{b.get('name')}）")

    # ④ 导航入口都在
    nav_targets = ["index.html", "items.html", "buildings.html", "scene.html",
                   "art.html", "chars.html", "systems.html"]
    for f in pages:
        h = f.read_text(encoding="utf-8")
        for t in nav_targets:
            if f'href="{t}"' not in h:
                errors.append(f"{f.name}: 导航里缺 {t}")
                break

    # ⑤ 总表里出现的物品名都能点
    items_html = (OUT / "items.html").read_text(encoding="utf-8")
    for it in items:
        if f'item_{it["item_type"]}.html' not in items_html:
            errors.append(f"物品总表没链到 {it['item_type']}（{it.get('name')}）")

    # ⑥ ★ 每种 config 建筑类型都必须有美术，而且建筑页必须精确指向它
    #    （防的是"建筑页拿一个同 kind 的资产来示意"—— 那会让没图的类型看起来有图）
    man_path = ROOT / "art/out/manifest.json"
    if not man_path.exists():
        errors.append("art/out/manifest.json 不存在 —— 先跑 bash art/build.sh")
    else:
        man = json.loads(man_path.read_text(encoding="utf-8"))
        btypes = man.get("buildingTypes", {})
        have = {a["name"] for a in man.get("assets", [])}
        for b in blds:
            base = btypes.get(b["type"])
            if not base:
                errors.append(f"建筑类型没美术: {b['type']}（{b.get('name')}）")
                continue
            if base not in have:
                errors.append(f"buildingTypes 指向不存在的资产: {b['type']} → {base}")
                continue
            page_path = OUT / f"building_{b['type']}.html"
            if page_path.exists():
                h = page_path.read_text(encoding="utf-8")
                if f"bld/{base}.svg" not in h:
                    errors.append(f"building_{b['type']}.html 没贴自己的美术（应贴 {base}）")

    bld_cov = ""
    man_path = ROOT / "art/out/manifest.json"
    if man_path.exists():
        bld_cov = f" · 建筑美术覆盖 {len(json.loads(man_path.read_text(encoding='utf-8')).get('buildingTypes', {}))}/{len(blds)}"

    print(f"页面 {len(pages)} 个 · 物品 {len(items)} · 建筑 {len(blds)}{bld_cov}")
    if errors:
        print(f"\n✗ {len(errors)} 个问题:")
        for e in errors[:30]:
            print("   " + e)
        if len(errors) > 30:
            print(f"   … 还有 {len(errors) - 30} 条")
        return 1
    print("\n✓ 全部通过（页面完整 / 无脏值 / 链接可落地 / 单页齐 / 导航齐 / 交叉链接齐 / 建筑美术覆盖齐）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
