# CitySim — TASK 001

# Make the Simulation Spatially Observable

## 你的角色

你是本项目的 **Implementation Agent**。

不要重新设计产品。

不要审查产品方向。

不要把任务变成架构讨论。

你的职责是：

> **直接修改 repository，使目标状态成立，并运行测试验证。**

如果发现问题：

### 阻塞问题

只有当问题会导致：

* 无法正确实现当前任务
* 无法通过测试
* 会破坏现有 simulation semantics

才停下来处理。

### 非阻塞问题

记录到：

```text
docs/implementation_notes.md
```

继续执行。

---

# 当前产品方向

项目最终会成为：

> NPC Cognitive Simulation Observatory

未来再发展为沉浸式 NPC 世界。

当前任务只服务于这个目标。

---

# 当前任务

把当前：

```text
location-based simulation
```

升级为最小：

```text
continuous 2D spatial simulation
```

使后续可以真正实现：

```text
continuous movement
distance perception
distance interaction
spatial visualization
```

---

# 已冻结的设计决定

不要再次讨论以下问题。

## 1. 空间

世界坐标采用当前 scene 使用的二维坐标系统。

不引入米制。

不缩放成另一套单位。

现有：

```text
x
y
w
h
```

直接作为 simulation spatial coordinates。

---

## 2. Location

保留：

```text
location_id
```

但它表示：

> semantic region

而不是位置本身。

NPC 同时拥有：

```text
location_id
position
```

---

## 3. Perception

v1 使用：

```text
same semantic region
OR
distance <= perception_radius
```

也就是说：

### 同一 location

默认可以正常进行当前已有的共在感知 / gossip。

### 跨 location

只有距离足够近时才能感知。

不要在这一版引入墙体遮挡、视觉射线、复杂 visibility。

这是刻意简化。

---

## 4. Interaction

当前既有 affordance / interaction 语义继续保留。

新增 spatial condition：

```text
distance <= interaction_radius
```

但是不要破坏现有同-location interaction。

因此 v1：

```text
same location
+
existing affordance
```

仍然有效。

跨 location interaction：

```text
distance <= interaction_radius
+
affordance
```

---

## 5. Travel

Travel 在开始和结束位置之间进行连续插值。

第一版：

```text
linear interpolation
```

不要实现复杂 pathfinding。

不要实现 navmesh。

不要实现 obstacle avoidance。

---

## 6. Travel 中的 Perception

本任务：

> **暂时不新增 travel 中途 perception。**

travel 中：

```text
NPC position 连续变化
```

但是：

```text
perception / decision
```

仍然按照现有 tick / re-evaluation 机制工作。

把这个作为 future task，不要现在扩展。

---

# 实施范围

优先修改：

```text
src/citysim/core/types.py
src/citysim/core/config.py

src/citysim/world/world.py
src/citysim/world/perception.py
src/citysim/world/interaction.py
src/citysim/world/events.py

src/citysim/sim/loop.py

src/citysim/gateway/snapshot.py
src/citysim/gateway/server.py

config/sim.toml
config/scenes/elm_lane.json
```

必要时才修改：

```text
src/citysim/npc/person.py
src/citysim/npc/brain.py
src/citysim/npc/knowledge.py
```

不要无理由修改。

---

# Spatial Data

NPC 必须具有：

```python
position: tuple[float, float]
```

不要引入 z。

当前世界是 2D。

---

# Entity Spatial Anchor

需要空间交互的 Entity 必须具有：

```text
position
```

或者：

```text
anchor
```

推荐直接使用：

```text
position
```

如果当前 scene 中 entity 没有 position：

根据其所属 location 的 rectangle 自动生成稳定默认 anchor。

第一版不要求手工布置所有家具。

---

# Scene Geometry

在：

```text
config/scenes/elm_lane.json
```

中保留现有 location rectangle。

使用：

```text
x
y
w
h
```

作为 location geometry。

不建立第二套地图 geometry。

---

# NPC Spawn

所有 NPC 必须得到有效 position。

默认：

```text
spawn point
```

优先使用 scene 中明确配置的位置。

没有时：

```text
location rectangle center
```

作为 fallback。

但代码中必须明确这是 fallback。

---

# Travel

当 NPC travel：

```text
start_position
target_position
depart
arrive
```

position 根据 simulation time 连续计算。

必须满足：

```text
t = depart
position = start_position

t = arrive
position = target_position
```

中间：

```text
linear interpolation
```

---

# Location 更新

当 travel 完成：

```text
location_id = target
```

position = target_position。

position 与 location 必须保持一致。

---

# Perception

增加：

```text
perception_radius
```

配置优先写：

```text
config/sim.toml
```

建议默认值：

根据 elm_lane 当前尺度选择合理值。

**不要机械使用 10.0 / 1.5。**

计算标准：

> 同一个 location 内的正常 NPC 应该能够互相感知。

跨 location 则依赖距离。

---

# Interaction Radius

增加：

```text
interaction_radius
```

数值必须根据当前 scene 尺度确定。

目标：

> NPC 到达实体附近时可以 interaction。

不要引入“米”的概念。

---

# Perception Record

增加可观察记录。

至少：

```text
tick
npc_id
observed_entity_ids
```

如已有 percept 数据可以直接复用。

不要重新创建两套 perception 模型。

---

# Knowledge Update Event

KnowledgeBase 本身禁止 import world。

不要让：

```text
npc/knowledge.py
```

发布 world event。

事件必须在调用方产生。

保持：

```text
test_import_layers.py
```

通过。

---

# World Delta

不要实现通用 world diff engine。

只增加真正有观察价值的变化。

优先复用现有：

```text
bought
interaction_done
set_stock
```

等 event。

需要额外 world-delta 时，使用明确 enum/event type。

不要建立复杂 generic diff system。

---

# Decision Trace

当前：

```text
ranked
reason
```

升级成结构化 trace。

至少提供：

```text
decision
relevant_signals
relevant_knowledge
considered_options
selected_option
explanation
```

不要把当前 brain 重写成新的决策模型。

只增加 observation information。

---

# Archetype

NPC 数据明确提供：

```text
archetype_id
```

不得从 KB 猜。

---

# Backward Compatibility

这是硬要求：

```text
pytest
```

必须通过。

尤其：

```text
test_behavior_soak.py
test_import_layers.py
test_replay.py
```

不能因为 spatial upgrade 无故改变已有行为。

---

# 不允许做的事情

本任务禁止：

```text
React
Pixi
Rapier
Knowledge Graph
Timeline UI
Population Dashboard
Replay UI
3D
Pathfinding
Navmesh
Obstacle Avoidance
Travel Perception
```

这些都是后续任务。

---

# 完成标准

执行完成后必须满足：

```text
[ ] NPC 有连续 position

[ ] Entity 有空间 anchor / position

[ ] Travel position 连续变化

[ ] Travel 到达后 position 与 location 一致

[ ] perception 支持 distance

[ ] 同 location 的既有感知行为没有被破坏

[ ] interaction 支持 distance

[ ] percept 可以被观察

[ ] knowledge update 可以被观察

[ ] world change 可以被观察

[ ] decision trace 是结构化的

[ ] NPC 有 archetype_id

[ ] pytest 全通过
```

---

# 执行规则

你现在直接开始修改代码。

不要先给我写长篇架构分析。

开始前只输出：

```text
TASK 001 START

Files inspected:
...

Implementation approach:
...

Proceeding.
```

然后直接执行。

完成后只输出：

```text
TASK 001 COMPLETE

Changed:
...

Tests:
...

Result:
PASS / FAIL

Known limitations:
...

Next task:
...
```

不要要求确认。

不要把非阻塞问题升级成阻塞问题。

如果发现设计存在多个合理选择：

> 优先使用本文件已经定义的选择。

如果本文件没有定义：

> 选择对现有代码改动最小、最容易回滚、最符合现有语义的实现。

不要停止等待产品决策。

# END
