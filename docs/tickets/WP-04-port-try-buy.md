# WP-04 `try_buy`（入队，异步）

- 状态：done
- 阶段：Step 1
- 依赖：WP-01
- 大小：M

## 目标

把 `Buy` 分支搬成端口动词。**注意：买是异步的**——一前台每 tick 服务 1 份，
所以 `try_buy` 只表示“已入队”，货要等柜台服务后走 `bought` 事件（WP-13 完整接线）。

## 改动

`WorldPortImpl.try_buy(pid, item_id, qty) -> Ack`：

- 搬 `_apply` 的 Buy 分支：目标不在同地 → `_execute_buy` 兜底；否则
  `_preempt` + `enqueue_buy(...)`。
- 返回 `Ack(ok=True)` 表示**入队成功**（不是成交）。成交由 `_serve_shops`/`_execute_buy`
  负责（保持不动）。

`engine._apply` 的 `Buy` 分支改为调 `try_buy`。

## 验收

- `tests/test_buy.py`、`tests/test_queue.py`、`tests/test_economy.py` 全绿。
- 新单测：`try_buy` 返回后 `systems.queued[pid]` 有记录、`buy_left` 数量正确；
  未注册公司的店 → 不成交（`_execute_buy` 的 `why`）。

## 风险

- 别把“入队成功”当成“买到了”去写 NPC 记忆——那是 `bought` 事件（WP-13）的事。
- `_preempt` 在端口里调，注意 `_can_preempt` 语义不变。
