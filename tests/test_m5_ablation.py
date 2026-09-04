"""testm5 第四节消融回归(off/archetype_only/full × seed 1-10)。

工具: tools/ablation.py。回归断言(实测冻结): full/arch 全员吃到(40/40),
off 饿死(0/40, stuck 巨大); full 有知识多样性(0.333)而 arch/off 为 0;
无解释不通的倒挂: full.ate >= arch.ate >= off.ate。
"""
from __future__ import annotations

import sys
from pathlib import Path

import ablation  # noqa: F401  (tools 在 pythonpath)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def test_ablation_kb_value_and_no_inversion() -> None:
    agg = ablation.run_all()
    a, b, c = agg["off"], agg["archetype_only"], agg["full"]
    print(f"\nABLATION: off={a} arch={b} full={c}")
    # off 饿死, KB 档全员吃到
    assert a["ate"] == 0, a
    assert b["ate"] == 40 and c["ate"] == 40, (b, c)
    # 生存(挨饿总 tick): off >> 带 KB 档(无倒挂)
    assert b["stuck_ticks"] <= a["stuck_ticks"], (a, b)
    assert c["stuck_ticks"] <= b["stuck_ticks"] + 1, (b, c)
    # full 是唯一有知识多样性的
    assert c["diversity"] > 0.1, c
    assert b["diversity"] == 0.0 and a["diversity"] == 0.0
