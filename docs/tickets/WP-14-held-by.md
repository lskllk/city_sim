# WP-14 `held_by` 持有表示（take ↔ put 之间持久）

- 状态：partial
- 阶段：Step 3
- 依赖：WP-08
- 大小：M

## 目标

东西被 NPC 拿走、还没消化完之前，**世界账本里仍然知道它在谁手上**——这样 put/
consume 才有据可查，NPC 也伪造不了。

## 改动

- `Entity` 增加持有表示：`held_by: str = ""`（或 `location_id="carried:<pid>"`，
  二选一，别两套）。
- `try_take`：把实体从来源容器移到持有者；生成 `handle`（world 签发，能校验）。
- `port.consume(pid, handle)`：校验 `held_by==pid` 且 handle 有效 → 扣/回收。
- 新增 `port.try_put(pid, handle, container_id) -> Ack`：校验持有 + 目标容器权限/容量
  → 原子还回去（合并同类 stock）。

## 验收

- 单测：`take` 后 `world` 里该实体 `held_by=="npc"`；伪造 handle → `Deny`；
  同一 handle 二次 `consume` → `Deny`。
- 单测：`take` → `put` 回同一容器 → 数量守恒。

## 风险

- **不要**把 `Entity` 交给 NPC（铁律 1）；`handle` 只是不透明字符串。
- 与 `_deliver`（买回来的东西进家容器）语义要对齐，别造出两个“持有”概念。


## 实际落地(partial)

- **已做**: 端口补齐 `consume(pid, handle)` / `release(pid, handle)`(收尾/归还),
  并加了唯一 `handle`(由 `InteractionSystem.submit` 签发, 带序号)——防止
  “中止后重拿”撞车。
- **暂缓**: `Entity.held_by` 字段与 `try_put`。原因: 现在“谁持有什么”已经由
  `InteractionSystem.active[pid].entity_id/handle` 这本账表达, `held_by` 会变成
  第二份真相; 且没有任何行为需要 `try_put`(归还)。等真出现“手递手/放下”的
  玩法时再上。
