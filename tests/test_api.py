"""api 门面测试 —— 守住"读到哪儿为止"。

三件事(分层纪律那两条在 `tools/check_imports.py`, 由 test_import_layers 负责):
  1 门面自洽: __all__ 里每个名字都能取到, 且不是模块
  2 门面零污染: import citysim.api 不得拉进 fastapi/uvicorn, 也不得拉进游戏层
  3 门面覆盖真实消费者: game/ + tools/ 用到内核的每个名字,
    都必须能从 citysim.api 拿到 —— 否则门面不够用, 人会绕过去
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from citysim import api

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "citysim"
GAME = sorted((SRC / "game").rglob("*.py"))
CONSUMERS = GAME + sorted((ROOT / "tools").glob("*.py"))


def _citysim_imports(path: Path) -> set[tuple[str, str]]:
    """从一个文件里挖出所有 `from citysim.* import X` → (模块全名, X)。

    `import citysim.x` 这种整模块形式以 ("", "<module:citysim.x>") 记下来 ——
    它同样是"绕过门面", 由分层测试处理。
    """
    names: set[tuple[str, str]] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("citysim"):
            names.update((node.module or "", a.name) for a in node.names if a.name != "*")
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("citysim."):
                    names.add(("", f"<module:{a.name}>"))
    return names


def _is_kernel_module(mod: str) -> bool:
    """是不是【内核】模块(即: 它导出的名字应当在门面上)。

    `citysim.game.*` 是游戏层自己, `citysim` 本身是 `from citysim import api`
    —— 这些不属于内核 API, 不参与覆盖检查。
    """
    if mod in ("citysim", "citysim.api"):
        return False
    return not (mod == "citysim.game" or mod.startswith("citysim.game."))


def _citysim_module_paths(path: Path) -> set[str]:
    """挖出所有 `from citysim.X... import` / `import citysim.X...` 的模块全名。"""
    mods: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            m = node.module or ""
            if m.startswith("citysim"):
                mods.add(m)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("citysim"):
                    mods.add(a.name)
    return mods


def test_all_names_resolve() -> None:
    """__all__ 无重复, 每个名字都是真属性, 且不是模块(门面只导名词/动作)。"""
    assert len(api.__all__) == len(set(api.__all__)), " __all__ 有重复项"
    for name in api.__all__:
        assert hasattr(api, name), f"__all__ 写了 {name!r}, 但 api 里没有"
        assert not isinstance(getattr(api, name), types.ModuleType), (
            f"{name!r} 是模块 —— 门面不导出模块, 导具体名字"
        )


def test_facade_covers_consumers() -> None:
    """门面必须够用: game/ + tools/ 用到的【内核】名字都得能从 api 拿到。

    这条测试是门面的"够不够大"的裁判。它红了说明要加导出, 不是在说代码错。
    (game/ 自己内部的 import 不算 —— 那些不是内核 API。)
    """
    missing: dict[str, set[str]] = {}
    for p in CONSUMERS:
        for mod, name in _citysim_imports(p):
            if not _is_kernel_module(mod):
                continue
            if name.startswith("<module:") or not hasattr(api, name):
                missing.setdefault(name, set()).add(p.name)
    assert not missing, "门面缺这些名字(名字 <- 谁在用):\n" + "\n".join(
        f"  {name}  <- {', '.join(sorted(who))}"
        for name, who in sorted(missing.items())
    )


def test_game_only_imports_api() -> None:
    """game/ 只许 import `citysim.api` 和 `citysim.game.*`。

    不许摸 core/ npc/ world/ sim/ gateway/ 的深层模块 —— 那是"绕过门面"。
    同一条规矩在 `tools/check_imports.py`(改 AST 静态检查, 由
    test_import_layers 跑)。这里再验一遍是因为这条最容易破得很隐蔽。
    """
    bad: list[str] = []
    for p in GAME:
        for mod in sorted(_citysim_module_paths(p)):
            if mod in ("citysim", "citysim.api"):
                continue
            if mod == "citysim.game" or mod.startswith("citysim.game."):
                continue
            bad.append(f"  {p.relative_to(ROOT)}  ->  {mod}")
    assert not bad, "game/ 绕过了门面(只许 import citysim.api):\n" + "\n".join(bad)


def test_no_third_party_dependency() -> None:
    """import citysim.api 不得拉进 viz extra, 也不得拉进游戏层。

    内核零依赖是它的资产(离网 / CI / 无头跑都靠它); 而 api 是【内核】的
    公开面, game 在内核之上 —— 反向依赖会让包变成一团。
    """
    code = (
        "import sys, citysim.api\n"
        "bad = [m for m in ('fastapi', 'uvicorn', 'starlette') if m in sys.modules]\n"
        "bad += [m for m in sys.modules if m.startswith('citysim.game')]\n"
        "print(','.join(bad))\n"
        "raise SystemExit(1 if bad else 0)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert proc.returncode == 0, (
        f"api 门面被污染了(不得拉进 viz extra 或游戏层): {proc.stdout.strip()!r}"
    )


@pytest.mark.parametrize(
    "group",
    ["Work", "Unwork", "Shift", "Wage", "Role", "Plan",
     "InteractionDone", "InteractionFailed", "ItemGone", "WagePaid", "Bought"],
)
def test_contract_vocabulary_is_exported(group: str) -> None:
    """两个口的词汇必须全在门面上 —— 它们是架构契约, 不是"有人用了才加"。"""
    assert group in api.__all__
