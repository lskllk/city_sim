# 计划表 —— 角色日程模板 + 自由块（MVP）

> ⚠️ **已被 `docs/20260914/plan.md` 修订取代**（2026-09-14）。本版以下内容已作废：
> - **F2 自由块 → 删除**（utility 回到主导后，自由块整块多余）
> - **定位收缩**：计划表不再是主导，只做「承诺」（上班/上学）
> - 新增：成本项（原 §7 F3 从"以后"变"必须"）、囤货模型、`alertness`/`energy` 拆分
>
> 本文件保留作历史记录，**新实现以 `docs/20260914/plan.md` 为准**。

> 状态：**M-P1 设计冻结，未实现**。上位文档：`docs/20260913/mind.md`、`docs/20260913/semantic_event.md`
>
> 决定：**计划表不用 LLM，用本地算法。** 本次只做两条功能。
>
> 一句话：**日程 = 强制块（角色模板）∪ 自由块（执行时用效用挑）。**

---

## 0. 前置：`thirst` / `fun` 已删除

本次实现前已完成（全栈清理，`pytest` 94 passed）：

- `SIGNALS` / `REFLEX_SIGNALS` / `sim.toml` / `planner` / `person.heartbeat` / `snapshot` / `scenarios`
- 物品：删 `drink_dispenser` / `media_tv` / `game_mahjong` / `seat_bench`；`food_*` / `meal_simple` 去掉 `thirst`
- 场景 `elm_lane.json` / `scene.json`：实体、记忆、计划、personality 全部清理
- 前端：`zh.gd` / `inspector/data.gd` / `editor/main.gd` / `editor/map_doc.gd`
- 工具与测试同步

**语义钉死：`fun` = 刺激需求（驱动），不是幸福度。** 幸福度是 `Mind` 里情绪的自然结果，不建字段。
（`thirst` 与 `hunger` 机制冗余，故砍；`fun` 是唯一非生存需求，将来做网吧/理发/商场时按同一套机制加回。）

---

## 1. 本次只做两条功能

| # | 功能 | 说明 |
|---|---|---|
| **F1** | **角色日程模板** | 每个角色一套 `[(时间窗, 目标类型)]`。确定、可解释、便宜 |
| **F2** | **自由块** | 计划里插入 `goal = {signal: "..."}` 的块；空档里**用效用挑**具体目标 |

两条合起来就是：**强制块保证"日子像日子"，自由块保证"今天有今天的意外"。**

---

## 2. 现状（代码事实）

| 事实 | 影响 |
|---|---|
| `planner.py` 的三个常量 `_MEALS` / `_SLEEP` 把日程写死 | 换业态要改代码 → **本次要拆的就是它** |
| `PlanEntry = (entry_id, at_tick, intent, status)`，**持有具体 Intent** | 计划在 0:00 就把目标定死，之后改价/缺货/被抢占都反应不了 → **改成 goal** |
| `entries_from_spec()` 校验「目标必须在记忆里」 | **红线，复用**：goal 实例化时用它 |
| `brain.decide()` 没有 `plans` 入参，`plan_mult` 未实现（`world/drive.py:8` TODO） | 计划目前是"直接下发 Intent"，不是"偏置打分" → **本次接上 D1** |
| `_gather_candidates` 有 `fallback_need = 0.9` | 平时不产生候选 → 行为几乎全靠计划表 |
| `decide` 不产生 `Buy`（没 import `Buy`） | 购物 100% 靠计划表 → 见 §7 F3 |

---

## 3. F1：角色日程模板

### 3.1 数据，不是代码

新增 `config/roles.json`：

```json
{
  "worker": {
    "anchors": [
      {"goal": {"kind": "work"},  "at": "09:00", "until": "18:00", "loc": "@affiliation"},
      {"goal": {"kind": "sleep"}, "at": "23:00", "loc": "@home"}
    ],
    "rhythm":  {"wake": "07:00"},
    "weights": {"hunger": 1.1}
  },
  "student":    {"anchors": [{"goal": {"kind": "school"}, "at": "08:00", "until": "15:00", "loc": "@affiliation"}]},
  "shopkeeper": {"anchors": [{"goal": {"kind": "work"},   "at": "09:00", "until": "21:00", "loc": "@shop"}]},
  "unemployed": {"anchors": []},
  "retired":    {"anchors": [], "rhythm": {"wake": "09:00"}}
}
```

### 3.2 核心：符号引用，不是地点 id

```text
@home         我家
@affiliation  我所属组织（公司 / 学校）的所在地
@shop         我开的那家店
```

`@affiliation` 是**解析器**，不是地点 id。所以：

| 事件 | 结果 |
|---|---|
| 失业 | `affiliation_id = ""` → `@affiliation` 解析失败 → **该锚点自动不生成** |
| 找到工作 | 写入 `affiliation_id` → 重编译 → 上班锚点自动出现 |
| 换公司 | 只改那一个字段 |
| 自己开店 | `@shop` 解析到自己的店 |

**这就是"一套代码满足所有目的"的答案：差异全在数据，代码不知道"角色类型"。**

### 3.3 同一段代码跑所有身份

| 身份 | anchors 数据 | 同一段代码产出 |
|---|---|---|
| 失业 | `[]` | 作息 + 自由块 |
| 打工人 | `work 09:00-18:00 @affiliation` | 07:00 起 → **08:40 出发** → 18:00 下班 → 回家 |
| 学生 | `school 08:00-15:00 @affiliation` | 同一个编译器，只换了锚点 |
| 店主 | `work 09:00-21:00 @shop` | 自己的店；空档走自由块 |
| 退休 | `[]` + 不同 rhythm | 晚起、空档更多 |

### 3.4 「按时上班」靠三件事，不靠门禁

1. **把通勤排进计划。** `at = 09:00` 的锚点，实际生成 `08:40 出发`（`09:00 − travel_cost`）。
   **准时靠预留，不靠门禁。**
2. **权重随临近陡增。** 离锚点越近，`plan_mult` 越大（软保证）。
3. **`plan` 本来就能硬中止。** 现有 `Decision.source` 已有语义（`reflex` 软挂起 / `plan` 硬中止），上班属于 `plan`。

**没走到怎么办？不做门禁，做后果**：迟到被记录 → 扣钱 / 警告 → 关系与信任变化 → 极端情况被辞退。
（这补足了 `20260910/requirements.md` 的 **D2**：不用硬门禁，但用「通勤预留 + 权重陡增 + plan 可中止」拿到事实上的准时。）

### 3.5 锚点冲突 → 裁剪，不丢弃

作息与锚点重叠 / 过紧时**按优先级裁剪**。
丢弃会让 NPC 直接没有日程，比裁剪更糟。

### 3.6 变更时重编译

`identity.affiliation_id` 变化 → 重编译当天**剩余**日程。
`Person.set_plan()` 已经能覆盖，现成的。

---

## 4. F2：自由块

### 4.1 形态：只说类型，不说具体目标

```python
PlanEntry(entry_id, at_tick, goal=Goal(signal="hunger"), status=PENDING)
```

`goal` **不带 item_id / dest**。具体去哪家店、买哪个货架、买几件，**执行时刻**才定。

### 4.2 执行时用效用挑

`decide` 收到 plans 后：

1. 把 goal 实例化：从**记忆**里找 `afford == goal.signal` 且 `value > 0` 的候选（复用 `entries_from_spec` 的红线）
2. 对匹配 goal 的候选加权 `plan_mult`
3. 照常打分选优 → 产出 `Interact` / `MoveTo` / `Buy`

**"去便宜的那家"就发生在第 3 步**（详见 §7 F3 的成本项）。

### 4.3 自由块要能覆盖非致命需求

现在只有 `REFLEX_SIGNALS` 才产生候选（`fallback_need = 0.9`，接近致命才动手）。
自由块必须能让**非致命信号**也产生候选：

```text
REFLEX_SIGNALS  → 兜底安全网（fallback_need 高阈值），不变
goal.signal     → 自由块驱动（不受 fallback_need 限制）
```

两者合流进同一张打分表 —— 这正是 D1「计划只改评分，不门禁」。

### 4.4 D1：计划只偏置

```
utility(candidate) = base × plan_mult × (将来的 mood_mult / emotion_mult)
```

不设 gate、不限制 `MoveTo`（沿用 D2）。三类来源同表竞争：① 计划目的地 ② 归巢 `home` ③ 应激。

---

## 5. 验收标准

1. **换 role 数据不改代码**：把某角色的 anchor goal 换成另一种 `signal` + `loc`，**一行代码不动**，链路照样跑通。这才证明不是"只能买菜的专用流程"。
2. **同 role 不同归属**：两个 `worker`，各自去各自的 `@affiliation`，不串门。
3. **失业 NPC** 没有工作锚点，日程只由作息 + 自由块组成，且不会卡死。
4. **中途改 `affiliation_id`** → 当天剩余日程重编译，第二天正常上班。
5. **通勤预留**：`at = 09:00` 的计划里，出发时刻 = `09:00 − travel_cost`。
6. **自由块能挑到目标**：`goal.signal = "hunger"` 时，选到的是记忆里 afford=hunger 的具体实体。
7. `test_replay.py` 仍通过（确定性未破坏）。

---

## 6. 代码落点

| 文件 | 改动 | 量 |
|---|---|---|
| `config/roles.json` | **新增**：角色 → anchors / rhythm / weights | 数据 |
| `npc/planner.py` | `template_plan()` → 从 role 数据编译 anchors；删 `_MEALS`/`_SLEEP` 常量 | 中 |
| `npc/schedule.py` | `PlanEntry.intent` → `goal`（保留旧构造做兼容） | 小 |
| `npc/goal.py` | **新增**：`Goal` + `@home`/`@affiliation`/`@shop` 解析器 | 小 |
| `npc/brain.py` | `decide(..., plans)` 入参；`_gather_candidates` 接受 goal.signal；`_score_candidates` 乘 `plan_mult` | 中 |
| `npc/person.py` | 透传 `plans` 给 `brain.decide` | 小 |
| `world/engine.py` | 计划截止 / 硬中止沿用现有；不新增 | — |
| `gateway/scenarios.py` | 解析 role → anchors（或走 `config/roles.json`） | 小 |
| `gateway/snapshot.py` + `godot/` | 时间线可视化改显示 goal（原显示具体 Intent） | 小 |

---

## 7. 不在本次范围

### 已定简化：货物移动 = 瞬移

`_execute_buy` → `_deliver()` 把货**直接送进家里容器**（nav 场景里 `container=auto1` 就是它）。
NPC 背包 / `Take` / `Place` 已全栈删除：`Place` 原本**完全不可达**，`Take` 只在濒死反射路径触发。

**这是有意识的玩法取舍**：MVP 阶段承认“买了就到家”。将来真做物流，用
`mass / volume / container` 重新设计，**而不是复活旧背包**。

### F3（下一步）：比价与成本项 —— 让 `decide` 能产生 `Buy`

现在 `decide` 不认识 `Buy`，且评分公式里**没有价格**：

```text
现状: eff = need^power × value × personality × believe × move_penalty
```

价格是**成本**，不是乘数。改用比率形式（保持正数、可乘、退化平滑）：

```text
cost = price × qty + κ × price × (1 − believe)
eff  = (need^power × value × personality × believe) / (1 + λ × cost)
```

两个附带结论：

- **不确定的便宜要打折**（`κ` 项）："听说便宜"不如"亲眼看到便宜"可靠 → 让传播/知识层有经济后果。
- **比价池 = 记忆里有的店**：没被人知道，就没进比价池 → "营销改的是别人脑子里知道什么"。
- `Mind` 在此拿到第一份正式工作：对店主的好感/信任 → 偏置（知道你便宜还是去老王家）。

### 其他延后

- **习惯层**（`(时间窗, 地点, 目标, 权重)`，重复 N 次成习惯）：个性化最便宜的来源，`Vision.md` §8 的落点。
- **跨天长期目标**（"我要攒钱开个店"）：不做完整 HTN，只做最顶层一层。
- 效用填充的细化（随机性、多样性）。

---

## 8. 铁律

1. **计划只偏置，不门禁**（D1 / D2）。
2. **计划只能引用记忆里的目标**（红线，复用 `entries_from_spec`）。
3. **符号引用在执行时解析**（角色可变，计划不能把地点写死）。
4. **`npc/` 不 import `world`**。
5. **日程生成要确定性**（同 seed 同日 → 同日程）。

---

## 9. 待定

- 锚点冲突的裁剪优先级表（时间锚点 > 自由块？上班 > 吃饭？）。
- `config/roles.json` 与 `config/scenes/*.json` 的职责边界：角色模板全局共享，还是允许场景覆盖？
- 自由块的**时长**从哪来（goal 没有 `duration_ticks`，交互时长在物品上）。
