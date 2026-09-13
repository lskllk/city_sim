# city_sim 需求拆解 · 2026-09-10

> 本文是**需求拆解 + 设计草案**，不是最终实现冻结稿。用于把讨论收敛成可执行任务，
> 待逐项确认后再落 `docs/task0XX.md`（设计冻结）。
>
> 核心来源：2026-09-10 讨论。目标是在现有「认知内核」上长出**角色 / 计划 / 经济 / 社会**
> 四层，使 NPC 具备"一步步发展"的人生轨迹，并为将来的 RPG 化身打底。

---

## 0. 背景与总目标

现有内核是"信号驱动"的：`signals(0..1)` → `brain.decide` 看记忆里的物品候选 → 选最优 →
`Intent`。它只能表达"我现在饿了 → 去吃眼前/记得的食物"。

本次要新增的是**时间维度的意图（计划）**、**社会身份（角色/关系）**、**长期资源积累（技能/钱）**，
让 NPC 从"应激反应体"变成"有日程、有身份、有发展的人生体"。

总目标一句话：

> NPC 拥有**身份**（我是谁）→ 由 LLM 生成**日计划**（今天干什么）→ 本地**策略**执行（具体怎么做）→
> 产生**经济与社会**后果（挣钱/学习/交友/结婚/死亡）。

---

## 1. 架构总纲：三层决策（本次最重要的架构决策）

```
第1层 人设层 (identity + role)
   我是谁: 角色 / 雇主 / 学校 / 技能 / 资产 / 关系
        │
        ▼  (每日一次, LLM)
第2层 计划层 (plan)  ← 偏置 MoveTo(去别处) 的地方
   今天 8:00 吃早饭 / 9:00 去某某公司上班 / 18:00 去超市补货 / 20:00 读书
        │
        ▼  (每 tick, 纯函数)
第3层 本地策略层 (brain.decide)  ← 只和【当前所在地】的物品/人交互
   饿了 → 吃眼前的饭；货架有货 → 买；同事在场 → 聊
```

### 关键决策

- **D1：计划不直接产生 Intent，只改评分（偏置）。**
  计划条目不发出 `MoveTo`；它给匹配的本地/异地候选加权（`plan_mult`）。
  Intent 仍由 `brain._choose` 统一打分选出。
- **D2：不设 gate，不限制 MoveTo。**
  `MoveTo` 由三类来源在同一张打分表竞争：① 计划目的地（强偏置）；② 归巢 `home`
  （默认兜底）；③ 本地无法满足的需求驱动的异地记忆目标（应激）。计划只**偏置**、不**门禁**。
  **原因（2026-09-10 修正）**：计划时间粒度粗、活动时长未知，硬 gate 会导致"买完东西回不了家"。
- **D3：计划是"日程槽"，不是"债务"。**
  每条计划有有效窗口 = `[本计划 at_tick, 下一条计划 at_tick)`；窗口内未完成 → 丢弃（skip）。
  **不做跨计划持久/叠加**（推翻早先"权重一直保持"的设想）。
- **D4：计划权重是评分乘子，纯函数注入。**
  `brain.decide` 新增入参 `plans`，引擎在重评前把 `Person` 的 active 计划传入；保持 `decide` 纯净。
- **D5：LLM 计划器只能读 NPC 的记忆与自身状态，绝不读 World 真值。**
  计划里每个 item/地点都必须在该 NPC 记忆中 `believe ≥ 阈值`，或属自身身份已知
  （公司/学校/家）。这是"有限认知"在计划层的红线。
- **D6：LLM 只负责"生成计划"，不负责"执行决策"。**
  决策仍在本地策略；LLM 每天产出一张计划表（可缓存/可回放），执行过程完全确定性。
- **D7：归巢兜底 + 计划前瞻。**
  `home` 是永续的默认目的地（解决"回不了家"）；空闲时可提前前往"下一条计划"的
  `dest`（避免原地空等）。

---

## 2. 需求拆解

### R1 角色系统（身份层）

**需求**：给 NPC 加角色（工程师 / 程序员 / 学生 / 失业 / 辍学…），并带具体信息
（如"工程师在 X 公司上班""学生在 Y 学校上学"）。

拆解子项：

- **R1-1 角色数据模型**：新增 `Role`（`kind / affiliation_id / title / wage_type / work_minutes`）。
  `Identity` 扩展或 `Person` 新增 `role` 字段。
- **R1-2 角色枚举与语义**：`engineer / programmer / student / unemployed / dropout / worker(日结) …`
  每种角色的差异：是否有稳定收入、是否要上学/上班、作息、可获得的计划模板。
- **R1-3 归属实体**：`Company` / `School` 作为**世界中真实组织实体**（不是字段字符串）。
  `affiliation_id` 指向它们。地点即它们的所在地。
- **R1-4 角色影响面**：作息（起床/上班时间）、收入方式（日结/月薪/无）、可生成的计划类型、
  初始技能与金钱、可发展路径（辍学→日结→学技能→白领）。
- **R1-5 场景装配**：`config/scenes/*.json` 的 npc spec 增加 `role` 段；
  `gateway/scenarios.py::load_scene` 解析并装配 `Company/School` 实体。

**代码接入点**：`npc/person.py`（Identity/Person）、`gateway/scenarios.py`、`world/world.py`（组织实体）。

---

### R2 计划表 + 计划权重（本次核心机制）

**需求**：NPC 有一张计划表：某时刻做什么。到点把对应意愿权重抬高；
若在**下一条计划到来前**仍未完成，则**跳过**（不持久、不叠加）。

拆解子项：

- **R2-1 计划数据结构**：`PlanEntry`（见第 3 节）。
- **R2-2 计划表容器**：`Person` 内持有计划队列，提供 `add_plan / active_plans / complete_plan /
  rollover`。计划按天生成、按 tick 激活。
- **R2-3 计划 → 候选匹配**：计划条目声明它要满足的 `signal` 和/或 `tags`，
  用于和 `MemItem`/本地实体匹配（如"吃早饭"匹配 `afford=hunger` 且 `tags` 含 `edible`）。
- **R2-4 计划权重（新增评分项）**：见下方专节。
- **R2-5 完成回写**：本地策略完成对应交互 / 抵达计划目的地后，把计划条目标 `done`；
  若窗口结束仍未完成（如无早饭）→ `dropped`（skip），**不顺延、不叠加**（见 D3）。
- **R2-6 计划与 MoveTo**：计划**不直接产生** `MoveTo`，只**偏置**候选打分（`plan_mult`）；
  `MoveTo` 仍由统一打分选出，承认三类来源（计划 / home / 应激，见 2.R2-B）。
  抵达后计划进入"本地阶段"，本地策略接管（买/吃/学/上班）。
- **R2-7 待办冲突**：多条 active 计划优先级排序；有效窗口 = `[本计划 at_tick, 下一条 at_tick)`。

#### 2.R2 计划权重设计（你要的那项新权重）

**目标**：把"计划"变成评分中一个可解释的乘子；到点渐入，窗口结束即丢弃（不累积）。

数据结构（详见第 3 节）：

```python
PlanEntry:
    id, goal, signal, tags, at_minute, priority, status, created_day
```

**匹配规则**：候选 `MemItem r` 匹配计划 `e`，当

```
e.signal is None or e.signal == r.afford
且  e.tags 为空 或  e.tags ∩ item_tags ≠ ∅
```

**权重公式**：在原有效用上叠乘一个计划乘子：

```
eff_base = need^power × value × personality × believe      # 现状不变
plan_mult(r) = 1 + Σ_{e 匹配 r 且 status=active} priority(e) × ramp(e)
ramp(e) = clamp((now_tick - e.start_tick) / ramp_ticks, 0, 1)   # 到点渐入, 封顶 1
eff = eff_base × plan_mult(r)
```

其中：

- `ramp(e)` 从计划时刻起渐增到 1（对应"8 点开始把意愿加到很高"），**不无限累积**。
- `ramp_ticks` 进 `config/sim.toml`（如 60）。
- **有效窗口**：`active` 仅含 `start_tick ≤ now < 下一条计划 start_tick` 的条目；
  窗口结束仍未完成 → `dropped`（skip），不叠加、不持久（对应 D3）。

**为什么用乘子而不是加项**：现有 `eff` 是乘积式，乘子能保证"计划优先"但不凭空造出候选
（没有饭就没有候选，符合你说的"没早饭就算饿也不会吃早饭"——那是计划/库存问题）。
当 `priority` 高到足以让 `eff` 越过 `utility_threshold`，计划就会压过随机应激。

**纯度**：`brain.decide(...)` 新增参数 `plans: Sequence[PlanEntry] = ()`。
`person.decide` 从自身计划表取 active 条目传入。`brain` 不 import world（红线不变）。

#### 2.R2-B MoveTo 由什么驱动（多来源 + 计划偏置）

**结论：不设 gate，不限制 MoveTo。** MoveTo 由多个来源在同一张打分表上竞争，
计划只做**强偏置**，不做门禁。

**为什么取消 gate（2026-09-10 修正）**：计划时间粒度粗、活动时长未知。例：17:00 到超市
买东西，买多久不知道；买完若计划里没有"回家"条目，硬 gate 会让 NPC 无法回家。
**计划表达的是"意向"，不是"移动日志"**，不可能枚举每一次移动。

**MoveTo 的三类来源（都参与打分）**：

1. **计划目的地**：当前窗口内计划声明的 `dest`（或匹配 signal/tags 的异地候选）→ `plan_mult` 抬分。
2. **归巢 `home`**：永续的默认目的地，基础分不高但始终可选 → 解决"回不了家"。
3. **需求驱动的异地目标**：本地无法满足的需求（记忆里别处有解）→ 保留自发 MoveTo（应激）。

**计划前瞻**：空闲时允许提前前往"下一条计划"的 `dest`（如买完 17:40、下一条 18:00 在家
吃饭 → 直接回家），避免原地空等。

**竞争与承诺**：
- 生存需求（hp 见底 / 膀胱满）可压过计划（软意图 + 生存否决）。
- 正在 travel 中不由决策打断；不可中断交互不被顶掉（现有语义已满足）。

决策流（伪代码）：

```python
decide(signals, personality, mem, loc, cfg, now_tick, money, plans, home):
    active = [e for e in plans if e.status == "active"]        # 含当前 + 前瞻窗口
    cands = gather_candidates(mem, signals, cfg, now_tick)     # 本地 + 异地都要
    for cand in cands:
        cand.score = base(cand) * plan_mult(cand, active)
        if not cand.local:
            cand.score *= cfg.move_penalty                     # 异地成本; 但不再砍掉
    if loc and loc != home:                                    # 归巢兜底
        cands.append(home_candidate(score=cfg.home_bias))
    best = argmax(c.score for c in cands if c.score > threshold)
    if best is None:   return Idle()
    if best.local:     return Buy(best) / Interact(best)
    return MoveTo(best.located)
```

**遗留待定项**：

- **T1 目的地锚定**：计划只能去记忆可信或身份已知的地方（沿用 D5 精神，但**不 gate 应激 MoveTo**）。
- **T2 归巢兜底强度**：`home_bias` 取多大？太大 → NPC 老想回家；太小 → 买完仍可能滞留。
- **T3 应激 MoveTo 是否要限制**：完全开放（方案 A）还是"本地不可解且紧急"才允许（方案 B）？

**代码接入点**：`npc/brain.py`（`_score_candidates`/`_gather_candidates`/签名）、
`npc/person.py`（计划表）、`world/engine.py`（调用处传 plans + 完成回写）、
`config/sim.toml`（ramp/cap/默认 priority）。

---

### R3 LLM 日计划生成

**需求**：用 LLM 读取 NPC 全部状态（角色、在哪上班、家里物资、资金…），规划明天/本周计划。

拆解子项：

- **R3-1 触发时机**：每天固定时刻（如 23:00 或 0:00）为每个 NPC 生成次日计划。
- **R3-2 输入快照（prompt 数据）**：待讨论，初拟（见第 6 节问题 Q1）：
  角色/雇主/学校、当前位置与作息、signals、money、家中物品清单（含库存/价格）、
  已知商店与价格（记忆）、进行中/未完成计划、技能、关系（后续）、天气/日程约束。
- **R3-3 输出契约（结构化，非自由文本）**：LLM 必须返回 `PlanEntry[]` 的 JSON，
  经 schema 校验后才入库；非法/超时 → 回退到规则模板计划（保证不停摆）。
- **R3-4 确定性/回放**：LLM 是外部非确定性源。必须**记录 LLM 原始响应**（或缓存产物）
  到场景/回放日志；`test_replay` 用缓存重放，不重新调用 API。
- **R3-5 降级策略**：无网/无 key/FX 失败 → 用"角色模板计划"（R1-4 的作息模板）。
- **R3-6 成本与频率**：只对"活跃/在视野/关键"NPC 调用（可结合未来 LOD），避免 N 倍 API 成本。

**代码接入点**：新增 `npc/planner.py` 或 `llm/` 模块（npc 层，不得 import world；
世界状态由调用方以纯数据注入）。`gateway`/`sim` 侧提供状态快照与缓存。

---

### R4 物品：电脑；地点：工地；日结打工；电脑找工作

**需求**：新增电脑物品、工地地点；没钱的人只能去工地搬砖挣日薪；有电脑才能找工作。

拆解子项：

- **R4-1 新物品**：`config/items/computer.json`（家用的上网/求职工具）、可能的 `brick/tools` 等。
- **R4-2 新地点**：`site`（工地，已有雏形 `work_bench` + scene `site`）、以及互联网咖啡馆（可选）。
- **R4-3 日结劳动**：`Work` 交互 → 产出 `money`（日结）。现有 `effects` 只有 5 个 op，
  需要新增经济 op（如 `earn_money` / `pay_wage`），并遵守"钱只增需显式 op"。
- **R4-4 求职前置条件**：找工作需要"电脑 + 联网"或"中介"，即某种交互/物品门槛；
  可在计划层表达为"需要 computer 才能生成 apply_job 计划"。
- **R4-5 工作成果与工资**：日结（当天结算）vs 月薪/年薪（定期结算），
  结算走**世界侧定时脚本**（`world/pulses.py`）或公司工资脉冲，保证记账闭环。
- **R4-6 记账闭环前置**：现有 `_execute_buy` 只扣钱不收款（`world/engine.py`）。
  经济系统落地前必须先补"买卖双方双分录 + 收款方账户"。

**代码接入点**：`config/items/*.json`、`config/scenes/elm_lane.json`、`world/effects.py`（新 op）、
`world/engine.py::_execute_buy`、`world/pulses.py`、`npc/person.py::pay`（加收入）。

---

### R5 书店 / 书本 / 技能 / 月薪年薪 / 逐步发展

**需求**：增加书店和书，NPC 买书回家学习；给 NPC 增加技能；技能带来月薪/年薪的稳定工作，
模拟一步步发展的过程。

拆解子项：

- **R5-1 新地点**：书店；新物品：书（`book_*.json`，含要学的技能与时长）。
- **R5-2 技能系统**：`Person.skills: dict[str, float]`（0..1 或等级）。
  学习交互（读书/上学/工作）按 tick 增长技能。
- **R5-3 技能 → 产出/准入**：技能影响工作效率、产量、质量；并作为岗位准入门槛。
- **R5-4 职位分级**：日结工（无门槛）→ 技术岗（需技能）→ 高薪岗（高技能 + 学历/关系）。
  岗位定义数据化（`config/jobs/*.json` 或场景内）。
- **R5-5 稳定收入**：月薪/年薪按游戏时间定期由雇主发放（pulses），可预期可规划。
- **R5-6 发展路径**：失业/辍学 → 工地日结 → 买电脑找工作/买书学技能 → 白领 →
  （后续）升职/创业。用计划模板 + 技能门槛驱动，**不写死脚本**。
- **R5-7 学历/在读**：学生角色按期上学提升技能（对应 R1）。

**代码接入点**：`config/items/book_*.json`、`npc/person.py`（skills）、
`npc/brain.py`（技能影响打分/准入）、`world/effects.py`（学习/涨技能 op）、岗位数据文件。

---

### R6 关系图谱 / 社交 / 家庭 / 生老病死

**需求**：NPC 关系图谱（人物与关系）；NPC↔NPC 交流、交换信息、成为朋友/敌人、结婚生子、生老病死。

拆解子项：

- **R6-0 前置（必须先做）**：**当前 NPC 看不见彼此**。
  `world/perception.py::build_percept` 只装实体，其它 Person 不在 Percept 里。
  必须先加**人物感知**（`PersonView`：谁、在哪、在做什么、认不认识），
  并让 `Interact` 的目标可以是"人"。这是 R6 一切社交的物理前提。
- **R6-1 关系数据模型**：`Person` 持有关系表 `relations: dict[person_id, Relation]`；
  `Relation{affinity, trust, kind(friend/enemy/spouse/parent/child/…), history}`。
  关系是**记忆的产物**，不写全局社交真值。
- **R6-2 对话/TOLD**：`EventView.kind="told"`、`SourceKind="TOLD"` 已有插槽但未实现。
  实现"人物间交换 MemItem（带 believe 折扣）+ 关系变化"，一次实现同时服务 NPC↔NPC 与
  （未来）玩家↔NPC。
- **R6-3 信息交换与传谣**：`_notify_due`（`world/engine.py`）是空壳，需实现"从已知事实挑一条
  告知同地他人"，带延迟/失真（Vision §15）。
- **R6-4 社交事件**：成为朋友/敌人（affinity 阈值 + 事件）、结婚（双向关系 + 条件）、
  生子（新 Person 生成、继承/变异 Vision §19）、衰老与死亡（年龄推进，已有 `npc_died` 事件的雏形）。
- **R6-5 家庭与人口**：生育/死亡进人口统计；与资源/关系/环境耦合。
- **R6-6 可解释性**：关系变化必须可追溯（复用 `DecisionTrace` / 事件溯源）。

**代码接入点**：`world/perception.py`、`core/types.py`（PersonView / 人物 Interact）、
`npc/person.py`（relations/skills）、`npc/brain.py`、`world/interaction.py`、
`world/engine.py::_notify_due`、`world/events.py`。

---

## 3. 新增数据模型汇总（草案）

```python
# 身份层
Role:
    kind: str                     # engineer/programmer/student/unemployed/dropout/worker
    affiliation_id: str = ""      # company_id / school_id
    title: str = ""
    wage_type: str = "none"       # none/daily/monthly/yearly
    work_minutes: tuple[int,int] | None

# 计划层
PlanEntry:
    id: str
    goal: str                     # eat_breakfast/go_work/buy_groceries/study/socialize/sleep
    signal: str | None            # 匹配本地候选的需求信号
    tags: tuple[str, ...]         # 匹配本地候选的物品标签
    at_minute: int                # 当天分钟(0..1439)
    priority: float               # 0..1, LLM/模板给
    status: str                   # pending/active/done/dropped
    created_day: int
    start_tick: int = -1          # 激活时刻(用于 overdue)
    dest: str = ""                # 非空 → 计划目的地(偏置, 非 gate)

# 资源/能力
Person.skills: dict[str, float]
Person.relations: dict[str, Relation]
Relation:
    affinity: float               # -1..1
    trust: float                  # 0..1
    kind: str                     # stranger/friend/enemy/spouse/parent/child/...
    since_tick: int

# 组织(世界实体)
Company / School:
    id, name, location_id, treasury, members, jobs[]
```

---

## 4. 与现有代码的接入点速查

| 需求 | 主要文件 | 关键函数/结构 |
|---|---|---|
| R1 角色 | `npc/person.py`, `gateway/scenarios.py`, `config/scenes/*.json` | `Identity`, `load_scene` |
| R2 计划权重 | `npc/brain.py`, `npc/person.py`, `world/engine.py`, `config/sim.toml` | `decide`, `_score_candidates`, `_choose` |
| R3 LLM 计划 | 新增 `npc/planner.py`（不 import world） | 新模块 |
| R4 打工/电脑 | `config/items/*`, `world/effects.py`, `world/engine.py`, `world/pulses.py` | `OPS`, `_execute_buy`, `_apply_op` |
| R5 技能/岗位 | `npc/person.py`, `world/effects.py`, `config/items/book_*.json` | `skills`, 学习 op |
| R6 关系/社交 | `world/perception.py`, `core/types.py`, `world/interaction.py`, `world/engine.py` | `build_percept`, `Interact`, `_notify_due` |

**红线提醒**：`npc/` 层严禁 import `citysim.world`（`tests/test_import_layers.py`）。
LLM 计划器要拿世界状态，必须由 `world/sim` 侧以纯数据注入。

---

## 5. 建议阶段路线（按依赖排序）

1. **S0 经济地基**：记账闭环（买卖双分录）+ 最小 `Company`。`_execute_buy` 补收款。
2. **S1 角色 + 组织**（R1）：`Role` / `Company` / `School` 数据 + 场景装配。
3. **S2 计划表 + 计划权重**（R2）：纯规则计划（先不接 LLM），验证"到点抬权、窗口结束跳过、home 兜底"。
4. **S3 人物感知 + 对话基础**（R6-0/R6-2 前置）：让 NPC 能看见/交谈，为 LLM 提供社交上下文。
5. **S4 技能 + 新物品/地点 + 日结/月薪**（R4/R5）：形成"发展"闭环。
6. **S5 接入 LLM 日计划**（R3）：带缓存/降级/回放。
7. **S6 关系图谱 + 社交/家庭/生死**（R6 完整）。
8. **S7（未来）**：玩家 RPG 化身接入同一套三/四层架构。

> 说明：R2 先用**规则模板计划**跑通再上 LLM（S2 在 S5 前），这样计划权重可独立验证，
> 不被 LLM 的非确定性干扰。

---

## 6. 待讨论问题（需你拍板）

- **Q1 LLM prompt 的输入数据到底包含哪些？** 候选清单：
  角色/雇主/学校、作息、signals、money、家中库存（含价格）、已知商店与价格（记忆）、
  未完成计划、技能、关系、天气/节日、附近可去场所。要不要包含"记忆里别人的信息"？
- **Q2 LLM 输出粒度**：只出"明天"还是"本周"？时间粒度到分钟还是到"上午/下午/晚上"？
- **Q3 计划冲突策略**：同刻多计划怎么排序？未完成条目保留多久（跨天顺延几次后丢弃）？
- **Q4 计划权重用乘子还是加项**（本文用乘子），`ramp/cap/默认 priority` 取值？
- **Q5 MoveTo 驱动的待定项**（见 2.R2-B）：T1 目的地锚定、T2 归巢兜底强度 `home_bias`、
  T3 应激 MoveTo 完全开放(方案 A) 还是限"本地不可解且紧急"(方案 B)？
- **Q6 记账细节**：月薪/年薪的结算周期、公司破产、通胀是否需要（Vision §25 反复杂度）。
- **Q7 关系是"每人对每人的矩阵"还是"稀疏有向图 + 记忆行"？** 规模（几十/上百人）下的取舍。
- **Q8 生育/死亡是否本阶段做**，还是先做"关系 + 交流"，家庭留到后面。
- **Q9 确定性边界**：LLM 计划要不要进 `test_replay`？用缓存回放还是测试里 mock？

---

## 7. 风险与冲突

- **C1 计划与应激抢 MoveTo**：不 gate 后，计划目的地与本地/应激候选在同一打分表竞争。
  靠 `plan_mult` 抬计划、`need^power` 让紧急需求爆炸、travel 中不打断来调和，而非 gate。
  需通过实验调参（`home_bias` / 计划 priority）。
- **C2 LLM 破坏确定性与回放**：必须缓存/记录 LLM 输入输出，测试用缓存重放（R3-4/Q9）。
- **C3 社交缺人物感知**：没有 R6-0，R6 全是空中楼阁。
- **C4 经济不通账**：没有 S0，工资/收入只是数字游戏，宏观现象无法涌现。
- **C5 复杂度失控**：角色/计划/技能/关系/经济/人口一起上会超出 Vision §25 的
  "一个机制→一个实验"原则。**必须按 S0→S7 分段验收。**
- **C6 玩家全知问题**（未来）：RPG 化身需要服务端只推玩家自身 Percept，与本文件暂不冲突，
  但设计计划/关系数据结构时要预留"玩家视角"可被裁剪。

---

## 8. 完成定义（本文档层面）

- [ ] 以上 R1–R6 每一项已确认范围与优先级
- [ ] 第 6 节 Q1–Q9 已拍板
- [ ] 确定动手的第一阶段（建议 S0 + S1）
- [ ] 将第一阶段拆成 `docs/task0XX.md` 设计冻结稿
