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

    # ⑦ ★ 美术产物必须已经拷进 wiki/out/a/（wiki 要能单独打包发出去）。
    #    静态 <img> 上面第 ② 条会查；但人物动画、格子这些是 JS 拼路径加载的，
    #    静态检查看不到 —— 所以拿 manifest.json 逐个对。
    if man_path.exists():
        man = json.loads(man_path.read_text(encoding="utf-8"))
        missing = [a["file"] for a in man.get("assets", [])
                   if not (OUT / "a" / a["file"]).exists()]
        if missing:
            errors.append(f"wiki/out/a/ 少了 {len(missing)} 个美术文件"
                          f"（例如 {missing[0]}）—— 先跑 bash art/build.sh")
        else:
            print(f"资源自足: wiki/out/a/ 里 {len(man.get('assets', []))} 个资产齐全")

    # ⑧ ★ 场景里写的每个资产路径都要存在。
    #    场景是 JS 拼出来的，静态 <img> 检查看不到；
    #    路径写错只表现为「场景里少了一块」，很容易被当成"这里没放东西"。
    art_html = (OUT / "art.html").read_text(encoding="utf-8")
    if art_html:
        js = (OUT / "wiki.js").read_text(encoding="utf-8")
        refs = set()
        for m in re.finditer(r'"(ground|bld|attach|props|items|people|road|atm)/[\w./-]+"', js):
            r = m.group(0)[1:-1]
            if r.endswith(("_", "/")):      # 拼接出来的（"props/car_" + n），量不到
                continue
            refs.add(r)
        # 拼接出来的（"props/car_" + n）静态量不到，交给 art/verify.py 的清单
        broken = sorted(r for r in refs if not (OUT / "a" / r).exists())
        if broken:
            errors.append(f"场景里引用了不存在的资产 {len(broken)} 个：{', '.join(broken[:4])}")
        else:
            print(f"场景引用: {len(refs)} 个资产路径全部落地")

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
    print("\n✓ 全部通过（页面完整 / 无脏值 / 链接可落地 / 单页齐 / 导航齐 / 交叉链接齐 / 建筑美术覆盖齐 / 资源自足）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
