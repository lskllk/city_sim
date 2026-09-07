# CitySim Vision

## 1. 我为什么做 CitySim

CitySim 是一个长期的个人探索项目。

它不是首先为了成为一款商业游戏，也不是为了证明某一种 AI 算法。

它最初的问题很简单：

> **如果给 NPC 一个有限的身体状态、有限的认知、有限的信息、不同的人格，以及一个持续变化的世界，它们最终会表现出什么样的行为？**

我希望通过 CitySim 探索：

```text
认知
→ 决策
→ 行为
→ 环境反馈
→ 社会互动
→ 群体行为
→ 涌现
```

我不要求一开始就知道答案。

真正有价值的部分，是：

> **建立一个可以不断提出假设、运行实验、观察结果、修改模型的人工社会实验场。**

---

# 2. 最终愿景

CitySim 最终希望成为一个：

> **拥有连续空间、有限认知、个人历史、资源约束、社会关系和经济交换的人工社会。**

其中每一个 NPC 都不是一个简单的行为脚本，而是一个生活在世界中的独立主体。

它拥有：

```text
身体
认知
人格
知识
资源
能力
历史
关系
目标
```

它会：

```text
观察
记忆
判断
选择
行动
学习
生产
消费
交换
建立关系
影响他人
被他人影响
```

而这些个体的互动，最终形成：

```text
家庭
社区
市场
组织
职业
经济
文化
人口
社会结构
```

---

# 3. CitySim 最核心的假设

CitySim 不试图直接让 NPC “像人”。

相反，它希望建立：

> **一组简单、有限、可解释的认知与行为机制，让复杂的人类式行为从中自然产生。**

因此：

```text
真实感
≠
更大的模型
```

更接近：

```text
真实感
≈
有限认知
×
有限资源
×
个人历史
×
局部观察
×
社会互动
×
时间连续性
×
环境反馈
```

---

# 4. NPC 的基本哲学

NPC 不是世界数据库的读取器。

NPC 不知道世界真实状态。

它只能知道：

```text
自己感知到的
自己记住的
别人告诉自己的
自己推断的
```

因此：

```text
World Truth
    ≠
NPC Knowledge
```

这是 CitySim 最重要的边界之一。

---

# 5. NPC 的认知闭环

最终希望形成：

```text
World
 ↓
Perception
 ↓
Knowledge / Belief
 ↓
Internal State
 ↓
Decision
 ↓
Intent
 ↓
Action
 ↓
World Change
 ↓
New Perception
```

因此 NPC 的现在，是它过去经历的一部分结果。

---

# 6. 人格

人格是 NPC 的长期稳定特征。

例如：

```text
sociality
novelty
thrift
routine
```

人格不应该频繁变化。

人格的作用不是直接决定行为，而是影响：

> NPC 在不同情境下更倾向于如何选择。

例如面对相同需求：

```text
Alice → 去市场
Bob   → 回家
Carol → 去找朋友
```

人格不是脚本。

它只是：

> 行为倾向。

---

# 7. Knowledge 与 Belief

长期目标中：

```text
Fact
```

与：

```text
Belief
```

应该有所区别。

Fact 描述：

> NPC 获取到了什么信息。

Belief 描述：

> NPC 认为世界是什么样。

同一个事实：

```text
Bob 说：
“市场有苹果。”
```

不同 NPC 可以产生不同程度的相信。

因为：

```text
source
history
reliability
recency
contradictory evidence
```

都可能影响判断。

因此最终希望出现：

```text
同一个世界
+
不同经历
=
不同认知
=
不同决策
```

---

# 8. 个人历史

NPC 的过去不应该只是日志。

过去应该逐渐影响未来。

例如：

```text
Alice 曾经被 Bob 欺骗
```

未来：

```text
Alice 不再轻易相信 Bob
```

又例如：

```text
Bob 曾经历食物短缺
```

未来：

```text
Bob 更倾向储备食物
```

因此长期目标是：

> **NPC 的行为应该具有历史连续性。**

---

# 9. 资源

资源是 CitySim 从“NPC 模拟器”走向“人工社会”的重要基础。

NPC 应该拥有有限资源，例如：

```text
money
food
tools
materials
medicine
```

资源可以：

```text
获得
消耗
储存
交换
生产
丢失
继承
```

资源不是单独的经济系统。

它是 NPC 生活和行为的基础约束。

---

# 10. 消费与生产

最终希望统一表达：

```text
Action
 ↓
Resource Transformation
```

例如：

### 吃饭

```text
food
 ↓
body state
```

### 工作

```text
time + energy + skill
 ↓
goods / service
```

### 学习

```text
time + resources
 ↓
skill
```

### 交易

```text
money ↔ goods
```

因此：

> **消费、生产、学习和交换，本质上都是资源与能力的转换过程。**

---

# 11. 囤货

“囤货”不是一个特殊行为脚本。

长期希望：

```text
未来风险
+
资源储备
+
人格
+
知识
+
预期
```

共同产生：

```text
stockpiling
```

因此：

```text
囤货
≠
if shortage:
    buy_many()
```

而应该是：

> 一个有限理性的资源主体，对未来不确定性的反应。

---

# 12. Skill / Capability

NPC 不应该只有“职业”。

更底层应该拥有：

```text
ability
skill
experience
```

例如：

```text
farming
cooking
mining
crafting
trading
```

技能影响：

```text
效率
成功率
产量
质量
```

职业只是：

> NPC 当前在社会中的角色。

---

# 13. 经济

长期目标是让世界能够形成：

```text
worker
producer
consumer
company
market
supply
demand
price
wage
```

但不预先假设市场必须遵循真实经济学。

真正要观察的是：

> **简单的个体决策是否能够自然产生某些宏观经济现象。**

例如：

```text
短缺
囤货
价格变化
工资变化
职业转移
生产过剩
局部繁荣
局部衰退
```

---

# 14. 公司与组织

未来世界应该允许：

```text
Person
 ↓
Company
 ↓
Production
 ↓
Wage
 ↓
Consumption
```

公司不是一个“NPC employer API”。

它应该成为：

> 世界中的一种真实组织实体。

最终可以观察：

```text
公司招聘
技能差异
工资
生产效率
扩张
衰退
竞争
```

---

# 15. 社会传播

信息不是全局广播。

信息应该通过：

```text
perception
conversation
gossip
trust
social proximity
```

传播。

因此：

```text
Fact
 ↓
Person A
 ↓
Person B
 ↓
Person C
```

传播过程中可能出现：

```text
confidence change
distortion
delay
forgetting
```

最终可能出现：

```text
不同社区
拥有不同认知
```

---

# 16. 空间

空间不是 UI 背景。

空间本身应该成为行为变量。

最终世界希望拥有：

```text
continuous 2D space
locations
buildings
roads
objects
distance
visibility
movement
```

NPC 不只是：

```text
location_id = market
```

而是真正：

```text
position
movement
destination
spatial relation
```

空间会影响：

```text
perception
interaction
travel
social contact
economic activity
```

---

# 17. 连续行为

长期目标不是：

```text
MoveTo
→
arrive
```

而是：

```text
Intent
 ↓
Plan
 ↓
Motion
 ↓
Interaction
```

NPC 应该可以：

```text
走路
停下
遇到别人
被打断
改变目标
继续行动
```

最终：

> **行为应该具有时间连续性，而不是 tick-to-tick 的瞬时跳跃。**

---

# 18. 家庭与人口

长期目标包括：

```text
family
partnership
children
aging
death
```

但是人口系统不是独立模块。

它应该与：

```text
resources
relationships
knowledge
skills
environment
```

产生耦合。

一个家庭是否产生孩子，可能受到：

```text
resources
relationship
social norms
future expectations
```

影响。

---

# 19. 遗传

长期希望探索：

```text
Genome
 ↓
Traits
 ↓
Personality / Capability
 ↓
Behavior
```

父母不会简单复制给孩子。

而是：

```text
inheritance
+
variation
+
environment
```

因此最终可以观察：

```text
personality distribution
skill distribution
social characteristics
```

如何在多个世代中发生变化。

---

# 20. 文化

长期甚至可以进一步探索：

```text
belief
custom
preference
behavior
```

在群体中传播后形成：

```text
culture
```

文化不应该被硬编码为：

```text
culture = "Japanese"
```

而应该是：

> 群体长期互动后形成的一组共享倾向。

---

# 21. Emergence

CitySim 最值得探索的问题：

> **如果不直接写“社会规则”，社会现象是否会自己出现？**

例如：

```text
没有写：
“恐慌性抢购”

但出现：

库存下降
 ↓
部分 NPC 注意到
 ↓
部分 NPC 开始储备
 ↓
更多 NPC 观察到库存下降
 ↓
更多 NPC 储备
 ↓
库存进一步下降
 ↓
恐慌性抢购
```

如果出现这种现象：

> 这就是 CitySim 最有价值的结果之一。

---

# 22. 可解释性

所有重要行为应该尽可能可以追溯：

```text
What happened?
Why?

What did the NPC perceive?
What did it know?
What did it believe?
What internal state did it have?
What alternatives existed?
Why did it choose this one?

What happened after the action?
Who noticed?
Who changed because of it?
```

因此 Observatory 是整个项目的重要组成部分。

---

# 23. Observatory

最终希望能够观察：

```text
World
NPC
Cognition
Events
Relationships
Economy
Population
```

并能够从：

```text
Micro
```

观察到：

```text
Macro
```

例如：

```text
一个 NPC 做了什么
        ↓
改变了什么
        ↓
谁受到影响
        ↓
群体如何响应
        ↓
世界发生了什么
```

---

# 24. 实验优先

CitySim 不追求：

> “第一次就做出正确系统。”

而追求：

> **能够快速提出假设并运行实验。**

理想工作方式：

```text
Hypothesis
 ↓
Minimal Mechanism
 ↓
Simulation
 ↓
Observation
 ↓
Unexpected Behavior
 ↓
Analysis
 ↓
Keep / Modify / Delete
```

---

# 25. 反复杂度原则

CitySim 不追求：

```text
最多模块
最多抽象
最通用架构
最复杂 AI
```

而追求：

> **在保持行为可观察、可解释、可修改的前提下，用尽可能简单的机制产生复杂行为。**

一个新的 abstraction 只有在它：

```text
解决实际问题
+
能够被测试
+
能够被观察
```

时才值得存在。

---

# 26. 不把 GOAP 当成目标

GOAP、Planner、Utility、Rule System、LLM 等都只是工具。

它们不是 CitySim 的目标。

真正的目标是：

> **探索哪种认知机制最容易产生有趣、可信、可解释的行为。**

如果简单规则已经足够：

> 不需要 GOAP。

如果 GOAP 真正解决问题：

> 再使用 GOAP。

如果未来某一部分适合 LLM：

> 可以局部使用。

技术服务于实验，而不是反过来。

---

# 27. 未来的高保真目标

长期希望世界至少在以下方面形成闭环：

```text
Physical World
        ↓
Perception
        ↓
Cognition
        ↓
Decision
        ↓
Action
        ↓
Resource Change
        ↓
Economic Effect
        ↓
Social Effect
        ↓
Population Effect
        ↓
World Change
```

最终：

```text
Individual
    ↓
Family
    ↓
Organization
    ↓
Community
    ↓
Economy
    ↓
Population
    ↓
Culture
```

---

# 28. 最终理想状态

当 CitySim 真正成熟时，我希望能够打开一个世界，观察其中一个 NPC：

```text
Alice
```

然后发现：

```text
她有自己的身体状态
她有自己的资源
她有自己的性格
她有自己的技能
她有自己的记忆
她有自己的信念
她有自己的关系
她有自己的历史
```

我问：

> 她为什么现在去市场？

系统可以告诉我：

```text
因为她饿了。

她知道市场有食物。

她更喜欢市场，而不是自己做饭。

她有足够的钱。

而且她预计今晚可能下雨，
所以希望提前买东西。

```

然后我继续观察：

```text
她在市场遇到了 Bob。

Bob 告诉她某种商品可能涨价。

Alice 不完全相信 Bob。

但她记得 Bob 上次预测是准确的。

于是她多买了一些。

```

几天以后：

```text
市场库存下降
→
其他 NPC 注意到
→
开始购买
→
价格变化
→
某个商人扩大进货
→
某个工人获得更多工作
→
工资变化
→
家庭消费改变
```

而这些都不是：

```text
if market_shortage:
    run_emergency_event()
```

写死的。

而是：

> **由个体行为逐渐累积产生的宏观现象。**

这就是 CitySim 最终真正想探索的东西。

---

# 29. 当前阶段与最终愿景

当前不要试图实现整个愿景。

当前阶段只需要：

```text
可靠 Simulation Core
+
可观察 Observation Contract
+
Observatory
```

然后逐步增加：

```text
空间
→
资源
→
能力
→
人格
→
信念
→
经济
→
组织
→
人口
→
遗传
→
文化
```

每一步都通过实验决定是否值得继续。

---

# 30. 最终原则

CitySim 的最高原则：

> **不要告诉 NPC 世界应该怎样运行。**
>
> **给 NPC 一套简单、有限、可解释的能力，然后观察世界会变成什么样。**

而作为开发者：

> **不要为了“最终高保真”提前建立巨大的系统。**

而应该：

```text
一个机制
→
一个实验
→
一个结果
→
一次判断
```

不断向前。

---

# Vision in One Sentence

> **CitySim 是一个用于探索“有限认知的个体如何在连续世界中通过感知、记忆、资源、人格、社会互动与行动，共同形成复杂人工社会”的实验平台。**

# END
