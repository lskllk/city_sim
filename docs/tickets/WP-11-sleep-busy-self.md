# WP-11 `sleep` / `busy` 由 NPC 自持

- 状态：todo
- 阶段：Step 2
- 依赖：WP-09
- 大小：S

## 目标

消掉 world 反向告诉 NPC“你在睡/你在忙”。

## 改动

- `engine._sleeping(world, systems, pid)` / `_busy(...)` 不再注入 `heartbeat`。
- `Person` 从**自己的状态**推：当前 `_intake`/活动里有没有 `sleepable`/`mode=="freeze"`；
  busy = 有进行中的 `_intake` 或在 travel（travel 可由 port/自身字段知道）。

## 验收

- `tests/test_energy_rhythm.py`（睡眠冻结 energy、busy 掉得快）仍绿。
- 单测：`_intake` 里挂一个 `mode="freeze"` 的 Grant → energy 不再下降；完成后回满
  （对应 `bed_basic` 的 `on_complete`）。

## 风险

- “在 travel”现在是 `systems.travel`，NPC 不持有 → 需要 `port` 提供一个只读的
  “我在移动中吗”，或 Person 自己记一个 flag（`try_move` 成功后置位）。
