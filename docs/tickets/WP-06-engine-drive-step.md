# WP-06 `engine.tick` 驱动 `npc.step`；删 `_apply`

- 状态：done
- 阶段：Step 1
- 依赖：WP-02、WP-03、WP-04、WP-05
- 大小：M

## 目标

去掉 god function，tick 循环只负责“推进人”。

## 改动

`world/engine.py`：

```python
# 5b 之前
port = WorldPortImpl(world, systems, cfg)
for npc_id in due:
    ...
    npc.step(port, cfg, can_preempt)      # ← 取代 build_percept + process + _apply
    # 观测/事件/气泡/决策签名这段保留(现在读 npc.last_intent 或 step 返回的 d)
```

- 删除 `_apply`（逻辑已搬 WP-02/03/04）。
- 保留：`_preempt` / `_can_preempt` / `_sleeping` / `_busy`（Step 2 才动）。
- 保留决策去重、`pending_speech`、`_notify_due`。

## 验收

- `tools/watch.py` / `tools/soak*.py` 跑起来行为与 main 基本一致（用 `test_behavior_soak.py` 兜底）。
- `engine.py` 行数显著下降；`_apply` 不存在。

## 风险

- **行为变化点**：不再“先全员决策再统一执行”（除非 WP-00 选 A）。用
  `test_replay.py` + `test_behavior_soak.py` 兜。
- `port` 每 tick 新建一次（无状态，开销可忽略）。
