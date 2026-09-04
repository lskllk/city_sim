"""M0 DoD: 层隔离 CI 检查(挂进 pytest)。

npc/ 不得 import citysim.world; legacy/(临时)除外。既以函数方式校验,
也以子进程方式跑脚本验证退出码。
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "check_imports.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("check_imports", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_no_npc_to_world_import() -> None:
    assert _load_tool().check() == []


def test_check_imports_script_exits_zero() -> None:
    r = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
