"""层隔离 CI 检查(挂进 pytest)。

`tools/check_imports.py` 管三条规矩:
  ① npc/ 不得反向 import citysim.world
  ② game/** 只许 import citysim.api(不许绕过门面摸内核深层)
  ③ citysim.api 不得 import citysim.game

既以函数方式校验, 也以子进程方式跑脚本验证退出码。
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


def test_no_layer_violations() -> None:
    assert _load_tool().check() == []


def test_check_imports_script_exits_zero() -> None:
    r = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
