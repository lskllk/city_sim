# KB 重构设计 —— 以实体为中心、与真实同构的"以为世界"

> 状态：**架构定稿草案（未实现）**。本文件锁定 KB 的目标形态；实现另起。
> 范围：只重构 `npc/knowledge.py` + `world/perception.py` 的**存储/读写语义**。
> **决策逻辑（`npc/brain.py::decide`）暂不改**（见 §决策源）。

---

## 1. 问题（为什么重构）

现有 KB 用**关系三元组**（`subject - relation - obj`，relation 泛化成
`affords / located_at / price_of`）存一切，且把**验证、置信、遗忘**都塞进
同一条 `confidence` + 一套全局半衰期。副作用：

- relation 的**易变度被无视**：恒常的 `affords` 和频繁变的 `located_at`
  用同一套衰减/证伪策略。
- **遗忘与置信混淆**：`confidence` 既当"信不信"又当"记不记得"，
  一条信息"确信但快忘了"和"半信但常被提"无法区分。
- owner / claimed / stock 这类**现场瞬时状态**是否进 KB、何时 refute 纠缠不清。

**本次定稿确立三个正交的轴**：内容（以为的真值）/ 证据强度（believe）/
记忆强度（remember）。并让 KB 的字段架构与真实 `Entity` **同构**——
世界持有"真值"，每个 Person 持有一份"我以为的"稀疏镜像，决策只读这份镜像。

---

## 2. 核心模型：双层 + 一个正交轴拆分

### 2.1 对象空间与分层
| 层 | 内容 | 谁持有 | 形态 |
|---|---|---|---|
| **真实世界** | Entity 当前真值 | `World`（每个人共享同一份）| `located/owner/claimed/attrs` + item def |
| **KB（本重构）** | 每个 Person **以为**的世界 | 每 NPC 一份、稀疏 | item 中心行（§3）|
| **类型/功能常识** | 物品"能干嘛" | archetype（人人共享只读）| §5 |

### 2.2 决策只读"以为"，真实只经 obs 灌入
```
真实 Entity ──(同地 build_percept / obs)──▶ 刷新 KB 对应行
KB(我以为) ──▶ decide 打分 ──▶ 决策
```
真实世界**不直接**进决策；只在可 obs（同地）时把 KB 刷成现场。

---

## 3. KB schema（以 item 为中心的稀疏表）

```python
# KB = dict[item_id -> Row]；稀疏：只含"我 obs 过 / 被 told 过"的 item
{
  "tv_1": {
    # ——— 内容：我以为的该 item 当前真值（与 Entity 同构）———
    "located": "market",        # 我以为它在哪（易变）
    "owner":   "market",        # 我以为归谁：me | <place id> | <person id>
    "claimed": False,           # 我以为是否正被占用
    "afford":  "fun",           # 它能提供什么（obs/told 自动填）
    "value":   0.4,             # 提供多少
    "price":   60.0,            # 我以为的现价（会变：调价/促销）
    "stock":   3,               # 我以为的库存（-1=无限；会变：消耗/补货）
    "attrs":   {...},           # 特殊/非通用属性（对齐 Entity.attrs）

    # ——— 证据强度：我信不信这条是真的（信几分）———
    "believe": 0.9,

    # ——— 记忆强度：我还记不记得有它（记不记得）———
    "remember": 1.0,
    "last_seen": 123456,        # 最近一次 obs/told 到它的 tick（冗余，便于推导）
  }
}
```

### 字段性质
| 字段 | 语义 | 可变性 | 参与 |
|---|---|---|---|
| afford / value | 功能（能补什么、补多少）| 近恒定 | decide 打分（need × value）|
| located | 我以为它位置 | 易变 | MoveTo 目标 |
| owner / claimed | 我以为归属 / 是否被占 | 易变 | 可否用/可否买（只比 `== me`）|
| price / stock | 我以为现价 / 库存 | 易变 | 去之前估“买得起/还有货吗” |
| attrs | 特殊属性 | 对象相关 | 特定交互 |
| **believe** | 证据强度 | 来源/现场 | 决定"信不信"，不决定"记不记得"|
| **remember** | 记忆强度 | 时间 | 决定"还记得不"，低→遗忘 |

---

## 4. 两轴更新规则

### 4.1 believe —— 证据强度（信几分）
| 事件 | believe |
|---|---|
| 同地 obs 到它（亲眼）| → 高（≈1）|
| 被 told 提及 | → 中（≈0.6）/ 依来源 |
| 现场与以为矛盾 / 失败纠错（证伪）| ↓ |
| 时间流逝 | 不直接因时间衰减（只随 obs 校正；"不刷新也仍信"由 remember 管）|

> 决定"用不用它做强决策"。OBSERVED 证据强、TOLD 弱、现场矛盾 → 降。

### 4.2 remember —— 记忆强度（记不记得）
| 事件 | remember / last_seen |
|---|---|
| 同地 obs 到它 | last_seen=now，remember → 1 |
| 被 told 提及 | last_seen=now，remember → 1（被提起 = 重新想起）|
| 时间流逝 | 每游戏日按半衰衰减 |
| **remember < FORGET（如 0.1）** | **整行删除（真忘了）** |

> 决定"检索/能不能想起来"。obs/told 都会"提神"（刷新记忆），
> 但提神不等于提高 believe（被反复 told 只让你常想起，未必更信）。

### 4.3 遗忘是 remember 的事，不是 believe 归 0
一条信息可能 **believe 高但 remember 低**（确信却久未重提 → 快忘），
或 **believe 低但 remember 高**（常被 told 想起却半信）。
**remember 衰竭到阈值 → 删行**；believe 只决定想起后信几分。

---

## 5. 类型/功能常识（archetype）—— afford/value 从哪来

决策需要"某 item 能解什么"。两个来源：
1. **共享原型常识（archetype，INJECTED）**：出生即认识"床能补 energy、饭能补 hunger"。
2. **个体 obs / told 习得**：首次见到某 item 时，把它的功能也填入该行。

> 设计取舍（已定）：**不做"type → affords"的二次间接查找**，而是当
> obs/told 到某个 item 时，把其 `afford/value` **直接填进该行**（§3）。
> 代价是同一类型多实例会重复存功能——换取单表直观、决策零查找。
> archetype 仍保留作为"初见之前"或"未 obs 时"的功能常识来源。

---

## 6. 来源与条目生命周期

| 来源 | 能否建行 | believe | remember |
|---|---|---|---|
| **obs（亲眼）** | ✅ | 高（≈1）| last_seen=now，→1 |
| **told（传闻）** | ✅ | 中（≈0.6）| last_seen=now，→1 |
| archetype（INJECTED）| 仅原型常识层 | 恒定 | 不衰减 |

删除 = **remember 衰减 < FORGET**（obs 重建可复活）。
（不再需要为每个 relation 单独 refute —— 内容行整体就是一个记忆单元。）

---

## 7. 决策源规则（本版不改 decide，但先定契约）

- decide 只读 KB（"我以为"），候选来自 KB 各行的 `afford/value` 与 `located`。
- **同地**：决策前先 build_percept，用现场 Entity 真值 **覆盖** 对应行的
  located/owner/claimed/afford/value，再决策 → 以最新现场为准。
- **异地**：obs 不到 → 沿用该行旧值（我以为）。若到达后发现"预期在却不在"，
  属 located 记忆过期 → obs 覆盖/纠错（单一负反馈通道）。
- owner/claimed/stock/open 等**现场瞬态**不入长期决策前提；到了现场以现场为准。

> （实现期再决定 decide 是否与如何消费这些新语义；本版冻结：决策逻辑不动。）

---

## 8. 从现状到目标的差异 + 重构删改清单（实现路线参考）

现状 `knowledge.py` / `perception.py` 需对照调整：

| 现状 | 目标 | 动作 |
|---|---|---|
| 存储 = relation 三元组 `overlay{fact_id: Fact}` | item 中心 `dict[item_id -> Row]` | 改存储形态 |
| relation 集合 `affords/located_at/price_of` 泛化 | relation 不再作存储维度；功能并入行内 afford/value | 收敛 |
| `confidence` 一身兼"信不信+遗忘" | 拆 `believe`（证据）+ `remember`（记忆）| 增字段、分更新 |
| `decay(now, half_life)` 全局半衰衰减 confidence | remember 半衰衰减 → 删行 | 改衰减对象 |
| `refute` + `tombstones` | （可选）现场矛盾→降 believe / 覆盖，未必进 tombstone | 待定 |
| upsert 按 (subject, relation, obj) 键去重 | 按 item_id 整行 upsert | 简化 |
| Fact.value 只服务 affords | value 并入行内功能 | 归并 |
| ArchetypeKB（INJECTED 共享）| 保留为"类型/功能常识"来源 | 保留（层语义变清晰）|
| trace / gossip 依赖 Fact.subject/relation | 需基于 item 行 + 来源 ref 重接 | 后续 |
| `learned` 事件 = 新 fact_id | 新 item 行 / believe 显著提升时发 | 调整触发 |

> 未决清单（实现前逐项敲定）：
> 1. `attrs` 是否需要独立可信/记忆，或随整行？
> 2. obs/told 对已存在行的 **believe 合并规则**（高于/低于/等于）。
> 3. FORGET 阈值数值；archetype 行的 remember 是否=∞（不衰减）。
> 4. trace（决策可追溯链）在新形态下如何表达。

---

## 9. 已确认的决策记录（来自讨论）
1. relation 只粗略分 **不变 / 变化** 两类心智，不必过度建模。
2. `affords` 是核心（能补什么、多少）；`is_a` / `kind` 语义价值低，不单独建模。
3. `owner` **非我即他**：KB 存归属，但决策只比 `== me`，不知也不需知"是谁"。
4. 失败（扑空/买不成）本质 = **易变 located 已变而我不知道** → 到达 obs 覆盖/纠错。
5. **遗忘**必须与**置信**分开：新增 remember / last_seen 记忆轴。
6. **obs 与 told 都能建行 / 提神**；行低到 FORGET 才删除。
7. **price（现价）与 stock（库存）都进 KB 行**：会变、需提前知道（去不去、买不买得起、还有没有货）。
