"""层隔离检查 —— 三条规矩, 命中任一即退出码 1。

① **`npc/` 不得反向 import `citysim.world`**
   认知与世界各自能独立推理与测试; NPC 只能通过 `core/ports.py` 的动词
   请求世界, 世界只能通过 `Person.notify()` / `assign()` 对 NPC 说话。

② **`citysim/game/**` 只许 import `citysim.api`(与 game 内部)**
   门面 `api.py` 是"读到哪儿为止"的答案。绕过它去摸
   `world.econ.market`, 这个答案就没了 —— 于是"我改游戏要懂多少代码"
   又变成没有答案。

③ **`citysim.api` 不得 import `citysim.game`**
   api 是【内核】的公开面, game 在内核之上。反向依赖会让包变成一团,
   也会把 fastapi 拖进内核(内核零依赖是它的资产)。

挂进 pytest(见 `tests/test_import_layers.py`); 命令行直接跑。
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "citysim"
NPC = SRC / "npc"
GAME = SRC / "game"
API = SRC / "api.py"

# game/ 允许 import 的 citysim 模块前缀(其余一律视为绕过门面)
_GAME_ALLOWED = ("citysim.api", "citysim.game")


def _imports(path: pathlib.Path) -> list[tuple[int, str, str]]:
    """列出文件里所有 `import citysim...` / `from citysim... import ...`。

    返回 [(行号, 被 import 的模块全名, 被 import 的具体名字或 "")]。
    对 `from citysim import x` 这种, 模块是 "citysim", 名字是 "x"。
    """
    out: list[tuple[int, str, str]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "citysim" or a.name.startswith("citysim."):
                    out.append((node.lineno, a.name, ""))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level and not mod:          # from . import x
                continue
            if mod == "citysim" or mod.startswith("citysim."):
                for a in node.names:
                    out.append((node.lineno, mod, a.name))
    return out


def _forbidden_npc(mod: str, name: str) -> bool:
    """规矩 ①: 是不是打到 citysim.world 上。

    两种写法都要看: `from citysim.world import X`(模块就是 world)与
    `from citysim import world`(模块是 citysim, 名字是 world)。
    """
    if mod == "citysim":
        full = f"citysim.{name}"
    elif name in ("", "*"):
        full = mod
    else:
        full = f"{mod}.{name}"
    parts = full.split(".")
    return len(parts) >= 2 and parts[0] == "citysim" and parts[1] == "world"


def _violates_game_facade(mod: str, name: str) -> bool:
    """规矩 ②: game/ 里的一条 import 是否绕过门面。"""
    if mod == "citysim":
        # `from citysim import api` ✓ ; `from citysim import world` ✗
        return name != "api"
    if mod in _GAME_ALLOWED or mod.startswith("citysim.game."):
        return False
    return True


def _violates_api_upward(mod: str, name: str) -> bool:
    """规矩 ③: api 是否反向依赖 game。"""
    if mod == "citysim.game" or mod.startswith("citysim.game."):
        return True
    return mod == "citysim" and name == "game"


def check() -> list[str]:
    """返回所有违规的可读描述(空列表 = 通过)。"""
    bad: list[str] = []

    for p in sorted(NPC.rglob("*.py")):
        if "legacy" in p.parts:
            continue
        for ln, mod, name in _imports(p):
            if _forbidden_npc(mod, name):
                bad.append(f"{_rel(p)}:{ln}  npc/ 反向 import citysim.world")

    for p in sorted(GAME.rglob("*.py")):
        for ln, mod, name in _imports(p):
            if _violates_game_facade(mod, name):
                target = f"{mod}.{name}" if name else mod
                bad.append(f"{_rel(p)}:{ln}  game/ 绕过门面: {target} "
                           f"(只许 citysim.api / citysim.game)")

    if API.exists():
        for ln, mod, name in _imports(API):
            if _violates_api_upward(mod, name):
                bad.append(f"{_rel(API)}:{ln}  api 反向依赖 game")

    return bad


def _rel(p: pathlib.Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def main() -> None:
    bad = check()
    if bad:
        for line in bad:
            print(f"VIOLATION {line}")
        print(f"FAIL: {len(bad)} 处违规")
        sys.exit(1)
    print("OK: 层隔离三条规矩全过 "
          "(npc/!->world/ · game/->api · api!->game)")


if __name__ == "__main__":
    main()
