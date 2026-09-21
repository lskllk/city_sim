"""game —— 游戏服务端层。

**内核不知道这个包存在。** 依赖只有一个方向:

    game/  →  citysim.api  →  (core · npc · world · sim · gateway)

`gateway/` 是纯数据桥(场景装载 + 快照投影), 不含游戏判断;
`game/` 知道"玩家 / 老板 / 快进 / 上帝版还是发行版"。

| 文件 | 管什么 |
|---|---|
| `actions.py` | 经营动词: 老板能对世界做的事(只改真值) |
| `lines.py`   | 台词模板池 + 词表: 语义事件 → 人话(内核不碰) |
| `clock.py`   | 快进编排: 档位 → 真实 ticks/秒 |
| `runner.py`  | SimRunner: 拥有世界 · 推进 · 60Hz 推送(观察驱动) |
| `commands.py`| WS 指令表: 名字 → 动作 → reply(玩家说的话) |
| `server.py`  | FastAPI app + WS 端点(接线与启动) |

规矩见 `tests/test_api.py` 与 `tools/check_imports.py`:
game/ 只许 `from citysim import api`, 不许摸内核深层模块。
"""
from __future__ import annotations

from pathlib import Path

# 仓库根(src/citysim/game/__init__.py → parents[3])。
# 配置与日志都用绝对路径 —— 后端进程的工作目录无关紧要
# (Godot 自动拉起后端时尤其重要)。
ROOT = Path(__file__).resolve().parents[3]
