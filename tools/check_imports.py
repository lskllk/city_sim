"""CI 层隔离检查：src/citysim/npc/ 不得反向 import citysim.world。

设计 0.2 硬性编码规范: npc/ 与 world/ 解耦。legacy/(M0~M3 临时迁移目录)
除外——它暂存旧 person/brain, 不参与新架构。挂进 pytest; 命令行直接跑,
命中任一违规即返回退出码 1。
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
NPC = ROOT / "src" / "citysim" / "npc"


def _forbidden(name: str) -> bool:
    """是否命中 citysim.world 路径。"""
    parts = name.split(".")
    return len(parts) >= 2 and parts[0] == "citysim" and parts[1] == "world"


def check() -> list[tuple[pathlib.Path, int]]:
    """返回 [(文件, 行号), ...] —— npc/ 里反向 import world 的违规点。"""
    bad: list[tuple[pathlib.Path, int]] = []
    for p in sorted(NPC.rglob("*.py")):
        if "legacy" in p.parts:
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if _forbidden(a.name):
                        bad.append((p, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if _forbidden(mod):
                    bad.append((p, node.lineno))
                elif mod == "citysim" and any(
                    getattr(a, "name", "") == "world" for a in node.names
                ):
                    bad.append((p, node.lineno))
    return bad


def main() -> None:
    bad = check()
    if bad:
        for p, ln in bad:
            print(f"VIOLATION {p}:{ln}  npc/ 反向 import citysim.world")
        print(f"FAIL: {len(bad)} 处违规")
        sys.exit(1)
    print("OK: npc/ 不依赖 world/")


if __name__ == "__main__":
    main()
