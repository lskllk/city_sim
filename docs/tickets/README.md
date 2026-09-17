# 票板 — `refactor/world-port`

**EPIC**：世界端口化 + NPC 主动拉。world 持有账本与权限（否决权），NPC 通过
`WorldPort` 的**动词**主动请求；NPC 拥有自己的身体过程（消化节律）。

现状回顾：
- NPC→world 是纯数据（`Intent`/`Percept`/EventBus）✅
- world→NPC 是命令式（`interaction.step` 调 `npc.add_signal`、engine 反写
  `npc.on_failure/note`、`_sleeping/_busy` 注入）❌ ← 本次要消除的
- `engine._apply` 是 god function ❌

> 前提：这套只在要做 **LOD/离线模拟** 或 **world 不再反写 NPC** 时才划算。
> 纯信号数学（封顶/离岗 cost）不需要它，见文末「不在本 EPIC 内」。

## 三阶段

| 阶段 | 目标 | 票 |
|---|---|---|
| **Step 1 端口化** | 调用方向翻转：NPC 自己 observe + 调 `try_*`；信号**仍**由 world 应用 | WP-00..07 |
| **Step 2 intake** | 信号数学搬进 NPC（`Grant` + `_intake` + 消化循环） | WP-08..12 |
| **Step 3 收尾** | 异步 buy / 持有表示 / 回放基线 | WP-13..15 |

## 票一览

| 票 | 标题 | 阶段 | 依赖 | 大小 | 状态 |
|---|---|---|---|---|---|
| WP-00 | 拍板：两阶段 vs 顺序执行 | — | — | S | ✅ done(选 B) |
| WP-01 | `core/ports.py` 契约（WorldPort / Ack / Deny / Grant） | 1 | — | S | ✅ |
| WP-02 | `world/port.py` + `try_move` | 1 | 01 | S | ✅ |
| WP-03 | `try_take`（Interact：校验 + claim） | 1 | 01 | M | ✅ |
| WP-04 | `try_buy`（入队，异步） | 1 | 01 | M | ✅ |
| WP-05 | `Person.step(port)` + Deny 自处理 | 1 | 01,00 | M | ✅ |
| WP-06 | `engine.tick` 驱动 `npc.step`；删 `_apply` | 1 | 02,03,04,05 | M | ✅ |
| WP-07 | Step 1 调用签名重钉（测试） | 1 | 06 | M | ✅ |
| WP-08 | `Grant` + `Person._intake` 消化循环 | 2 | 07 | M | ✅ |
| WP-09 | `InteractionSystem` 退化为 claim 表 | 2 | 08 | M | ✅ |
| WP-10 | `effects.py` 边界：`on_start/on_complete` 编译进 Grant | 2 | 08 | M | ✅ |
| WP-11 | `sleep` / `busy` 由 NPC 自持 | 2 | 09 | S | ✅ (sleep) |
| WP-12 | 中止语义：intake 暂停、不再“中止也扣饭” | 2 | 08,09 | S | ✅ |
| WP-13 | 异步 buy 通道（`bought` 事件 → NPC） | 3 | 06 | M | ✅ |
| WP-14 | `held_by` 持有表示 | 3 | 08 | M | ❌ 不做（用户明确不要“带货”） |
| WP-15 | 回放/确定性基线重钉 | 3 | 06 | M | ✅ |

## 铁律（每票都不得破）

1. **绝不把 `World` / `Entity` 交给 NPC**——只给 `Grant` / `Percept` / `Deny` 值对象。
2. **一次 request 在 world 内原子**：校验→改账→发事件不可被打断。
3. **NPC 只对已存在的世界对象发动词**，不能断言事实/创建物品（造物走 world 配方）。
4. **响应是可序列化纯数据**——回放与测试唯一能钉的东西。
5. `npc/` 不得 `import citysim.world`（`tests/test_import_layers.py`）。

## 不在本 EPIC 内（已达成、独立票）

- 食物按真实缺口封顶：`_score_candidates` 对 `now` 做 `min(value, need)`。
- 上班离岗 cost = 日薪（旷工）：`_score_candidates` 加 `leave_cost`。
- 修 `work_leave_floor` 0.35 无迟滞导致的中止吃饭/上厕所。
