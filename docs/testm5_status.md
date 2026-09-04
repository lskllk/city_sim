# M5 测试进度（testm5.MD 执行状态）

## 2026-09-04 · m5-rectify 16 票整改全部完成（main; pytest 106 passed, 回归网零变化）

按 M5v1阶段整改.md 拆 16 票并全部落地(.scratch/m5-rectify/issues/01-16)：
- P0: fact_id 命名空间(a:/o:) / query 逐键覆盖+all_facts / tick 显式+decay 按事实
  基线(无默认半衰期) / consume_self 回收唯一化 / learn upsert / 同地源不 move_to+
  不可见 located_at 纠错(含空容器 tombstone 原型 edible 防复活)
- P1: 传闻挂 due 重评+置信加权(不再每 tick O(N²) 且可二次传播) / TOLD 携带起源引用
- P1-5 回流: PLAN_STEP_HANDLERS+exec / sells 用 is_a 判可食(去 _EDIBLE_OBJS) /
  EntityView.provides+food_source(去 provides:edible 假键) / move_to 前 release
- P2+config: UTILITY/MOVE_TICKS 入 config / goap 装配注入 / effects logger /
  events 满箱 warning / interruptible 尊重 / 各种卫生
- 实测: S5 21 天 conf≈0.135(含目击日刷新, ∈0.125±0.02); S3 溯源 10/10; S4 假消息
  传→refute→归零 wasted≤2/人; 全量 106 passed
- 回归网: soak 0.86天 11->11 / scarcity 13.21% 2520 eats2 / golden 264行 零变化;
  macro(探索0.24 trace100% jaccard0.6 overlay2 max2)与消融(off饿/KB档全活) 不变

## 2026-09-04 · 全条款执行完毕 → 结果见 docs/testM5result.md（全量 96 passed）

### 本轮补齐
- sim 补接线(均 kb!=None 才生效, M4 平价保持): 每日 decay(half_life=7天) +
  感知学 located_at + 感知修正「空 vs 占用」→ 修掉误证伪(DOT 佐证)
- 场景测试 test_m5_full.py(S1-S5 7条绿):
  S1 firstB1468>>A53/idle378≥2×30/day3-7收敛10vs10
  S2 每NPC恰1次扑空→4/4 refute→改道 eats13×4; off对照 eats0
  S3 p=0.1 knowers10/10 每跳≤0.8(0.5/0.4/0.32) 溯源10/10; p=0 恒1
  S4 假消息 6/6信→亲赴refute→归零 wasted6
  S5 主循环21天 conf=0.125000±0.02; INJECTED恒1.0
- 宏观 test_m5_macro.py(kb_metrics, 7天×6NPC): trace100% jaccard0.6
  overlay 2→2 峰值2≤12 全员吃到 空跑0 —— 已冻结
- 消融 test_m5_ablation.py(seed1-10×3档): off 0/40吃 stuck199k vs KB档40/40
  stuck0; full diversity .333 唯一>0; 无倒挂 —— 已冻结
- review 产物: narrate 3天文本 + 4场景log + KB DOT(2人×d1/4/7) +
  behavior_debt §4(3意外/3呆/2局限)

### 未达/待 M6(同根因: 无回家/日循环/换店 → behavior_debt 4b/4c/4d)
- 探索率 0.24%<5-30%; 熟悉偏好; S3 S曲线; 知识源按字母序(brain);
  S2 文档版跨天通勤; golden 升级 M5 版(M6 起点做)

