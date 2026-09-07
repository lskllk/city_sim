# CitySim — TASK 002

# Build the Observation Contract

## 任务目标

在 TASK001 已完成的基础上，把 simulation 当前已经产生的：

```text
Snapshot
Perception
KnowledgeUpdate
Decision
WorldChange
Interaction
Travel
Gossip
```

整理成一个**稳定、明确、可供未来 Observatory 前端消费的 Observation Contract**。

本任务：

> **只处理后端 observation/data flow。**

不得开始 React / Pixi / Rapier / UI 开发。

---

# 1. 已冻结的原则

## 1.1 Simulation 仍然是真相源

Frontend 以后只能消费：

```text
Snapshot
Event
Trace
```

不得自己推断：

```text
perception
knowledge
decision
world mutation
```

---

## 1.2 不新造第二套 EventBus

当前项目已经存在：

```text
world/events.py
systems.ui_events
```

优先基于现有机制扩展。

不要创建：

```text
ObservationBus
UIEventBus
FrontendBus
```

等第二套并行系统。

目标：

```text
Simulation
   ↓
existing EventBus / ui_events
   ↓
Gateway
   ↓
WebSocket
```

---

# 2. 当前任务只解决三个问题

## 问题 A

前端如何获得：

> 当前世界状态？

答案：

```text
Snapshot
```

---

## 问题 B

前端如何知道：

> 刚刚发生了什么？

答案：

```text
Event
```

---

## 问题 C

前端如何知道：

> NPC 为什么这么决定？

答案：

```text
DecisionTrace
```

---

# 3. Snapshot Contract

继续使用：

```text
src/citysim/gateway/snapshot.py
```

不要重新建立 Snapshot 系统。

---

## Snapshot 至少保证

```text
protocol_version
tick
simulation_time
entities
```

NPC 至少：

```text
id
name
archetype_id
location_id
position
signals
intent
travel
last_percept
```

具体字段以当前真实代码为准。

---

# 4. Snapshot 原则

Snapshot 表示：

> **某一个 tick 的当前世界状态。**

Snapshot 不表示：

```text
历史
事件
因果
trace
```

不要把 Event 塞进 Snapshot。

---

# 5. Event Contract

定义统一 Event 数据结构。

建议最少：

```python
{
    "event_id": str,
    "tick": int,
    "type": str,
    "source": str | None,
    "target": str | None,
    "payload": dict
}
```

如果当前项目已有字段命名：

> 优先兼容现有字段。

不要为了“更漂亮”重命名大量已有 event。

---

# 6. Event 类型

当前已有事件继续保留。

至少确认这些类型能够统一发送：

```text
decision
told
bought
npc_died
intent_failed
interaction_done
learned
stock_changed
```

如果当前代码已经存在更多事件：

> 可以继续保留。

不要删除已有事件。

---

# 7. Perception Event

TASK001 已经拥有：

```text
Person.last_percept
PerceptionRecord
```

本任务新增：

```text
perceived
```

事件。

它应该在 perception 成功完成后，由调用侧发出。

---

## 事件至少包含

```text
event_id
tick
type = "perceived"
source = npc_id
target = null
payload
```

payload 至少：

```text
observed_entity_ids
```

如果现有 PerceptionRecord 已经包含更多有价值字段：

直接复用。

不要创建第二套 percept 数据模型。

---

# 8. Knowledge Update Event

继续使用 TASK001 已经实现的：

```text
learned
```

事件。

至少包含：

```text
event_id
tick
type = "learned"
source = npc_id
payload.fact_id
payload.source_kind
```

其中：

```text
source_kind
```

保持：

```text
INJECTED
OBSERVED
TOLD
```

---

# 9. learned 的语义

第一版保持当前 TASK001 行为：

> 只有产生新的 fact_id 时发送 `learned`。

如果是同一个 fact 的 confidence / 内容更新：

当前可以不发送。

不要在 TASK002 扩展成复杂 knowledge history。

将来再处理。

---

# 10. World Change Event

不要实现通用：

```text
deep diff
```

不要建立：

```text
GenericWorldDeltaEngine
```

---

## 优先复用已有事件

例如：

```text
bought
stock_changed
interaction_done
```

这些事件本身就是世界变化的可观察记录。

---

# 11. stock_changed

当前 `pulses.py` 已经发送：

```text
stock_changed
```

保持。

至少保证 payload 包含：

```text
entity / item
before
after
```

如果当前实际字段名字不同：

保持现状并写入 contract。

---

# 12. Bought Event

继续使用现有：

```text
bought
```

不要重新创建：

```text
money_changed
inventory_changed
stock_changed
purchase_completed
```

四套重复事件。

第一版：

> 一个 bought event 携带完整购买结果即可。

---

# 13. Decision Trace Contract

TASK001 已经增加：

```text
DecisionTrace.relevant_signals
```

现在把 trace 正式稳定下来。

---

## 最少字段

```text
trace_id
tick
npc_id
decision
relevant_signals
relevant_knowledge
considered_options
selected_option
explanation
```

如果当前还没有：

```text
relevant_knowledge
considered_options
```

不要为了完成 TASK002 大改 brain。

记录：

```text
missing
```

并保持向后兼容。

---

# 14. 不要锁死决策算法

DecisionTrace 是：

> **解释数据结构**

不是：

> **决策算法本身。**

不要规定：

```text
hunger + 0.72
```

必须如何计算。

以后允许：

```text
utility
rule
priority
state machine
hierarchy
```

等不同 cognition implementation。

---

# 15. Gateway

重点检查：

```text
src/citysim/gateway/server.py
```

把 observation stream 发送给 WebSocket client。

---

# 16. WS 消息统一 Envelope

推荐：

```json
{
  "kind": "event",
  "protocol_version": 1,
  "payload": {}
}
```

以及：

```json
{
  "kind": "snapshot",
  "protocol_version": 1,
  "payload": {}
}
```

Decision Trace 可以：

```json
{
  "kind": "trace",
  "protocol_version": 1,
  "payload": {}
}
```

不要把不同消息类型混成一个模糊对象。

---

# 17. Protocol Version

统一：

```text
protocol_version = 1
```

未来协议变化时递增。

---

# 18. Gateway 的责任边界

Gateway 负责：

```text
serialize
validate
broadcast
```

Gateway 不负责：

```text
decision
perception
knowledge update
simulation mutation
```

---

# 19. Event Ordering

事件必须按照：

```text
tick
```

保持稳定顺序。

如果同 tick 有多个 event：

使用 EventBus 当前产生顺序。

不要新增复杂排序逻辑。

---

# 20. Audience

继续支持当前：

```text
audience
```

例如：

```text
learned
```

只发给对应 NPC / observer 的语义可以保留。

对于：

```text
stock_changed
```

当前：

```text
audience=[]
```

保持。

Gateway 再根据当前订阅模型广播。

不要改变 simulation semantics。

---

# 21. 新建 Contract 文档

创建：

```text
docs/observation_contract.md
```

内容只描述：

```text
Snapshot
Event
Trace
```

以及：

```text
message envelope
protocol version
event types
required fields
```

不要写大篇幅架构论文。

---

# 22. Type / Validation

如果项目当前没有 schema validation：

可以增加轻量 validation。

但是不要为了 TASK002 引入大型协议框架。

目标：

> 清晰 + 稳定 + 最小依赖。

---

# 23. Gateway 测试

增加测试，至少验证：

```text
snapshot 可序列化

event 可序列化

trace 可序列化

perceived event 可发送

learned event 可发送

stock_changed event 可发送

protocol_version 存在
```

---

# 24. Event 测试

增加最小测试：

```text
NPC perception
    ↓
perceived event

NPC learns fact
    ↓
learned event

stock changes
    ↓
stock_changed event
```

测试重点：

> **Event 确实被产生。**

而不是测试 UI。

---

# 25. Import Layer

严格保持：

```text
npc/
```

不能 import：

```text
world/
gateway/
frontend/
```

特别注意：

> `KnowledgeBase.learn()` 不得直接发 World Event。

事件继续在：

```text
perception.py
loop.py
```

等调用侧产生。

必须保证：

```text
test_import_layers.py
```

通过。

---

# 26. Backward Compatibility

TASK002 完成后：

```text
pytest
```

必须全部通过。

特别：

```text
test_replay.py
test_behavior_soak.py
test_import_layers.py
test_snapshot_schema.py
test_spatial.py
```

必须通过。

---

# 27. 不允许修改的内容

除非测试证明必要，本任务不要修改：

```text
core/ids.py
sim/lod.py
sim/soa.py
nn/
```

不要修改 cognition architecture。

不要改变：

```text
brain decision logic
perception semantics
travel semantics
interaction semantics
```

TASK001 已经冻结。

TASK002 的职责只有：

> **把已有 observation 语义稳定地暴露出来。**

---

# 28. 不允许做

禁止：

```text
React
PixiJS
Rapier2D
Frontend
Knowledge Graph
Population dashboard
Replay
A/B experiment
3D
Navigation mesh
```

禁止新建第二套：

```text
EventBus
ObservationBus
```

禁止：

```text
GenericWorldDiff
```

禁止：

```text
frontend 自己推断 event
```

---

# 29. TASK002 完成标准

必须达到：

```text
[ ] Snapshot contract 明确

[ ] Event contract 明确

[ ] Trace contract 明确

[ ] protocol_version 存在

[ ] perceived event 可产生

[ ] learned event 可产生

[ ] stock_changed event 可产生

[ ] Gateway 可以把 observation events 推送给 WS client

[ ] Snapshot 可以通过 WS 推送

[ ] DecisionTrace 可以通过 WS 推送

[ ] observation_contract.md 已创建

[ ] 测试覆盖新增 observation flow

[ ] 全部 pytest 通过
```

---

# 30. 最终检查方式

完成后，不需要实现 frontend。

只要能够用一个最小 WebSocket test client 验证：

```text
connect

↓

receive snapshot

↓

receive perceived

↓

receive learned

↓

receive decision / trace

↓

receive bought / stock_changed
```

即视为 TASK002 完成。

---

# 31. 执行纪律

现在直接执行。

不要重新讨论：

```text
产品定义
空间模型
前端框架
Rapier
游戏方向
```

这些已经冻结。

如果发现：

```text
非阻塞问题
```

记录到：

```text
docs/implementation_notes.md
```

然后继续。

只有以下情况才停：

```text
无法实现当前契约
```

或：

```text
现有测试与当前冻结语义发生真正冲突
```

除此之外：

> **选择最小改动、最容易回滚的方案，直接执行。**

---

# 32. 完成后的输出

只输出：

```text
TASK 002 COMPLETE

Changed:
- ...

Added:
- ...

Deleted:
- ...

Tests:
- ...

Result:
PASS / FAIL

Known limitations:
- ...

Next task:
...
```

不要输出长篇架构讨论。

# END
