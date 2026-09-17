"""npc.brain —— 决策: 由"记忆 + 自身状态"算出下一个 Intent(纯函数)。

  decide.py     入口: 候选 → 打分 → 选优(decide / decide_scored)
  candidates.py 候选收集(记忆里的每一行 → 一条候选)
  scoring.py    打分: 效用 ÷ 成本(含走一趟的净价值)
  stockpile.py  囤货 = 目标存量模型(目标由保质期推导, 不写死数字)
  memory_io.py  记忆的写入与遗忘(感知 → 库; 半衰衰减)

铁律: decide 只读【记忆 + 自身状态】, 绝不看现场(percept/world)。
现场真值只在感知写入与执行失败反证时进入记忆。
"""
from __future__ import annotations

from citysim.npc.brain.decide import (  # noqa: F401
    decide_scored,
    _choose,
)
from citysim.npc.brain.candidates import (  # noqa: F401
    _gather_candidates,
    _self_use,
    MAX_BUY_QTY,
)
from citysim.npc.brain.scoring import (  # noqa: F401
    _score_candidates,
    _net_value,
    drain_per_tick,
    _travel_key,
    DEFAULT_TRAVEL_TICKS,
)
from citysim.npc.brain.stockpile import (  # noqa: F401
    _home_stock,
    _stock_target,
    _future_need,
)
from citysim.npc.brain.memory_io import (  # noqa: F401
    perceive_into,
    forget,
    FORGET_DEFAULT,
)
