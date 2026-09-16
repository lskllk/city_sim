# WP-10 `effects.py` 边界：`on_start`/`on_complete` 编译进 Grant

- 状态：todo
- 阶段：Step 2
- 依赖：WP-08
- 大小：M

## 目标

把“NPC 侧效果”变成**结构化数据**，避免 `npc/` 认识 `op` 字符串（抽象泄漏）。

## 改动

`world/effects.py` / `world/port.py`：

- 在 `try_take` 里把 `ent.on_start` / `ent.on_complete` **编译**成 `Grant.pending`
  / `Grant.on_done`：只保留 NPC 侧字段 `{signal|field, value|delta|amount}`。
- world 侧 op（`spawn_item` / `consume_self`）留在 world，不进入 Grant。
- `apply_effects` 里 NPC 侧那三个 op（`add_signal`/`set_signal`/`add_pending`）不再被
  world 调用（改由 Person 解释 Grant 的结构化字段）。

## 验收

- `tests/test_effects.py` 改到新路径后绿：`on_start`（简餐 bladder_pending）、
  `on_complete`（床 energy +1.0）效果等价。
- `grep -r "op" src/citysim/npc/` 不应出现 effect op 字符串。

## 风险

- 简餐的 `add_pending` 是 `bladder_pending` 字段（白名单只有它）——保持白名单语义。
- 床的 `on_complete: add_signal energy +1.0` 必须在**消化完成**时应用，不是开始时。
