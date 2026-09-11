# CitySim — TASK 006

# Plan Table + Interrupt（计划表 + 中断系统）设计冻结

> 状态：**已冻结**（2026-09-11 讨论）。本任务只落地**底层机制**；LLM 计划生成为最后一步。

## 1. 模型：计划 = 定时 Intent 脚本

计划不是"需求引导"，而是**当天有序的 `(at_tick, Intent)` 脚本**，由 LLM 生成：

```
MoveTo(company)      9:00
Interact(workbench)  9:00     ← 同刻串行：先到公司，到达后再 workbench
MoveTo(home)         18:00    ← 到点 = 硬中止 workbench，回家
```

- `MoveTo` 自然完成 = 到达 dest。
- `Interact` 自然完成 = 交互跑完 duration。
- **下一条的 `at_tick` 是当前条目的截止时刻**：到点即硬中止当前条目，推进下一条。
- 同刻多条按列表顺序**串行**（不做并行）。

## 2. 优先级与中断

```
致命 reflex（hunger/thirst/energy/bladder, need >= fallback_need）
    >  计划（PlanEntry 脚本）
    >  idle
```

| 触发 | 当前交互处理 | on_complete |
|---|---|---|
| 计划截止（下一条到点） | **硬中止**（drop，不保留） | **触发** |
| 致命 reflex | **软挂起**（保 remaining_ticks，完了恢复） | 不触发 |
| 自然完成 | — | 触发 |
| 执行失败 | 刷新记忆 + 记失败日志，**跳过该条** | 不触发 |

- **致命 reflex 可打断一切**，包括 `interruptible=false` 的睡觉（Q5）。
- **非致命需求（fun）不进 reflex**，交给 LLM 计划。
- **travel 中不打断**：在途不评估，到站再评估。

## 3. 恢复（高保真）

`reflex` 抢占 → `InteractionSystem.suspend`（存 `remaining_ticks`），reflex 完成后计划回来 → 若人不在目标地点，先 `MoveTo`，再 `resume`（还原剩余进度）。
**截止优先**：若恢复时已过下一条 `at_tick`，中止挂起、直接推进下一条。

## 4. 失败 → 夜间交给 LLM

```
失败 → 记忆刷新(删/冷却, 已有) + Person 失败日志 {tick, intent, target, why}
     → 该条计划 skip
0:00 → 把失败日志 + 现状快照交给 LLM → 次日计划
```
底层只记录 + 执行；"要不要去买吃的"由 LLM 推理。

## 5. LLM 契约

计划条目用**「和什么物体交互」**表达（首选）：

```json
{"id":"a", "at":"09:00", "intent":"interact", "target":"workbench"}
```

- 计划**不写走位**；执行器会自动先 `MoveTo(该物体在记忆里的 located)` 再到场交互（“去某地”是隐式的）。
- 只有“不需任何交互的纯移动”才用 `{"intent":"move_to","dest":<已知地点>}`（如 18:00 下班回家）。
- 买商品：`{"intent":"buy","target":<商店货物id>,"qty":N}`；执行器先到该货物所在地，扣钱减店库存，再把 N 件**合并**进家中的同类容器（同类只保留一个实体，数量记在 stock）。`target` 必须是记忆里已知的货物。
- `target` **只能取自该 NPC 记忆里的 id**（planner 校验，非法丢弃/降级）；`dest` 同理（只限已知地点+home）。
- 夜间生成、缓存进场景/回放。

## 6. 接口（代码形状）

```python
# core/types.py
@dataclass(frozen=True, slots=True)
class Decision:
    intent: Intent
    source: str = "idle"          # "plan" | "reflex" | "idle"

# npc/schedule.py（纯数据/纯逻辑, 不 import world）
@dataclass
class PlanEntry:
    entry_id: str
    at_tick: int
    intent: Intent
    status: str = "pending"       # pending/active/done/dropped

class Schedule:
    current() / peek_next() / deadline() / commit() / complete() / drop()

# world/interaction.py
submit()                      # 同 target 且已在交互 → 继续(不重置 remaining)
suspend(world, pid) -> Suspension | None   # 软挂起, 保进度, 释放 claim
resume(world, npc, susp) -> bool           # 重新 claim + 还原进度
abort(world, pid)             # 硬中止: 触发 on_complete + 消耗 + 回收

# npc/person.py（门面）
decide(cfg, now, can_preempt) -> Decision   # 仲裁: reflex > plan > idle
set_plan(entries) / on_interaction_done(id) / on_failure(...) 记失败日志
```

## 7. 改动清单

1. `core/types.py`：+`Decision`。
2. `npc/schedule.py`（新）：`PlanEntry` + `Schedule` + 单测。
3. `world/interaction.py`：`abort/suspend/resume` + 同 target 继续 + 中止也触发 on_complete。
4. `npc/person.py`：持有 `Schedule` + reflex/plan 执行器 + 失败日志。
5. `world/drive.py`：驱动改为"所有非旅行 NPC"（busy 也要跑，才能抢占）。
6. `world/engine.py`：按 `Decision` 仲裁 → 继续/挂起/中止/提交。
7. `npc/planner.py`（最后）：LLM → PlanEntry[]，带记忆校验 + 缓存 + 降级。
