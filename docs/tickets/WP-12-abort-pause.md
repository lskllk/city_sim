# WP-12 中止语义：intake 暂停、不再“中止也扣饭”

- 状态：todo
- 阶段：Step 2
- 依赖：WP-08、WP-09
- 大小：S

## 目标

修掉一个已知别扭：现在 `_finalize(aborted=True)` 仍扣 stock + 触发 `on_complete`
（“中止也照扣一份饭”）。intake 模型下，中止 = **暂停**，食物留在入口。

## 改动

- `world/interaction.py::_finalize(aborted=True)` 不再扣 stock、不再触发
  `on_complete`（改为只 `release` claim）。
- `Person` 侧：被打断时 `_intake` 里的 `_ActiveGrant` **保留**（进度不清零），
  下次接着消化。
- 若要“放回/丢掉”，那是显式 `port.release`（WP-14）。

## 验收

- 单测：吃 meal 第 3 tick 被上班打断 → 不扣 stock、`_intake` 保留、回头接着吃，
  总补充量不变。
- `tests/test_plan_interrupt.py` 的“计划截止硬中止仍触发 on_complete”断言需要改
  （那是世界计划条目，不是 intake 中止）——区分这两者。

## 风险

- 要区分“**计划截止抢占交互**”（可能仍应 on_complete）与“**需求目标被打断**”。
  本票要先把这两类中止的期望行为写清楚再动手。
