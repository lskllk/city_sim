# WP-13 异步 buy 通道（`bought` 事件 → NPC）

- 状态：done
- 阶段：Step 3
- 依赖：WP-06
- 大小：M

## 目标

买是排队的、异步的：`try_buy` 只入队，成交发生在柜台。让 NPC 在成交后**自己**更新。

## 改动

- `try_buy` 返回 `Ack(ok=True, reason="queued")`。
- 成交（`_execute_buy`）现在直接调 `npc.note(...)` 写送货记忆——改为发
  `bought` 事件（已有），由 NPC 在 `observe`/事件处理里自己 `note`。
- `Person` 增加“从事件更新记忆/钱”的入口（现在 `Percept.events` 会被忽略）。
- 排队放弃（`QUEUE_GIVEUP`）→ `intent_failed`：NPC 自己处理（`_on_denied`）。

## 验收

- `tests/test_buy.py`、`tests/test_queue.py`、`tests/test_economy.py` 绿。
- 单测：入队后等 N tick 成交 → NPC 记忆里出现送货容器行（afford/value/believe=1.0）。

## 风险

- 事件驱动的记忆写入必须**确定性**：`Percept.events` 的 drain 顺序稳定。
- 别让 world 既发事件又写 NPC 记忆（重复）。
