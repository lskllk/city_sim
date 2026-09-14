# 20260914 决议清单（索引）

> 一页速览。细节见同目录四份文档：`game.md` / `mvp.md` / `bubble.md` / `plan.md`。
> 本文件是**索引与验收清单**，不引入新设计；有冲突以对应机制文档为准。

---

## 1. 游戏定位

- [x] 玩家 = **一个可自由行动的 NPC（店主）**，不是上帝视角
- [x] 全局管理能力由**特殊物件**提供：电脑 → 经营面板（招聘 / 定价 / 管理）
- [x] **支柱 A**：顾客是**真实 NPC**（需求 / 日程 / 记忆 / 信任）
  - **禁止**引入"客流量 / 平均满意度"这类抽象层
- [x] **支柱 B**：气泡 = **语义层可视化**（HUD + juice + 反馈回路三合一）
  - **必须为真**（由真实内部状态长出）；气泡撒谎 = 游戏撒谎
- [x] 经营动作必须落在**具体 NPC 的信念**上；**看不见 ≠ 没发生**
- [x] **【定死·最高优先级】** **知识边界（P8 = B）**：**玩家的手只能碰世界，碰不到 NPC 的脑子。**
  - 经营动作**只写世界真值**（改价 → `world` 立刻变，**但没人知道**）
  - NPC 的知识**只能**由**感知**（`perceive_into`）或**传闻**（`_notify_due`）写入
  - **禁止任何"全局同步 NPC 知识"的捷径** —— 违反则支柱 A 当场死
  - 读侧 `decide` 只读记忆（已有）+ 写侧记忆只能由感知/传闻写（新）→ 架构上不可违反
  - 配套必需：**观察 UI**（气泡/Inspector，看"谁知道了 / 传多广"）+ **主动投放**（招牌）

## 2. MVP：消息传播 + 气泡（先做这个）

- [x] ① **知识** = 一行记忆 + `MemItem.source`（1 行代码）
- [x] ② **传播** = 同地 + 空闲 + 说一件对方不知道的
  - [x] 信任只有两档：**同址 `home` 相等 → 0.9~1.0**；否则 **0.4~0.7**
  - [x] **按两人 id 派生**（一次抽定：零存储、可回放）
  - [x] **不再需要 hop 折扣**（trust 就是折扣）
  - [x] **没有"家庭"概念**，只有"住址"这个**布尔谓词**（零新实体）
- [x] ③ **显示** = 头顶气泡
  - [x] 后端决定文字 → 快照带 `bubble` 字段 → 前端只画
  - [x] 瞬时事件（~40 ticks），**不是** `activity`
  - [x] `bubble_layer.gd`：`draw_style_box` + **屏幕坐标 + 固定像素字号**，**零节点**
  - [x] **挂听者**；MVP **不可点**
  - [x] 模板：`told → "听说{名字}{价格}块"`（不接 LLM）
- [x] **MVP 不做**：trust 演化 / verify / 情绪 / 关系网 / Episode / plan / LLM

## 3. PLAN 收敛版

### 3.1 定位
- [x] **PLAN = 承诺**（上班 / 上学）；**utility 主导其余一切**
- [x] **删除 F2 自由块**
- [x] 承诺以「**时间派生的紧迫度**」参与打分（不是指令），**可以被打败**

### 3.2 架构简化（✅ 已实现）

- [x] **删掉候选筛选层**：`REFLEX_SIGNALS` 白名单与 `fallback_need` **都已删除**，
      `SIGNALS` 只剩 `energy/hunger/bladder/hp`
- [x] **阈值只落在得分上**：`utility.threshold = 0.05`
      （它同时承担“琐碎需求别动”与“别为了小事跑一趟”）
- [x] **删双轨仲裁**：`_reflex_goal` / `_plan_goal` → **单个 `_goal`**，
      `source ∈ {need, plan}`；`Person.decide` 变成单轨：**需求 > 日程 > idle**
- [x] **迟滞抢占**（新增 `preempt_ratio = 1.5`）：需求每 tick 复评，
      只有 **明显更好**才改主意 —— 否则会在两个差不多好的目标间抽风，
      而不设防则会“快饿死了还在睡”。需求轨不看 `can_preempt`（命比规矩大）
- [x] **保留** 交互的 `interruptible`（正交，别一起删）
- [x] **`suspend` / `resume` 保留但语义变了**：不再由计划轨强制恢复，
      而是“那个目标仍值得做 → 重新被选中时 engine 自动 resume 挂起进度”
- [x] **删 `move_penalty`**：异地成本只由**真实行走 tick** 表达

### 3.3 打分与成本
- [x] `eff = (urgency^power × value × personality × believe) / (1 + λ × cost)`
- [x] `cost = price×qty + time_value×travel_ticks + κ×price×(1−believe)`
- [x] → **比价 / 比距离 / 顺路**（顺路是涌现的，不写逻辑）

### 3.4 承诺的维持
- [x] 在岗 = 进行中（incumbent 迟滞）；要离开需压过 **`breach_cost`**
- [x] `breach_cost` 是**当下就知道的价格**（不是前瞻）
- [x] **`breach_cost` 随 `hp` 衰减**：`hp < 0.5` 时 `plan_mult = breach_cost = 0`
- [x] 迟到复用同一机制；`conscientiousness` 调 `breach_cost`

### 3.5 囤货 = 目标存量模型
- [x] 容器实际存量 ∈ **家**（共享事实）；目标存量 ∈ **个人**（由 `thrift`）
- [x] 缺口 → `need_future`（**与睡觉同一条公式**）
- [x] **不做** "home 有需求 → 发任务"；重复购买**接受**（自限、lumpy）

### 3.6 睡眠 = 单信号 `energy` + 昼夜衰减（✅ 已实现）
- [x] **不拆 `alertness`**（拆的理由随 `REFLEX_SIGNALS` 一起消失）
- [x] `energy` 消耗 = **基准 × 昼夜倍率 × 活动倍率**
      （`apply_metabolism` 的 `rhythm_mul` / `activity_mul`）
- [x] **昼夜倍率**（`sim.toml [energy_rhythm]` 控制点插值，`config.rhythm_at()`）：
      白天 ~0.7、夜里 ~2.6 —— **夜里掉得快 → 困 → 去睡**，
      数据里没有「时刻 → 行为」的映射
- [x] **活动倍率**：睡觉**冻结**；在做事（交互/赶路）`busy_energy_mul = 1.8`；空闲为基准
- [x] **`energy` 是 1 天的存量（不再是 4 天）**：基准按曲线**归一化**，
      使"整整 24h 不睡刚好耗光 1.0"（白天占 ~0.38，夜里 ~0.62）
- [x] 结果：NPC 自己长出**作息**（22:00 睡 → 06:00 醒 → 三餐），全是涌现的
- [x] 归零 → `hp` 掉（现有行为保留）；睡觉恢复（床数据**不用改**）
- [x] **不新增信号**；`SIGNALS` 保持 `energy / hunger / bladder / hp`

### 3.7 生命（`hp`）三态（✅ 已实现）
- [x] `hp ↓`：`hunger == 0` 或 `energy == 0`
- [x] `hp ↑`：`hunger ≥ hp_regen_floor(0.5)` 且 `energy ≥ 0.5`
- [x] **其他 → hp 不动**（中间带 —— 否则咬一口饭 hp 就开始涨，“饿死”永远发生不了）
- [x] `bladder` **不参与** `hp`（憋不住不致命）
- [x] `hp < hp_override(0.5)` → **日程失去拉力**（命比钱大）：
      正在做的计划目标立即放弃（不看迟滞比）；要新起时也不给计划
      （暂时挂起而非丢弃，hp 回来再接着走 —— 否则会转圈）
- [x] 顺带按 D3 补上「计划窗口过期就跳过，不补做」，
      边界与 `Schedule.deadline()` 同口径（**严格更晚**的下一条才算截止 →
      同刻串行任务如 `MoveTo`+`Interact` 不会被互相跳掉）

### 3.8 惩罚
- [x] **惩罚 = 状态调制产出**（不写"违规扣分"）
- [x] `产出 = 基础产出 × f(energy)`；违约 → 扣钱 + 信任↓
- [x] 惩罚**回写状态**（钱少 → 买不起 → 更穷）→ 闭环

### 3.9 判据
- [x] 数据里**不出现「时刻 → 行为」的映射**
- 合法涌现燃料：昼夜节律、距离、价格、关门时间、工作承诺

## 4. 明确不做（重要的简化）

| 删掉 / 不做 | 理由 |
|---|---|
| `F2` 自由块 | utility 主导后多余 |
| `REFLEX_SIGNALS` + 双轨仲裁 | 计划只是偏置 → 没有"要抢占的计划" |
| `home_bias` 归巢兜底 | NPC 有需求自然会回家 |
| `safety` 安全感 | 让系统变复杂，收益已被"自然回家"覆盖 |
| `alertness`（拆信号） | 单信号 `energy` 够用；两个玩法杠杆延后 |
| 多 `afford` 物品（原 A2） | 等真需要"一个物品满足两种需求"时再做 |
| trust 系统 / verify / 情绪 / 关系 | 作为**插件**挂回同一条线（MVP 之后） |
| Episode / LLM / 前瞻 | 推迟 |

## 4.5 推送架构：观察驱动（✅ 阶段①②已实现）

> 详细：`docs/20260914/observe.md`

- [x] `PUSH_HZ` **保持 60**（靠观察驱动减压）；HUD 显示 `↓/↑ 字节/秒`
- [x] **超时 = 丢帧，不断线**（断开只会引发疯狂重连）
- [x] **状态未变 → 不推整帧**（暂停时流量归零）
- [x] **渲染签名 + dirty**：只推变化的 NPC ∪ 选中的
- [x] **位置只在状态迁移时推**：在家不动永远不推；途中一帧不推（客户端插值）
- [x] `build_snapshot(only=…)` 过滤
- [x] 客户端 **merge** 而非替换 + `select` 上报选中
- [x] `_traveling` “到站即停”（防丢帧留下幽灵圆点）
- 实测 60Hz：**7.8 KB/帧 ≈ 501 KB/s**（原 8.5 MB/s），≈17 倍降幅
- [ ] 待做 ③ L3 静态段只在变化时推；④ 按视口过滤（上千人）

## 4.6 多楼层（✅ 已实现，编辑器 + 后端 + 观测器全链路）

### 契约

```text
建筑 floors: N
导出:  bld_007 (本体) + bld_007_f1..fN (子地点, 同 footprint, 带 part_of: "bld_007")
容量:  每层 = 类型 capacity;  全栋 = capacity × N;  占地按【单层】算(密度↑不铺开)
```

- **下楼层不是实体**，就是普通地点 —— 后端不需要理解"楼层"。
- **每层一个家**（不是一个信息池）→ `home` 的高信任分组按楼层分开。
- 随机生成的居民 **`role = ""`（无角色）**；新增人/物 **不进编辑页**。

### 各处改动

| 层 | 改动 |
|---|---|
| 编辑器 `map_doc.gd` | `floors` / `unit_ids` / `unit_of` / `building_of` / `set_floors` / `target_unit` / `add_resident`（容量上限）/ `fill_residents` / `copy_floor_items`（复制品 owner 换目标层户主）；导出子地点；导入跳过 `part_of` |
| 编辑器 UI `main.gd` | 工具区「填满住户」；建筑页「楼层」（楼层数 / 编辑层下拉 / 容量 / 复制按钮）；人员·物件按当前层 |
| 编辑器 `map_view.gd` | 三个角标 `人 N` `物 N` `共 N 层`；**不再画 NPC 圆点与姓名** |
| 后端 `world/buildings.py` | `part_of` 透传（其余靠现有兜底: `door_point→region_center` / `bind_home` 按 location） |
| 观测器 `state/store.gd` | `floors` 统计 + `building_of()`（单元→父建筑） |
| 观测器 `render/map_labels.gd` | 占用/物品**按建筑归并**；`capacity × 层数`；`共 N 层` 角标；选中框归父建筑 |
| 观测器 `render/overlay_layer.gd` | `_frame` 归父建筑 |

### 已修的 bug

1. **观测器占用角标显示 0** —— NPC 住在 `_f2`，角标查 `bld_007`（精确匹配）→ 全部为 0。
   → 统一走 `Store.building_of()` 归并。
2. **分母超员** —— 父地点 `capacity` 是单层的 → 显示 `9/3`。→ `× 层数`。
3. **详情页人员为空** —— `page_location._people_at` 也是精确匹配 `loc`
   → 多楼层建筑一个都列不出。→ 同上归并。
4. **减层遗留「幽灵住所」** —— 编辑器里把楼层数调到 N 点了「填满住户」，
   再减回 M<N 导出 → `npc.home = bld_001_f7` 指向不存在的地点。
   后果：没床没饭 / 占用统计不到 / 详情页看不到。
   - 编辑器: `set_floors` 减层时自动 `purge_invalid_refs()`；`validate()` 报错；
     另给一个「清理无效引用」按钮。
   - 后端: **`_materialize_missing_units()`** —— 按父建筑把缺失单元补出来
     （几何/容量照搬 + `part_of`，不继承归属），比硬塞进父建筑更忠于数据。
     两者都缺时才回退到父建筑，再不行置空住所（并打 warning）。

### 角标缩放 / LOD

角标**贴合建筑框**（随建筑屏幕短边缩放，`BADGE_REF_PX = 60`），并按 `k` 分层：

| 层级 | `k ≥` | 建筑短边 | 画什么 |
|---|---|---|---|
| `LOD_NAME` | 0.62 | ~37 px | 建筑名 |
| `LOD_BADGE` | 0.85 | ~51 px | `人/容量` |
| `LOD_EMBLEM` | 1.05 | ~63 px | 徽记 |
| `LOD_DETAIL` | 1.15 | ~69 px | `物 N` · `共 N 层` |

相机 `MAX_ZOOM` 8 → **24**。

## 5. 待拍板（不阻塞 ①，但阻塞后续）

- [ ] **P7** 面板打开时世界是否暂停（本文档倾向**继续走**）
- [ ] MVP 先做 **(a) 路上传播** 还是 **(b) 店内可见 + 店内传**
- [ ] 话题 3 招牌：**建筑字段** vs 实体；`source = "sign:<bid>"`；检测半径 R
- [ ] 话题 2 多层建筑：目的是 (a) 真实感 / (b) 玩法 / (c) 容量

## 6. 实施顺序

```text
① MVP：MemItem.source + _notify_due(两档信任) + 气泡层        ← 最小、最可见
② PLAN-1：删白名单 + 放开 need_floor，跑 7 天 soak 校准 need_floor
③ PLAN-2：删双轨仲裁（顺带砍 suspend/resume）
④ energy 昼夜衰减 + hp 三态（含 hp_override）
⑤ 成本模型 + 囤货目标存量 + roles.json + breach_cost
⑥ 话题 3 招牌 → 话题 2 多层建筑
```

## 7. 代码落点速查

| 文件 | 改动 |
|---|---|
| `npc/memory.py` | `MemItem.source` |
| `npc/brain.py` | `_gather_candidates` 删白名单 + 放开；`_score_candidates` 加成本项；`need_future` |
| `npc/person.py` | 双轨 → 单轨；metabolism 支持**依赖 clock 的 delta**；`hp` 三态 |
| `npc/planner.py` | 删 `_MEALS` / `_SLEEP`；`template_plan` → 只生成工作锚点 |
| `core/config.py` | 删 `REFLEX_SIGNALS`；`need_floor` / `λ` / `κ` / `time_value` / `breach_cost` / `hp_regen_floor` / `hp_override` |
| `config/sim.toml` | `energy` 昼夜曲线；工作消耗系数；成本权重；`breach_cost`；`[health]` 两个阈值 |
| `config/roles.json` | **新增**（缩小版：只有工作锚点） |
| `config/items/bed_basic.json` | **不用改** |
| `world/engine.py` | 删 `_can_preempt` / `_preempt`；`_notify_due` 实现；按 clock 生成 metabolism |
| `world/interaction.py` | `suspend` / `resume` 可删；**保留 `interruptible`** |
| `gateway/snapshot.py` | 导出 `bubble`（纯读）；`build_snapshot(only=…)` |
| `gateway/server.py` | `_render_sig` / `_dirty_npcs` / `focus_npc`；推送节奏 |
| `godot/state/store.gd` | `_merge_into`（合并而非替换）+ `_notify_focus` |
| `godot/resources/bubble.tres` + `scripts/render/bubble_layer.gd` | **新增**：气泡渲染 |

## 8. 文档索引

| 文档 | 内容 |
|---|---|
| `docs/20260914/game.md` | 游戏定位总纲（玩家 / 两支柱 / 管理物件 / 红线） |
| `docs/20260914/mvp.md` | 消息传播 + 气泡 MVP（三件事） |
| `docs/20260914/bubble.md` | 气泡实现方案（渲染 / 契约 / 节流） |
| `docs/20260914/plan.md` | 计划与需求（PLAN 收敛版，含 §3.2 删双轨 / §5.5 承诺维持 / §7 睡眠 / §8 生命） |
| `docs/20260914/observe.md` | 推送架构：观察驱动（位置只在状态迁移时推） |
| `docs/20260913/mind.md` | 情绪 / 关系 / 信任（**设计稿，未实现**，MVP 之后） |
| `docs/20260913/semantic_event.md` | 语义层（气泡 / 传播载体，M-S1 是本 MVP 的上位） |
| `docs/20260913/memory.md` | L0 + L1 记忆（L1 Episode 延后） |
| `docs/20260913/plan.md` | ⚠️ **已被 `docs/20260914/plan.md` 取代** |
