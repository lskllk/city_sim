# CitySim — TASK 004

# Make NPC Behavior Understandable

## 任务目标

TASK003 已经完成 Observatory MVP。

当前主要问题不是功能缺失，而是：

1. Decision Trace 不够直观。
2. Knowledge 显示过多，干扰理解。
3. Inspector 更像数据库查看器，而不是行为解释器。
4. 当前地图虽然能显示位置，但空间语义弱，世界像棋盘。
5. 本任务不增加新的 simulation capability，重点是改善**行为解释的可读性**。

目标：

> 用户点击一个 NPC 后，能够在很短时间内理解：
>
> **“这个 NPC 现在在做什么、为什么这么做、依据了什么、产生了什么结果。”**

---

# 1. 本任务边界

允许修改：

```text
frontend/
```

如发现现有 frontend contract 的纯展示问题，可以做极小 backend contract 修正。

默认不修改：

```text
core/
npc/
world/
sim/
```

除非发现 TASK003 实现依赖的字段确实错误。

---

# 2. 本任务禁止

禁止加入：

```text
Rapier2D
Knowledge Graph
Population Statistics
Emergence Detection
Replay Seek
A/B Experiment
复杂路径规划
复杂动画
3D
```

禁止重新设计 cognition architecture。

禁止新增：

```text
Belief System
Memory System
Planner
GOAP
```

这些都不是 TASK004。

---

# 3. 核心 UX 改变

当前 Inspector：

```text id="v4jy8f"
Identity
Signals
Intent
Perception
Knowledge
Decision Trace
Events
```

继续保留这些信息，但改变层级。

核心原则：

> **主视图展示“当前行为解释”，详细数据全部降级为可展开内容。**

---

# 4. Inspector 新结构

固定为：

```text id="88m9mk"
NPC Header

Current Behavior

Why?

Relevant Knowledge

Signals

Last Perception

Recent Events

All Knowledge
```

---

# 5. NPC Header

显示：

```text
name
archetype
location
```

并显示当前状态：

```text
Idle
Moving
Interacting
Buying
Sleeping
```

不要显示大量内部 debug 字段。

---

# 6. Current Behavior

这是 Inspector 最重要的区域。

示例：

```text
Current Behavior

🛒 Buying Apple

Target:
Grocery

Status:
In progress
```

如果是：

```text
MoveTo
```

显示：

```text
🚶 Moving to Grocery
```

如果：

```text
Idle
```

显示：

```text
Idle
```

---

# 7. Why? 行为解释

这是 TASK004 的最高优先级。

必须把 backend 提供的：

```text
reason
relevant_signals
used_facts
ranked
```

重新组织成易读内容。

---

## 示例

不要只显示：

```text
reason:
Buy apple because hunger high...
```

改成：

```text
Why?

Hunger is high

Hunger
████████░░ 0.81

Known:
Apple restores energy

Can afford:
Yes

Selected:
Buy Apple
```

重要：

> 前端只负责重新组织 backend 数据，不重新计算 decision。

---

# 8. Decision Explanation

使用固定结构：

```text
Current decision
       ↓
Relevant signals
       ↓
Relevant knowledge
       ↓
Alternatives
       ↓
Reason
```

例如：

```text
Decision
Buy Apple

Relevant signals
Hunger      0.81
Energy      0.52
Money       12

Relevant knowledge
Apple restores energy
Source: OBSERVED
Confidence: 0.83

Alternatives
Buy Apple
Move Home
Idle

Reason
High hunger + known energy benefit + affordable
```

具体内容完全依据 backend 当前 trace。

不要虚构 alternatives。

如果 backend 没有 alternatives：

不显示该区。

---

# 9. Relevant Knowledge

把当前：

```text
Knowledge
```

拆成两个层级。

默认：

```text
Relevant Knowledge
```

只显示：

```text
used_facts
```

如果 backend 当前 trace 没有足够数据：

使用现有 intent / query 能得到的相关事实。

不得根据字符串相似度猜事实。

---

# 10. All Knowledge

完整 KB 降到：

```text
All Knowledge ▸
```

默认折叠。

展开后才显示全部 facts。

这样：

```text
NPC 有 100 个 facts
```

不会阻塞用户理解当前行为。

---

# 11. Knowledge 行为

每条 fact 显示：

```text
subject
relation
object
source
confidence
```

来源保持：

```text
INJECTED
OBSERVED
TOLD
```

不要改变 backend knowledge semantics。

---

# 12. Signals

Signals 不再占据大量纵向空间。

默认显示：

```text
Top relevant signals
```

也就是当前 DecisionTrace 中真正相关的 signals。

例如：

```text
Hunger  0.81
Energy  0.52
Money   12
```

提供：

```text
All Signals ▸
```

展开后才显示全部 signal。

---

# 13. Last Perception

保留：

```text
Last Perception
```

明确写：

> Last perception

不要写：

```text
Current vision
Current perception
```

因为 backend 当前只保存最近一次 perception。

显示：

```text
tick
observed entities
location
```

---

# 14. Recent Events

显示 selected NPC 最近事件。

默认只显示：

```text
最近 5~10 条
```

提供：

```text
Show more
```

避免整个 Inspector 被 event list 占满。

---

# 15. Behavior Narrative

在 Current Behavior 下增加一个非常简短的自然语言总结。

例如：

```text
Bob is buying an apple because
his hunger is high and he knows
the apple restores energy.
```

要求：

> 必须基于已有结构化 backend 数据生成。

第一版可以使用 frontend template。

例如：

```ts
`${name} is ${action} because ${reason}`
```

不要接 LLM。

不要增加新的 AI 服务。

---

# 16. 行为解释颜色/视觉层级

目标：

```text
Action
↓
Reason
↓
Evidence
```

而不是：

```text
所有字段视觉权重一样
```

主视觉权重：

```text
Current Behavior
Why
Relevant Knowledge
```

次级：

```text
Signals
Perception
Events
```

最低：

```text
All Knowledge
```

---

# 17. 地图问题

TASK003 当前地图的主要问题：

> 能显示位置，但没有“空间意义”。

TASK004 只进行轻量改善。

不要建设完整地图系统。

---

# 18. Location Semantic Label

地图上的 location 显示：

```text
Home
Market
Plaza
Apartment
```

而不是只有：

```text
apt_101
market
site
```

优先使用场景已有的名称字段。

如果没有：

使用稳定 human-readable fallback。

---

# 19. Entity Type Visual Differentiation

至少区分：

```text
NPC
Item
Location
```

使用简单视觉方式：

```text
NPC = circle
Item = small square
Location = outlined area
```

不要做复杂 sprite。

---

# 20. NPC 当前目标

当 selected NPC 有：

```text
Intent target
```

地图显示：

```text
NPC
  ↓
target
```

使用简单：

```text
line
arrow
highlight
```

仅用于说明：

> “他正在去哪里。”

---

# 21. Current Location Highlight

选中 NPC 后：

高亮：

```text
current location
```

如果存在 target location：

同时高亮：

```text
target location
```

让用户能够立刻理解：

```text
现在在哪里
→
准备去哪里
```

---

# 22. 不实现伪路径

如果 backend 只有：

```text
start_position
target_position
```

那么可以显示：

```text
start → target
```

但不得把它称为：

```text
navigation path
road path
optimal path
```

除非 backend 真正提供 path。

---

# 23. Event → World 联动

点击：

```text
Event Stream
```

如果 event 有 source NPC：

地图：

```text
highlight source
```

Inspector：

```text
select source
```

如果 event 有 target：

可以高亮 target。

不要修改 simulation。

---

# 24. Decision → Event 联动

如果当前行为有对应 decision event：

提供：

```text
View event
```

点击后：

定位到：

```text
Event Stream
```

---

# 25. Event → Decision 联动

点击：

```text
decision
```

Inspector 显示：

```text
Why?
```

并自动展开。

---

# 26. 当前 UI 的核心路径

完成 TASK004 后，用户操作流程应该是：

```text
点击 NPC

↓

看到：
Bob is buying Apple

↓

Why?

Hunger high
Apple known
Affordable

↓

Relevant Knowledge

Apple restores energy

↓

Signals

Hunger 0.81
Energy 0.52

↓

Last Perception

Apple visible

↓

Recent Event

Bob decided Buy Apple
```

这应该在**一个 Inspector 内完成**。

不要要求用户跳多个页面。

---

# 27. 空状态

必须处理：

```text
No current intent
No perception
No relevant knowledge
No recent events
```

显示友好的：

```text
None
Not available
No recent data
```

不要：

```text
undefined
null
NaN
```

出现在 UI。

---

# 28. Loading / Connection

明确显示：

```text
Connecting
Connected
Disconnected
Reconnecting
```

连接失败时：

世界区域不要直接白屏。

显示：

```text
Simulation disconnected
```

但保留最后 snapshot。

---

# 29. UI 性能

不要因为 Event Stream 更新导致：

```text
整个 Pixi world 重新 render
```

不要因为一个 NPC signal 变化导致：

```text
所有 Inspector component 更新
```

保持：

```text
Pixi
React
Zustand
```

职责分离。

---

# 30. 不修改 backend 的优先原则

如果现有 backend 已经提供足够信息：

直接在 frontend 重组。

不要为了 UI 文案：

```text
修改 brain
修改 knowledge
增加 event
增加 simulation state
```

只有发现 frontend 无法正确解释 backend 数据时，才记录：

```text
docs/implementation_notes.md
```

暂不扩 scope。

---

# 31. Visual Design

整体继续保持：

```text
dark observatory
```

但信息层级明显：

```text
Primary:
Current Behavior
Why

Secondary:
Knowledge
Signals
Perception
Events

Tertiary:
All Knowledge
```

不要大量卡片。

不要彩色图表。

不要复杂动画。

---

# 32. Acceptance Test

TASK004 完成后必须能够：

```text
1. 打开 Observatory

2. 点击 NPC

3. 第一眼看到当前行为

4. 第一眼看到 Why

5. 看到相关 signals

6. 看到相关 knowledge

7. 完整 KB 默认折叠

8. 看到 last perception

9. 看到 recent events

10. 点击 event 可以定位 NPC

11. 点击 decision 可以展开 Why

12. 地图高亮当前 location

13. 地图高亮 target

14. 地图显示 NPC → target 连线

15. 没有假造 navigation path

16. WS 断线不会导致 UI 崩溃
```

---

# 33. Build / Regression

必须：

```text
npm run build
```

成功。

backend：

```text
pytest
```

必须全绿。

---

# 34. TASK004 不需要新增复杂测试框架

至少补：

```text
UI data formatting tests
```

或现有 frontend test framework 下的最小测试。

重点覆盖：

```text
no intent
no knowledge
no perception
empty events
selected event
selected NPC
```

---

# 35. TASK004 Definition of Done

最终达到：

```text
[ ] NPC 当前行为一眼可见

[ ] Why 一眼可见

[ ] relevant knowledge 优先

[ ] full KB 默认折叠

[ ] relevant signals 优先

[ ] last perception 正确表达

[ ] event 可以联动 NPC

[ ] decision 可以联动 Why

[ ] current location 有视觉反馈

[ ] target location 有视觉反馈

[ ] NPC → target 有视觉连接

[ ] 没有伪造 path

[ ] UI 没有大量无意义信息

[ ] frontend build PASS

[ ] backend pytest PASS
```

---

# 36. 执行纪律

直接执行 TASK004。

不要：

```text
重新设计 cognition
重新设计 backend
新增 belief
新增 memory
新增 GOAP
新增 planner
```

不要：

```text
因为未来可能需要
```

而提前建立复杂抽象。

本任务目标非常明确：

> **让已经存在的 simulation data 更容易被人理解。**

优先修改 frontend。

如能通过 frontend 实现：

> 不改 backend。

只有确实无法实现时，才记录缺口。

如果遇到非阻塞问题：

记录：

```text
docs/implementation_notes.md
```

继续执行。

不要等待确认。

---

# 37. 完成后的输出

只输出：

```text
TASK 004 COMPLETE

Changed:
- ...

Added:
- ...

Deleted:
- ...

Frontend build:
- ...

Backend tests:
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

# END
