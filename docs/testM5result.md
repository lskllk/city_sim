# testM5 测试结果（按 testm5.md 全条款执行）

- 日期：2026-09-04 · 分支 main · 全部真实数据，无评价性软话
- 执行范围：前置 3 件基础设施 / S1–S6 六场景 / 宏观指标 / 消融矩阵 / 人工 review 产物
- 环境：Python 3.10.11 · 全量 pytest 106 passed（含 m5-rectify 16 票整改，见下注）
- 配套代码：`src/citysim/`(decay 接线、感知修正) · `tests/test_m5_full.py`(S1–S5) ·
  `tests/test_m5_macro.py` · `tests/test_m5_ablation.py` · `tools/kb_metrics.py` ·
  `tools/ablation.py` · `tools/narrate.py` · `docs/narrate_logs/` · `docs/*.dot`

---

## 〇、执行所需的两处 sim 补接线（kb!=None 才生效，M4 golden 零影响）

| 补丁 | 依据 | 效果 |
|---|---|---|
| 主循环每日 decay(5.5) | design 553「每游戏日 0 点批量 kb.decay」 | 遗忘真正随时间发生；config `[knowledge] half_life_ticks=10080`(7 天) |
| 感知区分「空 vs 被占用」 | design 5.3 只许在 stock=0 时 refute | 修掉「他人正用 → 误判空 → 误证伪自己可靠知识」的真实缺陷 |

> 注：本表之后按 M5v1阶段整改.md 又完成 m5-rectify 16 票（fact_id 命名空间、query 逐键
> 覆盖、learn tick/upsert、consume_self 时序、传闻挂重评+置信加权、TOLD 溯源、exec/
> is_a/food_source 清领域硬编码、常量入 config 等），全量 106 passed 且本节所有回归网
> 数值不变（详见 `.scratch/m5-rectify/issues/` 与 docs/testm5_status.md）。

DOT 复查（修复前 n0：`contains edible 0.82` 与 `contains none 0.67` 并存；修复后：
仅 `contains edible 0.50`，干净）。全量 96 passed，回归网零变化（下见 §6）。

---

## 一、前置设施

1. **KB 开关** `build_demo(kb_mode=off|archetype_only|full)`：`off`=kb None →
   与 M4 golden 逐行一致（`test_m4_equivalence` 264 行回放通过，见 §6）。
2. **初始噪声** `noise` 参数：初始信号 `uniform(-0.1,0.1)` 扰动破同相位。
3. **叙事日志** `tools/narrate.py`：已产出（见 §5 产物清单）。

## 二、六场景实测

| 场景 | 关键断言 | 实测数据 | 状态 |
|---|---|---|---|
| **S1 新来者 vs 老住户** | B 首餐 > A；B 摸索 idle+need ≥2×A；见过即学会；day3+ 收敛 | firstA=**53** firstB=**1468**；idleA=30 idleB=**378**(≥2×) ；late(day3-7)A=10 B=**10**；B 已学 OBSERVED | ✅ |
| **S2 过时知识纠错(4 NPC)** | 有人上当 → 全员学会 → 改道；KB off 对照饿 | 去厨房 {day0:4} 每 NPC 恰 **1 次**；4/4 refute；后期 eats=[13,13,13,13]；off 对照 eats=**0**、idle 401–449 | ✅(通勤版见注2) |
| **S3 传闻扩散(10 NPC)** | p=0 不传；p=0.1 7 天 knowers≥6；每跳×0.8；溯源到唯一 OBSERVED 根 | p=0.1：knowers=**10/10**，told=9，事件链溯源 reachable=**10/10**；置信按跳落 **0.50/0.40/0.32**（均≤0.8）；p=0：knowers 恒 1 | ✅(曲线见注3) |
| **S4 假消息生与死** | 传播 → 亲赴 refute → 归零；wasted 有上界(≤NPC×2) | wasted=**6**(每人1次) refuted=**6/6**；7 天信者归 **0**；wasted 6≤12 | ✅(见注4) |
| **S5 遗忘(真实主循环 21 天)** | 3 半衰期 conf≈0.125；跌破 0.3 不进决策；INJECTED 不衰减 | conf_after_21d=**0.135**(∈0.125±0.02, 含目击日刷新)；低置信不再 move_to；INJECTED 保持 **1.0** | ✅ |
| **S6 稀缺+知识=生存差** | 有知识 stuck0≈0；无知识≈原 2520 | 有知识 max hunger<300 & 吃到；无知识 **>1000** 饿 | ✅ |

场景注（如实）：
- **注1** S1 的 B「自主摸索」由测试在 day1 把 B 放到 market 模拟「路过即见」；
  真正的探索行为是 M6 项（见 §5 呆3）。
- **注2** S2 无「回家睡觉/补给」行为 → 到食点即扎营，跨天通勤扑空不可实现；
  本版=首次赴餐前( tick300 )清空冰箱 → 全员各扑空 1 次即纠错。通勤/按天单调版记
  behavior_debt（M6 回家行为）。
- **注3** S3 单地点全连通图下 p=0.1 扩散近瞬达（数小时内 10/10），无 S 形缓升；
  要真实 S 曲线需空间/移动约束（M6 旅行）。置信按跳分级递减已被实测证明。
- **注4** S4 不给真食物替代：脑当前按 subject 字母序挑知识源，若同时有真超市会恒
  盖过假消息→无人亲赴。此排序(应按置信/新近)记 debt。本场景专测「假消息传→亲历
  证伪→死」。

## 三、宏观真实感指标（7 天 × 6 NPC 城镇，full KB）

| 指标 | 定义(操作化) | testm5 目标 | **实测** | 冻结? |
|---|---|---|---|---|
| 探索率 | move_to/决策 | 5–30% | **0.24%** | 否(见注) |
| 空跑率 | intent_failed/move_to | <20% | **0%** | ✅(≤0.2) |
| 熟悉偏好 | (当前无来源日志, 未操作化) | ≥60% | — | 待 M6 |
| 知识多样性 | 两两 overlay Jaccard 距离 | ≥0.3 | **0.60** | ✅(≥0.3) |
| 追溯完整性 | 抽样 KB 决策链到根 | 100% | **6/6=100%** | ✅(==1.0) |
| KB 增长 | 人均 overlay day3 vs day7 | 有界 | **2.0 → 2.0**，峰值 **2** ≤K(12) | ✅ |
| 全员吃到 | 靠 KB 找到食 | True | **True**(6/6) | ✅ |

决策 2462 · move_to 6 · failed 0。
注：探索率 0.24% 远低于目标——NPC 无回家行为、到食点即扎营，KB 只在初始一次寻食
被用；此指标待 M6 生活循环后重测，本期只记录不冻结（写入 `test_m5_macro.py`
docstring 与 `docs/kb_metrics.json`）。

## 四、消融矩阵（同场景同 seed1–10 × off/archetype_only/full）

| 档位 | 吃上人数 | 平均首餐 tick | stuck0 总 tick | 空跑率 | Jaccard 距离 |
|---|---|---|---|---|---|
| off | **0**/40 | — | **199047** | n/a(0 move) | 0.0 |
| archetype_only | 40/40 | 332.7 | 0 | 0.125 | 0.0 |
| full | 40/40 | 332.7 | 0 | 0.125 | **0.333** |

- 结论：带 KB 档生存全优且无挨饿，off 饿死（0/40、199k stuck tick）；**无倒挂**
  （food 充足的场景里 full 与 archetype_only 生存相同，差异只在个体化/多样性——这
  正是预期，非倒挂）。30 行明细存 `docs/ablation.json`。
- 结构回归断言：`test_m5_ablation.py`（off=0 ate、KB 档=40、full.diversity>0、无倒挂）。

## 五、人工 review（机器初筛 + 产物，真人确认仍不可省）

**产物**（已落盘）：
- 3 天叙事：`docs/narrate_logs/review_n0_day1-3.txt`(534 行)、`review_n3_day1-3.txt`(533 行)、
  及 S1–S4 各场景 `*.log`（`python tools/narrate.py --log <file> --npc <名>` 可随时回放）
- KB DOT × 3 天 × 2 人：`docs/kb_n0_d{1,4,7}.dot`、`docs/kb_n3_d{1,4,7}.dot`
  （灰=INJECTED 骨架、绿=OBSERVED、蓝=TOLD 稀疏、橙=INFERRED 0(应为 0, M6 才有)）
- DOT 直观看：n0 day7 仅 1 食物结点(market_a) + 其 sells/located_at 灰边 + 亲历绿边，
  干净无环。

**3 条「意外但合理」（宣传素材）**
1. S2：每人**恰好 1 次**扑空即改道——信念第一次被现实戳破就瓦解，无执迷。
2. S3：9 次 told 后全员置信精确落 0.50/0.40/0.32 三档——谣言每传一手自然变淡。
3. S4：假消息 6/6 全信过、又 6/6 亲赴证伪，7 天内**无审查地自然归零**。

**3 条「明显呆」（进 M6/M7 需求）** → 详见 `behavior_debt.md` §4
1. (已修) 感知把「他人占用」当「空」→ 误证伪；已修复并有 DOT 佐证。
2. 无食物知识且眼前无食的 NPC 只会 idle 饿着，从不探索（无好奇心）。
3. 到食点即扎营、不回家（无睡觉/补给回家行为）→ 探索率极低、S2 通勤不可行、S3 无 S 曲线。

**脑排序局限**：多知识源按 subject 字母序而非置信/新近取源（S4 由此需隔离真食物）——
记 debt，M6 改。

## 六、回归网（M5 全绿，M4 平价保持）

```
pytest 全量:       96 passed
soak 7d×3(off):    睡眠 0.86/天 · 实体 11->11 · intent_failed 0/1176 · 无抖动
scarcity(off):     failed/交互 13.21% · stuck0 2520 · eats 2  (与 M3 记档一致)
golden replay:     test_m4_equivalence 264 行相等 ✅  (kb off 平价保持)
```

## 七、结论与未完成

- **达成**：S1–S6 六场景全绿；宏观指标中「多样性/追溯 100%/KB 有界/全员吃到/空跑」达
  标并已冻结为回归网；消融表无解释不通的倒挂；`off` 与 M4 golden 平价保持。
- **未达/待 M6（如实）**：探索率(0.24%<5-30%)、熟悉偏好、S 形扩散曲线——三者同因：
  NPC 无回家/日循环/换店行为。已在 `behavior_debt.md`、`testm5_status.md` 记档。
- **建议放行条件**：按 testm5「退出」口径——本批 5 个「冻结阈值」均为回归网非人性
  证明；真人 narrate/DOT 复核（§5）通过后即可更新 golden 为 M5 版并放行 M6。
  golden 更新建议放到 M6 起点做（与 kb 默认档一起），避免打断当前 M4 平价回归锚。
