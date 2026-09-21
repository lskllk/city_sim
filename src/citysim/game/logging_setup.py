"""logging_setup —— 把 stdout/stderr 接管到 `.logs/backend.log`。

**只给 `server.py` 用, 别的模块不要 import 它。**

为什么需要: 后端现在默认【无控制台窗口】后台运行(Godot 自动拉起), 没有
控制台 → uvicorn 的日志无处可去。而 uvicorn 的日志 handler 绑定的是
**启动那一刻**的 `sys.stderr`, 所以必须在 import 期间接管, 才能连 uvicorn
自己的日志一起收进文件。

副作用是 import 即改全局状态 —— 所以单独一个模块, 免得有人顺手 import
就把进程的 stdout 换掉了。
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from citysim.game import ROOT


class Tee(io.TextIOBase):
    """把 stdout/stderr 同时写向原流与日志文件(原流不可写时静默跳过)。"""

    def __init__(self, *streams) -> None:
        self._streams = streams

    def write(self, text: str) -> int:  # noqa: D102
        for st in self._streams:
            try:
                st.write(text)
            except Exception:  # noqa: BLE001  (无控制台时 stdout 可能不可写)
                pass
        return len(text)

    def flush(self) -> None:  # noqa: D102
        for st in self._streams:
            try:
                st.flush()
            except Exception:  # noqa: BLE001
                pass


def tee_to_log_file() -> Path | None:
    """接管 stdout/stderr 到 `.logs/backend.log`; 返回日志路径(失败则 None)。

    超过 8MB 时启动前轮转为 `backend.1.log`(只保留一份备份, 不无限长)。
    """
    logdir = ROOT / ".logs"
    try:
        logdir.mkdir(exist_ok=True)
        path = logdir / "backend.log"
        if path.exists() and path.stat().st_size > 8_000_000:
            path.replace(logdir / "backend.1.log")
        f = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    sys.stdout = Tee(sys.stdout, f)   # type: ignore[assignment]
    sys.stderr = Tee(sys.stderr, f)   # type: ignore[assignment]
    return path
