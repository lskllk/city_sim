# WP-09 `InteractionSystem` 退化为 claim 表

- 状态：todo
- 阶段：Step 2
- 依赖：WP-08
- 大小：M

## 目标

`InteractionSystem` 不再管信号与进度，只做**占位/容量**。

## 改动

`world/interaction.py`：

- 删除 `step()` 里的 affordances 分摊与 `remaining_ticks` 递减（→ WP-08）。
- `submit` → `claim(pid, entity_id) -> bool`：只做校验 + `claimants.add` + `set_activity`。
- 新增 `consume(pid, handle)` / `release(pid, handle)`：扣 stock、`on_complete` 应用、
  发 `interaction_done` 事件、回收空实体、清记忆（现在 `_finalize` 的后半）。
- `abort` 保留：撤销 claim（中止的语义见 WP-12）。
- 容量 = `stock`（`claimable_by`）不动。

## 验收

- `tests/test_multi_use.py`（3 床 3 人）仍绿。
- `tests/test_interaction_completeness_contract.py`：**事件先于实体回收**的时序契约仍绿。
- 新单测：`claim` 成功后 `consume` 扣 1；`release` 不扣。

## 风险

- “谁来决定完成”从 world 变成 NPC → 需要一个 done 回传（WP-08 的 `port.consume`）。
- `on_complete` 在中止时是否触发，本票先维持旧行为，WP-12 再改。
- 事件发布仍在 world（铁律：事件归 world）。
