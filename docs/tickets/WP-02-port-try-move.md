# WP-02 `world/port.py` + `try_move`

- 状态：todo
- 阶段：Step 1
- 依赖：WP-01
- 大小：S

## 目标

新增 world 侧实现体，先搬 `MoveTo` 分支。

## 改动

- 新增 `src/citysim/world/port.py`：

```python
class WorldPortImpl:
    def __init__(self, world, systems, cfg): ...
    def observe(self, pid): return build_percept(self.world, self.world.npcs[pid])
    def try_move(self, pid, dest) -> Ack:
        # 搬 engine._apply 的 MoveTo 分支:
        #   已在途中 / 有 active(可打断?) / same loc / entry_check / route / travel[pid]=Travel
        ...
```

- `engine._apply` 的 `MoveTo` 分支**保留原样**（本票先不删，等 WP-06 统一删），
  `WorldPortImpl.try_move` 与它**共用同一段逻辑**：从 `engine` 抽成
  `world/port.py` 里的函数，`engine._apply` 改为调用它（避免两份真相）。

## 验收

- 单测：`try_move` 到异地 → `systems.travel[pid]` 被设置、`Ack.ok`；
  到同地 → 不设置 travel；`entry_check` 失败 → `Deny/Ack(ok=False, reason)`。
- 现有 `tests/test_roads.py` / `test_access.py` 行为不变。

## 风险

- `_route_between` / `_travel_cost` 目前在 `engine.py`，搬动时注意 `roads` 从
  `systems` 取。
- 别在端口里发事件后又在 engine 发一次（重复）。
