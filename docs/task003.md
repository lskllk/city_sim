# CitySim — TASK 003

# Observatory MVP

## 任务目标

基于 TASK001 + TASK002 已经完成的后端能力，建立第一个真正可用的：

> **NPC Cognitive Simulation Observatory**

本任务第一次开始 frontend。

目标只有一个：

> **可以在浏览器里看到真实 simulation，并点击一个 NPC，查看它当前状态、知识、感知、决策和最近事件。**

---

# 1. 本任务允许使用的技术

固定：

```text
React
TypeScript
Vite
Zustand
PixiJS
WebSocket
```

暂不使用：

```text
Rapier2D
React Flow
Three.js
Godot
ECS
```

---

# 2. 当前后端已经存在的能力

不要重新实现。

当前 backend 已经提供：

```text id="5vlzns"
WS /ws

hello
snapshot
event
reply

pause
step
set_speed
reset
query
```

Snapshot 已经包含：

```text id="b6v4ab"
tick
day
hour_f
clock
speed
running
tps
entities
npcs
```

NPC 已经包含：

```text id="jeqka9"
id
name
loc
position
archetype
activity
act_class
signals
travel
intent
last_percept
kb
kb_counts
events
```

Intent 已经包含：

```text id="3akb7n"
kind
target
reason
ranked
relevant_signals
used_facts
```

Event 已经通过独立：

```text id="q3e6gv"
kind = "event"
```

推送。

---

# 3. 当前任务不修改 simulation core

原则：

```text id="fj7ubj"
TASK003 = frontend implementation
```

除非发现明确的 backend contract bug：

不要修改：

```text id="r61jpc"
core/
npc/
world/
sim/
```

也不要为了 frontend convenience 改 simulation semantics。

---

# 4. Frontend 目录

创建：

```text id="gyx3ap"
frontend/
```

结构：

```text id="k4vmj2"
frontend/
  package.json
  tsconfig.json
  vite.config.ts
  index.html

  src/
    app/
      App.tsx

    protocol/
      schemas.ts
      websocket.ts

    state/
      worldStore.ts
      simulationStore.ts
      selectionStore.ts

    simulation/
      snapshot.ts
      interpolation.ts

    engine/
      pixi/
        SimulationStage.ts
        Camera.ts
        MapRenderer.ts
        EntityRenderer.ts

    views/
      WorldView.tsx

    ui/
      Toolbar.tsx
      EventStream.tsx
      Timeline.tsx

      Inspector/
        NPCInspector.tsx
        SignalsPanel.tsx
        IntentPanel.tsx
        PerceptionPanel.tsx
        KnowledgePanel.tsx
        DecisionTracePanel.tsx

    styles/
      app.css
```

不要提前创建：

```text
KnowledgeGraph
PopulationStats
EmergenceView
Rapier
Replay
```

---

# 5. Bootstrap

使用：

```text id="l4l4m9"
Vite + React + TypeScript
```

确保：

```text id="rgyqsh"
npm install
npm run dev
```

可以启动。

页面标题：

```text
CitySim Observatory
```

---

# 6. Protocol Layer

创建：

```text id="osq9hj"
frontend/src/protocol/schemas.ts
frontend/src/protocol/websocket.ts
```

---

## schemas.ts

定义当前真实 backend contract。

至少：

```text id="9qkq7n"
HelloMessage
SnapshotMessage
EventMessage
ReplyMessage

Snapshot
NPCSnapshot
EntitySnapshot
IntentSnapshot
PerceptionRecord
KnowledgeData
```

不要定义 backend 当前不存在的字段作为 required。

如果字段可能为空：

明确：

```ts
T | null
```

禁止随意：

```ts
any
```

---

# 7. WebSocket

`websocket.ts` 只负责：

```text id="8rxv9a"
connect
disconnect
reconnect
send
parse
dispatch
```

当前 endpoint：

```text
/ws
```

---

# 8. WebSocket 行为

连接成功后：

```text id="dq01ts"
hello
```

然后接收：

```text id="0yew4g"
snapshot
event
reply
```

---

# 9. Reconnect

连接断开：

自动重连。

要求：

```text id="1fsqoh"
backoff
```

第一版简单即可。

不要引入复杂状态机。

---

# 10. State

创建：

```text id="vcju3k"
worldStore
simulationStore
selectionStore
```

---

## worldStore

保存：

```text
entities
npcs
```

当前 backend snapshot 是 authoritative。

收到 snapshot：

> 更新当前 world mirror。

---

## simulationStore

保存：

```text
tick
day
hour
clock
speed
running
tps
connectionStatus
```

---

## selectionStore

保存：

```text
selectedNpcId
selectedEventId
```

---

# 11. Snapshot Handling

建立：

```text id="8t1rbu"
frontend/src/simulation/snapshot.ts
```

职责：

```text
WS snapshot
↓
typed snapshot
↓
worldStore
+
simulationStore
```

不要在这里实现 simulation logic。

---

# 12. Event Handling

收到：

```text id="i99w6m"
kind = event
```

执行：

```text id="pf7a1g"
EventStream append
```

如果事件与当前 selected NPC 有关：

更新其：

```text id="32e0g9"
recent activity
```

不要修改 world truth。

下一次 snapshot 会再次同步真实状态。

---

# 13. Pixi World

建立：

```text id="c7u6cx"
SimulationStage
Camera
MapRenderer
EntityRenderer
```

---

# 14. WorldView

React 页面：

```text id="w06qfy"
WorldView
```

只负责挂载 Pixi。

不要让 React 为每个 NPC 建 component。

---

# 15. MapRenderer

使用 backend `hello` 中：

```text id="bjbpqh"
locations
canvas
```

绘制 Elm Lane。

第一版只用：

```text
rectangle
line
text
```

不要做美术资源系统。

---

# 16. EntityRenderer

显示：

```text id="8xl7jt"
NPC
Entity
```

NPC 第一版使用简单图形。

必须根据 snapshot：

```text id="j8q9u0"
position
```

定位。

---

# 17. NPC Movement

NPC 位置使用：

```text id="vz3qrd"
snapshot.position
```

前端可以平滑 interpolation。

但：

> interpolation 只是视觉处理，不是 simulation。

不得修改 backend state。

---

# 18. Camera

支持：

```text id="o1m3jo"
drag / pan
zoom
reset view
```

最低可用即可。

---

# 19. NPC Selection

点击 NPC：

```text id="9br65p"
Pixi
 ↓
selectedNpcId
 ↓
NPCInspector
```

不允许：

```text
Pixi → simulation mutation
```

---

# 20. Inspector

固定布局：

```text id="os3kod"
NPC Inspector

Identity

Signals

Current Intent

Current Perception

Knowledge

Decision Trace

Recent Events
```

---

# 21. Identity

显示：

```text id="3v6j3j"
name
id
archetype
location
```

---

# 22. Signals

展示：

```text id="j15s1t"
所有 signals
```

每项：

```text
name
value
```

视觉：

```text
progress bar
```

范围：

```text
0..1
```

---

# 23. Intent

显示：

```text id="t67u9b"
kind
target
reason
ranked
relevant_signals
```

如果没有 intent：

```text
No current intent
```

---

# 24. Perception

当前 backend 提供：

```text id="m3w8qf"
last_percept
```

因此第一版显示：

```text
tick
location
position
observed entities
```

明确标题：

```text
Last Perception
```

不要假装它是“当前实时感知”。

---

# 25. Knowledge

展示 backend：

```text id="0fck1t"
kb
kb_counts
```

第一版使用列表，不做 graph。

每条 Fact 至少显示：

```text
subject
relation
object
source_kind
confidence
```

必须视觉区分：

```text
INJECTED
OBSERVED
TOLD
```

---

# 26. Decision Trace

显示：

```text id="y2r6l5"
reason
ranked
relevant_signals
used_facts
```

---

## Trace 的第一版展示

推荐：

```text
Decision
↓
Reason
↓
Relevant Signals
↓
Considered Options
↓
Used Knowledge
```

不要自行计算新的分数。

所有数据直接来自 backend。

---

# 27. Recent Events

显示 selected NPC 最近事件。

来源：

```text id="s0g07k"
NPCSnapshot.events
```

以及收到的实时 event。

按：

```text
tick
```

显示。

---

# 28. Event Stream

底部或者右侧建立全局 Event Stream。

显示：

```text id="l4tqko"
tick
type
source
target
summary
```

至少支持：

```text
decision
perceived
learned
told
bought
interaction_done
intent_failed
stock_changed
npc_died
```

---

# 29. Event Click

点击 Event：

```text id="8lffn5"
selectedEventId
```

如果 event 有 source：

尝试：

```text
select source NPC
```

但如果 source 不是 NPC：

不要报错。

---

# 30. Toolbar

显示：

```text id="jaf87s"
Connection
Scenario
Seed
Day
Clock
Tick
Speed
```

控制：

```text
Pause
Play
Step
1x
10x
100x
```

使用已有 backend command：

```text
set_speed
step
```

---

# 31. Reset

提供：

```text
Reset
```

调用：

```text
reset
```

不在 frontend 自己清理 simulation。

收到 hello + snapshot 后：

重新同步 frontend state。

---

# 32. Timeline

第一版只做：

```text id="gb0qxf"
current tick
current clock
play/pause
step
speed
```

不要做 seek。

不要做历史回放。

---

# 33. 页面最终结构

第一版固定：

```text id="0v13j3"
┌────────────────────────────────────────────────────┐
│ Toolbar                                            │
├───────────────────────────────┬────────────────────┤
│                               │                    │
│                               │ NPC Inspector      │
│                               │                    │
│         PIXI WORLD            │ Identity           │
│                               │ Signals            │
│                               │ Intent             │
│                               │ Perception         │
│                               │ Knowledge          │
│                               │ Decision Trace     │
│                               │                    │
├───────────────────────────────┴────────────────────┤
│ Event Stream                                       │
├────────────────────────────────────────────────────┤
│ Timeline                                           │
└────────────────────────────────────────────────────┘
```

---

# 34. Styling

不要做 UI 设计大工程。

目标：

```text
清晰
稳定
信息密度合理
```

优先：

```text
dark observatory style
```

但不要花大量时间做动画、渐变、3D 特效。

---

# 35. Error Handling

以下情况不能导致页面崩溃：

```text
malformed WS message
unknown message kind
unknown event type
NPC 不存在
entity 不存在
snapshot 缺 optional field
WS disconnect
```

错误显示：

```text
console.error
+
UI connection status
```

不要弹窗骚扰。

---

# 36. Performance

必须避免：

```text
一个 NPC = 一个 React component
```

Pixi 管理 entity rendering。

React 只管理：

```text
UI
Inspector
Event Stream
Toolbar
```

---

# 37. 第一版暂不做

禁止：

```text
Rapier2D
Knowledge Graph
Population Statistics
Emergence View
Run A/B
Replay Seek
Path visualization
Perception radius overlay
Interaction radius overlay
Complex animation
Spritesheet pipeline
```

这些都属于后续任务。

---

# 38. Legacy Static Observer

当前 backend 下仍有：

```text
gateway/static/
```

不要立即删除。

TASK003 先让新 frontend 独立运行。

如果不需要修改 legacy observer：

不要动它。

完成 MVP 后再决定是否删除。

---

# 39. Backend Modification Rule

如果实现过程中发现 frontend 缺少字段：

先检查现有：

```text
snapshot.py
observation_contract.md
```

只有确实缺少且 MVP 必须的信息，才能做最小 backend modification。

不要顺手重构 backend。

---

# 40. Acceptance Test

TASK003 完成必须能实际跑通：

```text
1. 启动 backend

2. 启动 frontend

3. frontend 连接 /ws

4. 收到 hello

5. 显示 Elm Lane

6. 显示 NPC

7. NPC 位置正确

8. 点击 NPC

9. Inspector 出现

10. Signals 显示

11. Intent 显示

12. Last Perception 显示

13. Knowledge 显示

14. Decision Trace 显示

15. Event Stream 出现 perceived / decision / learned 等事件

16. 点击 Event 可以定位 source NPC

17. Pause

18. Step

19. Speed 变化

20. Reset

21. Reset 后界面重新同步
```

---

# 41. Backend Tests

运行：

```text
pytest
```

要求全部通过。

尤其：

```text
test_replay.py
test_behavior_soak.py
test_import_layers.py
test_spatial.py
test_observation.py
```

不能回归。

---

# 42. Frontend Build

必须：

```text
npm run build
```

成功。

不得：

```text
TypeScript errors
```

---

# 43. TASK003 完成定义

满足以下全部条件：

```text
[ ] React application 可以启动

[ ] WebSocket 可以连接

[ ] hello 可以解析

[ ] snapshot 可以解析

[ ] event 可以解析

[ ] Pixi 世界可以显示

[ ] NPC 可以显示

[ ] NPC 可以连续平滑移动

[ ] NPC 可以选择

[ ] Inspector 正常

[ ] Signals 正常

[ ] Intent 正常

[ ] Last Perception 正常

[ ] Knowledge 正常

[ ] Decision Trace 正常

[ ] Event Stream 正常

[ ] Pause / Play 正常

[ ] Step 正常

[ ] Speed 正常

[ ] Reset 正常

[ ] WS reconnect 正常

[ ] backend pytest 全绿

[ ] frontend npm run build 全绿
```

---

# 44. 执行纪律

这是一个明确的 implementation task。

不要重新讨论：

```text
Spatial Semantics
Belief Architecture
Cognitive Architecture
Rapier
Knowledge Graph
Emergence
Godot
游戏方向
```

这些不是 TASK003。

如果发现非阻塞问题：

```text
记录 docs/implementation_notes.md
```

然后继续。

如果发现 contract 缺字段：

优先采用当前已有字段。

不要为了“未来优雅”增加新的抽象层。

---

# 45. 最终输出

只输出：

```text
TASK 003 COMPLETE

Changed:
- ...

Added:
- ...

Deleted:
- ...

Backend tests:
- ...

Frontend build:
- ...

Manual verification:
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
