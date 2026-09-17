# 现状与拍板记录

> 本文件 = 设计真源 + 现状：**定过什么 / 机制是什么 / 到哪了 / 下一步做什么**。

---

## 1 已定（2026-09-15 拍板）

### 玩法方向

| # | 问题 | 决定 |
|---|---|---|
| 1 | 经济走哪条线 | **规模线与品质线都要，但现阶段不做这么复杂**（先最小闭环） |
| 2 | 店员是什么 | **招募来的 NPC，会给他发工资** |
| 3 | 时间尺度 | **保持不变**（1 天 = 1440 tick = 24 分钟 @1x）；**倍率回到 1x** |
| 4 | 气泡信息量上限 | **只给我关注的人**（现状：选中的人 + 选中建筑里的人） |
| 5 | 面板打开时世界走不走 | **继续走**（世界不等你） |

### 功能范围

| # | 问题 | 决定 |
|---|---|---|
| 6 | 经济做到什么程度 | **做成"公司"这个单位**（店铺属于 Company，公司有账，工资从公司出） |
| 7 | `roles.json` 口径 | **先做 A：只做"几点到几点在哪个楼上班"**（最简承诺） |
| 8 | 招牌 | ~~**下一步要验证的东西**~~ → **已删**(归公司侧经营, 以后重做)：*路过一家不知道的店，有招牌、价格一样却更近 → 看现有 NPC 会不会直接去这家买* |
| 9 | verify 校验闭环 | **不做**（P6"骗"整条线放弃） |
| 10 | 情绪 / 关系 / 信任演化 | **不做** |
| 11 | 语义层上层 | **只做语域（persona × mood），不接 LLM** |
| 12 | Episode(L1 情景记忆) | **不做**（L0 物化记忆够用） |
| 13 | 生老病死 | **只保留饿死 / 累死**（不做衰老/生育） |
| 14 | 推送性能优化（静态段/视口） | **先不做** |
| 15 | 编辑器编 `plans`/`pulses` | **不做**，也不手改 JSON —— **游戏内部写死规则** |
| 16 | 归档文档 | **全删**（见 §4） |
| 17 | 下一个要做的 | 经济闭环 → 公司运营界面(弹窗 TabView) |

### （已作废）招牌 —— 已整条删除

2026-09-15 后期决定: 招牌是**经营手段**, 归公司侧; 数据/后端/前端/编辑器/场景
里的相关代码与字段**全部删除**(`sign` 字段、`_sign_broadcast`、`_draw_sign`、
编辑器招牌区、`tests/test_sign.py`)。以后要做"广告/招牌", 在**公司运营界面**
里重做, 不要在建筑详情里挂。

---

## 1.5 ❄ 冻结点（2026-09-15）

以下三块**行为已定型并冻结**（commit `84711a3`），后续只在此基础上加，不再改口径：

| 块 | 定型的口径 |
|---|---|
| **决策与成本** | `eff = (need^power × 净收益 × personality × believe) / (1+λ×cost)`；净收益 = `value − 该需求每 tick 掉的量 × 走的 tick × travel_penalty ÷ 买几份`；cost = 纯钱 + 不确定性（**没有** time_value） |
| **需求边际** | 出门去拿的要扣掉**家里已有的供货**（`need − 存货×value`）；吃家里现成的不扣 |
| **囤货** | 目标存量 = 每天消耗份数 × 保质期天数 × `stock_fill(0.8)` × thrift —— 全部由物理量推导，没有拍出来的数字 |
| **传播** | 一对一搭桥（说×听×同屋/路人权重）；招牌 = 虚拟说者，门口半径、一条消息 1 tick |

实测基准（7 天，6 人场景）：全城采购 37 次，其中 `future`(囤货) 32 / `now`(眼前饿) 5；
吴勇 ¥471 → 买 4 次花 ¥230（与实际食量相符）。**剩下的开支缺口 = 没有收入**。

## 2 已实现

| 块 | 到什么程度 |
|---|---|
| **决策** | 效用主导单轨；候选不过滤，阈值只在得分上；手上有事就做完再决策；空闲才每 tick 重算。**`interruptible` 已删**：任何新动作都能顶掉当前交互（但仍只在 NPC 自己决定换动作时发生）；唯一能"硬抢"的是**上班开始那一刻** |
| **需求** | hunger 半天 / energy（**24h 基础≈50% + 入夜 20:00–22:00 陡降**；睡觉时冻结）/ bladder 1.6 天 + 三餐跳量 / **fun**（上班·闲逛涨，真空闲掉，吃睡厕不变） |
| **生命** | hp **只有 hunger 参与**：连续为 0 **满 3 天**才开始掉，**1 天掉完**（第 4 天 die）；中途吃饭清零重计；**无回血**；睡觉/精力不参与 |
| **买卖** | 扣钱 → 减店库存 → 送货进家容器（合并、保质期取最早）→ 变质销毁；**货款记到店铺所属公司的账**（`_credit_shop`） |
| **囤货** | 目标存量由保质期推导；只对 `consumable` 生效；缺口只驱动补货 |
| **感知 → 记忆** | `EntityView → MemItem`；`believe/remember/source`；写入口只有感知与传闻 |
| **传播** | 一对一搭桥（说/听各掷骰子；说的不听/听的不说；同屋高、路人低）；六条硬规则；信任两档 |
| **语义层 + 气泡** | 6 种 act + 模板池（确定性措辞）；气泡只在关注范围冒，两侧都写"谁给谁说" |
| **空间** | 多楼层（`_f1..fN` + `part_of`，容量×层数）；家 = 楼层单元；旅行按路径折线插值 |
| **观察驱动推送** | 60Hz；只推变化的 ∪ 观察集；超时丢帧不断线；HUD 流量 |
| **编辑器** | 路网/建筑/楼层/住户/物件/认知(批量)/按人记忆/无住所的人面板/导入导出；建筑名自动编号 |
| **观察器** | 只读镜像 + LOD 分级标签 + Event Log + Inspector（记忆/事件/意图/决策理由） |
| **公司/经济** | 市场进货(建筑) · 成交双分录进公司账 · 每天按在岗时间发薪 · 招聘=公司发启事+意愿撮合 · 柜台交易(前台=销售位, 排队) · 好感度慢变量 |
| **经济（最小）** | 公司表（店铺归属/账/老板/员工）；成交双分录进公司账；每天 `wage_minute` 发工资（发不出 → `wage_failed`）；观测：hello.companies + 地点页公司现金 |
| **确定性** | 同 seed 可回放；随机只走 `systems.rng`（不用内置 `hash()`） |

---

## 2.1 当前口径（最近收口，覆盖上面旧描述）

- **世界端口（NPC 主动拉）**：`core/ports.py`（`WorldPort` 动词 + `Ack/Deny/Grant`）
  + `world/edge/port.py`（`WorldPortImpl`）。`engine._apply` 已删；NPC 自己 `observe` +
  `try_move/try_take/try_buy/try_wander`，失败自己处理。
- **world→NPC 只有两个口（进行中）**：
  - `Person.notify(ev)` —— 世界只说「发生了什么」，怎么改自己是 NPC 的事。
    已收：`on_interaction_done / on_failure / forget_item / earn`。
    类型：`InteractionDone / InteractionFailed / ItemGone / WagePaid`。
  - `Person.assign(cmd)` —— 上面的人（老板/作者/计划器）下指令。
    已收：`set_work / set_shift / set_wage / set_role / clear_work / set_plan`。
    类型：`Work / Unwork / Shift / Wage / Role / Plan`。
  - 这两个名字**必须消失**（否则又是一条暗门）；`tests/test_person_notify.py` /
    `test_person_assign.py` / `test_person_activity.py` 用 `hasattr` 反向钉住。
  - **「我在干什么」也是 NPC 自己的**：删了 `set_activity`(×6)，改由
    `Person.activity() -> (大类, 文字)` 从 `_intake`(Grant 带 `name`+`tags`) +
    `_moving/_queued` 推导；`world.act_class_of` 只转发。
  - **还没收**：`set_signal/add_signal/add_bladder_pending`(身体) / `pay` /
    `bump_favor` / `worked/reset_worked` / `set_bubble` / `mark_said` / `note` / `heartbeat`。
- **信号数学在 NPC**：`Person._intake` 逐 tick 消化 `Grant`（`value/duration`）；
  「满了优先结束，否则按 duration」；world 只在 `interaction.step` 做收尾（扣货/回收）。
  中止 = 弃掉体内那份（不扣货、不触发 on_complete）。
- **fun + 闲逛**：新信号 `fun`；闲逛 `Wander(dest)` 是**两段式 committed goal**
  （先赶路 move → 到了建筑里才开逛 wander），目的地 = **非住宅地点里随机选一个**
  （`scenarios` 注入 `places`）；逛街补 fun；**决策冷却 1 小时**（`fun_roam_ticks=60`）。
- **上班**：守台 = committed goal（前台 `duration_ticks=60` → **每 60t 一次决策**）；
  班次内闸门把人钉在工位；**离岗 cost = 日薪（旷工）**；食物 `value` 按**真实缺口封顶**。
- **公司面板**：「人员管理」= 员工名单 + 工位分配 + **每人排班**（`_work.open/close`，
  只影响本人，不动公司营业时间）；`engine.schedule_worker` / `op="schedule"`。
- **时间线**：引擎每 tick 记 `Systems.activity_log`（当天行为段），只在选中的
  rich 帧里下发；前端画彩色行为带 + 悬浮。
- **场景可声明公司（作者直选）**：`scenes/*.json` 的 `companies` 段（id/name/
  shops/cash/open/close/wage_per_hour/hiring_slots/restock_to/**staff**）→
  `load_scene` 建公司 + 绑店铺 + 预置员工（不用等运行期 `hire_minute`）。
  编辑器：商铺详情 →「经营 · 公司」段（注册/编辑 + 勾选员工）。**这样场景才能无头跑。**
- **已知未做**：`favor`（好感度）只记账**未接入决策**；`template_plan` 恒空
  （无 `config/roles.json`）；DEMO 测试场景没写 `companies` → 脚本 `buy` 会卡排队。

---

## 3 下一步（按顺序）

```
① ~~招牌~~ → 已删除(归公司侧经营, 以后重做)
② 经济最小闭环 —— Company 单位: 店铺属于公司, 公司有账, 收入进公司, 工资从公司出
③ 工作与承诺 —— config/roles.json: "几点到几点在哪个楼上班"(最简承诺)
④ 玩家那一侧 —— 店主化身 + 电脑 → 经营面板(定价 / 招聘 / 把消息挂上招牌)
⑤ 语义层语域(persona × mood) · 气泡/观察器的边角改进
```

**明确不做**：verify 校验 / 情绪 / 关系网 / trust 演化 / Episode / 衰老生育 / LLM 润色 /
编辑器编 plans·pulses / 视口过滤 / `nn/` 学习层。

---

## 4 文档

活文档：`checklist.md`（本文）· `naming.md` · `plan_timeline_viz.md`。

**已删除**（历史讨论，与实现脱节）：
`20260910/requirements.md`、`20260913/{semantic_event,mind,memory,plan}.md`、
`20260914/{game,plan,mvp,bubble,observe}.md`、`Vision.md`。
