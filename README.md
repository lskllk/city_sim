# citysim · 城市生活模拟内核

**一个确定性、数据驱动的「城市生活模拟内核」。**
城里每个人都是**真的会想、会记、会打听的 agent** —— 他看不到全知地图，
只知道**自己记得的东西**。这条约束自然长出信息差、传闻、误判与探索。

> 8,025 行 Python（54 文件）· 10,009 行 GDScript（56 文件）· 274 个测试 · 内核零第三方依赖

**规则与内容都在 `config/` 里 —— 改动优先改数据，而不是改代码。**

---

## 一、架构：认知与世界分开，只靠两个口说话

```
        ┌─────────────── npc/ ───────────────┐
        │  认知侧:  只有【记忆】与【需求】     │
        │  person(聚合根) · brain(决策)      │
        │  memory · schedule · semantic      │
        └───────┬───────────────────▲────────┘
   5 个动词请求 │                   │ 两个口说话
  (observe/move │                   │ notify(ev)  世界说"发生了什么"
   /take/buy…)  ▼                   │ assign(cmd) 上面的人说"你以后照这个做"
        ┌─────────────── world/ ─────────────┐
        │  世界侧:  账本 + 权限 + 时钟         │
        │  model/ 世界长什么样                │
        │  edge/  与 npc 的边界               │
        │  run/   世界的时钟(主循环)           │
        │  econ/  钱与货                      │
        │  mechanism/ 通用机制                │
        └───────────────┬────────────────────┘
                        │  sim/loop.py → run_tick
                        ▼
     gateway/  场景→世界(scenarios) · 世界→JSON(snapshot)  ← 纯数据桥(不渲染)
                        ▼
         api.py  门面: 内核唯一的公开面 (game/ 只能看见它)
                        ▼
     game/  经营动词 · 快进编排 · 台词模板 · WS 服务   ← 知道玩家/老板/文风
                        ▼
                   Godot 观察器 / 编辑器
                     (只渲染与发命令, 不算模拟)
```

### 六条红线（`tools/check_imports.py` 强制前三条，违规即测试失败）

| # | 规则 | 为什么 |
|---|---|---|
| **1** | **`npc/` 严禁 `import citysim.world`** | 认知与世界各自能独立推理与测试；NPC 只知道"我能请求什么" |
| **2** | **`game/` 只许 `import citysim.api`** | 门面是"读到哪儿为止"的答案；绕过它，答案就没了 |
| **3** | **`api` 严禁 `import citysim.game`** | 门面只覆盖内核；反向依赖会让包变成一团，还会把 fastapi 拖进内核 |
| **4** | **world → NPC 只有两个口**：`notify(ev)` + `assign(cmd)` | 世界只说"发生了什么"；怎么改自己是 NPC 的事 |
| **5** | **决策只读记忆**，不查世界 | 记忆里没有的 = 他不知道 —— 整个认知系统的基础 |
| **6** | **Godot 只渲染、只发命令，不算任何模拟** | 画面与逻辑不打架；换前端不用改内核 |

### 那两个口分别是什么

```
notify(ev)   世界说【发生了什么】 —— NPC 自己决定怎么改自己
             InteractionDone / InteractionFailed / ItemGone / WagePaid / Bought
             例: "你吃的那份东西用完了, 还剩 3 份" → NPC 自己决定刷记忆、结束目标

assign(cmd)  上面的人(老板/作者/计划器)说【你以后照这个做】 —— NPC 照做
             Work / Unwork / Shift / Wage / Role / Plan
```

`assign` 是**"绑定与承诺"的通道** —— 它改的是 NPC 的**身份与义务**，不是世界的真假：

| Command | 干什么 | 谁发的 |
|---|---|---|
| `Work(company, shop, station, open, close, wage, role)` | 雇佣/改岗：把公司+店+工位+班次+时薪一次绑上 | 招聘桥接（`hire_at`）· 场景绑定 · 面板派岗 |
| `Unwork()` | 撤岗/辞退（保留这个人，只清掉绑定）| 面板 |
| `Shift(open, close)` | 改**本人**班次（不动公司营业时间）| 面板 · 老板 NPC |
| `Wage(v)` | 改**本人**时薪（逐人；公司 payroll 世界侧同步）| 面板 · 老板 NPC |
| `Role(r)` | 给/改角色 | 场景 · 以后的任务系统 |
| `Plan(entries)` | 灌入当天日程表（覆盖旧的）| 作者脚本 · 计划器 |

```python
# 世界侧调用点（都是这一句）
npc.assign(Work(...))     # 例: world/econ/company.py::assign_station
npc.assign(Wage(6.5))
```

**为什么要有 `assign` 而不是散装 setter**：以前是 `set_work` / `set_shift` /
`set_wage` / `set_role` / `clear_work` / `set_plan` 六个方法，谁都可能从任何地方改
NPC 的内部状态 —— 边界消失，NPC 就不再有"自己"。收成一条
「上面的人下指令，NPC 照做」的窄口之后：**世界代码再也拿不到 Permission 去改认知**。

**它和 `notify` 的分工**（一句话）：
> `notify` = **世界对 NPC 说事实**（"发生了什么"）；`assign` = **人对 NPC 下令**（"照这个做"）。
> 二者之外的任何入口都不该存在。

---

## 二、目录

```
src/citysim/
  core/     契约层: types(Percept/Intent/Notify/Command) · ports(5 个动词) · config
  npc/      认知侧: person(门面) · brain(决策) · memory · schedule · semantic · planner
  world/    世界侧: world(容器) + 五个子包:
               model/      世界长什么样(buildings · roads · itemdefs · companies)
               edge/       与 npc 的边界(port · perception)
               run/        世界的时钟(run/engine.py = 主循环 · drive · travel · gossip)
               econ/       钱与货(shop · economy · company · market · factory)
               mechanism/  通用机制(interaction · events)
  sim/      loop.py(推进入口 run_tick + Systems 容器)
  gateway/  纯数据桥: scenarios(场景→世界) · snapshot(世界→JSON)
  api.py    门面: 内核唯一的公开面 —— 门外(含 game/)只许 import 这个
  game/     游戏服务端层:
               actions.py   经营动词(定价/进货/雇人/排班/装修 …) 只改世界真值
               clock.py     快进编排(档位 → ticks/秒)
               lines.py     台词模板池 + 词表(语义事件 → 人话)
               runner.py    SimRunner: 拥有世界 · 推进 · 60Hz 推送(观察驱动)
               commands.py  WS 指令表: 名字 → 动作 → reply
               server.py    FastAPI app + WS 端点(接线与启动)
config/     sim.toml + items/ · buildings/ · scenes/   ← 数值与内容都在这
godot/      观察器 + 编辑器(只渲染/发命令, 不算模拟)
tools/      观测脚本: sim_report · watch · narrate · soak_report …
tests/      pytest
```

---

## 三、跑起来

```bash
python -m pip install -e .            # 内核 + 测试(零第三方依赖)
python -m pip install -e ".[viz]"     # 额外: 观察器后端 (fastapi + uvicorn)

python tools/sim_report.py config/scenes/scene.json 30   # 无头跑 30 天, 出健康度报告
python tools/watch.py --npc 6 --ticks 2400               # 终端观察器(无依赖, 最快看行为)
python -m uvicorn citysim.game.server:app --port 8765 # 只跑后端

"D:/Godot_v4.7.2-stable_win64.exe" --path godot                              # 观察器
"D:/Godot_v4.7.2-stable_win64.exe" --path godot res://scenes/editor/editor.tscn  # 编辑器
```

观察器会自己拉起后端（端口已监听则跳过）、退出时收掉；日志在 `.logs/backend.log`。
编辑器导出的场景用 `set CITYSIM_SCENE=<路径>` 让观察器加载。

## 四、测试

```bash
python -m pytest                                # 全量(274)
python -m pytest tests/test_import_layers.py    # 层隔离: npc/ 禁 import world/
python tools/sim_report.py <scene> <days>       # 改动后跑一遍, 看行为有没有变
```

---

## 五、已经实现的机制

### 认知（这套东西是内核的灵魂）

| 机制 | 说明 |
|---|---|
| **观察是有条件的** | 只有三种理由才"看世界"：**第一次来** ∨ **正在闲逛** ∨ **本地缺东西（且这次没查过）**。呆着不动 = 世界变了也不知道 |
| **看 ≠ 刷新** | "看"只**发现记忆里没有的**；已有的行只靠**用过（反证）**刷新，否则自然变旧 → 被忘 |
| **遗忘** | 半衰 2 天 → 约 7 天删行。例外：**地点行永不删**（"那地方是干嘛的"是常识）· **家永不衰减**（身份常识）|
| **闲逛 = 观察窗口** | 由 `fun`（好奇心）驱动，60 tick 连续观察；目的地在建筑间**加权随机**挑（有料的地方 3:1 更常去）|
| **fun = 知识增长** | 基础回报 + Σ(1 − 旧记忆) → 探索有回报，且自动收敛，不需要摆娱乐设施 |
| **传闻（gossip）** | 一对一搭桥，三道骰子（想说 / 愿跟这人说 / 愿听）；传的是**行情记忆**（含 tags）|
| **惊讶** | "预期 vs 看到"不一致时冒泡 —— 它是"认知差"存在的证据 |
| **好感度** | 对店铺的慢变量：顺利买到 ↑ / 白跑 ↓ / 每天向中性回升 |
| **囤货** | 目标存量模型（按保质期推）→ 家里缺了才买，不会重复买 |

### 经济

| 机制 | 说明 |
|---|---|
| **公司 = 经济单位** | `cash` 是它的账；店铺属于它；工资从它出。**类型由建筑定死**：店铺→零售 / 工厂→制造 |
| **零售** | 向批发市场进货 → 上架 → 居民买（售价自己定）|
| **制造（加工厂）** | 工人站工位**按在岗时间**产出**原料** → 每天 0 点批发市场按定义价**全收** → **钱从城外进来**（城里唯一的外部资金来源）|
| **原料价 = 成品 × 0.8** | 城市**出口原料、进口成品**，外部赚那 20% |
| **熟练度** | 新员工 2 → 老手 5（30 个工作日）→ 一份产出由 82 分钟提到 33 分钟 |
| **工业机器** | 家具 ¥600：**一台配一个工位 → 产量 ×3**（多余机器没用 → 逼"机器 + 工位一起投"）|
| **自动经营** | 开门前补货到 `restock_to` · 每天 0 点招聘撮合 · 每天 8 点发工资（**按出勤算，不到岗没钱**）|

### 行为

```
需求:      energy / hunger / bladder / hp / fun      (hp 只由饥饿参与)
决策:      committed goal 优先(做完才重决策) → 否则打分选一个
           ★ 唯一能硬抢的只有 PLAN 的开始(上班/上学这类"有人在等"的承诺)
           ★ 需求满足只能"做满 或 duration 结束"才换下一个
行为类别:  吃饭 / 睡觉 / 上厕所 / 闲逛 / 上班   (前端是平等的一排)
```

### 物件（家具 vs 货物，定死）

| | 家具（tag `fixture`）| 货物 |
|---|---|---|
| 数量 | **恒为 1** | 可多（同类型同地点会合并）|
| 消耗 | **永不消耗** | 用完减 1 |
| 并发 | 一次一个人用（容量 = 数量）| 一"堆"可多人同时取 |
| 例子 | 床 ¥200 · 马桶 ¥120 · 工位 ¥150 · 销售台 ¥300 · 工业机器 ¥600 | 苹果 · 梨 · 简餐 · 简餐原料 |

> 没有 `stock = -1` 无限这回事 —— 想多一个就多摆一件。

---

## 六、⛳ 不写代码能改什么

```
config/sim.toml       全部数值: 代谢/评分/囤货/工资/生产/传播/好感度/知识衰减 …
config/items/*.json   9 种物件(种类/affordance/价格/保质期/是家具还是货)
config/buildings/     12 种建筑(kind 决定能开什么公司)
config/scenes/*.json  场景: 地点/建筑/NPC/物件/公司(含预置员工)/初始记忆/旅行成本
```

**编辑器（Godot）能做**：摆建筑/道路与命名 · 摆物件（**家具按建筑类型过滤**）·
注册公司（名字/现金/时薪/招聘数/营业时间/产出物）· NPC 取名/性别/生日/角色/性格/初始记忆 ·
一键填满住户 · 导出/导入场景 JSON。

---

## 七、当前状态（诚实版）

### ✅ 已经稳的

```
观察有条件(观测 0.93 → 0.07 次/人·tick, 耗时 −42%)
记忆三路径(观察发现 / 反证修正 / 传闻得知) · 遗忘与"过时"行为正确
闲逛 = 观察窗口 + 加权随机选址 · 制造/零售两行业 + 出口闭环
家具/货物分离 · 公司类型由建筑定 · 274 测试 · 层隔离强制 · 前后端确定性可复现
```

### ⚠️ 已知不平衡（做玩法设计时先面对这三件）

| # | 问题 | 数字 |
|---|---|---|
| **1** | **岗位数 < 人数** → 有人必然没收入 | 6 人只有 4 岗（加工厂可多摆工位）|
| **2** | **食物点只有一个**（吵吵小店，还要 1 个店员守着）| 那唯一店员一离岗 → 全城断粮 |
| **3** | **时薪定得不一致** | 保本 = `1.4545 × 熟练度`（新手 2.91 / 老手 7.27）；现场景混着 3.0 与 10.0 |

> 实测 60 天后仍会全灭 —— **不是 bug，是"经济模型缺一条腿"**：
> 时薪不够 → 长期营养不良 → 精 0 → 一直离岗找吃的 → 店没人守台 → 全城买不到 → 全灭。

### 🔧 还没做的

```
· 市场/广场是空的 → 闲逛去了没东西可发现 → 惊讶/传闻起不来
· 老板 NPC(用电脑经营: 定价/进货/雇人/装修) —— 插槽都在
· 记忆一行只能记一个 affordance(多需求物件只登记第一个)
```

---

## 八、工具

| 工具 | 用途 |
|---|---|
| `python tools/sim_report.py 场景 天数` | **任意场景无头跑 N 天 → 生死/现金流/库存/行为报告**（有人死或公司破产 → 退出码 1）|
| `python tools/watch.py --npc N --ticks T` | 终端观察器（无依赖，最快看行为）|
| `python tools/soak.py` / `soak_report.py` | 长局压力测试 |
| `python tools/check_imports.py` | 层隔离（已挂进 pytest）|
| `python -m uvicorn citysim.game.server:app` | 只跑后端（给别的前端用）|
| Godot 编辑器 | 场景创作 + 导出 JSON |

---

## 九、正在基于它做的游戏

见 **[游戏构思](docs/game-concept.md)**（我们要做什么）· **[Demo 计划](docs/demo-plan.md)**（怎么做 · 五条线 · 分工 · 契约）。

前端设计已冻结：

| 文档 | 管什么 |
|---|---|
| **[UI 实现规格](docs/ui-spec.md)** ❄ | **实现依据**：布局 · 组件 · 交互 · 动效 · 占位清单 |
| [UI 与信息设计](docs/ui-design.md) | 什么该给玩家看 / 藏（设计理由） |
| [美术方向](docs/art-direction.md) | 画风 · 网格 · 资产交付 |
| [`proto/ui-prototype.html`](proto/ui-prototype.html) | 参考实现（看得见摸得着的标准答案） |

一句话：

> **一个视野有限的人，在一座小城里，靠关系和情报做买卖；赚够了钱，去看更大的世界。**
> 店主经营 + **声誉玩法**（钱是记分牌，不是玩法）—— 靠的是这个内核唯一做得出来的东西：
> NPC 不看全知地图，只靠自己记得的东西活。

## 十、给"继续改内核"的话

**它已经给你的**

1. **一个能自洽运转的世界观** —— NPC 不看全知地图、只靠自己记得的东西活。
   这天然产生**信息差、传闻、误判、探索**，而不需要额外写剧本。
2. **一条完整的经济脊椎** —— 劳动 → 产出 → 出口换钱 → 工资 → 消费，闭合成环。
3. **一切内容都是数据** —— 新物件/建筑/场景/公司都不用改代码。
4. **确定性与可复现** —— 同一个种子跑两遍一模一样（世界指纹可校验）。
5. **一个还没被使用的"老板视角"** —— `Company.owner` 的注释写着
   *"老板 npc（以后玩家化身就是他）"*。

**最容易长成玩法的三个接口**

```
① Services.planner   —— 更"聪明"的决策插槽(现在 None = 纯 utility)
② assign(Command)    —— world 侧的经营动词已经到了 NPC 手里(见第一节)
③ 玩家 = 一个 NPC    —— 让玩家接管某个人的 decide(), 或用现成面板当"上帝视角"
```
